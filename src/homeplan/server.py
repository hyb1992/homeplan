"""로컬 GUI API. 계산은 기존 core, 저장은 revision을 검사하는 SQLite."""

import argparse
import hashlib
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .checks import evaluate
from .excel_upload import install_excel_routes
from .models import Household
from .repository import Repository, RevisionConflict, clean_household, seed_repository
from .solver import max_price
from .storage import dumps, load_rules
from .updates import build_id, data_root, fetch_release
from .workspaces import install_workspace_routes


class EvaluationInput(BaseModel):
    household: Household
    listing_id: str | None = None
    confirmed_only: bool = False


class MaximumInput(EvaluationInput):
    mode: Literal["general", "listing"] = "listing"
    minimum: int = Field(default=100000, ge=0)
    maximum: int = Field(default=3000000000, ge=1, le=10000000000)
    precision: int = Field(default=100000, ge=10000)


class SaveInput(BaseModel):
    household: dict[str, Any]
    revision: int = Field(ge=0)


class RestoreInput(BaseModel):
    revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)


def today_korea() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def changes_between(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in set(before["settings"]) | set(after["settings"]):
        old, new = before["settings"].get(key), after["settings"].get(key)
        if old != new and key not in {"setting_statuses"}:
            result.append({"kind": "setting", "key": key, "before": old, "after": new})
    for section in (
        "fund_events",
        "parent_support",
        "listings",
        "expense_items",
        "loan_prepayments",
        "bank_quotes",
    ):
        old_rows = {
            row.get("id") or f"P{i:02}": row for i, row in enumerate(before.get(section) or [], 1)
        }
        new_rows = {
            row.get("id") or f"P{i:02}": row for i, row in enumerate(after.get(section) or [], 1)
        }
        if section == "expense_items" and before[section] is None and after[section] == []:
            result.append(
                {
                    "kind": section,
                    "key": "plan",
                    "label": "기간별 지출 계획",
                    "before": None,
                    "after": [],
                }
            )
        for key in sorted(set(old_rows) | set(new_rows)):
            old, new = old_rows.get(key), new_rows.get(key)
            if old != new:
                result.append(
                    {
                        "kind": section,
                        "key": key,
                        "label": (new or old or {}).get(
                            "name",
                            (new or old or {}).get("bank", (new or old or {}).get("kind", key)),
                        ),
                        "before": old,
                        "after": new,
                    }
                )
    return result


def mark_app_edits(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    candidate = clean_household(after)
    imported = candidate.pop("_excel_import_baseline", {})
    old = clean_household(before)
    keys = set(candidate.get("app_setting_keys", []))
    keys.update(
        key
        for key, value in candidate["settings"].items()
        if value != old["settings"].get(key)
        and (key not in imported.get("settings", {}) or value != imported["settings"][key])
    )
    candidate["app_setting_keys"] = sorted(keys)
    for section in ("fund_events", "parent_support", "listings"):
        previous = {row.get("id") or f"P{i:02}": row for i, row in enumerate(old[section], 1)}
        for i, row in enumerate(candidate[section], 1):
            key = row.get("id") or f"P{i:02}"
            if section == "parent_support" and not row.get("id"):
                row["id"] = key
            if row != previous.get(key) and row != imported.get(section, {}).get(key):
                row["origin"] = "app"
    return candidate


def create_app(db_path: Path | None = None, *, seed_root: Path | None = None) -> FastAPI:
    root = seed_root or data_root()
    repo = Repository(db_path or root / "data/homeplan.local.sqlite")
    seed_repository(repo, root)
    repo.backup(daily=True)
    rules = load_rules()
    app = FastAPI(title="우리집 매수계획", version=__version__, docs_url=None, redoc_url=None)
    app.state.last_heartbeat = time.monotonic()
    update_cache: dict[str, Any] = {"time": 0.0, "release": None}
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.state.repository = repo
    install_excel_routes(app, today_korea)

    @app.middleware("http")
    async def local_requests(request: Request, call_next: Any) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "DELETE", "PATCH"}
            and origin
            and origin.rstrip("/") != str(request.base_url).rstrip("/")
        ):
            return JSONResponse({"detail": "앱 화면에서 실행한 요청만 허용합니다"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(RevisionConflict)
    async def conflict_handler(request: Request, exc: RevisionConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def validation_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def not_found_handler(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "service": "homeplan-gui",
            "version": __version__,
            "build": build_id(),
            "today": today_korea().isoformat(),
            "instance": hashlib.sha256(str(repo.path.resolve()).encode()).hexdigest()[:16],
        }

    @app.post("/api/heartbeat")
    def heartbeat() -> dict[str, bool]:
        app.state.last_heartbeat = time.monotonic()
        return {"ok": True}

    @app.get("/api/workspaces")
    def workspaces() -> list[dict[str, Any]]:
        return repo.list_workspaces()

    @app.get("/api/updates")
    def updates(force: bool = False) -> dict[str, Any]:
        if force or not update_cache["time"] or time.monotonic() - update_cache["time"] > 900:
            update_cache["release"] = fetch_release()
            update_cache["time"] = time.monotonic()
        return {
            "current_version": __version__,
            "current_build": build_id(),
            "release": update_cache["release"],
        }

    @app.get("/api/workspaces/{key}")
    def workspace(key: str) -> dict[str, Any]:
        return repo.get(key)

    @app.post("/api/evaluate")
    def evaluation(payload: EvaluationInput) -> dict[str, Any]:
        as_of = today_korea()
        result = evaluate(
            payload.household,
            payload.listing_id,
            rules,
            confirmed_only=payload.confirmed_only,
            as_of=as_of,
        )
        resolved = payload.household.resolved(as_of=as_of)
        return {
            **result.model_dump(mode="json"),
            "expense_schedule": [
                item.model_dump(mode="json") for item in resolved.expense_items or []
            ],
            "schedule": {
                key: str(getattr(resolved.settings, key) or "")
                for key in (
                    "contract_date",
                    "interim_date",
                    "closing_date",
                    "move_in_date",
                    "lease_refund_date",
                    "lease_loan_repay_date",
                    "asset_base_date",
                )
            },
        }

    @app.post("/api/max-price")
    def maximum(payload: MaximumInput) -> dict[str, Any]:
        return max_price(
            payload.household,
            payload.listing_id,
            rules,
            mode=payload.mode,
            minimum=payload.minimum,
            maximum=payload.maximum,
            precision=payload.precision,
            confirmed_only=payload.confirmed_only,
            as_of=today_korea(),
        )

    @app.post("/api/workspaces/{key}/preview")
    def preview(key: str, payload: SaveInput) -> dict[str, Any]:
        stored = repo.get(key)
        if stored["revision"] != payload.revision:
            raise RevisionConflict(
                "다른 화면에서 데이터가 변경되었습니다. 새로고침 후 다시 확인하세요."
            )
        candidate = clean_household(payload.household)
        as_of = today_korea()
        before = evaluate(
            Household.model_validate(stored["household"]),
            None,
            rules,
            analyze_assumptions=False,
            as_of=as_of,
        )
        after = evaluate(
            Household.model_validate(candidate), None, rules, analyze_assumptions=False, as_of=as_of
        )
        keys = (
            "closing_cash_available",
            "min_balance_overall",
            "interim_shortfall",
            "after_purchase_cash",
        )
        return {
            "revision": stored["revision"],
            "before": {"status": before.status, **{key: before.kpis[key] for key in keys}},
            "after": {"status": after.status, **{key: after.kpis[key] for key in keys}},
            "changes": changes_between(clean_household(stored["household"]), candidate),
        }

    @app.put("/api/workspaces/{key}")
    def save(key: str, payload: SaveInput) -> dict[str, Any]:
        previous = repo.get(key)
        repo.backup(daily=True)
        return repo.save(
            key, mark_app_edits(previous["household"], payload.household), payload.revision
        )

    @app.get("/api/workspaces/{key}/history")
    def history(key: str) -> list[dict[str, Any]]:
        rows = repo.history(key)
        for row in rows:
            if row["revision"]:
                try:
                    row["changes"] = changes_between(
                        repo.version(key, row["revision"] - 1), repo.version(key, row["revision"])
                    )
                except KeyError:
                    row["changes"] = []
        return rows

    @app.post("/api/workspaces/{key}/restore")
    def restore(key: str, payload: RestoreInput) -> dict[str, Any]:
        return repo.save(key, repo.version(key, payload.target_revision), payload.revision)

    @app.get("/api/workspaces/{key}/export")
    def export(key: str) -> Response:
        data = repo.get(key)["household"]
        return Response(
            dumps(data),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="homeplan-{key}.local.json"'},
        )

    @app.post("/api/workspaces/{key}/import-json")
    def import_json(key: str, payload: SaveInput) -> dict[str, Any]:
        # 명시적 JSON 가져오기도 동일한 preview/save 계약을 사용한다.
        return preview(key, payload)

    install_workspace_routes(app, repo, rules, lambda: today_korea())
    web = Path(__file__).resolve().parents[2] / "web"
    if not web.exists():
        web = Path(__file__).parent / "web_assets"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="gui")
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--seed-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    app = create_app(args.db, seed_root=args.seed_root)
    if args.check:
        print("GUI 준비 완료: 앱 DB·계산 엔진 확인")
        return
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        use_colors=False,
    )
    server = uvicorn.Server(config)
    if os.environ.get("HOMEPLAN_MANAGED_CHILD"):
        import threading

        def stop_when_idle() -> None:
            while not server.should_exit:
                time.sleep(5)
                if time.monotonic() - app.state.last_heartbeat > 90:
                    server.should_exit = True

        threading.Thread(target=stop_when_idle, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
