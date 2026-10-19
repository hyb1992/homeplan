"""원금을 원 단위로 보존하는 상환표와 대출금 계산."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from .dates import add_months
from .models import Household, Listing
from .money import dec, floor_to, won
from .rules import RuleBook


class Payment(BaseModel):
    date: date
    principal: int
    interest: int
    balance: int

    @property
    def total(self) -> int:
        return self.principal + self.interest


def pmt(amount: Any, rate: Any, months: int) -> Decimal:
    if months <= 0:
        raise ValueError("상환 회차는 1 이상이어야 합니다")
    r = dec(rate) / 12
    if not r:
        return dec(amount) / months
    return dec(amount) * r / (1 - (1 + r) ** -months)


def mortgage_first_payment(amount: int, rate: Any, years: int, method: str = "원리금균등") -> int:
    return (
        won(pmt(amount, rate, years * 12))
        if method == "원리금균등"
        else won(dec(amount) / (years * 12)) + won(amount * dec(rate) / 12)
    )


def amortization(
    amount: int,
    rate: Any,
    months: int,
    draw_date: date,
    method: str = "원리금균등",
    reset_after: int = 0,
    reset_rate: Any = 0,
    first_adjustment: int = 0,
) -> list[Payment]:
    if amount == 0:
        return []
    balance, current_rate = amount, dec(rate)
    installment = won(pmt(balance, current_rate, months))
    principal_fixed = won(dec(amount) / months)
    out: list[Payment] = []
    for k in range(1, months + 1):
        if reset_after and k == reset_after + 1:
            current_rate = dec(reset_rate)
            installment = won(pmt(balance, current_rate, months - k + 1))
        interest = won(balance * current_rate / 12)
        principal = min(
            balance, max(0, installment - interest) if method == "원리금균등" else principal_fixed
        )
        if k == months:
            principal = balance
        balance -= principal
        interest += first_adjustment if k == 1 else 0
        out.append(
            Payment(
                date=add_months(draw_date, k),
                principal=principal,
                interest=interest,
                balance=balance,
            )
        )
        if balance == 0:
            break
    return out


def interest_only(
    amount: int, rate: Any, draw: date, end: date, repay: date | None = None
) -> list[Payment]:
    out: list[Payment] = []
    k = 1
    while (day := add_months(draw, k)) <= end and (repay is None or day <= repay):
        out.append(
            Payment(date=day, principal=0, interest=won(amount * dec(rate) / 12), balance=amount)
        )
        k += 1
    if repay and draw <= repay <= end:
        out.append(Payment(date=repay, principal=amount, interest=0, balance=0))
    return out


def card_installments(
    amount: int, months: int, paid_installments: int = 0, fee_rate: Any = 0
) -> list[int]:
    if months < 1 or not 0 <= paid_installments <= months:
        raise ValueError("할부 개월 및 고객 부담 회차를 확인하세요")
    principal, remaining = amount // months, amount
    out: list[int] = []
    for k in range(months):
        repayment = principal if k < months - 1 else remaining
        fee = won(remaining * dec(fee_rate) / 12) if k < paid_installments else 0
        out.append(repayment + fee)
        remaining -= repayment
    return out


def annual_factor(rate: Any, years: int, method: str, basis: str = "전체 평균") -> Decimal:
    if method == "원리금균등":
        return pmt(1, rate, years * 12) * 12
    n = Decimal(years * 12)
    return Decimal(1) / years + dec(rate) * (
        (n + 1) / (2 * n) if basis == "전체 평균" else 1 - Decimal("5.5") / n
    )


def credit_full_limit(
    rules: RuleBook, borrower_gross: int, existing_credit: int = 0
) -> dict[str, Any]:
    calc = rules["lending"]["calculation"]
    limit = max(
        0,
        floor_to(
            min(
                borrower_gross * dec(rules["lending"]["credit_loan_rules"]["income_cap_ratio"]),
                calc["credit_purchase_safe_cap"],
            )
            - existing_credit,
            calc["credit_round_unit"],
        ),
    )
    return {"limit": limit}


def loan_amounts(h: Household, listing: Listing, rules: RuleBook) -> dict[str, Any]:
    s, r = h.settings, rules["lending"]
    calc = r["calculation"]
    credit_years = calc["credit_dsr_years"]
    closing = h.day("closing_date")
    sub = (
        (
            (s.sub_amount if s.sub_amount_mode != "자동" else 0)
            or (
                0
                if s.sub_amount_mode == "직접"
                else floor_to(
                    (s.sub_principal_husband + s.sub_principal_wife) * s.sub_ratio,
                    calc["subscription_round_unit"],
                )
            )
        )
        if s.sub_loan_use
        else 0
    )
    sub_limit = floor_to(
        (s.sub_principal_husband + s.sub_principal_wife) * s.sub_ratio,
        calc["subscription_round_unit"],
    )
    sub_rate = s.sub_savings_rate + s.sub_spread
    gross = s.husband_gross if s.credit_borrower == "남편" else s.wife_gross
    income = s.bank_income or s.husband_gross + s.wife_gross
    factor = annual_factor(
        s.mortgage_rate + s.stress_rate,
        s.mortgage_years,
        s.mortgage_method,
        s.equal_principal_dsr_basis,
    )
    credit_factor = Decimal(1) / credit_years + s.credit_rate
    if s.credit_method != "만기일시":
        credit_factor = pmt(1, s.credit_rate, credit_years * 12) * 12
    sub_before = bool(
        sub
        and h.day("sub_draw_date") <= closing
        and (s.sub_repay_date is None or h.day("sub_repay_date") > closing)
    )
    credit_before = (
        s.credit_use
        and h.day("credit_draw_date") <= closing
        and (s.credit_repay_date is None or h.day("credit_repay_date") > closing)
    )
    preliminary = min(s.mortgage_desired, s.bank_confirmed_limit or s.mortgage_cap)
    borrower_other = (
        sub * sub_rate
        if (s.credit_borrower == "남편" and s.sub_principal_husband)
        or (s.credit_borrower == "아내" and s.sub_principal_wife)
        else Decimal(0)
    )
    if s.credit_borrower == s.mortgage_borrower:
        borrower_other += preliminary * factor
    dsr_credit = (
        max(
            0,
            floor_to(
                (gross * s.dsr_limit - borrower_other) / credit_factor, calc["credit_round_unit"]
            ),
        )
        if gross
        else 0
    )
    full_credit = min(credit_full_limit(rules, gross)["limit"], dsr_credit)
    if credit_before:
        full_credit = min(
            full_credit,
            max(
                0,
                floor_to(
                    (
                        income * s.dsr_limit
                        - s.existing_debt_annual
                        - preliminary * factor
                        - (sub * (sub_rate + s.stress_rate) if sub_before else 0)
                    )
                    / credit_factor,
                    calc["credit_round_unit"],
                ),
            ),
        )
    credit = (
        (
            full_credit
            if s.credit_amount_mode == "자동"
            else s.credit_amount
            if s.credit_amount_mode == "직접"
            else s.credit_amount or full_credit
        )
        if s.credit_use
        else 0
    )
    caps = {
        "사용자 상한": s.mortgage_cap,
        "LTV": floor_to(
            (listing.appraisal if listing.appraisal is not None else listing.price) * s.ltv, 1
        ),
    }
    caps["가격대 상한"] = int(
        max(
            (b for b in r["mortgage_amount_cap_capital_area"] if listing.price > b["price_over"]),
            key=lambda b: b["price_over"],
            default={"cap": 0},
        )["cap"]
    )
    other = (
        s.existing_debt_annual
        + (credit * credit_factor if credit_before else 0)
        + (sub * (sub_rate + s.stress_rate) if sub_before else 0)
    )
    estimate = max(0, floor_to((income * s.dsr_limit - other) / factor, 1)) if income else 0
    caps["은행 확인" if s.bank_confirmed_limit else "DSR 추정"] = s.bank_confirmed_limit or estimate
    limit = min(caps.values())
    desired = s.mortgage_desired
    if s.mortgage_mode == "월 상환 한도 역산":
        first_factor = (
            pmt(1, s.mortgage_rate, s.mortgage_years * 12)
            if s.mortgage_method == "원리금균등"
            else Decimal(1) / (s.mortgage_years * 12) + s.mortgage_rate / 12
        )
        desired = floor_to(dec(s.monthly_repay_limit) / first_factor, s.mortgage_round_unit)
    mortgage = min(desired, limit)
    return {
        "mortgage": mortgage,
        "desired": desired,
        "mortgage_limit": limit,
        "caps": caps,
        "dsr_estimate_limit": estimate,
        "credit": credit,
        "credit_limit": full_credit,
        "sub": sub,
        "sub_limit": sub_limit,
        "sub_rate": sub_rate,
        "credit_factor": credit_factor,
        "mortgage_factor": factor,
        "other_review_annual": other,
    }
