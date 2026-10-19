from datetime import timedelta

import pytest
from pydantic import ValidationError

from homeplan.checks import evaluate
from homeplan.models import Listing
from homeplan.solver import max_price


def test_manual_tax_replaces_final_total_once_in_cash_and_debt(household, rules):
    household.settings.card_pay_tax = False
    original = evaluate(household, None, rules, analyze_assumptions=False)
    listing = household.listings[0]
    automatic = original.costs["acquisition_taxes_total"]
    listing.acquisition_tax_amount = 1234567
    manual = evaluate(household, None, rules, analyze_assumptions=False)
    assert manual.costs["acquisition_taxes_total"] == 1234567
    assert manual.costs["taxes"]["calculated"]["total"] == automatic
    assert (
        manual.costs["cash_closing_fees"]
        == original.costs["cash_closing_fees"] - automatic + 1234567
    )
    closing = household.resolved().day("closing_date")
    old = next(row for row in original.daily_balances if row.date == closing)
    new = next(row for row in manual.daily_balances if row.date == closing)
    assert new.closing - old.closing == automatic - 1234567
    assert new.debt_total == old.debt_total
    assert [entry.amount for entry in manual.ledger if entry.category == "purchase_cost"] == [
        -manual.costs["cash_closing_fees"]
    ]


def test_manual_tax_is_card_principal_and_early_settlement_amount(household, rules):
    household.listings[0].acquisition_tax_amount = 1234567
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    result = evaluate(household, None, rules, analyze_assumptions=False)
    closing = household.resolved().day("closing_date")
    day = next(row for row in result.daily_balances if row.date == closing)
    assert day.debt_breakdown["취득세 카드 할부"] == 1234567
    assert [entry.amount for entry in result.ledger if entry.category == "card_payment"] == [
        -1234567
    ]
    settled = next(row for row in result.daily_balances if row.date == closing + timedelta(days=1))
    assert "취득세 카드 할부" not in settled.debt_breakdown


def test_manual_zero_and_auto_reset_and_solver_are_distinct(household, rules):
    household.fund_events[0].value = 1000000000
    listing = household.listings[0]
    original = evaluate(household, None, rules, analyze_assumptions=False)
    listing.acquisition_tax_amount = 0
    zero = evaluate(household, None, rules, analyze_assumptions=False)
    assert zero.costs["acquisition_taxes_total"] == 0
    maximum = max_price(
        household, None, rules, mode="listing", minimum=listing.price, maximum=listing.price
    )
    assert maximum["at_price_kpis"]["after_purchase_cash"] == zero.kpis["after_purchase_cash"]
    listing.acquisition_tax_amount = None
    restored = evaluate(household, None, rules, analyze_assumptions=False)
    assert restored.costs == original.costs and restored.ledger == original.ledger
    with pytest.raises(ValidationError):
        Listing.model_validate({**listing.model_dump(), "acquisition_tax_amount": -1})
