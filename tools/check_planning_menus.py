"""로컬/정적 웹에서 새 메뉴와 엑셀 가져오기를 가상 입력으로 검증한다."""

import argparse
import functools
import http.server
import json
import os
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def check(url: str, folder: Path) -> None:
    workbook = runpy.run_path(str(ROOT / "tests/unit/test_menu_features.py"))["make_excel"]()
    excel = folder / "synthetic.xlsx"
    excel.write_bytes(workbook)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge" if os.name == "nt" else None)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('[data-upgrade="advanced"]')).to_be_visible(timeout=120000)
        if page.locator("#modal").evaluate("e=>e.open"):
            page.locator("#modal-close").click()
        data = json.loads((ROOT / "tests/fixtures/synthetic_household.json").read_text("utf-8"))
        key = page.evaluate(
            """async h=>{
            const r=await fetch('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:'MENU_SYNTHETIC_ONLY',household:h})});
            const plan=await r.json();localStorage.setItem(`homeplan-last-workspace:${location.origin}`,plan.id);return plan.id;
        }""",
            data,
        )
        page.reload()
        expect(page.locator(".runtime-summary")).to_be_visible(timeout=120000)
        page.locator('a[href="#leave"]:visible').first.click()
        page.locator("#field-birth_date").fill("2027-04-15")
        page.locator("#field-wife_leave_start").fill("2027-05-01")
        page.locator("#field-wife_leave_months").fill("6")
        page.locator("#field-wife_ordinary_wage").fill("300만원")
        page.locator('[data-menu="calculate"]').click()
        expect(page.locator(".recalculate-note")).to_have_count(0)
        page.locator('a[href="#banks"]:visible').first.click()
        page.locator('[data-menu="bank-add"]').click()
        page.locator("#bank-name").fill("가상은행")
        page.locator("#bank-date").fill("2026-10-19")
        first = page.locator(".bank-option-fields").first
        first.get_by_label("연 금리 · %", exact=True).fill("4.2")
        first.get_by_label("상담 한도", exact=True).fill("3억원")
        page.locator("#bank-add-option").click()
        second = page.locator(".bank-option-fields").nth(1)
        second.get_by_label("연 금리 · %", exact=True).fill("4.7")
        second.get_by_label("상담 한도", exact=True).fill("3억원")
        page.locator('#bank-form button[type="submit"]').click()
        expect(page.locator("#bank-form")).not_to_be_visible()
        expect(page.locator('[data-menu="bank-select"]')).to_have_count(2)
        page.locator('[data-menu="bank-select"]').first.click()
        expect(page.locator('[data-menu="bank-select"]').first).to_have_text("적용 중")
        page.locator("#save-button").click()
        expect(page.locator("#modal")).to_be_visible()
        page.get_by_role("button", name="확인하고 저장", exact=True).click()
        expect(page.locator("#save-state")).to_have_text("저장된 계획")
        saved = page.evaluate("async key=>(await fetch(`/api/workspaces/${key}`)).json()", key)
        assert saved["household"]["settings"]["mortgage_rate"] == "0.042"
        assert saved["household"]["settings"]["wife_leave_months"] == 6
        assert len(saved["household"]["bank_quotes"][0]["options"]) == 2
        page.locator('a[href="#repayment"]:visible').first.click()
        expect(page.locator("#repayment-table tbody tr")).to_have_count(360)
        with page.expect_download() as download:
            page.locator("#repayment-download").click()
        assert "상환 원금" in Path(download.value.path()).read_text("utf-8-sig")
        page.locator("#repayment-year").select_option(index=1)
        assert page.locator("#repayment-table tbody tr").count() <= 12
        page.locator('a[href="#banks"]:visible').first.click()
        page.locator('[data-menu="bank-edit"]').click()
        page.locator("#bank-options [data-bank-remove]").last.click()
        page.locator('#bank-form button[type="submit"]').click()
        expect(page.locator('[data-menu="bank-select"]')).to_have_count(1)
        page.locator('[data-menu="bank-delete"]').click()
        page.get_by_role("button", name="삭제", exact=True).last.click()
        expect(page.locator(".bank-record")).to_have_count(0)
        page.locator('a[href="#import"]:visible').first.click()
        page.locator("#excel-file").set_input_files(excel)
        page.locator("#excel-mode").select_option("merge")
        page.locator('#excel-form button[type="submit"]').click()
        expect(page.locator("#excel-apply")).to_be_visible(timeout=120000)
        # Preview does not change the saved revision or bank records.
        untouched = page.evaluate("async key=>(await fetch(`/api/workspaces/${key}`)).json()", key)
        assert untouched == saved
        page.locator("#excel-apply").click()
        expect(page.locator('a[href="#plan"].active:visible').first).to_be_visible()
        page.locator('a[href="#funds"]:visible').first.click()
        expect(page.locator("#content")).to_contain_text("가상 예금")
        page.locator('a[href="#settings"]:visible').first.click()
        assert (
            page.locator("#field-husband_net_pay").evaluate(
                "e=>Number(e.value.replaceAll(',',''))*Number(document.querySelector('[data-unit-for=field-husband_net_pay]').value)"
            )
            == data["settings"]["husband_net_pay"]
        )
        page.locator('a[href="#import"]:visible').first.click()
        page.locator("#excel-file").set_input_files(excel)
        page.locator('#excel-form button[type="submit"]').click()
        expect(page.locator("#excel-apply")).to_be_visible(timeout=120000)
        page.locator("#excel-apply").click()
        page.get_by_role("button", name="새 계획 저장", exact=True).click()
        expect(page.locator("#save-state")).to_have_text("저장된 계획")
        expect(page.locator("#page-title")).to_have_text("매수 계획을 한눈에")
        # Original workspace and history remain after creating the imported plan.
        assert (
            page.evaluate("async key=>(await fetch(`/api/workspaces/${key}`)).json()", key) == saved
        )
        page.reload()
        expect(page.locator("#content")).to_contain_text("가상 매물", timeout=120000)
        page.set_viewport_size({"width": 390, "height": 844})
        for route in ["leave", "repayment", "banks", "import"]:
            page.locator(f'a[href="#{route}"]:visible').first.click()
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        assert not errors, errors
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator('a[href="#leave"]:visible').first.click()
        page.screenshot(path=ROOT / "data/planning-menus.local.png")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=Path)
    pages = parser.parse_args().pages
    with tempfile.TemporaryDirectory(prefix="homeplan-menu-qa-") as folder:
        seed = Path(folder)
        if pages:

            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *_args: object) -> None:
                    pass

            handler = functools.partial(QuietHandler, directory=str(pages.resolve().parent))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                check(f"http://127.0.0.1:{server.server_port}/{pages.name}/", seed)
            finally:
                server.shutdown()
        else:
            (seed / "data").mkdir()
            (seed / "data/demo.local.json").write_bytes(
                (ROOT / "tests/fixtures/synthetic_household.json").read_bytes()
            )
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "homeplan.server",
                    "--port",
                    str(port),
                    "--db",
                    str(seed / "data/qa.sqlite"),
                    "--seed-root",
                    str(seed),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            url = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    try:
                        if httpx.get(url + "/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                check(url, seed)
            finally:
                process.terminate()
                process.wait(timeout=10)
    print(
        "PASS: leave, repayment CSV, bank CRUD/select, Excel preview/merge/new plan, preservation, mobile"
    )


if __name__ == "__main__":
    main()
