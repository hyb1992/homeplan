"""심사 시점과 차주를 구별하는 참고 DSR."""

from decimal import Decimal
from typing import Any

from .loans import annual_factor, mortgage_first_payment
from .models import Household


def dsr_mortgage_review(
    household_income: int,
    mortgage: int,
    rate: Any,
    stress: Any,
    years: int,
    method: str,
    other_annual: Any = 0,
) -> Decimal:
    from .money import dec

    return (
        (mortgage * annual_factor(dec(rate) + dec(stress), years, method) + dec(other_annual))
        / household_income
        if household_income
        else Decimal(0)
    )


def dsr_metrics(h: Household, loans: dict[str, Any]) -> dict[str, Any]:
    s = h.settings
    income = s.bank_income or s.husband_gross + s.wife_gross
    mortgage, credit, sub = loans["mortgage"], loans["credit"], loans["sub"]
    review = mortgage * loans["mortgage_factor"]
    actual = (
        mortgage_first_payment(mortgage, s.mortgage_rate, s.mortgage_years, s.mortgage_method) * 12
    )
    credit_annual = credit * loans["credit_factor"]
    sub_annual = sub * loans["sub_rate"]
    borrower_income = s.husband_gross if s.credit_borrower == "남편" else s.wife_gross
    borrower_sub = sub_annual * (
        Decimal(s.sub_principal_husband if s.credit_borrower == "남편" else s.sub_principal_wife)
        / max(1, s.sub_principal_husband + s.sub_principal_wife)
    )
    borrower_annual = (
        credit_annual + borrower_sub + (review if s.credit_borrower == s.mortgage_borrower else 0)
    )
    return {
        "dsr_mortgage_review": (review + loans["other_review_annual"]) / income if income else None,
        "dsr_credit_borrower": borrower_annual / borrower_income if borrower_income else None,
        "dsr_household_actual": (actual + credit_annual + sub_annual + s.existing_debt_annual)
        / income
        if income
        else None,
        "dsr_refinance_check": (
            review
            + credit_annual
            + sub * (loans["sub_rate"] + s.stress_rate)
            + s.existing_debt_annual
        )
        / income
        if income
        else None,
    }
