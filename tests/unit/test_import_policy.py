import copy

from homeplan.importer import merge_import
from homeplan.storage import read_json


def test_import_adds_new_records_preserves_app_values_and_never_deletes(household):
    before = household.model_dump(mode="json")
    incoming = copy.deepcopy(before)
    incoming["settings"]["living_cost"] = 3000000
    incoming["fund_events"][0]["value"] = 1
    incoming["fund_events"] = [e for e in incoming["fund_events"] if e["id"] != "A02"]
    incoming["fund_events"].append({"id": "A99", "value": 123, "origin": "excel"})
    merged = merge_import(before, incoming)
    assert merged["settings"]["living_cost"] == 2000000
    assert next(e for e in merged["fund_events"] if e["id"] == "A01")["value"] == 80000000
    assert {e["id"] for e in merged["fund_events"]} == {e["id"] for e in before["fund_events"]} | {
        "A99"
    }
    twice = merge_import(merged, incoming)
    assert twice["fund_events"] == merged["fund_events"]
    assert before == household.model_dump(mode="json")


def test_refresh_requires_explicit_option_and_preserves_app_edits(household):
    before = household.model_dump(mode="json")
    incoming = copy.deepcopy(before)
    before["fund_events"][0]["origin"] = "app"
    incoming["fund_events"][0]["value"] = 1
    incoming["fund_events"][1]["value"] = 999
    incoming["settings"]["living_cost"] = 3000000
    refreshed = merge_import(before, incoming, refresh_imported=True)
    assert refreshed["fund_events"][0]["value"] == 80000000
    assert refreshed["fund_events"][1]["value"] == 999
    assert refreshed["settings"]["living_cost"] == 3000000


def test_calculation_and_edits_work_with_excel_missing(tmp_path, monkeypatch, household):
    from typer.testing import CliRunner

    import homeplan.importer
    from homeplan.cli import app
    from homeplan.storage import dumps

    raw = household.model_dump(mode="json")
    raw["_source"] = str(tmp_path / "does-not-exist.xlsx")
    path = tmp_path / "household.local.json"
    path.write_text(dumps(raw), encoding="utf-8")

    def no_excel(*args, **kwargs):
        raise AssertionError("앱 실행 중 엑셀을 읽으면 안 됩니다")

    monkeypatch.setattr(homeplan.importer, "load_workbook", no_excel)
    runner = CliRunner()
    evaluated = runner.invoke(app, ["--data", str(path), "evaluate", "--json"])
    assert evaluated.exit_code == 0, evaluated.output
    edited = runner.invoke(
        app, ["--data", str(path), "fund", "edit", "A01", "--set", "value=9000만", "--yes"]
    )
    assert edited.exit_code == 0, edited.output
    assert read_json(path)["fund_events"][0]["value"] == 90000000
