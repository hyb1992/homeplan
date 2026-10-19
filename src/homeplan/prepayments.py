"""명시적인 추가 상환 이후의 상환표. 날짜와 원금 흐름을 분리한다."""

from datetime import date
from decimal import Decimal

from .loans import Payment, pmt
from .models import LoanPrepayment
from .money import won


def with_prepayments(
    schedule: list[Payment],
    amount: int,
    draw: date,
    rate: Decimal,
    events: list[LoanPrepayment],
    method: str = "원리금균등",
    reset_after: int = 0,
    reset_rate: Decimal = Decimal(0),
) -> tuple[list[Payment], list[tuple[date, int, int]]]:
    events = [e for e in events if e.enabled]
    if not events or not amount:
        return schedule, []
    if any(not isinstance(e.date, date) or e.date < draw for e in events):
        raise ValueError("추가 상환일은 대출 실행일 이후여야 합니다")
    if any(isinstance(e.date, date) and schedule and e.date > schedule[-1].date for e in events):
        raise ValueError("대출 만기 이후에는 추가 상환할 수 없습니다")
    timeline: list[tuple[date, int, int]] = [(row.date, 0, i) for i, row in enumerate(schedule)]
    timeline += [(e.date, 1, i) for i, e in enumerate(events) if isinstance(e.date, date)]
    timeline.sort()
    balance, changed = amount, False
    installment: int | None = None
    fixed_principal: int | None = None
    result: list[Payment] = []
    payments: list[tuple[date, int, int]] = []
    current_mode = "납입 감소"
    for day, kind, index in timeline:
        if kind:
            event = events[index]
            if event.amount > balance:
                raise ValueError("추가 상환금이 남은 대출 원금보다 큽니다")
            balance -= event.amount
            payments.append((day, event.amount, event.fee))
            future = [(i, row) for i, row in enumerate(schedule) if row.date > day]
            current_mode = event.method
            if future and method != "만기일시":
                next_index, next_row = future[0]
                active_rate = reset_rate if reset_after and next_index >= reset_after else rate
                if event.method == "납입 감소":
                    installment = won(pmt(balance, active_rate, len(future)))
                    fixed_principal = won(Decimal(balance) / len(future))
                elif installment is None:
                    installment, fixed_principal = next_row.total, next_row.principal
            changed = True
            continue
        row = schedule[index]
        if not balance:
            continue
        if not changed:
            balance = row.balance
            result.append(row)
            continue
        active_rate = reset_rate if reset_after and index >= reset_after else rate
        if reset_after and index == reset_after and current_mode == "납입 감소":
            installment = won(pmt(balance, active_rate, len(schedule) - index))
        interest = won(balance * active_rate / 12)
        if method == "만기일시":
            principal = balance if row.principal else 0
        elif method == "원금균등":
            principal = min(balance, fixed_principal or 0)
        else:
            principal = min(balance, max(0, (installment or row.total) - interest))
        if index == len(schedule) - 1:
            principal = balance
        balance -= principal
        result.append(Payment(date=day, principal=principal, interest=interest, balance=balance))
    return result, payments
