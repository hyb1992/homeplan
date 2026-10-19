"""새 가구, 비교, 독립 백업. 계산은 core를 사용한다."""

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .checks import evaluate
from .dates import add_months
from .models import Household, Settings
from .repository import Repository, clean_household
from .rules import RuleBook


class CreatePlan(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    household: dict[str, Any] | None = None


class ComparePlans(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=5)


class BackupInput(BaseModel):
    directory: str | None = None


class RecoverInput(BaseModel):
    key: str
    name: str
    revision: int = Field(ge=0)


def blank_plan(today: date) -> dict[str, Any]:
    return Household.model_validate(
        {
            "settings": {
                "asset_base_date": today,
                "start_today": True,
                "contract_date": add_months(today, 1),
                "interim_date": add_months(today, 2),
                "closing_date": add_months(today, 4),
                "move_in_date": add_months(today, 4),
                "land_permit_required": False,
            },
            "expense_items": [],
            "listings": [{"id": "HOME1", "name": "검토할 집", "price": 0}],
            "selected_listing": "HOME1",
        }
    ).model_dump(mode="json")


def install_workspace_routes(
    app: FastAPI, repo: Repository, rules: RuleBook, today: Callable[[], date]
) -> None:
    @app.get("/api/new-plan")
    def template() -> dict[str, Any]:
        return {
            "household": blank_plan(today()),
            "today": today().isoformat(),
            "settings_schema": Settings.model_json_schema()["properties"],
        }

    @app.post("/api/workspaces")
    def create(payload: CreatePlan) -> dict[str, Any]:
        key = "plan-" + uuid4().hex[:12]
        data = clean_household(payload.household or blank_plan(today()))
        repo.seed(key, payload.label.strip(), data)
        repo.backup()
        return repo.get(key)

    @app.post("/api/compare")
    def compare(payload: ComparePlans) -> list[dict[str, Any]]:
        as_of = today()
        rows = []
        for key in payload.keys:
            plan = repo.get(key)
            try:
                result = evaluate(
                    Household.model_validate(plan["household"]), None, rules, as_of=as_of
                )
                rows.append(
                    {
                        "id": key,
                        "label": plan["label"],
                        "status": result.status,
                        "kpis": result.model_dump(mode="json")["kpis"],
                        "assumptions": result.model_dump(mode="json")["assumptions"],
                    }
                )
            except ValueError as error:
                rows.append({"id": key, "label": plan["label"], "error": str(error)})
        return rows

    @app.get("/api/backups")
    def backups() -> dict[str, Any]:
        return {"directory": str(repo.backup_directory()), "files": repo.backup_versions()}

    @app.post("/api/backups")
    def backup(payload: BackupInput) -> dict[str, Any]:
        if payload.directory:
            repo.set_backup_directory(payload.directory)
        return {"name": repo.backup().name}

    @app.post("/api/backups/preview")
    def recovery_preview(payload: RecoverInput) -> dict[str, Any]:
        return {"household": repo.backup_household(payload.name, payload.key)}

    @app.post("/api/backups/restore")
    def recover(payload: RecoverInput) -> dict[str, Any]:
        data = repo.backup_household(payload.name, payload.key)
        repo.backup()
        return repo.save(payload.key, data, payload.revision)

    @app.get("/api/rules")
    def rule_sources() -> dict[str, Any]:
        return {
            name: data.get("meta", {})
            for name, data in rules.data.items()
            if isinstance(data, dict)
        }
