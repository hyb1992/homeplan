from datetime import date

import pytest
from pydantic import ValidationError

from homeplan.checks import evaluate
from homeplan.models import Household, PurchaseTracking
from homeplan.purchase_tracking import purchase_progress
from homeplan.repository import Repository
from homeplan.server import changes_between


def record():
    return {
        "property_name": "계약한 집 · 가상",
        "listing_id": "L01",
        "price": 500000000,
        "deposit_amount": 50000000,
        "interim_amount": 100000000,
        "contract_date": "2026-10-20",
        "milestones": [
            {
                "id": "contract",
                "name": "매매 계약",
                "status": "완료",
                "completed_date": "2026-10-20",
            },
            {"id": "closing", "name": "잔금", "planned_date": "2027-01-20"},
            {"id": "skip", "name": "해당 없는 수리", "status": "해당 없음"},
        ],
        "payments": [
            {"id": "p1", "category": "계약금", "amount": 10000000, "paid_date": "2026-10-20"},
            {"id": "p2", "category": "계약금", "amount": 40000000, "paid_date": "2026-10-22"},
            {"id": "p3", "category": "중개보수", "amount": 2000000, "paid_date": "2026-10-22"},
        ],
    }


def test_actuals_separate_fees_partial_payments_progress_and_remaining():
    value = PurchaseTracking.model_validate(record())
    summary = purchase_progress(value, date(2026, 10, 23))
    assert summary["price_paid"] == 50000000
    assert summary["expenses_paid"] == 2000000
    assert summary["total_paid"] == 52000000
    assert summary["remaining_price"] == 450000000
    assert summary["expected"]["잔금"] == 350000000
    assert summary["completed_steps"] == 1 and summary["total_steps"] == 2
    assert summary["progress_percent"] == 50 and summary["paid_percent"] == 10
    assert summary["next_step"]["id"] == "closing"


def test_future_records_and_overpayment_are_visible_without_negative_remainder():
    value = record()
    value["payments"].append(
        {"id": "future", "category": "잔금", "amount": 600000000, "paid_date": "2027-01-20"}
    )
    tracking = PurchaseTracking.model_validate(value)
    before = purchase_progress(tracking, date(2026, 10, 23))
    assert before["future_payments"] == 1 and before["price_paid"] == 50000000
    after = purchase_progress(tracking, date(2027, 1, 20))
    assert after["remaining_price"] == 0 and after["overpaid_price"] == 150000000
    assert after["paid_percent"] == 100
    assert purchase_progress(None, date(2026, 10, 23)) is None


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v.update(price=0),
        lambda v: v.update(deposit_amount=500000001),
        lambda v: v["payments"][0].update(amount=-1),
        lambda v: v["payments"][0].update(amount=0),
        lambda v: v["payments"][0].update(paid_date="잔금일"),
        lambda v: v["payments"][0].update(paid_date="2026-02-30"),
        lambda v: v["payments"].append(v["payments"][0]),
        lambda v: v["milestones"].append(v["milestones"][0]),
        lambda v: v["milestones"][0].update(completed_date=None),
        lambda v: v.update(property_name=" "),
    ],
)
def test_invalid_actual_records_are_rejected(change):
    value = record()
    change(value)
    with pytest.raises(ValidationError):
        PurchaseTracking.model_validate(value)


def test_tracking_does_not_change_forecast_cash_debt_or_kpis(household, rules):
    before = evaluate(household, None, rules, as_of=date(2026, 10, 23))
    raw = household.model_dump(mode="json")
    raw["purchase_tracking"] = record()
    after = evaluate(Household.model_validate(raw), None, rules, as_of=date(2026, 10, 23))
    assert before.ledger == after.ledger and before.daily_balances == after.daily_balances
    assert (
        before.kpis == after.kpis and before.loans == after.loans and before.checks == after.checks
    )
    assert after.purchase_progress["total_paid"] == 52000000


def test_existing_data_stays_empty_and_tracking_survives_history_restore(tmp_path, household):
    repo = Repository(tmp_path / "data/test.sqlite")
    raw = household.model_dump(mode="json")
    raw.pop("purchase_tracking", None)
    repo.seed("actual", "Synthetic", raw)
    base = repo.get("actual")
    assert base["household"]["purchase_tracking"] is None
    raw["purchase_tracking"] = record()
    saved = repo.save("actual", raw, 0)
    assert saved["household"]["purchase_tracking"]["payments"][0]["amount"] == 10000000
    changes = changes_between(base["household"], saved["household"])
    assert any(row["kind"] == "purchase_tracking" for row in changes)
    restored = repo.save("actual", repo.version("actual", 0), 1)
    assert restored["household"]["purchase_tracking"] is None
    assert len(repo.history("actual")) == 3
    assert repo.version("actual", 1)["purchase_tracking"]["payments"][2]["category"] == "중개보수"
