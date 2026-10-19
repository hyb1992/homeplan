from datetime import date, timedelta
from decimal import Decimal

import pytest

from homeplan.checks import evaluate
from homeplan.dates import add_months
from homeplan.models import FundEvent, ParentSupport


def balances(household, rules, **kwargs):
    result = evaluate(household, None, rules, analyze_assumptions=False, **kwargs)
    return result, {row.date: row for row in result.daily_balances}


def test_cash_includes_draw_once_and_debt_starts_on_execution(household, rules):
    result, days = balances(household, rules)
    closing = household.resolved().day("closing_date")
    base = result.daily_balances[0]
    assert base.closing == 80000000
    assert base.debt_total == 100000000
    assert base.net_cash == -20000000
    assert days[closing - timedelta(days=1)].debt_total == 100000000
    assert days[closing].debt_breakdown == {"주택담보대출": 300000000}
    assert days[closing + timedelta(days=1)].debt_total == 330000000
    # 실행금은 현금 원장에 이미 포함된다. 빚을 다시 더하지 않는다.
    for day in result.daily_balances:
        movements = [row for row in result.ledger if row.date == day.date]
        assert day.closing == day.opening + sum(row.amount for row in movements)
        assert day.debt_total == sum(day.debt_breakdown.values())
        assert day.net_cash == day.closing - day.debt_total


def test_mortgage_principal_only_reduces_debt_and_idle_day_carries(household, rules):
    result, days = balances(household, rules)
    payment = result.loans["mortgage_schedule"][0]
    day = payment["date"]
    previous = days[day - timedelta(days=1)]
    assert days[day].debt_total == previous.debt_total - payment["principal"]
    assert payment["interest"] > 0
    idle = day + timedelta(days=4)
    assert not [row for row in result.ledger if row.date == idle]
    assert days[idle].closing == days[idle - timedelta(days=1)].closing
    assert days[idle].debt_total == days[idle - timedelta(days=1)].debt_total


def test_credit_and_subscription_stop_on_repayment(household, rules):
    household.settings.sub_loan_use = True
    household.settings.sub_amount = 5000000
    household.settings.credit_repay_date = "잔금일+2개월"
    household.settings.sub_repay_date = "잔금일+3개월"
    _, days = balances(household, rules)
    h = household.resolved()
    credit_repay, sub_repay = h.day("credit_repay_date"), h.day("sub_repay_date")
    assert days[credit_repay - timedelta(days=1)].debt_breakdown["신용대출"] == 30000000
    assert "신용대출" not in days[credit_repay].debt_breakdown
    assert days[sub_repay - timedelta(days=1)].debt_breakdown["청약담보대출"] == 5000000
    assert "청약담보대출" not in days[sub_repay].debt_breakdown


def test_amortizing_credit_balance_matches_payment_schedule(household, rules):
    household.settings.credit_method = "5년 분할"
    result, days = balances(household, rules)
    for payment in result.loans["credit_schedule"]:
        if payment["date"] in days:
            assert days[payment["date"]].debt_breakdown.get("신용대출", 0) == payment["balance"]


def test_family_loan_principal_ignores_fees_and_gifts(household, rules):
    draw = date(2027, 1, 15)
    household.parent_support.append(
        ParentSupport(kind="차입", amount=20000000, date=draw, status="확정")
    )
    household.fund_events.append(
        FundEvent(
            id="FAMILY",
            type="가족 차입",
            value=10000000,
            cost=100000,
            available_date=draw,
            status="확정",
        )
    )
    household.settings.family_loan_repay_start = "2027-02-15"
    household.settings.family_loan_rate = Decimal("0.12")
    household.settings.family_loan_monthly_principal = 10000000
    result, days = balances(household, rules)
    assert days[draw - timedelta(days=1)].debt_total == 100000000
    # 같은 날 기존 증여 1억은 부채가 아니며 차입 비용도 원금에서 차감하지 않는다.
    assert days[draw].debt_total == 130000000
    assert days[date(2027, 2, 15)].debt_breakdown["가족 차입"] == 20000000
    payment = next(row for row in result.ledger if row.category == "family_payment")
    assert payment.amount == -10300000
    assert "가족 차입" not in days[date(2027, 4, 15)].debt_breakdown


def test_card_debt_uses_principal_and_clears_last_rounding_remainder(household, rules):
    household.settings.card_pay_tax = True
    household.settings.card_months = 3
    household.settings.card_paid_installments = 3
    household.settings.card_fee_rate = Decimal("0.12")
    result, days = balances(household, rules)
    closing = household.resolved().day("closing_date")
    tax = result.costs["acquisition_taxes_total"]
    assert days[closing].debt_breakdown["취득세 카드 할부"] == tax
    assert days[add_months(closing, 1)].debt_breakdown["취득세 카드 할부"] == tax - tax // 3
    assert "취득세 카드 할부" not in days[add_months(closing, 3)].debt_breakdown
    assert sum(-row.amount for row in result.ledger if row.category == "card_payment") > tax


def test_existing_debt_without_date_is_still_owed_and_fee_is_not_principal(household, rules):
    household.fund_events.append(
        FundEvent(id="OTHER", type="기타 부채", name="기존 차입", value=7000000, cost=100000)
    )
    _, days = balances(household, rules)
    assert all(row.debt_breakdown["기존 차입 (OTHER)"] == 7000000 for row in days.values())


def test_confirmed_only_excludes_future_loan_but_keeps_existing_debt(household, rules):
    household.settings.credit_status = "미확정"
    household.parent_support.append(
        ParentSupport(kind="차입", amount=20000000, date="2027-01-15", status="예정")
    )
    _, days = balances(household, rules, confirmed_only=True)
    assert days[household.resolved().day("asset_base_date")].debt_total == 100000000
    assert all("신용대출" not in row.debt_breakdown for row in days.values())
    assert all("가족 차입" not in row.debt_breakdown for row in days.values())


def test_card_repaid_on_credit_draw_preserves_cash_and_clears_debt(household, rules):
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.credit_status = "확인 완료"
    result, days = balances(household, rules)
    h = household.resolved()
    closing, draw = h.day("closing_date"), h.day("credit_draw_date")
    tax = result.costs["acquisition_taxes_total"]
    payments = [row for row in result.ledger if row.category == "card_payment"]
    assert [(row.date, row.amount) for row in payments] == [(draw, -tax)]
    assert days[closing].debt_breakdown["취득세 카드 할부"] == tax
    assert "취득세 카드 할부" not in days[draw].debt_breakdown
    assert days[draw].debt_breakdown["신용대출"] == 30000000
    assert days[draw].closing == days[closing].closing + 30000000 - tax
    for row in days.values():
        assert row.closing == row.opening + sum(
            entry.amount for entry in result.ledger if entry.date == row.date
        )


@pytest.mark.parametrize("draw_input", ["잔금일+2개월", "2027-04-27"])
def test_card_settlement_keeps_only_prior_installments(household, rules, draw_input):
    # Both a scheduled payment day and a later day settle only the remaining principal.
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.card_fee_rate = Decimal("0.12")
    household.settings.card_paid_installments = 3
    household.settings.credit_draw_date = draw_input
    result, days = balances(household, rules)
    draw = household.resolved().day("credit_draw_date")
    tax = result.costs["acquisition_taxes_total"]
    principal = tax // 3
    paid_before = 1 if draw.day == 26 else 2
    payments = [row for row in result.ledger if row.category == "card_payment"]
    assert len(payments) == paid_before + 1
    assert payments[-1].date == draw
    assert payments[-1].amount == -(tax - principal * paid_before)
    assert sum(-row.amount for row in payments) > tax  # Only prior fees remain.
    assert all(row.date <= draw for row in payments)
    assert "취득세 카드 할부" not in days[draw].debt_breakdown


def test_card_settlement_after_final_payment_does_not_charge_twice(household, rules):
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.credit_draw_date = "잔금일+4개월"
    result, days = balances(household, rules)
    payments = [row for row in result.ledger if row.category == "card_payment"]
    assert len(payments) == 3
    assert sum(-row.amount for row in payments) == result.costs["acquisition_taxes_total"]
    assert (
        "취득세 카드 할부" not in days[household.resolved().day("credit_draw_date")].debt_breakdown
    )


def test_unconfirmed_credit_does_not_erase_planned_card_settlement(household, rules):
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.credit_status = "미확정"
    result, days = balances(household, rules, confirmed_only=True)
    draw = household.resolved().day("credit_draw_date")
    assert not [row for row in result.ledger if row.category == "loan_draw"]
    assert next(row for row in result.ledger if row.category == "card_payment").date == draw
    assert "취득세 카드 할부" not in days[draw].debt_breakdown
    assert "신용대출" not in days[draw].debt_breakdown


@pytest.mark.parametrize("same_day", [True, False])
def test_card_settlement_respects_same_day_inflow_rule(household, rules, same_day):
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.same_day_inflow_usable = same_day
    result, days = balances(household, rules)
    day = days[household.resolved().day("credit_draw_date")]
    tax = result.costs["acquisition_taxes_total"]
    assert day.minimum == (day.opening if same_day else day.opening - tax)


def test_card_settlement_keeps_obligation_without_credit_and_rejects_early_draw(household, rules):
    household.settings.card_pay_tax = True
    household.settings.card_repay_on_credit_draw = True
    household.settings.credit_use = False
    result, _ = balances(household, rules)
    assert not [row for row in result.ledger if row.category == "loan_draw"]
    assert len([row for row in result.ledger if row.category == "card_payment"]) == 1
    household.settings.credit_use = True
    household.settings.credit_draw_date = "잔금일-1"
    with pytest.raises(ValueError, match="잔금일보다"):
        balances(household, rules)
