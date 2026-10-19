"""모든 현금 이동과 일별 장중 최저 잔고. core에는 I/O가 없다."""

from datetime import date, timedelta
from typing import Any

from .dates import add_months, month_day, month_diff
from .expenses import monthly_bill
from .loans import amortization, card_installments, interest_only
from .models import DailyBalance, ExpenseItem, Household, LedgerEntry, Listing
from .money import dec, won
from .prepayments import with_prepayments
from .rules import RuleBook, parental_benefit


def is_confirmed(status: str) -> bool:
    return status in {"확정", "확인 완료", "승인 완료"}


def is_opening(type_name: str, when: date | None, base: date) -> bool:
    return type_name in {"현금·예금", "투자자산", "적금·청년도약계좌"} and (
        when is None or when <= base
    )


def return_month(h: Household) -> date | None:
    start = h.settings.wife_leave_start
    if not isinstance(start, date):
        return None
    return add_months(
        start.replace(day=1), h.settings.wife_leave_months + h.settings.return_delay_months
    )


def build_ledger(
    h: Household,
    listing: Listing,
    loans: dict[str, Any],
    costs: dict[str, Any],
    rules: RuleBook,
    confirmed_only: bool = False,
) -> dict[str, Any]:
    s = h.settings
    base, closing, move = h.day("asset_base_date"), h.day("closing_date"), h.day("move_in_date")
    returned = return_month(h)
    end = max(add_months(move, 36), add_months(returned, 12) if returned else add_months(move, 36))
    end = month_day(end, 31)
    entries: list[LedgerEntry] = []
    opening = 0
    assumptions: list[dict[str, Any]] = []
    missing: list[str] = []
    if s.annual_cost and not s.fixed_in_living and not s.annual_cost_month:
        missing.append("연 비용 납부월 (1~12월)")
    # 원금 흐름은 현금 원장과 별도다. 실행금 이중 가산·이자 원금 차감을 막는다.
    debt_moves: list[tuple[date, str, int]] = []

    def debt(day: date, label: str, principal: int) -> None:
        if principal and day <= end:
            debt_moves.append((day, label, principal))

    def add(day: date, amount: int, category: str, label: str, source: str) -> None:
        if base < day <= end and amount:
            entries.append(
                LedgerEntry(date=day, amount=amount, category=category, label=label, source=source)
            )

    for e in h.fund_events:
        if not e.active:
            continue
        if e.value is None and e.cash_out_amount is None:
            missing.append(e.id)
            continue
        when = e.available_date if isinstance(e.available_date, date) else None
        if "부채" in e.type:
            principal = e.cash_out_amount if e.cash_out_amount is not None else (e.value or 0)
            label = f"{e.name} ({e.id})"
            debt(date.min, label, principal)
            if when is not None:
                debt(when, label, -principal)
        if is_opening(e.type, when, base):
            opening += e.amount
            continue
        if e.type == "퇴직 관련 수령금" and not is_confirmed(e.status):
            continue
        if when is None:
            missing.append(f"{e.id}: 날짜")
            continue
        if when > base and (e.amount > 0 or e.is_variable) and not is_confirmed(e.status):
            assumptions.append(
                {
                    "id": e.id,
                    "label": e.name,
                    "date": when,
                    "amount": e.amount,
                    "status": e.status,
                    "kind": "fund",
                }
            )
            if confirmed_only:
                continue
        add(when, e.amount, "fund", e.name, e.id)
    for i, support in enumerate(h.parent_support):
        if support.status == "제외":
            continue
        key = support.id or f"P{i + 1:02}"
        if support.amount is None or not isinstance(support.date, date):
            missing.append(key)
            continue
        if not is_confirmed(support.status) and support.date > base:
            assumptions.append(
                {
                    "id": key,
                    "label": f"부모님 {support.kind}",
                    "date": support.date,
                    "amount": support.amount,
                    "status": support.status,
                    "kind": "support",
                }
            )
            if confirmed_only:
                continue
        add(support.date, support.amount, "support", f"부모님 {support.kind}", key)

    mortgage_payments = amortization(
        loans["mortgage"],
        s.mortgage_rate,
        s.mortgage_years * 12,
        closing,
        s.mortgage_method,
        s.mortgage_reset_after_months,
        s.mortgage_reset_rate,
        s.first_interest_adjustment,
    )
    mortgage_payments, extra_mortgage = with_prepayments(
        mortgage_payments,
        loans["mortgage"],
        closing,
        s.mortgage_rate,
        [e for e in h.loan_prepayments if e.loan == "mortgage"],
        s.mortgage_method,
        s.mortgage_reset_after_months,
        s.mortgage_reset_rate,
    )
    for day, principal, fee in extra_mortgage:
        add(day, -principal, "prepayment", "주담대 추가 상환", "mortgage")
        add(day, -fee, "prepayment_fee", "주담대 추가 상환 수수료", "mortgage")
        debt(day, "주택담보대출", -principal)
    add(closing, loans["mortgage"], "mortgage_draw", "주택담보대출 실행", "mortgage")
    debt(closing, "주택담보대출", loans["mortgage"])
    for row in mortgage_payments:
        add(row.date, -row.total, "mortgage_payment", "주담대 원리금", "mortgage")
        debt(row.date, "주택담보대출", -row.principal)

    other_schedules: dict[str, Any] = {}
    prepayment_schedules = {"mortgage": extra_mortgage}
    for prefix, key, rate, label in [
        ("credit", "credit", s.credit_rate, "신용대출"),
        ("sub", "sub", loans["sub_rate"], "청약담보대출"),
    ]:
        amount = loans[key]
        draw = h.day(f"{prefix}_draw_date")
        repay = getattr(s, f"{prefix}_repay_date")
        repay = repay if isinstance(repay, date) else None
        if amount and not is_confirmed(getattr(s, f"{prefix}_status")):
            assumptions.append(
                {
                    "id": key,
                    "label": f"{label} 은행 한도·실행",
                    "date": draw,
                    "amount": amount,
                    "status": getattr(s, f"{prefix}_status"),
                    "kind": "loan",
                }
            )
            if confirmed_only and draw > base:
                amount = 0
        add(draw, amount, "loan_draw", f"{label} 실행", key)
        debt(draw, label, amount)
        if prefix == "credit" and s.credit_method != "만기일시":
            schedule = amortization(
                amount, rate, rules["lending"]["calculation"]["credit_dsr_years"] * 12, draw
            )
            if repay:
                before = [row for row in schedule if row.date < repay]
                balance = before[-1].balance if before else amount
                schedule = before
                from .loans import Payment

                schedule.append(Payment(date=repay, principal=balance, interest=0, balance=0))
        else:
            schedule = interest_only(amount, rate, draw, end, repay) if amount else []
        schedule, extra = with_prepayments(
            schedule,
            amount,
            draw,
            rate,
            [e for e in h.loan_prepayments if e.loan == key],
            "원리금균등" if prefix == "credit" and s.credit_method != "만기일시" else "만기일시",
        )
        for day, principal, fee in extra:
            add(day, -principal, "prepayment", f"{label} 추가 상환", key)
            add(day, -fee, "prepayment_fee", f"{label} 추가 상환 수수료", key)
            debt(day, label, -principal)
        for row in schedule:
            add(row.date, -row.total, f"{key}_payment", f"{label} 납입", key)
            debt(row.date, label, -row.principal)
        other_schedules[key] = schedule
        prepayment_schedules[key] = extra

    deposit = won(listing.price * s.deposit_ratio)
    if deposit + s.interim_amount > listing.price:
        missing.append("계약금+중도금이 매매가 초과")
    add(h.day("contract_date"), -deposit, "purchase", "계약금", "purchase")
    if s.interim_amount:
        add(h.day("interim_date"), -s.interim_amount, "purchase", "중도금", "purchase")
    add(closing, -(listing.price - deposit - s.interim_amount), "purchase", "잔금", "purchase")
    add(closing, -costs["cash_closing_fees"], "purchase_cost", "세금·중개·등기", "costs")
    add(move, -costs["move_in_costs"], "move_in", "수리·이사·입주 비용", "move_in")
    if s.card_pay_tax:
        card_repay = h.day("credit_draw_date") if s.card_repay_on_credit_draw else None
        if card_repay is not None:
            if card_repay < closing:
                raise ValueError("취득세 카드 완납일이 잔금일보다 빠릅니다")
        debt(closing, "취득세 카드 할부", costs["acquisition_taxes_total"])
        card_principals = card_installments(costs["acquisition_taxes_total"], s.card_months)
        card_remaining = costs["acquisition_taxes_total"]
        for k, payment in enumerate(
            card_installments(
                costs["acquisition_taxes_total"],
                s.card_months,
                s.card_paid_installments,
                s.card_fee_rate,
            )
        ):
            payment_day = add_months(closing, s.card_first_offset + k)
            if card_repay is not None and payment_day >= card_repay:
                break
            card_remaining -= card_principals[k]
            debt(
                payment_day,
                "취득세 카드 할부",
                -card_principals[k],
            )
            add(
                payment_day,
                -payment,
                "card_payment",
                "취득세 카드 할부",
                "card",
            )
        if card_repay is not None and card_remaining:
            debt(card_repay, "취득세 카드 할부", -card_remaining)
            add(card_repay, -card_remaining, "card_payment", "취득세 카드 할부 완납", "card")

    lease_balance = sum(-e.amount for e in h.fund_events if e.active and "전세대출" in e.type)
    repay_day = h.day("lease_loan_repay_date")
    expense_day = s.expense_day or s.payday
    month = base.replace(day=1)
    family_draws: list[tuple[date, int]] = []
    for support in h.parent_support:
        if support.kind == "차입" and support.status != "제외" and isinstance(support.date, date):
            if not confirmed_only or is_confirmed(support.status) or support.date <= base:
                family_draws.append((support.date, support.amount or 0))
    for e in h.fund_events:
        if e.active and e.type == "가족 차입" and isinstance(e.available_date, date):
            if not confirmed_only or is_confirmed(e.status) or e.available_date <= base:
                principal = e.cash_out_amount if e.cash_out_amount is not None else (e.value or 0)
                family_draws.append((e.available_date, principal))
    family_draws.sort()
    for draw, principal in family_draws:
        debt(draw, "가족 차입", principal)
    family_payments: dict[str, tuple[date, int]] = {}
    if isinstance(s.family_loan_repay_start, date):
        balance, cursor, k = 0, 0, 0
        while (day := add_months(s.family_loan_repay_start, k)) <= end:
            while cursor < len(family_draws) and family_draws[cursor][0] <= day:
                balance += family_draws[cursor][1]
                cursor += 1
            principal = min(balance, s.family_loan_monthly_principal)
            payment = principal + won(balance * s.family_loan_rate / 12)
            balance -= principal
            debt(day, "가족 차입", -principal)
            family_payments[day.strftime("%Y-%m")] = (day, payment)
            k += 1
    spend: dict[str, int] = {}
    expense_breakdown: dict[str, dict[str, int]] = {}
    management = ExpenseItem(
        id="management",
        name="새집 관리비",
        amount=listing.mgmt_fee if listing.mgmt_fee is not None else s.mgmt_fee_default,
        start_date=s.management_start_date or move,
        end_date=s.management_end_date,
    )
    while month <= end:
        pay, expense = month_day(month, s.payday), month_day(month, expense_day)
        month_key = month.strftime("%Y-%m")
        monthly_spend = 0
        details: dict[str, int] = {}

        def record_spend(amount: int, label: str, breakdown: dict[str, int] = details) -> None:
            nonlocal monthly_spend
            monthly_spend += amount
            if amount:
                breakdown[label] = breakdown.get(label, 0) + amount

        for person in ("husband", "wife"):
            wage = getattr(s, f"{person}_net_pay")
            start = getattr(s, f"{person}_leave_start")
            months = getattr(s, f"{person}_leave_months") + (
                s.return_delay_months if person == "wife" else 0
            )
            leave_month = month_diff(month, start) if isinstance(start, date) else -1
            leave_active = 0 <= leave_month < months and (person == "wife" or s.husband_leave_use)
            maternity_month = (
                month_diff(month, s.maternity_start)
                if person == "wife" and isinstance(s.maternity_start, date)
                else -1
            )
            maternity_active = 0 <= maternity_month < s.maternity_months
            label = "남편" if person == "husband" else "아내"
            if maternity_active:
                maternity = s.maternity_pay_m12 if maternity_month < 2 else s.maternity_pay_m3
                add(pay, maternity, "income", "출산휴가 수령액", "maternity")
            elif leave_active:
                if leave_month < getattr(s, f"{person}_gov_benefit_months"):
                    amount = parental_benefit(
                        rules,
                        leave_month + 1,
                        getattr(s, f"{person}_ordinary_wage"),
                        s.parents_6p6 and s.husband_leave_use,
                    )
                    add(
                        add_months(pay, s.benefit_pay_delay_months),
                        amount,
                        "income",
                        f"{label} 육아휴직급여",
                        f"{person}_benefit",
                    )
                if leave_month < getattr(s, f"{person}_company_topup_months"):
                    add(
                        pay,
                        getattr(s, f"{person}_company_topup"),
                        "income",
                        f"{label} 회사 보전",
                        f"{person}_company",
                    )
            else:
                add(pay, wage, "income", f"{label} 급여", person)

        def expense_entry(
            amount: int,
            label: str,
            category: str = "living",
            when: date = expense,
            source: str | None = None,
        ) -> None:
            add(when, -amount, category, label, source or category)
            record_spend(amount, label)

        manual_bills = [
            (item, bill)
            for item in h.expense_items or []
            if (bill := monthly_bill(item, month, expense_day)) is not None
        ]
        if h.expense_items is None:
            expense_entry(s.living_cost, "생활비")
            if not s.fixed_in_living:
                expense_entry(s.fixed_cost, "고정비")
        else:
            for item, (when, amount) in manual_bills:
                expense_entry(amount, item.name, "expense", when, item.id)
        if not s.fixed_in_living:
            if month.month == s.annual_cost_month:
                add(expense, -s.annual_cost, "annual", "연 1회 비용", "annual")
            record_spend(won(dec(s.annual_cost) / 12), "연 1회 비용 · 월평균")
        management_included = (
            s.mgmt_in_living
            if h.expense_items is None
            else any(item.includes_management and amount > 0 for item, (_, amount) in manual_bills)
        )
        management_bill = monthly_bill(management, month, expense_day)
        if management_bill and not management_included:
            when, amount = management_bill
            expense_entry(amount, "관리비", when=when)
        lease_included = (
            s.lease_interest_in_living
            if h.expense_items is None
            else any(
                item.includes_lease_interest and amount > 0 for item, (_, amount) in manual_bills
            )
        )
        if month_diff(month, repay_day) <= 0 and not lease_included:
            expense_entry(
                won(lease_balance * s.lease_loan_rate / 12),
                "전세대출 이자",
                "lease_interest",
                min(expense, repay_day),
            )
        # 6월 1일 과세 기준은 연도 자격이다. 같은 해 매수 전 월의 예산은 제외한다.
        if closing <= date(month.year, 6, 1) and month >= closing.replace(day=1):
            if month.month in {s.property_tax_month1, s.property_tax_month2}:
                first = s.property_tax_annual // 2
                add(
                    expense,
                    -(
                        first
                        if month.month == s.property_tax_month1
                        else s.property_tax_annual - first
                    ),
                    "property_tax",
                    "보유세",
                    "property_tax",
                )
            record_spend(won(dec(s.property_tax_annual) / 12), "보유세 · 월평균")
        if not isinstance(s.saving_end_date, date) or expense <= s.saving_end_date:
            add(expense, -s.monthly_saving, "saving", "적금·투자 납입", "saving")
            if s.saving_in_spend_limit:
                record_spend(s.monthly_saving, "적금·투자 납입")
        if isinstance(s.birth_date, date):
            age = month_diff(month, s.birth_date)
            if age >= 0:
                if h.expense_items is None:
                    expense_entry(s.childcare_cost, "양육비", when=max(expense, s.birth_date))
                if age == 0:
                    add(s.birth_date, -s.birth_one_off, "birth", "출산 일회성 비용", "birth")
                for rule in rules["childcare"]["cash_support"]:
                    if rule["cash"] and rule["from_month"] <= age <= rule["to_month"]:
                        add(
                            max(pay, s.birth_date),
                            rule["monthly"],
                            "income",
                            rule["name"],
                            "child_support",
                        )
        if month_key in family_payments:
            family_day, payment = family_payments[month_key]
            expense_entry(payment, "가족 차입 상환", "family_payment", family_day)
        for row in mortgage_payments:
            if row.date.strftime("%Y-%m") == month_key:
                record_spend(row.total, "주담대 원리금")
        for schedule in other_schedules.values():
            for row in schedule:
                if row.date.strftime("%Y-%m") == month_key:
                    amount = row.interest + (
                        row.principal
                        if s.credit_method != "만기일시"
                        and schedule is other_schedules.get("credit")
                        else 0
                    )
                    record_spend(
                        amount,
                        "신용대출 상환"
                        if schedule is other_schedules.get("credit")
                        else "청약담보대출 상환",
                    )
        spend[month_key] = monthly_spend
        expense_breakdown[month_key] = details
        month = add_months(month, 1)

    # 같은 날 유입 사용 불가이면 모든 유출이 그날의 유입에 앞선다.
    entries.sort(
        key=lambda e: (e.date, (e.amount < 0) if s.same_day_inflow_usable else (e.amount >= 0))
    )
    daily: list[DailyBalance] = []
    debt_moves.sort(key=lambda row: row[0])
    debt_balances: dict[str, int] = {}
    debt_cursor = 0
    balance, i, day = opening, 0, base
    while day <= end:
        while debt_cursor < len(debt_moves) and debt_moves[debt_cursor][0] <= day:
            _, label, principal = debt_moves[debt_cursor]
            debt_balances[label] = debt_balances.get(label, 0) + principal
            debt_cursor += 1
        outstanding = {label: amount for label, amount in debt_balances.items() if amount > 0}
        total_debt = sum(outstanding.values())
        start_balance, minimum = balance, balance
        while i < len(entries) and entries[i].date == day:
            balance += entries[i].amount
            entries[i].balance = balance
            minimum = min(minimum, balance)
            i += 1
        daily.append(
            DailyBalance(
                date=day,
                opening=start_balance,
                closing=balance,
                minimum=minimum,
                debt_breakdown=outstanding,
                debt_total=total_debt,
                net_cash=balance - total_debt,
            )
        )
        day += timedelta(days=1)
    month_end = {
        d.date.strftime("%Y-%m"): d.closing for d in daily if month_day(d.date, 31) == d.date
    }
    leave_start = s.maternity_start if isinstance(s.maternity_start, date) else s.wife_leave_start
    leave_days = [
        d
        for d in daily
        if isinstance(leave_start, date) and returned and leave_start <= d.date < returned
    ]
    purchase_end = month_day(max(closing, move), 31)
    post_days = [d for d in daily if closing <= d.date <= purchase_end]
    return {
        "entries": entries,
        "daily": daily,
        "opening": opening,
        "end": end,
        "month_end": month_end,
        "leave_days": leave_days,
        "post_days": post_days,
        "monthly_spend": spend,
        "expense_breakdown": expense_breakdown,
        "mortgage_payments": mortgage_payments,
        "other_schedules": other_schedules,
        "prepayment_schedules": prepayment_schedules,
        "assumptions": assumptions,
        "missing": missing,
    }
