"""근거 숫자와 사유를 반환하는 판정·평가."""

from datetime import date
from typing import Any

from .dates import add_months, month_day
from .dsr import dsr_metrics
from .ledger import build_ledger, is_confirmed
from .loans import loan_amounts
from .models import Check, Household, Listing, Result
from .money import korean_money, won
from .rules import RuleBook, acquisition_taxes, brokerage_fee, registration_costs


def calculate_costs(
    h: Household, listing: Listing, loans: dict[str, Any], rules: RuleBook
) -> dict[str, Any]:
    s = h.settings
    taxes = acquisition_taxes(
        rules,
        listing.price,
        listing.area_m2,
        s.first_home_tax_relief,
        h.day("closing_date"),
        s.manual_tax_rate,
    )
    if listing.acquisition_tax_amount is not None:
        taxes = {"total": listing.acquisition_tax_amount, "manual_total": True, "calculated": taxes}
    brokerage = brokerage_fee(rules, listing.price, s.brokerage_rate, listing.brokerage_amount)
    registration = registration_costs(rules, listing.price, loans["mortgage"], **s.model_dump())
    move = (
        (listing.repair if listing.repair is not None else s.repair_default)
        + s.appliances
        + s.moving
        + s.cleaning
        + s.temp_housing
    )
    total = taxes["total"] + brokerage + registration["total"]
    return {
        "taxes": taxes,
        "brokerage": brokerage,
        "registration": registration,
        "acquisition_taxes_total": taxes["total"],
        "closing_costs_total": total,
        "cash_closing_fees": total - (taxes["total"] if s.card_pay_tax else 0),
        "move_in_costs": move,
    }


def evaluate(
    household: Household,
    listing: str | Listing | None,
    rules: RuleBook,
    overrides: dict[str, Any] | None = None,
    *,
    confirmed_only: bool = False,
    analyze_assumptions: bool = True,
    as_of: date | None = None,
) -> Result:
    h = household.resolved(overrides, as_of=as_of)
    s = h.settings
    item = listing.model_copy(deep=True) if isinstance(listing, Listing) else h.listing(listing)
    loan_household = h
    if confirmed_only:
        loan_household = h.model_copy(deep=True)
        for prefix in ("credit", "sub"):
            if h.day(f"{prefix}_draw_date") > h.day("asset_base_date") and not is_confirmed(
                getattr(s, f"{prefix}_status")
            ):
                setattr(
                    loan_household.settings,
                    "credit_use" if prefix == "credit" else "sub_loan_use",
                    False,
                )
    loans = loan_amounts(loan_household, item, rules)
    costs = calculate_costs(h, item, loans, rules)
    book = build_ledger(h, item, loans, costs, rules, confirmed_only)
    all_entries = book["entries"]
    if s.start_today and as_of is not None:
        if as_of > book["end"]:
            raise ValueError("오늘이 계획 기간 이후입니다. 매수 일정과 보유 자금을 갱신해 주세요")
        for key in ("daily", "post_days", "leave_days"):
            book[key] = [row for row in book[key] if row.date >= as_of]
        book["entries"] = [row for row in book["entries"] if row.date >= as_of]
        if not book["post_days"]:
            book["post_days"] = book["daily"][:1]
    entries, daily = book["entries"], book["daily"]
    minimum = min(daily, key=lambda d: d.minimum)
    closing = h.day("closing_date")
    contract = h.day("contract_date")
    purchase_end = month_day(max(closing, h.day("move_in_date")), 31)
    after = min(book["post_days"], key=lambda d: d.minimum)
    leave = min(book["leave_days"], key=lambda d: d.minimum) if book["leave_days"] else None
    loan_first = book["mortgage_payments"][0].total if book["mortgage_payments"] else 0

    def available(day: date) -> int:
        return int(
            book["opening"]
            + sum(
                e.amount
                for e in all_entries
                if e.category not in {"purchase", "purchase_cost", "move_in", "mortgage_draw"}
                and (e.date < day or (e.date == day and (s.same_day_inflow_usable or e.amount < 0)))
            )
        )

    contract_cash = available(contract)
    interim_cash = available(h.day("interim_date")) if s.interim_amount else 0
    closing_cash = available(closing)
    deposit = won(item.price * s.deposit_ratio)
    closing_needed = item.price + costs["cash_closing_fees"] - loans["mortgage"]
    checks: list[Check] = []

    def money_check(name: str, actual: int, required: int, day: date | None = None) -> None:
        ok = actual >= required
        short = max(0, required - actual)
        checks.append(
            Check(
                name=name,
                ok=ok,
                reason=f"{day.isoformat() + ' ' if day else ''}{name}: {korean_money(actual)} {'≥' if ok else '<'} {korean_money(required)}"
                + (f" → {korean_money(short)} 부족" if short else ""),
                numbers={"actual": actual, "required": required, "shortfall": short, "date": day},
            )
        )

    checks.append(
        Check(
            name="입력",
            ok=not book["missing"],
            reason="입력 완료"
            if not book["missing"]
            else f"입력 필요: {', '.join(book['missing'])}",
        )
    )
    money_check("계약금", contract_cash, deposit, contract)
    money_check(
        "중도금",
        interim_cash - deposit if s.interim_amount else 0,
        s.interim_amount,
        h.day("interim_date") if s.interim_amount else None,
    )
    money_check("잔금", closing_cash, closing_needed, closing)
    money_check("현금 잔고", minimum.minimum, 0, minimum.date)
    money_check("매수 직후", after.minimum, s.target_cash_after_purchase, after.date)
    money_check("최소 비상금", minimum.minimum, s.min_emergency_cash, minimum.date)
    money_check("월 상환 한도", s.monthly_repay_limit, loan_first)
    spend_start = max(
        h.day("move_in_date"), as_of if s.start_today and as_of else h.day("asset_base_date")
    )
    spend_items = [
        (key, value)
        for key, value in book["monthly_spend"].items()
        if key >= spend_start.strftime("%Y-%m")
    ]
    spend_month, max_spend = max(spend_items, key=lambda pair: pair[1], default=("", 0))
    money_check("월 가계지출 한도", s.monthly_spend_limit, max_spend)
    checks[-1].numbers["month"] = spend_month
    checks[-1].numbers["period_start"] = spend_start.strftime("%Y-%m")
    checks[-1].numbers["period_end"] = book["end"].strftime("%Y-%m")
    checks[-1].reason = f"{spend_month} · " + checks[-1].reason
    money_check("대출 한도", loans["mortgage_limit"], loans["mortgage"])
    money_check("신용대출 한도", loans["credit_limit"], loans["credit"])
    money_check("청약담보 한도", loans["sub_limit"], loans["sub"])
    permit_start = s.permit_date if isinstance(s.permit_date, date) else contract
    permit_limit = add_months(
        permit_start,
        rules["land_permit"].get(
            "closing_plan_within_months_after_permit",
            rules["land_permit"]["move_in_within_months_after_permit"],
        ),
    )
    deferral = item.tenant == "세안고매매" and s.tenant_deferral_confirmed
    permit_ok = not s.land_permit_required or deferral or closing <= permit_limit
    checks.append(
        Check(
            name="토허 4개월",
            ok=permit_ok,
            reason=f"{'허가일' if s.permit_date else '계약일 대용(잠정)'} 기준 잔금기한 {permit_limit}, 예정 잔금 {closing} (자금계획 기준)"
            + (" / 유예 확인 반영" if deferral else ""),
            numbers={
                "deadline": permit_limit,
                "closing": closing,
                "comparison_date": "closing_date",
                "move_in": h.day("move_in_date"),
                "provisional": s.permit_date is None,
            },
        )
    )
    move_deadline = add_months(closing, rules["land_permit"]["mortgage_move_in_months"])
    if deferral and isinstance(s.lease_end_date, date):
        move_deadline = add_months(s.lease_end_date, 1)
    move_ok = not loans["mortgage"] or h.day("move_in_date") <= move_deadline
    checks.append(
        Check(
            name="전입 6개월",
            ok=move_ok,
            reason=f"전입기한 {move_deadline}, 계획 {h.day('move_in_date')}",
            numbers={"deadline": move_deadline},
        )
    )
    metrics = dsr_metrics(h, loans)
    warnings = ["지급일·휴직 상태·일할이자 규칙은 DECISIONS의 잠정 가정입니다."]
    warnings.extend((h.model_extra or {}).get("_import_warnings", []))
    if s.land_permit_required and s.permit_date is None:
        warnings.append(
            "토지거래허가일 미입력: 계약일을 대용한 잠정 일정 점검입니다. 구청 확인 필요."
        )
    if s.land_permit_required and not deferral and closing <= permit_limit < h.day("move_in_date"):
        warnings.append(
            "토허 잔금 일정은 기한 내입니다. 수리 후 입주일은 별도이며, 실거주 이행과 수리 기간은 허가조건을 확인하세요."
        )
    if loans["desired"] > loans["mortgage"]:
        warnings.append(
            f"주담대 희망 {loans['desired']:,}원 → {loans['mortgage']:,}원으로 한도 제한: {loans['caps']}"
        )
    if (
        isinstance(item.move_in_available, (date, str))
        and str(item.move_in_available) > h.day("move_in_date").isoformat()
    ):
        warnings.append(
            "계획 입주일이 매물의 미확인 입주 가능일보다 빠릅니다. 매도인과 재확인하세요."
        )
    selected_id = s.mortgage_quote_option.get(s.mortgage_method)
    selected_quote: dict[str, Any] | None = None
    for q in h.bank_quotes:
        for option in q.options:
            if option.id == selected_id:
                selected_quote = {
                    "bank": q.bank,
                    "date": q.date,
                    "option": option.model_dump(),
                    "basis": q.basis,
                    "age_days": ((as_of or h.day("asset_base_date")) - q.date).days,
                }
                if option.rate_type != s.mortgage_rate_type:
                    warnings.append(
                        f"은행 상품 금리유형 '{option.rate_type}'과 설정 '{s.mortgage_rate_type}' 불일치: 스트레스 가산 재확인 필요."
                    )
    rule_assumptions = [
        {
            "id": f"rule:{key}",
            "status": rule["meta"]["status"],
            "source": rule["meta"].get("source"),
            "checked_at": rule["meta"]["checked_at"],
        }
        for key, rule in rules.data.items()
        if rule["meta"]["status"] != "확인 완료"
    ]
    failed = {c.name for c in checks if not c.ok}
    if "입력" in failed:
        status = "입력 미완료"
    elif failed & {"계약금", "중도금", "잔금", "현금 잔고"}:
        status = "현금 부족"
    elif failed & {"토허 4개월", "전입 6개월"}:
        status = "일정 조건 위반"
    elif failed & {"월 상환 한도", "월 가계지출 한도"}:
        status = "월 지출 초과"
    elif failed & {"최소 비상금", "매수 직후"}:
        status = "비상금 부족"
    elif failed or s.loan_status != "승인 완료" or item.appraisal is None or book["assumptions"]:
        status = "대출 확인 필요"
    else:
        status = "입력 조건 충족"
    kpis = {
        "calculation_start_date": daily[0].date,
        "asset_base_date": h.day("asset_base_date"),
        "opening_cash": daily[0].opening,
        "variable_asset_mode": s.variable_asset_mode,
        "purchase_price": item.price,
        "mortgage_amount": loans["mortgage"],
        "mortgage_first_payment": loan_first,
        "mortgage_max_payment": max((p.total for p in book["mortgage_payments"]), default=0),
        "credit_loan_amount": loans["credit"],
        "subscription_loan_amount": loans["sub"],
        "contract_cash_available": contract_cash,
        "interim_cash_available_before_deposit": interim_cash,
        "interim_shortfall": max(0, s.interim_amount - (interim_cash - deposit))
        if s.interim_amount
        else 0,
        "closing_cash_available": closing_cash,
        "closing_shortfall": max(0, closing_needed - closing_cash),
        "after_purchase_cash": after.minimum,
        "after_purchase_date": after.date,
        "min_balance_overall": minimum.minimum,
        "min_balance_date": minimum.date,
        "min_balance_during_leave": leave.minimum if leave else None,
        "min_balance_during_leave_date": leave.date if leave else None,
        "month_end_balance": {
            month: value
            for month, value in book["month_end"].items()
            if month >= daily[0].date.strftime("%Y-%m")
        },
        "month_end_min_balance": min(
            value
            for month, value in book["month_end"].items()
            if month >= daily[0].date.strftime("%Y-%m")
        ),
        "month_end_leave_min": min(
            (d.closing for d in book["leave_days"] if month_day(d.date, 31) == d.date), default=None
        ),
        "month_end_after_purchase": book["month_end"][purchase_end.strftime("%Y-%m")],
        "max_monthly_spend": max_spend,
        "monthly_spend": {
            month: value
            for month, value in book["monthly_spend"].items()
            if month >= daily[0].date.strftime("%Y-%m")
        },
        "monthly_expense_breakdown": {
            month: value
            for month, value in book["expense_breakdown"].items()
            if month >= daily[0].date.strftime("%Y-%m")
        },
        "expense_mode": "기간별" if h.expense_items is not None else "기존 입력",
        **metrics,
    }
    assumptions = book["assumptions"]
    if analyze_assumptions and not confirmed_only:
        for assumption in assumptions:
            variant = h.model_copy(deep=True)
            key = assumption["id"]
            if assumption["kind"] == "fund":
                for e in variant.fund_events:
                    if e.id == key:
                        e.status = "제외"
            elif assumption["kind"] == "support":
                for i, support in enumerate(variant.parent_support):
                    if (support.id or f"P{i + 1:02}") == key:
                        support.status = "제외"
            else:
                setattr(
                    variant.settings, "credit_use" if key == "credit" else "sub_loan_use", False
                )
            alternative = evaluate(variant, item, rules, analyze_assumptions=False, as_of=as_of)
            changed = [
                c.name
                for c, other in zip(checks, alternative.checks, strict=True)
                if c.ok != other.ok
            ]
            affected = [
                {
                    "name": c.name,
                    "before_ok": c.ok,
                    "after_ok": other.ok,
                    "before": c.numbers,
                    "after": other.numbers,
                }
                for c, other in zip(checks, alternative.checks, strict=True)
                if c.numbers != other.numbers or c.ok != other.ok
            ]
            assumption["without"] = {
                "status": alternative.status,
                "changed_checks": changed,
                "affected_checks": affected,
                "interim_shortfall": alternative.kpis["interim_shortfall"],
                "closing_shortfall": alternative.kpis["closing_shortfall"],
                "closing_cash_delta": alternative.kpis["closing_cash_available"] - closing_cash,
                "min_balance_delta": alternative.kpis["min_balance_overall"] - minimum.minimum,
            }
            for check in checks:
                if check.name in {row["name"] for row in affected}:
                    check.assumptions.append(key)
    loan_summary = {
        **loans,
        "selected_quote": selected_quote,
        "mortgage_schedule": [p.model_dump() for p in book["mortgage_payments"]],
        "credit_schedule": [p.model_dump() for p in book["other_schedules"]["credit"]],
        "subscription_schedule": [p.model_dump() for p in book["other_schedules"]["sub"]],
    }
    repayment_details = {}
    for key, schedule in {
        "mortgage": book["mortgage_payments"],
        "credit": book["other_schedules"]["credit"],
        "sub": book["other_schedules"]["sub"],
    }.items():
        rows = [{**p.model_dump(), "fee": 0, "kind": "정기 납부"} for p in schedule] + [
            {"date": day, "principal": principal, "interest": 0, "fee": fee, "kind": "추가 상환"}
            for day, principal, fee in book["prepayment_schedules"][key]
        ]
        rows.sort(key=lambda row: (row["date"], row["kind"] == "추가 상환"))
        balance = loans[key]
        for row in rows:
            balance -= row["principal"]
            row["balance"] = balance
            row["total"] = row["principal"] + row["interest"] + row["fee"]
        repayment_details[key] = rows
    loan_summary["repayment_details"] = repayment_details
    return Result(
        status=status,
        checks=checks,
        kpis=kpis,
        costs=costs,
        loans=loan_summary,
        ledger=entries,
        daily_balances=daily,
        assumptions=assumptions + rule_assumptions,
        warnings=warnings,
    )
