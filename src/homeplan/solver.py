"""가격 구간별 탐색. 평가 함수와 같은 비상금·잔고 조건을 적용한다."""

from datetime import date
from typing import Any

from .checks import evaluate
from .models import Household, Listing, Result
from .rules import RuleBook

GATES = {"토허 4개월", "전입 6개월"}


def max_price(
    household: Household,
    listing: str | Listing | None,
    rules: RuleBook,
    overrides: dict[str, Any] | None = None,
    *,
    mode: str = "general",
    minimum: int = 100000,
    maximum: int = 3000000000,
    precision: int = 100000,
    confirmed_only: bool = False,
    as_of: date | None = None,
) -> dict[str, Any]:
    if mode not in {"general", "listing"}:
        raise ValueError("탐색 모드는 general / listing 중 하나입니다")
    if minimum < 0 or maximum < minimum or precision < 1:
        raise ValueError("탐색 범위와 정밀도를 확인하세요")
    h = household.resolved(overrides, as_of=as_of)
    item = listing.model_copy(deep=True) if isinstance(listing, Listing) else h.listing(listing)
    if mode == "general":
        item.repair, item.mgmt_fee, item.area_m2 = (
            h.settings.repair_default,
            h.settings.mgmt_fee_default,
            h.settings.comparison_area_m2,
        )
        item.appraisal = None
        item.brokerage_amount = None
        item.acquisition_tax_amount = None
    initial = evaluate(
        h, item, rules, analyze_assumptions=False, confirmed_only=confirmed_only, as_of=as_of
    )
    gate_failures = [c.model_dump() for c in initial.checks if c.name in GATES and not c.ok]
    cache: dict[int, Result] = {}

    def at(price: int) -> Result:
        if price not in cache:
            candidate = item.model_copy(update={"price": price}, deep=True)
            cache[price] = evaluate(
                h,
                candidate,
                rules,
                analyze_assumptions=False,
                confirmed_only=confirmed_only,
                as_of=as_of,
            )
        return cache[price]

    def passes(price: int) -> bool:
        return all(c.ok for c in at(price).checks if c.name not in GATES)

    first = ((minimum + precision - 1) // precision) * precision
    last = (maximum // precision) * precision
    # 요율 변화·감면 상실·금액 상한 변화의 양쪽을 개별 평가한다.
    boundaries = {b["price_from"] for b in rules["brokerage"]["brackets"]}
    boundaries |= {
        rules["acquisition_tax"]["rate"]["lower_price"],
        rules["acquisition_tax"]["rate"]["upper_price"],
        rules["acquisition_tax"]["first_home_relief"]["max_price"],
    }
    boundaries |= {b["price_over"] for b in rules["lending"]["mortgage_amount_cap_capital_area"]}
    points = {first, last}
    stride = max(precision, (10000000 // precision) * precision)
    points.update(range(first, last + 1, stride))
    for boundary in boundaries:
        aligned = (boundary // precision) * precision
        points.update(
            p for p in [aligned - precision, aligned, aligned + precision] if first <= p <= last
        )
    ordered = sorted(p for p in points if first <= p <= last)
    best: int | None = None
    states = [(p, passes(p)) for p in ordered]
    for p, ok in states:
        if ok:
            best = p if best is None else max(best, p)
    for (low, ok), (high, higher_ok) in zip(states, states[1:], strict=False):
        if ok and not higher_ok:
            while high - low > precision:
                middle = ((low + high) // (2 * precision)) * precision
                if passes(middle):
                    low = middle
                else:
                    high = middle
            best = low if best is None else max(best, low)
    priority = [
        "입력",
        "계약금",
        "중도금",
        "잔금",
        "현금 잔고",
        "최소 비상금",
        "매수 직후",
        "월 상환 한도",
        "월 가계지출 한도",
        "대출 한도",
        "신용대출 한도",
        "청약담보 한도",
    ]
    if best is not None and best < last:
        failed = {c.name for c in at(best + precision).checks if not c.ok and c.name not in GATES}
        binding = next((name for name in priority if name in failed), next(iter(failed), None))
    else:
        binding = "탐색 상한" if best == last else "조건 충족 가격 없음"
    result = {
        "price": None if gate_failures else best,
        "mode": mode,
        "binding_check": gate_failures[0]["name"] if gate_failures else binding,
        "gate_failures": gate_failures,
        "conditional_price": best,
        "conditional_binding_check": binding,
        "at_price_kpis": at(best).kpis if best is not None else None,
        "search": {
            "minimum": minimum,
            "maximum": maximum,
            "precision": precision,
            "evaluations": len(cache),
        },
        "conditional": bool(
            initial.assumptions or gate_failures or h.settings.loan_status != "승인 완료"
        ),
        "warnings": initial.warnings,
    }
    return result
