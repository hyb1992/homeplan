from datetime import date, timedelta
from decimal import Decimal

import pytest

from homeplan.checks import evaluate
from homeplan.loans import amortization
from homeplan.models import ExpenseItem, LoanPrepayment
from homeplan.prepayments import with_prepayments


def test_maternity_only_does_not_pass_zero_spend(household, rules):
    household.settings.maternity_start = "2027-05-01"
    household.settings.wife_leave_start = None
    household.settings.living_cost = 20000000
    result = evaluate(household, None, rules, analyze_assumptions=False)
    check = next(c for c in result.checks if c.name == "월 가계지출 한도")
    assert not check.ok
    assert check.numbers["required"] >= 20000000
    assert check.numbers["month"]
    assert check.numbers["period_start"] == "2027-03"


def test_annual_amount_requires_month_but_included_amount_does_not(household, rules):
    household.settings.annual_cost = 12000000
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert not next(c for c in result.checks if c.name == "입력").ok
    household.settings.fixed_in_living = True
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert next(c for c in result.checks if c.name == "입력").ok
    household.settings.fixed_in_living = False
    household.settings.annual_cost_month = 12
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert next(c for c in result.checks if c.name == "입력").ok
    assert all(e.date.month == 12 for e in result.ledger if e.category == "annual")


def test_today_carries_opening_cash_and_debt_without_repeating_events(household, rules):
    household.settings.start_today = True
    before = evaluate(household, None, rules, as_of=date(2026, 10, 18), analyze_assumptions=False)
    after = evaluate(household, None, rules, as_of=date(2026, 10, 19), analyze_assumptions=False)
    assert before.daily_balances[0].date == date(2026, 10, 18)
    assert after.daily_balances[0].opening == before.daily_balances[0].closing
    assert after.daily_balances[0].debt_total == before.daily_balances[0].debt_total
    assert before.kpis["closing_cash_available"] == after.kpis["closing_cash_available"]
    assert before.kpis["contract_cash_available"] == after.kpis["contract_cash_available"]
    assert all(e.date >= date(2026, 10, 18) for e in before.ledger)
    assert "2026-09" not in before.kpis["month_end_balance"]
    assert household.settings.asset_base_date == "2026-09-10"


def test_today_carries_past_support_and_only_bills_the_remaining_day(household, rules):
    household.settings.start_today = True
    whole = evaluate(household, None, rules, as_of=date(2026, 10, 1), analyze_assumptions=False)
    start = date(2026, 12, 20)
    viewed = evaluate(household, None, rules, as_of=start, analyze_assumptions=False)
    original = next(d for d in whole.daily_balances if d.date == start)
    assert viewed.daily_balances[0] == original
    assert len([e for e in viewed.ledger if e.source == "A02"]) == 1
    assert viewed.kpis["closing_cash_available"] == whole.kpis["closing_cash_available"]


def test_expense_replacement_keeps_alias_and_changes_partial_month(household, rules):
    household.settings.birth_date = "2027-05-30"
    household.expense_items = [
        ExpenseItem(id="old", name="기존", amount=3000000, start_date="기준일"),
        ExpenseItem(
            id="new", name="변경", amount=1500000, start_date="출산예정일", replaces_id="old"
        ),
    ]
    result = evaluate(household, None, rules, analyze_assumptions=False)
    detail = result.kpis["monthly_expense_breakdown"]
    assert detail["2027-04"]["기존"] == 3000000
    assert detail["2027-05"]["기존"] == 2806452
    assert detail["2027-05"]["변경"] == 96774
    assert "기존" not in detail["2027-06"]
    assert detail["2027-06"]["변경"] == 1500000
    assert household.expense_items[0].end_date is None
    household.settings.birth_date = "2027-06-01"
    resolved = household.resolved()
    assert resolved.expense_items[0].end_date == date(2027, 5, 31)
    household.expense_items[0].replaces_id = "new"
    with pytest.raises(ValueError, match="순환"):
        household.resolved()


@pytest.mark.parametrize("mode", ["납입 감소", "기간 단축"])
def test_partial_repayment_conserves_principal_and_fee(mode):
    draw = date(2027, 3, 20)
    schedule = amortization(82000000, Decimal("0.0468"), 60, draw)
    adjusted, extras = with_prepayments(
        schedule,
        82000000,
        draw,
        Decimal("0.0468"),
        [LoanPrepayment(id="one", date=draw, amount=45000000, fee=10000, method=mode)],
    )
    assert extras == [(draw, 45000000, 10000)]
    assert sum(p.principal for p in adjusted) + 45000000 == 82000000
    assert adjusted[-1].balance == 0
    if mode == "납입 감소":
        assert adjusted[0].total == 692824
        assert adjusted[-1].date == schedule[-1].date
    else:
        assert adjusted[0].total == schedule[0].total
        assert adjusted[-1].date < schedule[-1].date


def test_multiple_repayments_and_same_day_regular_payment():
    draw = date(2027, 1, 1)
    original = amortization(12000000, Decimal("0.06"), 12, draw)
    rows, extra = with_prepayments(
        original,
        12000000,
        draw,
        Decimal("0.06"),
        [
            LoanPrepayment(id="a", date=original[0].date, amount=1000000),
            LoanPrepayment(id="b", date=original[2].date + timedelta(days=1), amount=2000000),
        ],
    )
    assert rows[0] == original[0]
    assert sum(row.principal for row in rows) + sum(item[1] for item in extra) == 12000000
    with pytest.raises(ValueError, match="原金|원금"):
        with_prepayments(
            original,
            12000000,
            draw,
            Decimal("0.06"),
            [LoanPrepayment(id="over", date=draw, amount=12000001)],
        )


def test_partial_repayment_ledger_debt_and_budget(household, rules):
    household.settings.credit_amount = 82000000
    household.settings.credit_method = "5년 분할"
    household.settings.credit_rate = Decimal("0.0468")
    household.loan_prepayments = [
        LoanPrepayment(id="a", loan="credit", date="잔금일+1", amount=45000000, fee=10000)
    ]
    result = evaluate(household, None, rules, analyze_assumptions=False)
    draw = household.resolved().day("credit_draw_date")
    day = next(d for d in result.daily_balances if d.date == draw)
    assert day.debt_breakdown["신용대출"] == 37000000
    assert [
        (e.amount, e.category) for e in result.ledger if e.source == "credit" and e.date == draw
    ] == [(82000000, "loan_draw"), (-45000000, "prepayment"), (-10000, "prepayment_fee")]
    assert (
        result.loans["credit_schedule"][0]["principal"]
        + result.loans["credit_schedule"][0]["interest"]
        == 692824
    )
    assert result.kpis["monthly_expense_breakdown"]["2027-03"]["신용대출 상환"] == 692824


def test_direct_zero_credit_does_not_trigger_auto_limit(household, rules):
    household.settings.credit_amount = 0
    household.settings.credit_amount_mode = "직접"
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert result.kpis["credit_loan_amount"] == 0
