from datetime import date

import pytest

from homeplan.checks import evaluate
from homeplan.expenses import monthly_bill
from homeplan.models import ExpenseItem, Household
from homeplan.solver import max_price


@pytest.mark.parametrize(
    ("closing", "first_budget_month", "first_payment_year"),
    [
        ("2027-03-19", "2027-03", 2027),
        ("2027-06-01", "2027-06", 2027),
        ("2027-06-02", "2028-01", 2028),
    ],
)
def test_property_tax_budget_starts_after_purchase_and_keeps_annual_payments(
    household, rules, closing, first_budget_month, first_payment_year
):
    household.settings.closing_date = closing
    household.settings.move_in_date = "잔금일+28"
    household.settings.property_tax_annual = 1000001
    result = evaluate(household, None, rules, analyze_assumptions=False)
    budget = result.kpis["monthly_expense_breakdown"]
    tax_months = [month for month in sorted(budget) if "보유세 · 월평균" in budget[month]]
    assert tax_months[0] == first_budget_month
    assert all("보유세 · 월평균" not in budget[m] for m in budget if m < first_budget_month)
    assert budget[first_budget_month]["보유세 · 월평균"] == 83333
    payments = [entry for entry in result.ledger if entry.category == "property_tax"]
    assert payments[0].date.year == first_payment_year
    for year in {entry.date.year for entry in payments}:
        year_payments = [entry for entry in payments if entry.date.year == year]
        assert [(entry.date.month, entry.amount) for entry in year_payments] == [
            (7, -500000),
            (9, -500001),
        ]
    for month, total in result.kpis["monthly_spend"].items():
        assert sum(budget[month].values()) == total


def test_monthly_period_boundary_full_and_prorated():
    row = ExpenseItem(
        id="E",
        name="기간 지출",
        amount=310000,
        start_date=date(2027, 1, 15),
        end_date=date(2027, 2, 10),
    )
    assert monthly_bill(row, date(2026, 12, 1), 25) is None
    assert monthly_bill(row, date(2027, 1, 1), 5) == (date(2027, 1, 15), 310000)
    assert monthly_bill(row, date(2027, 2, 1), 25) == (date(2027, 2, 10), 310000)
    assert monthly_bill(row, date(2027, 3, 1), 25) is None
    row.prorate = True
    assert monthly_bill(row, date(2027, 1, 1), 25) == (date(2027, 1, 25), 170000)
    assert monthly_bill(row, date(2027, 2, 1), 25) == (date(2027, 2, 10), 110714)


def test_current_housing_replaces_fixed_cost_and_suppresses_included_lease_interest(
    household, rules
):
    household.settings.fixed_cost = 1500000
    household.settings.childcare_cost = 800000
    household.settings.birth_date = "2027-04-01"
    household.expense_items = [
        ExpenseItem(id="LIVING", name="생활비", category="생활비", amount=3000000),
        ExpenseItem(
            id="HOUSING",
            name="전세 이자+관리비",
            category="주거비",
            amount=1500000,
            end_date="퇴거일",
            includes_lease_interest=True,
        ),
        ExpenseItem(
            id="AFTER",
            name="이사 후 고정비",
            category="고정비",
            amount=400000,
            start_date="퇴거일+1",
        ),
        ExpenseItem(
            id="CHILD", name="양육비", category="양육비", amount=800000, start_date="출산예정일"
        ),
    ]
    result = evaluate(household, None, rules, analyze_assumptions=False)
    housing = [e for e in result.ledger if e.source == "HOUSING"]
    assert housing and housing[-1].date == date(2027, 2, 25)
    assert all(e.date <= date(2027, 2, 26) for e in housing)
    assert not any(e.category == "lease_interest" for e in result.ledger)
    assert not any(e.label == "고정비" for e in result.ledger)
    assert [e.amount for e in result.ledger if e.source == "AFTER" and e.date.month == 3][
        0
    ] == -400000
    child = [e for e in result.ledger if e.source == "CHILD"]
    assert child[0].date == date(2027, 4, 25)
    assert all(e.amount == -800000 for e in child)
    assert not any(e.category == "living" and e.label == "양육비" for e in result.ledger)
    for month, total in result.kpis["monthly_spend"].items():
        assert sum(result.kpis["monthly_expense_breakdown"][month].values()) == total
    assert household.expense_items[1].end_date == "퇴거일"


def test_lease_interest_and_new_management_are_independent_and_keep_automatic_loans(
    household, rules
):
    household.expense_items = [ExpenseItem(id="E", name="보험", amount=100000)]
    household.settings.management_start_date = "잔금일"
    household.settings.management_end_date = "잔금일+1개월"
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert any(e.category == "lease_interest" for e in result.ledger)
    management = [e for e in result.ledger if e.label == "관리비"]
    assert management[0].date == date(2027, 2, 26)
    assert management[-1].date == date(2027, 3, 25)
    assert any(e.category == "mortgage_payment" for e in result.ledger)
    household.expense_items[0].includes_management = True
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert not any(e.label == "관리비" for e in result.ledger)


def test_empty_plan_removes_direct_expenses_but_keeps_automatic_costs(household, rules):
    household.expense_items = []
    result = evaluate(household, None, rules, analyze_assumptions=False)
    assert not any(e.label == "생활비" for e in result.ledger)
    assert any(e.category == "lease_interest" for e in result.ledger)
    assert any(e.category == "mortgage_payment" for e in result.ledger)
    assert result.kpis["expense_mode"] == "기간별"


def test_relative_expense_dates_follow_schedule_and_solver_uses_the_plan(household, rules):
    household.expense_items = [ExpenseItem(id="E", name="보험", amount=500000, end_date="퇴거일")]
    result = evaluate(
        household, None, rules, {"lease_refund_date": "2027-01-20"}, analyze_assumptions=False
    )
    assert max(e.date for e in result.ledger if e.source == "E") == date(2027, 1, 20)
    household.settings.interim_date = "2027-01-20"
    maximum = max_price(household, None, rules, minimum=580000000, maximum=580000000)
    assert maximum["at_price_kpis"]["expense_mode"] == "기간별"


def test_disabled_birth_placeholder_is_allowed_but_invalid_active_periods_rejected(household):
    household.expense_items = [
        ExpenseItem(
            id="E",
            name="양육비",
            category="양육비",
            amount=800000,
            start_date="출산예정일",
            enabled=False,
        )
    ]
    household.resolved()
    household.expense_items[0].enabled = True
    with pytest.raises(ValueError, match="비어"):
        household.resolved()
    household.expense_items = [
        ExpenseItem(
            id="E", name="보험", amount=100000, start_date="2027-03-01", end_date="2027-02-01"
        )
    ]
    with pytest.raises(ValueError, match="종료일"):
        household.resolved()
    with pytest.raises(ValueError, match="중복"):
        Household.model_validate(
            {
                **household.model_dump(),
                "expense_items": [household.expense_items[0].model_dump()] * 2,
            }
        )
