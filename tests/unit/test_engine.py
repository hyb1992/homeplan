from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from homeplan.checks import evaluate
from homeplan.dates import add_months, resolve
from homeplan.importer import date_formula, merge_import
from homeplan.loans import amortization, card_installments
from homeplan.money import parse_money
from homeplan.storage import dumps


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3600만", 36000000),
        ("1억 2천만", 120000000),
        ("1.2억", 120000000),
        ("36,000,000", 36000000),
    ],
)
def test_money_input(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["-1", "1.1원", "1억실수", ""])
def test_bad_money(text):
    with pytest.raises(ValueError):
        parse_money(text)


def test_relative_dates_cycle_and_month_end():
    assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert resolve("잔금일+1", {"closing_date": "2027-03-27"}) == date(2027, 3, 28)
    with pytest.raises(ValueError, match="순환"):
        resolve(
            "closing_date",
            {"closing_date": "lease_refund_date", "lease_refund_date": "closing_date"},
        )
    with pytest.raises(ValueError, match="없는"):
        resolve("unknown+1", {})


@given(
    amount=st.integers(1, 1000000000),
    rate=st.decimals(min_value="0", max_value="0.15", places=4),
    method=st.sampled_from(["원리금균등", "원금균등"]),
)
def test_amortization_conserves_principal(amount, rate, method):
    schedule = amortization(
        amount, rate, 360, date(2027, 1, 31), method, reset_after=60, reset_rate="0.07"
    )
    assert sum(p.principal for p in schedule) == amount
    assert schedule[-1].balance == 0
    assert all(p.balance >= 0 and p.principal >= 0 for p in schedule)
    assert all(
        a.balance - b.principal == b.balance for a, b in zip(schedule, schedule[1:], strict=False)
    )


def test_integer_card_conservation():
    assert sum(card_installments(10000001, 7)) == 10000001


def test_ledger_reconciliation_and_intraday_order(household, rules):
    result = evaluate(household, None, rules, analyze_assumptions=False)
    opening = result.daily_balances[0].opening
    assert opening + sum(e.amount for e in result.ledger) == result.daily_balances[-1].closing
    assert min(d.minimum for d in result.daily_balances) == result.kpis["min_balance_overall"]
    yes = evaluate(
        household, None, rules, {"interim_date": "2027-01-20"}, analyze_assumptions=False
    )
    no = evaluate(
        household,
        None,
        rules,
        {"interim_date": "2027-01-20", "same_day_inflow_usable": False},
        analyze_assumptions=False,
    )
    assert no.kpis["min_balance_overall"] < yes.kpis["min_balance_overall"]


def test_assumptions_and_confirmed_only_keep_existing_cash_and_debt(household, rules):
    result = evaluate(household, None, rules)
    assert {a["id"] for a in result.assumptions if "without" in a} == {"A02", "P01"}
    confirmed = evaluate(household, None, rules, confirmed_only=True)
    assert confirmed.daily_balances[0].opening == 80000000
    assert any(e.source == "L01" for e in confirmed.ledger)
    assert not any(e.source in {"A02", "P01"} for e in confirmed.ledger)


def test_excluded_and_example_rows_never_count(household, rules):
    from homeplan.models import FundEvent

    before = evaluate(household, None, rules, analyze_assumptions=False)
    household.fund_events += [
        FundEvent(id="X1", value=999999999, data_kind="예시"),
        FundEvent(id="X2", value=999999999, status="제외"),
    ]
    after = evaluate(household, None, rules, analyze_assumptions=False)
    assert before.kpis == after.kpis


def test_formula_parser_and_merge_preserves_manual_data(household):
    assert date_formula("=잔금일+1", {}, {"잔금일": "closing_date"}) == "closing_date+1"
    assert date_formula("=C16", {"C16": "lease_refund_date"}, {}) == "lease_refund_date"
    assert date_formula("=__import__('os')", {}, {}) is None
    raw = household.model_dump(mode="json")
    raw["bank_quotes"] = [
        {
            "date": "2026-10-01",
            "bank": "가상은행",
            "options": [{"method": "원리금균등", "rate": 0.04, "limit": 300000000}],
        }
    ]
    raw["fund_events"].append({"id": "A99", "value": 123, "origin": "app"})
    incoming = household.model_dump(mode="json")
    merged = merge_import(raw, incoming)
    assert merged["bank_quotes"][0]["bank"] == "가상은행"
    assert any(e["id"] == "A99" for e in merged["fund_events"])
    assert merged["settings"]["mortgage_quote_option"] == {"원리금균등": "q1-o1"}
    assert "A99" not in dumps(incoming)


def test_bank_quote_override_precedence(household, rules):
    from homeplan.models import BankQuote

    household.bank_quotes = [
        BankQuote.model_validate(
            {
                "date": "2026-10-01",
                "bank": "가상은행",
                "options": [{"id": "q1", "method": "원리금균등", "rate": 0.05, "limit": 290000000}],
            }
        )
    ]
    household.settings.mortgage_quote_option = {"원리금균등": "q1"}
    resolved = household.resolved({"mortgage_rate": "0.045"})
    assert str(resolved.settings.mortgage_rate) == "0.045"
    assert resolved.settings.bank_confirmed_limit == 290000000


def test_confirmed_only_reports_executed_loan_amounts(household, rules):
    household.settings.credit_status = "미확정"
    result = evaluate(household, None, rules, confirmed_only=True)
    assert result.kpis["credit_loan_amount"] == 0
    assert not any(e.source == "credit" for e in result.ledger)


def test_family_repayments_never_precede_future_draw(household, rules):
    from homeplan.models import ParentSupport

    household.parent_support.append(
        ParentSupport(id="P02", kind="차입", amount=3000000, date="2027-01-31", status="확정")
    )
    household.settings.family_loan_repay_start = "2027-01-01"
    household.settings.family_loan_monthly_principal = 1000000
    result = evaluate(household, None, rules, analyze_assumptions=False)
    payments = [e for e in result.ledger if e.category == "family_payment"]
    assert [e.date for e in payments] == [date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
    assert sum(e.amount for e in payments) == -3000000


@settings(max_examples=12, deadline=None)
@given(increase=st.integers(min_value=1, max_value=200000000))
def test_higher_price_reduces_closing_margin(increase):
    from pathlib import Path

    from homeplan.storage import load_household, load_rules

    household = load_household(Path(__file__).parents[1] / "fixtures/synthetic_household.json")
    rules = load_rules()
    listing = household.listing()
    before = evaluate(household, listing, rules, analyze_assumptions=False)
    listing.price += increase
    after = evaluate(household, listing, rules, analyze_assumptions=False)

    def margin(result):
        check = next(c for c in result.checks if c.name == "잔금")
        return check.numbers["actual"] - check.numbers["required"]

    assert margin(after) <= margin(before)
