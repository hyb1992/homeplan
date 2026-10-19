"""고정 날짜와 상대 날짜. 입력 문법을 해석하며 수식 eval은 사용하지 않는다."""

import calendar
import re
from datetime import date, timedelta

type DateInput = date | str | None
ALIASES = {
    "기준일": "asset_base_date",
    "자산기준일": "asset_base_date",
    "계약일": "contract_date",
    "중도금일": "interim_date",
    "중도금지급일": "interim_date",
    "잔금일": "closing_date",
    "입주일": "move_in_date",
    "보증금반환일": "lease_refund_date",
    "퇴거일": "lease_refund_date",
    "전세대출상환일": "lease_loan_repay_date",
    "전세만기": "lease_end_date",
    "출산예정일": "birth_date",
}
DATE_KEYS = set(ALIASES.values()) | {
    "credit_draw_date",
    "credit_repay_date",
    "sub_draw_date",
    "sub_repay_date",
    "maternity_start",
    "wife_leave_start",
    "husband_leave_start",
    "family_loan_repay_start",
    "saving_end_date",
    "permit_date",
    "management_start_date",
    "management_end_date",
}


def add_months(value: date, months: int) -> date:
    year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
    return date(year, month + 1, min(value.day, calendar.monthrange(year, month + 1)[1]))


def month_day(value: date, day: int) -> date:
    return value.replace(day=min(day, calendar.monthrange(value.year, value.month)[1]))


def month_diff(value: date, start: date) -> int:
    return (value.year - start.year) * 12 + value.month - start.month


def resolve(
    value: DateInput,
    anchors: dict[str, DateInput],
    stack: tuple[str, ...] = (),
    *,
    as_of: date | None = None,
) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    value = value.replace(" ", "").removeprefix("=")
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    match = re.fullmatch(r"([\w]+)([+-]\d+)?(일|개월|months|days)?", value)
    if not match:
        raise ValueError(f"날짜 표현을 확인하세요: {value}")
    key = ALIASES.get(match[1], match[1])
    if key in {"지금", "오늘", "today"}:
        if as_of is not None:
            offset = int(match[2] or 0)
            return (
                add_months(as_of, offset)
                if match[3] in {"개월", "months"}
                else as_of + timedelta(days=offset)
            )
        # Context-free validation retains the historical base-date fallback.
        key = "asset_base_date"
    if key not in anchors:
        raise ValueError(f"알 수 없는 날짜 기준: {key}")
    if key in stack:
        raise ValueError(f"날짜 순환 참조: {' → '.join((*stack, key))}")
    base = resolve(anchors[key], anchors, (*stack, key), as_of=as_of)
    if base is None:
        raise ValueError(f"날짜 기준이 비어 있습니다: {key}")
    offset = int(match[2] or 0)
    return (
        add_months(base, offset)
        if match[3] in {"개월", "months"}
        else base + timedelta(days=offset)
    )


def parse_user_date(value: str, base: date) -> str:
    if re.fullmatch(r"\d{1,2}/\d{1,2}", value):
        month, day = map(int, value.split("/"))
        candidate = date(base.year, month, day)
        return candidate.replace(year=base.year + (candidate < base)).isoformat()
    return value
