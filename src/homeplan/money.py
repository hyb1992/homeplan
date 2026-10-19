"""금액은 원, 비율 계산은 Decimal, 반올림은 HALF_UP."""

import re
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def won(value: Any) -> int:
    return int(dec(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def floor_to(value: Any, unit: int = 10) -> int:
    return int((dec(value) / unit).to_integral_value(rounding=ROUND_FLOOR)) * unit


def parse_money(value: str | int) -> int:
    if isinstance(value, int):
        if value < 0:
            raise ValueError("금액은 0 이상이어야 합니다")
        return value
    value = re.sub(r"[\s,원]", "", value)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        amount = dec(value)
    else:
        units = {
            "조": 10**12,
            "억": 10**8,
            "천만": 10**7,
            "백만": 10**6,
            "십만": 10**5,
            "만": 10**4,
            "천": 1000,
            "백": 100,
            "십": 10,
        }
        tokens = list(re.finditer(r"(\d+(?:\.\d+)?)(천만|백만|십만|조|억|만|천|백|십)?", value))
        if not tokens or "".join(t.group() for t in tokens) != value:
            raise ValueError("금액은 3600만, 1억 2천만, 1.2억 또는 원 단위 숫자로 입력하세요")
        amount = sum((dec(t[1]) * units.get(t[2], 1) for t in tokens), Decimal(0))
    if amount != amount.to_integral_value() or amount < 0:
        raise ValueError("금액은 0 이상의 정수 원이어야 합니다")
    return int(amount)


def korean_money(amount: int) -> str:
    sign = "−" if amount < 0 else ""
    n = abs(amount)
    if n < 10000:
        return f"{sign}{n:,}원"
    eok, man = divmod(n // 10000, 10000)
    return (sign + (f"{eok:,}억 " if eok else "") + (f"{man:,}만" if man else "")).strip()
