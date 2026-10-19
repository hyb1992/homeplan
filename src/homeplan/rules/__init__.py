"""제도 규칙을 입력으로 받는 순수 계산 함수."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ..money import dec, floor_to


@dataclass(frozen=True)
class RuleBook:
    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]


def acquisition_taxes(
    rules: RuleBook,
    price: int,
    area_m2: Any,
    first_home_relief: bool = False,
    closing_date: date | str | None = None,
    manual_rate: Any = 0,
) -> dict[str, Any]:
    r = rules["acquisition_tax"]
    band = r["rate"]
    low, high = band["lower_price"], band["upper_price"]
    rate = dec(band["lower_rate"] if price <= low else band["upper_rate"])
    if low < price <= high:
        rate = dec(band["lower_rate"]) + dec(price - low) / (high - low) * (
            dec(band["upper_rate"]) - dec(band["lower_rate"])
        )
        from decimal import ROUND_HALF_UP

        rate = rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if manual_rate:
        rate = dec(manual_rate)
    acquisition = floor_to(price * rate)
    education = floor_to(acquisition * dec(r["local_education_tax"]["ratio_of_acquisition_tax"]))
    rural = (
        floor_to(price * dec(r["rural_special_tax"]["rate"]))
        if dec(area_m2) > dec(r["rural_special_tax"]["applies_if_area_m2_over"])
        else 0
    )
    relief_rule = r["first_home_relief"]
    closing = date.fromisoformat(closing_date) if isinstance(closing_date, str) else closing_date
    eligible = (
        first_home_relief
        and price <= relief_rule["max_price"]
        and closing is not None
        and closing <= date.fromisoformat(str(relief_rule["until"]))
    )
    relief = min(acquisition, relief_rule["cap"]) if eligible else 0
    return {
        "rate": rate,
        "acquisition_tax": acquisition,
        "education_tax": education,
        "rural_tax": rural,
        "relief": relief,
        "total": acquisition + education + rural - relief,
    }


def brokerage_fee(
    rules: RuleBook, price: int, negotiated_rate: Any = 0, amount: int | None = None
) -> int:
    r = rules["brokerage"]
    bracket = max(
        (b for b in r["brackets"] if price >= b["price_from"]), key=lambda b: b["price_from"]
    )
    rate = (
        min(dec(bracket["rate"]), dec(negotiated_rate)) if negotiated_rate else dec(bracket["rate"])
    )
    before_vat = min(price * rate, dec(bracket["cap"])) if bracket["cap"] else price * rate
    upper = floor_to(before_vat * (1 + dec(r["vat_rate"])))
    return min(amount, upper) if amount is not None else upper


def registration_costs(rules: RuleBook, price: int, loan: int, **settings: Any) -> dict[str, int]:
    r = rules["registration"]
    bond = r["national_housing_bond"]
    burden = floor_to(
        dec(price)
        * dec(settings.get("official_price_ratio", bond["official_price_ratio_default"]))
        * dec(settings.get("bond_buy_rate", bond["buy_rate"]))
        * dec(settings.get("bond_discount_rate", bond["discount_rate_default"]))
    )
    brackets = r["stamp_tax"]["brackets"]

    def stamp(amount: int, kind: str) -> int:
        return int(
            max(
                (b for b in brackets if amount > b["amount_over"]),
                key=lambda b: b["amount_over"],
                default={kind: 0},
            )[kind]
        )

    out = {
        "lawyer": int(settings.get("lawyer_fee", r["defaults"]["lawyer_fee"])),
        "registry": int(settings.get("registry_fee", r["defaults"]["registry_fee"])),
        "bond_burden": burden,
        "stamp_loan_borrower": floor_to(
            stamp(loan, "loan")
            * dec(settings.get("loan_stamp_share", r["stamp_tax"]["loan_share_of_borrower"])),
            1,
        ),
        "stamp_sale_contract": stamp(price, "sale_contract"),
    }
    return {**out, "total": sum(out.values())}


def parental_benefit(
    rules: RuleBook, month: int, ordinary_wage: int, six_plus_six: bool = False
) -> int:
    r = rules["childcare"]["parental_leave_benefit"]
    if month < 1:
        return 0
    bracket = max(
        (b for b in r["brackets"] if month >= b["from_month"]), key=lambda b: b["from_month"]
    )
    if six_plus_six and month <= len(r["six_plus_six_caps"]):
        return int(min(ordinary_wage, r["six_plus_six_caps"][month - 1]))
    return int(max(bracket["floor"], min(bracket["cap"], ordinary_wage * dec(bracket["rate"]))))


def family_loan_interest_free_max(rules: RuleBook) -> int:
    r = rules["family_transfer"]["family_loan"]
    return floor_to(dec(r["deemed_gift_threshold_annual"]) / dec(r["adequate_interest_rate"]), 1)
