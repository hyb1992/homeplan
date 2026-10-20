from datetime import date

import pytest
from fastapi.testclient import TestClient

from homeplan.checks import evaluate
from homeplan.models import LoanPrepayment
from homeplan.server import changes_between, create_app


@pytest.fixture
def menu_client(tmp_path, household):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/demo.local.json").write_text(household.model_dump_json(), "utf-8")
    with TestClient(create_app(tmp_path / "qa.sqlite", seed_root=tmp_path)) as client:
        yield client


def test_repayment_details_conserve_principal_with_same_day_extra_payment(household, rules):
    initial = evaluate(household, None, rules, analyze_assumptions=False)
    day = initial.loans["mortgage_schedule"][0]["date"]
    household.loan_prepayments = [
        LoanPrepayment(
            id="EXTRA",
            loan="mortgage",
            date=day,
            amount=10000000,
            fee=1234,
        )
    ]
    result = evaluate(household, None, rules, analyze_assumptions=False)
    rows = result.loans["repayment_details"]["mortgage"]
    assert [r["kind"] for r in rows[:2]] == ["정기 납부", "추가 상환"]
    assert rows[1]["total"] == 10001234
    assert rows[1]["balance"] == rows[0]["balance"] - 10000000
    assert sum(r["principal"] for r in rows) == result.loans["mortgage"]
    assert rows[-1]["balance"] == 0
    assert sum(r["interest"] for r in rows) < sum(
        r["interest"] for r in initial.loans["mortgage_schedule"]
    )


def test_bank_quote_changes_are_in_save_preview(household):
    before = household.model_dump(mode="json")
    after = household.model_dump(mode="json")
    after["bank_quotes"] = [
        {"id": "BANK1", "bank": "가상은행", "date": date(2026, 10, 19).isoformat(), "options": []}
    ]
    changes = changes_between(before, after)
    assert any(c["kind"] == "bank_quotes" and c["key"] == "BANK1" for c in changes)


def test_existing_excel_plan_remains_editable_without_upload(menu_client):
    client = menu_client
    stored = client.get("/api/workspaces/demo").json()
    candidate = stored["household"]
    candidate["fund_events"][0]["origin"] = "excel"
    client.app.state.repository.seed("legacy-excel", "Imported plan", candidate)
    stored = client.get("/api/workspaces/legacy-excel").json()
    candidate = stored["household"]
    candidate["settings"]["husband_net_pay"] = 6200000
    response = client.put(
        "/api/workspaces/legacy-excel",
        json={"household": candidate, "revision": stored["revision"]},
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["household"]["fund_events"][0]["origin"] == "excel"
    assert saved["household"]["settings"]["husband_net_pay"] == 6200000
    assert client.get("/api/workspaces/legacy-excel").json() == saved
    before = client.get("/api/workspaces").json()
    assert client.post("/api/import-excel/preview", json={}).status_code in (404, 405)
    assert client.get("/api/workspaces").json() == before
