import copy
import json
import mimetypes
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from homeplan.repository import Repository, RevisionConflict, seed_repository
from homeplan.server import create_app


@pytest.fixture
def api_context(tmp_path, household):
    (tmp_path / "tests/fixtures").mkdir(parents=True)
    (tmp_path / "tests/fixtures/synthetic_household.json").write_text(
        household.model_dump_json(), encoding="utf-8"
    )
    app = create_app(tmp_path / "data/homeplan.local.sqlite", seed_root=tmp_path)
    with TestClient(app) as client:
        yield client, app.state.repository


def test_api_evaluation_and_ui_assets(api_context):
    client, _ = api_context
    loaded = client.get("/api/workspaces/demo").json()
    result = client.post("/api/evaluate", json={"household": loaded["household"]})
    assert result.status_code == 200
    assert result.json()["status"] == "현금 부족"
    assert result.json()["kpis"]["interim_shortfall"] == 13900000
    assert result.json()["schedule"]["closing_date"] == "2027-02-26"
    cash = {row["date"]: row for row in result.json()["daily_balances"]}
    assert cash["2027-02-26"]["debt_breakdown"] == {"주택담보대출": 300000000}
    assert cash["2027-02-27"]["debt_total"] == 330000000
    assert cash["2027-02-27"]["net_cash"] == cash["2027-02-27"]["closing"] - 330000000
    assert len(client.get("/api/workspaces/demo/history").json()) == 1
    assert client.get("/").status_code == 200
    assert "매수 계획을 한눈에" in client.get("/").text
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200
    assert "/api/workspaces/{key}/preview" in client.get("/openapi.json").json()["paths"]
    assert client.get("/data/homeplan.local.sqlite").status_code == 404
    assert client.get("/expense-plan.mjs").status_code == 200


@pytest.mark.parametrize("wrong_type", ["text/plain", "application/octet-stream"])
def test_javascript_content_type_ignores_os_file_associations(api_context, monkeypatch, wrong_type):
    client, _ = api_context
    mimetypes.init()
    for extension in (".js", ".mjs"):
        monkeypatch.setitem(mimetypes.types_map, extension, wrong_type)
    web = Path(__file__).resolve().parents[2] / "web"
    for asset in web.rglob("*"):
        if asset.suffix not in {".js", ".mjs"}:
            continue
        url = "/" + asset.relative_to(web).as_posix() + "?v=mime-regression"
        for method in ("GET", "HEAD"):
            response = client.request(method, url)
            assert response.status_code == 200, url
            assert response.headers["content-type"] == "text/javascript; charset=utf-8", url
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["cache-control"] == "no-store"
    assert client.get("/missing.mjs").status_code == 404
    assert client.get("/api/health").headers["content-type"] == "application/json"


def test_release_detection_does_not_change_saved_plan_and_failure_is_optional(api_context):
    client, repo = api_context
    before = repo.get("demo")
    history = repo.history("demo")
    with patch(
        "homeplan.server.fetch_release", return_value={"tag_name": "v9.0.0", "assets": []}
    ) as check:
        assert client.get("/api/updates").json()["release"]["tag_name"] == "v9.0.0"
        assert client.get("/api/updates").status_code == 200
        assert check.call_count == 1
    with patch("homeplan.server.fetch_release", return_value=None):
        assert client.get("/api/updates?force=true").json()["release"] is None
    assert repo.get("demo") == before and repo.history("demo") == history
    assert client.get("/api/workspaces").status_code == 200


def test_expense_plan_preview_save_and_restore(api_context):
    client, repo = api_context
    loaded = repo.get("demo")
    data = copy.deepcopy(loaded["household"])
    data["expense_items"] = [
        {
            "id": "E1",
            "name": "전세 주거비",
            "category": "주거비",
            "amount": 1500000,
            "start_date": "기준일",
            "end_date": "퇴거일",
            "includes_lease_interest": True,
        }
    ]
    payload = {"household": data, "revision": 0}
    preview = client.post("/api/workspaces/demo/preview", json=payload)
    assert preview.status_code == 200
    change = next(row for row in preview.json()["changes"] if row["kind"] == "expense_items")
    assert change["label"] == "전세 주거비" and change["after"]["amount"] == 1500000
    assert repo.get("demo") == loaded
    assert client.put("/api/workspaces/demo", json=payload).status_code == 200
    stored = repo.get("demo")["household"]
    assert stored["expense_items"][0]["end_date"] == "퇴거일"
    result = client.post("/api/evaluate", json={"household": stored}).json()
    assert result["kpis"]["expense_mode"] == "기간별"
    assert result["expense_schedule"][0]["end_date"] == "2027-02-26"
    assert not any(e["category"] == "lease_interest" for e in result["ledger"])
    restored = client.post(
        "/api/workspaces/demo/restore", json={"revision": 1, "target_revision": 0}
    )
    assert restored.status_code == 200
    assert restored.json()["household"]["expense_items"] is None


def test_empty_and_invalid_expense_plan_preview(api_context):
    client, repo = api_context
    original = repo.get("demo")
    data = copy.deepcopy(original["household"])
    data["expense_items"] = []
    preview = client.post("/api/workspaces/demo/preview", json={"household": data, "revision": 0})
    assert preview.status_code == 200
    assert any(row["kind"] == "expense_items" for row in preview.json()["changes"])
    data["expense_items"] = [{"id": "E", "name": "보험", "amount": -100}]
    assert (
        client.put("/api/workspaces/demo", json={"household": data, "revision": 0}).status_code
        == 422
    )
    assert repo.get("demo") == original


def test_api_saved_now_resolves_again_on_every_request(api_context, monkeypatch):
    import homeplan.server as server

    client, repo = api_context
    data = repo.get("demo")["household"]
    data["fund_events"].append(
        {"id": "NOW", "value": 30000000, "available_date": "지금", "status": "확정"}
    )
    saved = client.put("/api/workspaces/demo", json={"household": data, "revision": 0})
    assert saved.status_code == 200
    for today in (date(2026, 10, 18), date(2026, 10, 19)):
        monkeypatch.setattr(server, "today_korea", lambda day=today: day)
        result = client.post("/api/evaluate", json={"household": data}).json()
        assert [(e["date"], e["amount"]) for e in result["ledger"] if e["source"] == "NOW"] == [
            (today.isoformat(), 30000000)
        ]
    assert repo.get("demo")["household"]["fund_events"][-1]["available_date"] == "지금"
    assert repo.get("demo")["revision"] == 1

    # Read the clock once for a before/after comparison, including at midnight.
    with (
        patch.object(server, "today_korea", return_value=today) as clock,
        patch.object(server, "evaluate", wraps=server.evaluate) as engine,
    ):
        response = client.post(
            "/api/workspaces/demo/preview", json={"household": data, "revision": 1}
        )
        assert response.status_code == 200
        assert clock.call_count == 1
        assert [call.kwargs["as_of"] for call in engine.call_args_list] == [today, today]
    with patch.object(server, "max_price", wraps=server.max_price) as solver:
        response = client.post(
            "/api/max-price", json={"household": data, "minimum": 580000000, "maximum": 580000000}
        )
        assert response.status_code == 200
        assert solver.call_args.kwargs["as_of"] == today


def test_preview_does_not_save_and_save_has_revision_and_history(api_context):
    client, repo = api_context
    loaded = client.get("/api/workspaces/demo").json()
    edited = copy.deepcopy(loaded["household"])
    edited["fund_events"][0]["value"] += 20000000
    payload = {"household": edited, "revision": loaded["revision"]}
    preview = client.post("/api/workspaces/demo/preview", json=payload)
    assert preview.status_code == 200
    data = preview.json()
    assert (
        data["after"]["closing_cash_available"] - data["before"]["closing_cash_available"]
        == 20000000
    )
    assert repo.get("demo")["revision"] == 0
    saved = client.put("/api/workspaces/demo", json=payload)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    assert saved.json()["household"]["fund_events"][0]["origin"] == "app"
    assert client.put("/api/workspaces/demo", json=payload).status_code == 409
    assert client.post("/api/workspaces/demo/preview", json=payload).status_code == 409
    assert len(repo.history("demo")) == 2


def test_history_restore_and_json_export(api_context):
    client, repo = api_context
    before = repo.get("demo")
    edited = copy.deepcopy(before["household"])
    edited["settings"]["living_cost"] = 2500000
    client.put("/api/workspaces/demo", json={"household": edited, "revision": 0})
    exported = client.get("/api/workspaces/demo/export")
    assert exported.json()["settings"]["living_cost"] == 2500000
    assert ".local.json" in exported.headers["content-disposition"]
    restored = client.post(
        "/api/workspaces/demo/restore", json={"revision": 1, "target_revision": 0}
    )
    assert restored.status_code == 200
    assert restored.json()["revision"] == 2
    assert restored.json()["household"]["settings"]["living_cost"] == 2000000
    assert len(client.get("/api/workspaces/demo/history").json()) == 3


def test_listing_deletion_preview_save_and_restore(api_context):
    client, repo = api_context
    original = repo.get("demo")["household"]
    second = {**original["listings"][0], "id": "S2", "name": "삭제할 가상 매물"}
    original["listings"].append(second)
    original["selected_listing"] = "S2"
    repo.save("demo", original, 0)
    candidate = copy.deepcopy(original)
    candidate["listings"] = [row for row in candidate["listings"] if row["id"] != "S2"]
    candidate["selected_listing"] = "S1"
    payload = {"household": candidate, "revision": 1}
    preview = client.post("/api/workspaces/demo/preview", json=payload)
    assert preview.status_code == 200
    removed = next(row for row in preview.json()["changes"] if row["key"] == "S2")
    assert removed["before"]["name"] == "삭제할 가상 매물"
    assert removed["after"] is None
    assert len(repo.get("demo")["household"]["listings"]) == 2
    saved = client.put("/api/workspaces/demo", json=payload)
    assert saved.status_code == 200
    exported = client.get("/api/workspaces/demo/export").json()
    assert [row["id"] for row in exported["listings"]] == ["S1"]
    assert exported["selected_listing"] == "S1"
    restored = client.post(
        "/api/workspaces/demo/restore", json={"revision": 2, "target_revision": 1}
    )
    assert restored.status_code == 200
    assert restored.json()["household"]["listings"] == original["listings"]
    assert restored.json()["household"]["selected_listing"] == "S2"


def test_variable_asset_preview_save_evaluate_and_restore(api_context):
    client, repo = api_context
    candidate = repo.get("demo")["household"]
    candidate["settings"]["variable_asset_mode"] = "공격적"
    candidate["fund_events"].append(
        {
            "id": "VARIABLE",
            "name": "가상 성과급",
            "type": "성과급·환급금",
            "value": 900,
            "cash_out_amount": 800,
            "cost": 100,
            "is_variable": True,
            "conservative_amount": 1000,
            "aggressive_amount": 2000,
            "available_date": "2026-11-15",
            "status": "확정",
        }
    )
    payload = {"household": candidate, "revision": 0}
    preview = client.post("/api/workspaces/demo/preview", json=payload)
    assert preview.status_code == 200
    assert (
        preview.json()["after"]["closing_cash_available"]
        - preview.json()["before"]["closing_cash_available"]
        == 1900
    )
    assert repo.get("demo")["revision"] == 0
    saved = client.put("/api/workspaces/demo", json=payload)
    assert saved.status_code == 200
    stored = repo.get("demo")["household"]
    assert stored["settings"]["variable_asset_mode"] == "공격적"
    event = stored["fund_events"][-1]
    assert (
        event["value"],
        event["cash_out_amount"],
        event["conservative_amount"],
        event["aggressive_amount"],
    ) == (900, 800, 1000, 2000)
    result = client.post("/api/evaluate", json={"household": stored}).json()
    assert result["kpis"]["variable_asset_mode"] == "공격적"
    assert next(row["amount"] for row in result["ledger"] if row["source"] == "VARIABLE") == 1900
    restored = client.post(
        "/api/workspaces/demo/restore", json={"revision": 1, "target_revision": 0}
    )
    assert restored.status_code == 200
    assert restored.json()["household"]["settings"]["variable_asset_mode"] == "보수적"
    assert all(row["id"] != "VARIABLE" for row in restored.json()["household"]["fund_events"])


@pytest.mark.parametrize("invalid", ["empty_list", "missing_selected_listing"])
def test_invalid_listing_deletion_does_not_save(api_context, invalid):
    client, repo = api_context
    before = repo.get("demo")
    candidate = copy.deepcopy(before["household"])
    if invalid == "empty_list":
        candidate["listings"] = []
        candidate["selected_listing"] = ""
    else:
        candidate["selected_listing"] = "DELETED"
    payload = {"household": candidate, "revision": 0}
    assert client.post("/api/workspaces/demo/preview", json=payload).status_code == 422
    assert client.put("/api/workspaces/demo", json=payload).status_code == 422
    assert repo.get("demo") == before
    assert len(repo.history("demo")) == 1


def test_bad_inputs_do_not_change_database_and_cross_origin_is_rejected(api_context):
    client, repo = api_context
    data = repo.get("demo")["household"]
    data["settings"]["contract_date"] = "closing_date"
    data["settings"]["closing_date"] = "contract_date"
    assert (
        client.put("/api/workspaces/demo", json={"household": data, "revision": 0}).status_code
        == 422
    )
    assert repo.get("demo")["revision"] == 0
    response = client.post("/api/evaluate", json={}, headers={"Origin": "https://example.com"})
    assert response.status_code == 403
    assert client.get("/api/health", headers={"Host": "example.com"}).status_code == 400


def test_api_maximum_uses_same_engine(api_context):
    client, repo = api_context
    data = repo.get("demo")["household"]
    data["settings"]["interim_date"] = "2027-01-20"
    response = client.post(
        "/api/max-price", json={"household": data, "minimum": 550000000, "maximum": 650000000}
    )
    assert response.status_code == 200
    assert response.json()["price"] == 606100000
    assert response.json()["binding_check"] == "최소 비상금"


def test_json_is_only_seed_and_db_survives_source_changes(tmp_path, household):
    (tmp_path / "data").mkdir()
    (tmp_path / "tests/fixtures").mkdir(parents=True)
    seed = tmp_path / "data/household.local.json"
    seed.write_text(household.model_dump_json(), encoding="utf-8")
    (tmp_path / "tests/fixtures/synthetic_household.json").write_text(
        household.model_dump_json(), encoding="utf-8"
    )
    repo = Repository(tmp_path / "data/homeplan.local.sqlite")
    seed_repository(repo, tmp_path)
    actual = repo.get("actual")
    actual["household"]["fund_events"][0]["value"] = 90000000
    repo.save("actual", actual["household"], 0)
    seed.write_text("not valid json anymore", encoding="utf-8")
    seed_repository(repo, tmp_path)
    reloaded = Repository(repo.path)
    assert reloaded.get("actual")["household"]["fund_events"][0]["value"] == 90000000
    assert reloaded.get("demo")["household"]["fund_events"][0]["value"] == 80000000
    with pytest.raises(RevisionConflict):
        repo.save("actual", actual["household"], 0)


def test_legacy_cli_storage_routes_to_db_without_rewriting_json(api_context, tmp_path, monkeypatch):
    import homeplan.repository
    from homeplan.storage import read_json, save_json

    _, repo = api_context
    path = tmp_path / "household.local.json"
    path.write_text('{"original": true}', encoding="utf-8")
    monkeypatch.setattr(homeplan.repository, "canonical_repository", lambda _: (repo, "demo"))
    data = read_json(path)
    data["fund_events"][0]["value"] = 91000000
    save_json(path, data)
    assert json.loads(path.read_text(encoding="utf-8")) == {"original": True}
    assert repo.get("demo")["household"]["fund_events"][0]["value"] == 91000000


def test_concurrent_saves_keep_one_consistent_revision(api_context):
    from concurrent.futures import ThreadPoolExecutor

    _, repo = api_context
    original = repo.get("demo")["household"]

    def save_variant(amount):
        candidate = copy.deepcopy(original)
        candidate["settings"]["living_cost"] = amount
        try:
            return repo.save("demo", candidate, 0)["revision"]
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(save_variant, [2100000, 2200000]))
    assert sorted(map(str, result)) == ["1", "conflict"]
    assert len(repo.history("demo")) == 2
    assert repo.get("demo")["household"]["settings"]["living_cost"] in {2100000, 2200000}


def test_card_settlement_preview_and_save_preserve_option(api_context):
    client, repo = api_context
    loaded = repo.get("demo")
    data = copy.deepcopy(loaded["household"])
    data["settings"]["card_pay_tax"] = True
    data["settings"]["card_repay_on_credit_draw"] = True
    request = {"household": data, "revision": loaded["revision"]}
    preview = client.post("/api/workspaces/demo/preview", json=request)
    assert preview.status_code == 200
    assert any(change["key"] == "card_repay_on_credit_draw" for change in preview.json()["changes"])
    assert repo.get("demo")["household"]["settings"]["card_repay_on_credit_draw"] is False
    result = client.post("/api/evaluate", json={"household": data}).json()
    payments = [row for row in result["ledger"] if row["category"] == "card_payment"]
    assert len(payments) == 1
    assert payments[0]["date"] == "2027-02-27"
    assert client.put("/api/workspaces/demo", json=request).status_code == 200
    assert repo.get("demo")["household"]["settings"]["card_repay_on_credit_draw"] is True


def test_new_plan_copy_compare_and_sources(api_context):
    client, repo = api_context
    template = client.get("/api/new-plan").json()
    assert template["household"]["settings"]["start_today"] is True
    assert template["household"]["fund_events"] == []
    assert "wife_leave_start" in template["settings_schema"]
    source = repo.get("demo")["household"]
    created = client.post("/api/workspaces", json={"label": "비교안", "household": source})
    assert created.status_code == 200
    key = created.json()["id"]
    compared = client.post("/api/compare", json={"keys": ["demo", key]}).json()
    assert compared[0]["kpis"] == compared[1]["kpis"]
    assert client.get("/api/rules").json()["lending"]["checked_at"]


def test_independent_backup_recovery_does_not_overwrite_other_workspaces(api_context):
    client, repo = api_context
    baseline = repo.get("demo")
    backup = client.post("/api/backups", json={}).json()["name"]
    data = copy.deepcopy(baseline["household"])
    data["settings"]["living_cost"] = 777777
    repo.save("demo", data, baseline["revision"])
    other = client.post("/api/workspaces", json={"label": "다른 계획", "household": data}).json()
    request = {"key": "demo", "revision": baseline["revision"] + 1, "name": backup}
    preview = client.post("/api/backups/preview", json=request)
    assert preview.json()["household"] == baseline["household"]
    restored = client.post("/api/backups/restore", json=request)
    assert restored.status_code == 200
    assert restored.json()["household"] == baseline["household"]
    assert restored.json()["revision"] == baseline["revision"] + 2
    assert repo.get(other["id"])["household"] == other["household"]
    assert client.post("/api/backups/restore", json=request).status_code == 409
    assert (
        client.post("/api/backups/preview", json={**request, "name": "../bad.sqlite"}).status_code
        == 422
    )
    assert client.get("/api/workspaces/demo/history").json()[0]["changes"]


def test_update_application_requires_prepared_code_and_backs_up_before_restart(
    api_context, tmp_path
):
    client, repo = api_context
    preparation = client.app.state.update_preparation
    before, history = repo.get("demo"), repo.history("demo")
    assert client.post("/api/updates/apply").json() == {"restarting": False}
    restart = MagicMock()
    client.app.state.restart_for_update = restart
    preparation.status = "ready"
    with (
        patch("homeplan.server.installed_update", return_value=tmp_path / "app.exe"),
        patch.object(repo, "backup", wraps=repo.backup) as backup,
    ):
        assert client.post("/api/updates/apply").json() == {"restarting": True}
        backup.assert_called_once()
        restart.assert_called_once()
        assert client.post("/api/updates/apply").json() == {"restarting": False}
    assert repo.get("demo") == before and repo.history("demo") == history
