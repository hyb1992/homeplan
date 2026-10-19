from datetime import date

import pytest

from homeplan.checks import evaluate
from homeplan.solver import max_price


def plan(household):
    household.settings.contract_date = "2026-12-24"
    household.settings.interim_date = "2027-02-26"
    household.settings.closing_date = "2027-04-23"
    household.settings.move_in_date = "2027-05-21"
    return household


@pytest.mark.parametrize("permit_date", [None, "2026-12-24"])
def test_closing_before_deadline_passes_with_later_renovation_move_in(
    household, rules, permit_date
):
    plan(household).settings.permit_date = permit_date
    result = evaluate(household, None, rules, analyze_assumptions=False)
    check = next(c for c in result.checks if c.name == "토허 4개월")
    assert check.ok
    assert check.numbers["deadline"] == date(2027, 4, 24)
    assert check.numbers["closing"] == date(2027, 4, 23)
    assert check.numbers["comparison_date"] == "closing_date"
    assert check.numbers["provisional"] == (permit_date is None)
    assert "예정 잔금 2027-04-23" in check.reason
    assert "입주기한" not in check.reason
    assert any("실거주 이행과 수리 기간" in warning for warning in result.warnings)
    assert [e.date for e in result.ledger if e.category == "move_in"] == [date(2027, 5, 21)]
    assert [e.date for e in result.ledger if e.category == "mortgage_draw"] == [date(2027, 4, 23)]


@pytest.mark.parametrize("closing, passes", [("2027-04-24", True), ("2027-04-25", False)])
def test_closing_deadline_is_inclusive(household, rules, closing, passes):
    plan(household).settings.closing_date = closing
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert next(c.ok for c in result.checks if c.name == "토허 4개월") is passes


def test_explicit_permit_date_and_separate_mortgage_move_in_check(household, rules):
    h = plan(household)
    h.settings.permit_date = "2026-12-20"
    result = evaluate(h, None, rules, analyze_assumptions=False)
    assert not next(c.ok for c in result.checks if c.name == "토허 4개월")
    h.settings.permit_date = "2026-12-24"
    h.settings.move_in_date = "2027-10-24"
    result = evaluate(h, None, rules, analyze_assumptions=False)
    assert next(c.ok for c in result.checks if c.name == "토허 4개월")
    assert not next(c.ok for c in result.checks if c.name == "전입 6개월")


def test_maximum_uses_closing_gate_even_with_later_renovation(household, rules):
    h = plan(household)
    for closing, fails in [("2027-04-23", False), ("2027-04-25", True)]:
        result = max_price(
            h,
            None,
            rules,
            {"closing_date": closing},
            minimum=580000000,
            maximum=580000000,
        )
        assert any(c["name"] == "토허 4개월" for c in result["gate_failures"]) is fails
