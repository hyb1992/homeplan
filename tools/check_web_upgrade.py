"""가상 DB를 만들고 제품의 주요 브라우저 경로를 반복 확인한다."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="homeplan-web-") as folder:
        seed = Path(folder)
        (seed / "data").mkdir()
        data = json.loads((ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8"))
        data["settings"].update(birth_date="2027-05-30", start_today=True)
        (seed / "data/demo.local.json").write_text(json.dumps(data), "utf-8")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        command = [
            sys.executable,
            "-m",
            "homeplan.server",
            "--port",
            str(port),
            "--db",
            str(seed / "data/qa.sqlite"),
            "--seed-root",
            str(seed),
        ]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    if httpx.get(base + "/api/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    time.sleep(0.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    channel="msedge" if os.name == "nt" else None, headless=True
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                with page.expect_response(
                    lambda r: r.url.endswith("/api/evaluate") and r.request.method == "POST"
                ):
                    page.goto(base)
                expect(page.locator(".runtime-summary")).to_contain_text("매일 오늘부터 계산")
                page.locator('a[href="#settings"]:visible').first.click()
                # Open income group and verify invalid input blocks calculation.
                income = page.locator(".settings-group").filter(
                    has=page.locator("#field-husband_net_pay")
                )
                income.locator("summary").click()
                page.locator("#field-husband_net_pay").fill("-1")
                page.locator("#field-husband_net_pay").press("Tab")
                page.locator("#toolbar-calculate").click()
                expect(page.locator("#field-husband_net_pay")).to_have_value("-1")
                page.locator("#field-husband_net_pay").fill("400만원")
                page.locator("#field-husband_net_pay").press("Tab")
                # Full advanced settings are editable, including previously hidden leave dates.
                page.locator('[data-upgrade="advanced"]').click()
                expect(page.locator("#upgrade-advanced")).to_be_visible()
                expect(
                    page.locator('#upgrade-advanced [data-key="wife_leave_start"]')
                ).to_be_attached()
                page.locator('[data-upgrade="close"]').click()
                # First legacy conversion asks what the existing fixed cost contains.
                page.locator('[data-action="expense-apply"]').click()
                expect(page.locator("#upgrade-composition")).to_be_visible()
                page.get_by_role("button", name="지출 계획 적용", exact=True).click()
                expect(page.locator("#upgrade-composition")).not_to_be_visible()
                page.locator('[data-upgrade="replace"]').first.click()
                page.locator("#upgrade-amount").fill("150만원")
                page.locator("#replacement-preview-button").click()
                expect(page.locator("#replacement-preview table")).to_be_visible()
                page.get_by_role("button", name="반영하고 계산", exact=True).click()
                expect(page.locator("#upgrade-replace")).not_to_be_visible()
                page.locator('[data-upgrade="prepay"]').first.click()
                page.locator("#upgrade-amount").fill("500만원")
                page.get_by_role("button", name="반영하고 계산", exact=True).click()
                expect(page.locator("#upgrade-prepay")).not_to_be_visible()
                expect(page.locator("#prepayment-plan tbody tr")).to_have_count(1)
                # Save preview/confirmation and persistent values.
                page.locator("#save-button").click()
                page.get_by_role("button", name="확인하고 저장", exact=True).click()
                expect(page.locator("#save-button")).to_be_disabled()
                stored = httpx.get(base + "/api/workspaces/demo").json()
                assert stored["household"]["loan_prepayments"][0]["amount"] == 5000000
                # Named copy and comparison.
                page.locator('[data-upgrade="copy"]').click()
                page.locator("#upgrade-label").fill("비교용 가구")
                page.get_by_role("button", name="복사해 저장", exact=True).click()
                expect(page.locator("#upgrade-copy")).not_to_be_visible()
                page.locator('[data-upgrade="compare"]').click()
                expect(page.locator("#upgrade-compare")).to_be_visible()
                page.locator('input[name="compare-plan"]').first.check()
                page.get_by_role("button", name="비교", exact=True).click()
                expect(page.locator("#modal-title")).to_have_text("계획 비교 결과")
                page.locator("#modal-close").click()
                # Backup round trip is confirmed in API tests; verify UI creation.
                page.locator('[data-upgrade="backup"]').click()
                expect(page.locator("#upgrade-backup")).to_be_visible()
                backup_count = page.locator(".backup-list .history-row").count()
                page.get_by_role("button", name="현재 DB 백업", exact=True).click()
                expect(page.locator(".backup-list .history-row")).to_have_count(backup_count + 1)
                page.locator("#modal-close").click()
                # New user can create their own plan without seeded private data.
                page.locator('[data-upgrade="new"]').click()
                expect(page.locator("#upgrade-new")).to_be_visible()
                page.locator("#upgrade-label").fill("처음 만든 계획")
                page.get_by_role("button", name="다음", exact=True).click()
                page.locator("#upgrade-cash").fill("8000만원")
                page.locator("#upgrade-husband").fill("400만원")
                page.locator("#upgrade-living").fill("200만원")
                page.get_by_role("button", name="다음", exact=True).click()
                page.locator("#upgrade-price").fill("5억원")
                page.get_by_role("button", name="다음", exact=True).click()
                page.locator("#upgrade-tax").fill("123만원")
                page.locator("#upgrade-lawyer_fee").fill("120만원")
                page.locator("#upgrade-cost-preview").click()
                expect(page.locator("#upgrade-lawyer_fee")).to_be_visible()
                page.get_by_role("button", name="새 계획 저장", exact=True).click()
                expect(page.locator("#upgrade-new")).not_to_be_visible()
                expect(page.locator("#cost-tax-mode")).to_have_value("manual")
                created = next(
                    row
                    for row in httpx.get(base + "/api/workspaces").json()
                    if row["label"] == "처음 만든 계획"
                )
                new_plan = httpx.get(base + f"/api/workspaces/{created['id']}").json()
                assert new_plan["household"]["listings"][0]["acquisition_tax_amount"] == 1230000
                assert new_plan["household"]["settings"]["lawyer_fee"] == 1200000
                page.locator("#cost-tax-mode").select_option("auto")
                expect(page.locator("#field-acquisition_tax_amount")).not_to_be_visible()
                page.locator("#cost-tax-mode").select_option("manual")
                page.locator("#field-acquisition_tax_amount").fill("0")
                page.locator("#field-acquisition_tax_amount").press("Tab")
                page.locator("#field-lawyer_fee").fill("210만원")
                page.locator("#field-lawyer_fee").press("Tab")
                with page.expect_response(
                    lambda r: (
                        r.url.endswith("/api/evaluate")
                        and r.request.method == "POST"
                        and r.request.post_data_json["household"]["listings"][0].get(
                            "acquisition_tax_amount"
                        )
                        == 0
                        and r.request.post_data_json["household"]["settings"]["lawyer_fee"]
                        == 2100000
                    )
                ) as cost_response:
                    page.locator("#costs-calculate").click()
                costs = cost_response.value.json()["costs"]
                assert (
                    costs["acquisition_taxes_total"] == 0
                    and costs["registration"]["lawyer"] == 2100000
                )
                page.locator("#costs-save").click()
                page.get_by_role("button", name="확인하고 저장", exact=True).click()
                expect(page.locator("#save-button")).to_be_disabled()
                updated = httpx.get(base + f"/api/workspaces/{created['id']}").json()
                assert updated["household"]["listings"][0]["acquisition_tax_amount"] == 0
                assert updated["household"]["settings"]["lawyer_fee"] == 2100000
                page.screenshot(path=str(ROOT / "data/purchase-costs.local.png"), full_page=True)
                # Desktop and mobile result explanations.
                page.locator('a[href="#plan"]:visible').first.click()
                page.locator('[data-action="inspect-minimum"]').click()
                expect(page.locator(".cash-details")).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 844})
                for route in ("plan", "costs", "funds", "support", "settings", "ledger"):
                    page.locator(f'a[href="#{route}"]:visible').first.click()
                    assert page.evaluate("()=>document.documentElement.scrollWidth<=innerWidth")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.locator('a[href="#settings"]:visible').first.click()
                salary_group = page.locator(".settings-group").filter(
                    has=page.locator("#field-husband_net_pay")
                )
                if not salary_group.evaluate("e=>e.open"):
                    salary_group.locator("summary").click()
                page.locator("#field-husband_net_pay").fill("777만원")
                page.locator("#field-husband_net_pay").press("Tab")
                # beforeunload both warns and flushes the draft, even on an immediate reload.
                page.on("dialog", lambda dialog: dialog.accept())
                page.reload()
                expect(page.locator("#modal-title")).to_have_text("임시 초안을 복구할까요?")
                page.get_by_role("button", name="초안 복구", exact=True).click()
                expect(page.locator("#field-husband_net_pay")).to_have_value("777")
                # Restored input is still a draft, not silently saved.
                assert not page.locator("#save-button").is_disabled()
                assert not errors, errors
                browser.close()
            print(
                "PASS: input errors, legacy conversion, expense replacement, partial repayment, settings, save, copy/compare, backup, new plan, explanations, mobile"
            )
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
