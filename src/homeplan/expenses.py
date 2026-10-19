"""기간별 월 지출. 날짜는 이미 해석된 입력을 사용한다."""

from datetime import date

from .dates import month_day
from .models import ExpenseItem
from .money import dec, won


def monthly_bill(item: ExpenseItem, month: date, default_day: int) -> tuple[date, int] | None:
    if not item.enabled:
        return None
    first, last = month.replace(day=1), month_day(month, 31)
    start = max(first, item.start_date) if isinstance(item.start_date, date) else first
    end = min(last, item.end_date) if isinstance(item.end_date, date) else last
    if start > end:
        return None
    payment_day = min(max(month_day(month, item.pay_day or default_day), start), end)
    amount = (
        won(dec(item.amount) * ((end - start).days + 1) / last.day) if item.prorate else item.amount
    )
    return payment_day, amount
