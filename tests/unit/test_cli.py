import json
from pathlib import Path

from typer.testing import CliRunner

from homeplan.cli import app
from homeplan.storage import dumps, load_household, read_json, save_json

runner = CliRunner()


def input_file(tmp_path):
    path = tmp_path / "household.local.json"
    source = Path(__file__).parents[1] / "fixtures/synthetic_household.json"
    path.write_bytes(source.read_bytes())
    return path


def test_cli_json(tmp_path):
    path = input_file(tmp_path)
    result = runner.invoke(app, ["--data", str(path), "evaluate", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "현금 부족"


def test_add_preview_cancel_and_save_then_edit_restore_remove(tmp_path):
    path = input_file(tmp_path)
    original = path.read_bytes()
    command = [
        "--data",
        str(path),
        "fund",
        "add",
        "--type",
        "현금·예금",
        "--name",
        "가상 새 예금",
        "--amount",
        "3600만",
        "--date",
        "지금",
    ]
    canceled = runner.invoke(app, command, input="n\n")
    assert canceled.exit_code == 0, canceled.output
    assert path.read_bytes() == original
    saved = runner.invoke(app, [*command, "--yes"])
    assert saved.exit_code == 0, saved.output
    row = next(e for e in read_json(path)["fund_events"] if e["name"] == "가상 새 예금")
    assert row["available_date"] == "지금"
    assert row["value"] == 36000000
    assert row["origin"] == "app"
    backups = list((tmp_path / "backups").glob("*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    key = row["id"]
    for tail in [
        ["edit", key, "--set", "value=4000만"],
        ["remove", key],
        ["edit", key, "--set", "status=확인 완료"],
    ]:
        changed = runner.invoke(app, ["--data", str(path), "fund", *tail, "--yes"])
        assert changed.exit_code == 0, changed.output
    assert next(e for e in read_json(path)["fund_events"] if e["id"] == key)["value"] == 40000000
    removed = runner.invoke(app, ["--data", str(path), "fund", "remove", key, "--hard", "--yes"])
    assert removed.exit_code == 0, removed.output
    assert not any(e["id"] == key for e in read_json(path)["fund_events"])


def test_wizard_and_parent_support(tmp_path):
    path = input_file(tmp_path)
    result = runner.invoke(
        app,
        ["--data", str(path), "fund", "add"],
        input="1\n가상 통장\n공동\n360만\n지금\n확인 완료\ny\ny\n",
    )
    assert result.exit_code == 0, result.output
    support = runner.invoke(
        app,
        [
            "--data",
            str(path),
            "support",
            "add",
            "--amount",
            "1000만",
            "--date",
            "잔금일-1",
            "--status",
            "확정",
            "--yes",
        ],
    )
    assert support.exit_code == 0, support.output
    assert len(load_household(path).parent_support) == 2


def test_invalid_change_leaves_file_and_backups_untouched(tmp_path):
    path = input_file(tmp_path)
    original = path.read_bytes()
    failed = runner.invoke(
        app,
        ["--data", str(path), "fund", "edit", "A01", "--set", "available_date=없는날+1", "--yes"],
    )
    assert failed.exit_code == 2
    assert path.read_bytes() == original
    assert not (tmp_path / "backups").exists()
    raw = read_json(path)
    raw["settings"]["closing_date"] = "contract_date"
    raw["settings"]["contract_date"] = "closing_date"
    import pytest

    with pytest.raises(ValueError, match="순환"):
        save_json(path, raw)
    assert path.read_bytes() == original
    assert dumps(read_json(path))
