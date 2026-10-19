import json
from decimal import Decimal
from pathlib import Path

import pytest

from homeplan.dsr import dsr_mortgage_review
from homeplan.loans import card_installments, credit_full_limit, mortgage_first_payment
from homeplan.rules import (
    acquisition_taxes,
    brokerage_fee,
    family_loan_interest_free_max,
    registration_costs,
)

CASE_FILE = Path(__file__).parent / "units.json"
if not CASE_FILE.exists():
    CASE_FILE = Path(__file__).parent / "units_public.json"
CASES = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_golden_unit(case, rules):
    fn, args = case["fn"], case.get("in", {})
    if fn == "retirement_income_tax":
        pytest.skip("퇴직소득세 U10~U12는 인계 문서의 후속 범위")
    if fn == "brokerage_fee":
        for row in case["cases"]:
            assert brokerage_fee(rules, row["price"]) == row["out"]
        return
    if fn == "acquisition_taxes":
        actual = acquisition_taxes(rules, **args)
    elif fn == "registration_costs":
        actual = registration_costs(rules, **args)
    elif fn == "mortgage_first_payment":
        actual = mortgage_first_payment(**args)
    elif fn == "card_installments":
        actual = card_installments(**args)
    elif fn == "dsr_mortgage_review":
        actual = dsr_mortgage_review(**args)
    elif fn == "credit_full_limit":
        actual = credit_full_limit(rules, **args)
        actual["borrower_dsr_lump_sum_4_68"] = (
            Decimal(actual["limit"]) * Decimal("0.2468") / args["borrower_gross"]
        )
    elif fn == "family_loan_interest_free_max":
        actual = family_loan_interest_free_max(rules)
    else:
        raise AssertionError(f"알 수 없는 golden 함수: {fn}")
    expected = case["out"]
    if isinstance(expected, dict):
        for key, value in expected.items():
            if isinstance(value, float):
                assert float(actual[key]) == pytest.approx(value, abs=case.get("tolerance", 0.0005))
            else:
                assert actual[key] == value
    elif isinstance(expected, float):
        assert float(actual) == pytest.approx(expected, abs=case.get("tolerance", 0.0005))
    else:
        assert actual == expected
