"""Actual purchase records are informational; they never add cash-ledger entries."""

from datetime import date
from typing import Any

from .models import PurchaseTracking

PRICE_CATEGORIES = ("계약금", "중도금", "잔금")


def purchase_progress(tracking: PurchaseTracking | None, as_of: date) -> dict[str, Any] | None:
    if tracking is None:
        return None
    paid = [row for row in tracking.payments if row.paid_date <= as_of]
    categories = {
        category: sum(row.amount for row in paid if row.category == category)
        for category in (
            "계약금",
            "중도금",
            "잔금",
            "취득세",
            "중개보수",
            "법무·등기",
            "수리",
            "이사",
            "기타",
        )
    }
    price_paid = sum(categories[key] for key in PRICE_CATEGORIES)
    expenses_paid = sum(row.amount for row in paid) - price_paid
    milestones = [row for row in tracking.milestones if row.status != "해당 없음"]
    done = sum(row.status == "완료" for row in milestones)
    upcoming = sorted(
        (row for row in milestones if row.status != "완료"),
        key=lambda row: (row.planned_date is None, row.planned_date or date.max),
    )
    expected = {
        "계약금": tracking.deposit_amount,
        "중도금": tracking.interim_amount,
        "잔금": tracking.price - tracking.deposit_amount - tracking.interim_amount,
    }
    return {
        "as_of": as_of.isoformat(),
        "total_paid": price_paid + expenses_paid,
        "price_paid": price_paid,
        "expenses_paid": expenses_paid,
        "remaining_price": max(0, tracking.price - price_paid),
        "overpaid_price": max(0, price_paid - tracking.price),
        "paid_percent": min(100, price_paid * 100 // tracking.price),
        "completed_steps": done,
        "total_steps": len(milestones),
        "progress_percent": done * 100 // len(milestones) if milestones else 0,
        "next_step": upcoming[0].model_dump(mode="json") if upcoming else None,
        "current_steps": [row.name for row in milestones if row.status == "진행 중"],
        "categories": categories,
        "expected": expected,
        "future_payments": sum(row.paid_date > as_of for row in tracking.payments),
    }
