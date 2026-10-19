from datetime import date

import pytest
from pydantic import ValidationError

from homeplan.checks import evaluate
from homeplan.models import FundEvent
from homeplan.solver import max_price


def variable(**overrides):
    return FundEvent.model_validate(
        {
            "id": "VARIABLE",
            "name": "가상 변동자산",
            "type": "투자자산",
            "value": 900,
            "cash_out_amount": 800,
            "cost": 100,
            "is_variable": True,
            "conservative_amount": 1000,
            "aggressive_amount": 2000,
            "available_date": "2026-11-15",
            "status": "확정",
            **overrides,
        }
    )


def test_variable_amount_replaces_old_amount_once_and_preserves_input(household, rules):
    household.fund_events.append(variable())
    original = household.model_dump()
    conservative = evaluate(household, None, rules, analyze_assumptions=False)
    aggressive = evaluate(
        household, None, rules, {"variable_asset_mode": "공격적"}, analyze_assumptions=False
    )
    for result, expected, mode in [(conservative, 900, "보수적"), (aggressive, 1900, "공격적")]:
        movements = [row for row in result.ledger if row.source == "VARIABLE"]
        assert len(movements) == 1
        assert movements[0].amount == expected
        assert movements[0].date == date(2026, 11, 15)
        assert result.kpis["variable_asset_mode"] == mode
    for left, right in zip(conservative.daily_balances, aggressive.daily_balances, strict=True):
        assert right.closing - left.closing == (1000 if left.date >= date(2026, 11, 15) else 0)
        assert right.debt_total == left.debt_total
    assert household.model_dump() == original
    resolved = household.resolved({"variable_asset_mode": "공격적"})
    assert resolved.resolved().fund_events[-1].amount == 1900


def test_current_stock_and_zero_conservative_amount(household, rules):
    household.fund_events = [
        variable(available_date=None, cost=0, conservative_amount=0, aggressive_amount=2000)
    ]
    conservative = evaluate(household, None, rules, analyze_assumptions=False)
    aggressive = evaluate(
        household, None, rules, {"variable_asset_mode": "공격적"}, analyze_assumptions=False
    )
    assert conservative.daily_balances[0].closing == 0
    assert aggressive.daily_balances[0].closing == 2000
    assert not any(row.source == "VARIABLE" for row in aggressive.ledger)


def test_new_variable_asset_needs_no_old_fixed_amount(household, rules):
    household.fund_events.append(variable(value=None, cash_out_amount=None))
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert next(row.amount for row in result.ledger if row.source == "VARIABLE") == 900


@pytest.mark.parametrize("mode", ["보수적", "공격적"])
def test_confirmed_only_excludes_pending_future_variable_asset(household, rules, mode):
    household.fund_events.append(variable(status="미확정"))
    result = evaluate(
        household,
        None,
        rules,
        {"variable_asset_mode": mode},
        confirmed_only=True,
        analyze_assumptions=False,
    )
    assert not any(row.source == "VARIABLE" for row in result.ledger)


def test_pending_zero_variable_income_does_not_leave_its_cost_in_confirmed_only(household, rules):
    household.fund_events.append(variable(status="미확정", conservative_amount=0))
    result = evaluate(household, None, rules, confirmed_only=True, analyze_assumptions=False)
    assert not any(row.source == "VARIABLE" for row in result.ledger)


@pytest.mark.parametrize("mode", ["보수적", "공격적"])
@pytest.mark.parametrize(
    "excluded", [{"status": "제외"}, {"data_kind": "예시"}, {"use_for_purchase": False}]
)
def test_variable_assets_keep_exclusion_rules(household, rules, mode, excluded):
    baseline = evaluate(
        household, None, rules, {"variable_asset_mode": mode}, analyze_assumptions=False
    )
    household.fund_events.append(variable(**excluded))
    result = evaluate(
        household, None, rules, {"variable_asset_mode": mode}, analyze_assumptions=False
    )
    assert result.daily_balances == baseline.daily_balances


@pytest.mark.parametrize(
    "invalid",
    [
        {"conservative_amount": None},
        {"aggressive_amount": None},
        {"conservative_amount": 3000},
        {"conservative_amount": -1},
        {"aggressive_amount": 0.2},
        {"type": "기존 전세대출(부채)"},
        {"type": "기타 나갈 돈"},
        {"type": "가족 차입"},
    ],
)
def test_invalid_variable_asset_is_rejected(invalid):
    with pytest.raises(ValidationError):
        variable(**invalid)


def test_maximum_price_uses_same_variable_asset_basis(household, rules):
    household.fund_events.append(
        variable(
            available_date=None, cost=0, conservative_amount=30000000, aggressive_amount=50000000
        )
    )
    conservative = max_price(household, None, rules, minimum=550000000, maximum=650000000)
    aggressive = max_price(
        household,
        None,
        rules,
        {"variable_asset_mode": "공격적"},
        minimum=550000000,
        maximum=650000000,
    )
    assert conservative["price"] is not None
    assert aggressive["price"] >= conservative["price"]
    assert conservative["at_price_kpis"]["variable_asset_mode"] == "보수적"
    assert aggressive["at_price_kpis"]["variable_asset_mode"] == "공격적"
