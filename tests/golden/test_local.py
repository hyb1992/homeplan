"""개인 입력은 저장소에 포함하지 않는다. 없는 환경에서는 이 대조만 skip."""

import json
from pathlib import Path

import pytest

from homeplan.checks import evaluate
from homeplan.importer import extract_excel, merge_import
from homeplan.models import Household
from homeplan.solver import max_price
from homeplan.storage import load_household

ROOT = Path(__file__).parents[2]
LOCAL = ROOT / "data/household.local.json"
CASE_FILE = Path(__file__).parent / "scenarios.json"
CASES = (json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"] if CASE_FILE.exists() else [])[
    :3
]
pytestmark = [
    pytest.mark.local,
    pytest.mark.skipif(not LOCAL.exists(), reason="실제 가구 입력은 로컬에서만 제공"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_local_excel_reconciliation(case, rules):
    # 엑셀 대조는 최초 이관 원본 기준이다. 앱에서 편집 중인 DB를 기준값과 비교하지 않는다.
    h = Household.model_validate_json(LOCAL.read_text(encoding="utf-8-sig"))
    result = evaluate(h, case["listing"], rules, case["overrides"], analyze_assumptions=False)
    expected, note = case["expected"], case["excel_simplification"]
    compatible = note["compatible_kpis"]
    engine = note["engine_expected"]
    for key, value in expected.items():
        if key in {"max_price", "max_price_binding", "at_max_price", "status"}:
            continue
        if key == "month_end_balance":
            for month, amount in value.items():
                assert result.kpis[key][month] == amount
        elif key in engine:
            assert result.kpis[key] == engine[key]
            if key in compatible:
                assert result.kpis[compatible[key]] == value
        else:
            actual = result.costs[key] if key in result.costs else result.kpis[key]
            assert float(actual) == pytest.approx(value, abs=0.002 if key.startswith("dsr_") else 0)
    assert result.status == expected["status"]
    # 상대 날짜가 적용되었는지도 별도로 확인한다.
    resolved = h.resolved(case["overrides"])
    assert (
        resolved.day("credit_draw_date").toordinal() == resolved.day("closing_date").toordinal() + 1
    )
    assert resolved.day("sub_draw_date") == resolved.day("credit_draw_date")
    assert next(e.available_date for e in resolved.fund_events if e.id == "A12") == resolved.day(
        "interim_date"
    )
    if "max_price" in note:
        maximum = max_price(
            h, case["listing"], rules, case["overrides"], minimum=500000000, maximum=1300000000
        )
        for key, value in note["max_price"].items():
            if key == "at_price_minimum":
                assert maximum["at_price_kpis"]["min_balance_overall"] == value
            else:
                assert maximum[key] == value
    if "at_excel_max_compatible" in note:
        general = h.listing(case["listing"])
        general.price = expected["max_price"]
        general.repair, general.mgmt_fee = h.settings.repair_default, h.settings.mgmt_fee_default
        general.area_m2 = h.settings.comparison_area_m2
        at_excel_max = evaluate(h, general, rules, case["overrides"], analyze_assumptions=False)
        for original, kpi in note["at_excel_max_compatible"].items():
            assert at_excel_max.kpis[kpi] == pytest.approx(
                expected["at_max_price"][original], abs=500000
            )


def test_reimport_preserves_bank_options_and_application_funds():
    from datetime import date

    sources = list(ROOT.parent.glob("*.xlsx"))
    if not sources:
        pytest.skip("대조할 엑셀 원본 없음")
    h = load_household(LOCAL)
    raw = h.model_dump(mode="json")
    raw["fund_events"].append({"id": "APP-TEST", "value": 123, "origin": "app"})
    merged = merge_import(raw, extract_excel(sources[0], date(2026, 10, 18)))
    assert merged["bank_quotes"] == raw["bank_quotes"]
    assert any(e["id"] == "APP-TEST" for e in merged["fund_events"])
    resolved = Household.model_validate(merged).resolved(
        {"closing_date": "2027-03-27", "move_in_date": "2027-04-01"}
    )
    assert resolved.day("credit_draw_date").isoformat() == "2027-03-28"
    assert resolved.settings.setting_statuses
