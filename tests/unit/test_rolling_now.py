from datetime import date, timedelta

from homeplan.checks import evaluate
from homeplan.dates import parse_user_date, resolve
from homeplan.models import FundEvent
from homeplan.solver import max_price


def test_now_uses_explicit_calculation_date_and_preserves_fixed_anchors():
    anchors = {"asset_base_date": "2026-09-10", "closing_date": "지금+1개월"}
    today = date(2026, 10, 31)
    assert resolve("지금", anchors, as_of=today) == today
    assert resolve("today", anchors, as_of=today) == today
    assert resolve("잔금일-1", anchors, as_of=today) == date(2026, 11, 29)
    assert resolve("기준일", anchors, as_of=today) == date(2026, 9, 10)
    assert resolve("2026-10-18", anchors, as_of=today) == date(2026, 10, 18)
    assert resolve("지금", anchors) == date(2026, 9, 10)
    assert parse_user_date("지금", date(2026, 9, 10)) == "지금"


def test_same_saved_now_moves_to_next_day_once_without_mutating_input(household, rules):
    household.fund_events.append(
        FundEvent(id="NOW", value=30000000, available_date="지금", status="확정")
    )
    today = date(2026, 10, 18)
    first = evaluate(household, None, rules, as_of=today, analyze_assumptions=False)
    second = evaluate(
        household, None, rules, as_of=today + timedelta(days=1), analyze_assumptions=False
    )
    assert [(e.date, e.amount) for e in first.ledger if e.source == "NOW"] == [(today, 30000000)]
    assert [(e.date, e.amount) for e in second.ledger if e.source == "NOW"] == [
        (today + timedelta(days=1), 30000000)
    ]
    day1 = next(row for row in first.daily_balances if row.date == today)
    day2 = next(row for row in second.daily_balances if row.date == today)
    assert day1.closing - day2.closing == 30000000
    assert first.daily_balances[-1].closing == second.daily_balances[-1].closing
    assert household.fund_events[-1].available_date == "지금"


def test_maximum_resolves_now_with_the_same_date_as_evaluation(household, rules):
    household.fund_events.append(
        FundEvent(id="NOW", value=30000000, available_date="지금", status="확정")
    )
    # After closing, this money cannot fund the purchase. A base-date fallback could.
    today = date(2027, 3, 20)
    outcome = max_price(household, None, rules, minimum=580000000, maximum=580000000, as_of=today)
    fixed = household.model_copy(deep=True)
    fixed.fund_events[-1].available_date = today
    expected = max_price(fixed, None, rules, minimum=580000000, maximum=580000000, as_of=today)
    assert outcome == expected
    assert household.fund_events[-1].available_date == "지금"
