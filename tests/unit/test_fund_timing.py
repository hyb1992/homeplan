from datetime import date

import pytest

from homeplan.checks import evaluate
from homeplan.models import FundEvent, ParentSupport


def test_lease_deposit_arrives_once_on_move_out_and_follows_date_changes(household, rules):
    household.settings.lease_end_date = "2027-04-30"
    household.fund_events.append(
        FundEvent(
            id="TIMING",
            type="전세보증금",
            value=205000000,
            available_date="퇴거일",
            status="확정",
        )
    )
    for move_out in (date(2027, 2, 26), date(2027, 3, 20)):
        result = evaluate(
            household, None, rules, {"lease_refund_date": move_out}, analyze_assumptions=False
        )
        assert [(e.date, e.amount) for e in result.ledger if e.source == "TIMING"] == [
            (move_out, 205000000)
        ]
        assert result.daily_balances[0].opening == 80000000
    assert household.fund_events[-1].available_date == "퇴거일"
    assert household.settings.move_in_date == "2027-03-02"
    assert household.settings.lease_end_date == "2027-04-30"


@pytest.mark.parametrize("same_day_usable", [True, False])
def test_interim_fund_follows_schedule_without_adding_purchase_payments(
    household, rules, same_day_usable
):
    household.settings.same_day_inflow_usable = same_day_usable
    baseline = evaluate(household, None, rules, analyze_assumptions=False)
    household.fund_events.append(
        FundEvent(
            id="TIMING",
            type="전세보증금",
            value=30000000,
            available_date="중도금일",
            status="확정",
        )
    )
    result = evaluate(household, None, rules, analyze_assumptions=False)
    difference = (
        result.kpis["interim_cash_available_before_deposit"]
        - baseline.kpis["interim_cash_available_before_deposit"]
    )
    assert difference == (30000000 if same_day_usable else 0)
    for interim_day in (date(2026, 12, 1), date(2027, 1, 20)):
        result = evaluate(
            household, None, rules, {"interim_date": interim_day}, analyze_assumptions=False
        )
        assert [(e.date, e.amount) for e in result.ledger if e.source == "TIMING"] == [
            (interim_day, 30000000)
        ]
        assert [(e.date, e.amount) for e in result.ledger if e.label == "중도금"] == [
            (interim_day, -50000000)
        ]
        assert sum(e.amount for e in result.ledger if e.category == "purchase") == -580000000
    assert household.fund_events[-1].available_date == "중도금일"


@pytest.mark.parametrize("interim", ["2026-12-01", "2027-01-20"])
def test_linked_move_out_moves_deposit_and_lease_loan_repayment_once(household, rules, interim):
    household.settings.lease_refund_date = "중도금일"
    result = evaluate(household, None, rules, {"interim_date": interim}, analyze_assumptions=False)
    day = date.fromisoformat(interim)
    assert [(e.date, e.amount) for e in result.ledger if e.source == "A03"] == [(day, 200000000)]
    assert [(e.date, e.amount) for e in result.ledger if e.source == "L01"] == [(day, -100000000)]
    assert [(e.date, e.amount) for e in result.ledger if e.label == "중도금"] == [(day, -50000000)]
    assert household.settings.lease_refund_date == "중도금일"
    assert household.settings.closing_date == "2027-02-26"
    assert household.settings.move_in_date == "2027-03-02"


def test_linked_move_out_rejects_circular_interim_reference(household):
    household.settings.interim_date = "퇴거일"
    household.settings.lease_refund_date = "중도금일"
    with pytest.raises(ValueError, match="순환"):
        household.resolved()


@pytest.mark.parametrize(
    "anchor, field, changed",
    [("중도금일", "interim_date", "2027-01-20"), ("잔금일", "closing_date", "2027-03-01")],
)
def test_retirement_receipt_follows_selected_schedule_once(
    household, rules, anchor, field, changed
):
    household.fund_events.append(
        FundEvent(
            id="RETIREMENT",
            type="퇴직 관련 수령금",
            value=82000000,
            cost=1000000,
            available_date=anchor,
            status="확인 완료",
        )
    )
    for overrides in (None, {field: changed}):
        result = evaluate(
            household, None, rules, overrides, confirmed_only=True, analyze_assumptions=False
        )
        day = household.resolved(overrides).day(field)
        assert [(e.date, e.amount) for e in result.ledger if e.source == "RETIREMENT"] == [
            (day, 81000000)
        ]
    assert household.fund_events[-1].available_date == anchor
    assert household.fund_events[-1].status == "확인 완료"


def test_retirement_date_selection_does_not_confirm_unverified_receipt(household, rules):
    event = FundEvent(
        id="RETIREMENT",
        type="퇴직 관련 수령금",
        value=82000000,
        available_date="중도금일",
        status="미확정",
    )
    household.fund_events.append(event)
    for anchor in ("중도금일", "잔금일"):
        event.available_date = anchor
        result = evaluate(household, None, rules, analyze_assumptions=False)
        assert not any(e.source == "RETIREMENT" for e in result.ledger)
        assert event.status == "미확정"


@pytest.mark.parametrize(
    "anchor, field, changed",
    [("중도금일", "interim_date", "2027-01-20"), ("잔금일", "closing_date", "2027-03-01")],
)
def test_parent_support_dates_follow_schedule_without_duplicate_cash_or_debt(
    household, rules, anchor, field, changed
):
    household.parent_support.extend(
        [
            ParentSupport(
                id="GIFT", to="남편", kind="증여", amount=30000000, date=anchor, status="확정"
            ),
            ParentSupport(
                id="LOAN", to="아내", kind="차입", amount=20000000, date=anchor, status="확정"
            ),
        ]
    )
    for overrides in (None, {field: changed}):
        result = evaluate(household, None, rules, overrides, analyze_assumptions=False)
        day = household.resolved(overrides).day(field)
        for key, amount in [("GIFT", 30000000), ("LOAN", 20000000)]:
            assert [(e.date, e.amount) for e in result.ledger if e.source == key] == [(day, amount)]
        balance = next(row for row in result.daily_balances if row.date == day)
        assert balance.debt_breakdown["가족 차입"] == 20000000
    assert household.parent_support[-2].date == anchor
    assert household.parent_support[-1].kind == "차입"
    assert household.parent_support[-1].to == "아내"


def test_date_link_does_not_restore_excluded_parent_support(household, rules):
    household.parent_support.append(
        ParentSupport(id="EXCLUDED", kind="차입", amount=50000000, date="중도금일", status="제외")
    )
    for anchor in ("중도금일", "잔금일"):
        household.parent_support[-1].date = anchor
        result = evaluate(household, None, rules, analyze_assumptions=False)
        assert not any(e.source == "EXCLUDED" for e in result.ledger)
        assert all("가족 차입" not in row.debt_breakdown for row in result.daily_balances)
        assert household.parent_support[-1].status == "제외"
