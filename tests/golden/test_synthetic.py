import json
from datetime import date
from pathlib import Path

import pytest

from homeplan.checks import evaluate
from homeplan.solver import max_price

CASES = json.loads((Path(__file__).parent / "synthetic.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_synthetic(case, household, rules):
    listing = household.listing()
    if "price" in case:
        listing.price = case["price"]
    if "max_price" in case:
        result = max_price(
            household,
            listing,
            rules,
            case["overrides"],
            mode="listing",
            minimum=550000000,
            maximum=650000000,
        )
        assert result["price"] == case["max_price"]
        assert result["binding_check"] == case["binding"]
        assert result["at_price_kpis"]["min_balance_overall"] == case["at_max_minimum"]
        listing.price = case["max_price"] + 100000
        above = evaluate(household, listing, rules, case["overrides"], analyze_assumptions=False)
        assert not next(c.ok for c in above.checks if c.name == "최소 비상금")
        return
    result = evaluate(household, listing, rules, case["overrides"])
    assert result.status == case["status"]
    for key, value in case["expected"].items():
        assert result.kpis[key] == value, key
    for key, value in case.get("costs", {}).items():
        assert result.costs[key] == value, key
    for key, value in case.get("month_end", {}).items():
        assert result.kpis["month_end_balance"][key] == value
    assert household.resolved(case["overrides"]).day("credit_draw_date") == (
        date(2027, 3, 16) if case["id"] == "S03" else date(2027, 2, 27)
    )
