"""정적 서버만 띄워 WASM 계산·저장·재로드·충돌·내보내기를 검증한다."""

import argparse
import functools
import http.server
import json
import os
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    root = parser.parse_args().directory.resolve()
    requests = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            requests.append(self.path)
            super().do_GET()

    handler = functools.partial(Handler, directory=str(root.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/{root.name}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**({"channel": "msedge"} if os.name == "nt" else {}))
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            sent = []
            page.on("request", lambda request: sent.append((request.url, request.post_data)))
            page.goto(url)
            expect(page.locator("#upgrade-new")).to_be_visible(timeout=120000)
            page.locator("#upgrade-label").fill("BROWSER_SYNTHETIC_ONLY")
            page.get_by_role("button", name="다음", exact=True).click()
            page.locator("#upgrade-cash").fill("1234만원")
            page.locator("#upgrade-husband").fill("400만원")
            page.locator("#upgrade-living").fill("200만원")
            page.get_by_role("button", name="다음", exact=True).click()
            page.locator("#upgrade-price").fill("5억원")
            page.get_by_role("button", name="새 계획 저장", exact=True).click()
            expect(page.locator("#upgrade-new")).not_to_be_visible(timeout=30000)
            request = """async ({path,body,method})=>{
                const r=await fetch(path,{method:method||'GET',body:body?JSON.stringify(body):undefined});
                return {status:r.status,data:await r.json()};
            }"""

            def api(path: str, body: dict | None = None, method: str = "GET") -> dict:
                return page.evaluate(request, {"path": path, "body": body, "method": method})

            workspaces = api("/api/workspaces")["data"]
            key = next(row["id"] for row in workspaces if row["label"] == "BROWSER_SYNTHETIC_ONLY")
            stored = api(f"/api/workspaces/{key}")["data"]
            assert stored["household"]["fund_events"][0]["value"] == 12340000
            assert api("/api/evaluate", {"household": stored["household"]}, "POST")["status"] == 200
            with page.expect_download() as download:
                page.locator("#export-button").click()
            assert json.loads(Path(download.value.path()).read_text("utf-8")) == stored["household"]
            candidate = json.loads(json.dumps(stored["household"]))
            candidate["settings"]["husband_net_pay"] = 4100000
            payload = {"household": candidate, "revision": stored["revision"]}
            assert api(f"/api/workspaces/{key}/preview", payload, "POST")["status"] == 200
            assert api(f"/api/workspaces/{key}", payload, "PUT")["status"] == 200
            assert api(f"/api/workspaces/{key}", payload, "PUT")["status"] == 409
            assert api("/api/backups", {}, "POST")["status"] == 200
            page.reload()
            expect(page.locator("#save-state")).to_contain_text("저장된", timeout=120000)
            assert (
                api(f"/api/workspaces/{key}")["data"]["household"]["settings"]["husband_net_pay"]
                == 4100000
            )
            assert not errors, errors
            assert not any("/api/" in path for path in requests), requests
            assert not any(body for _, body in sent), sent
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(
        "PASS: static subpath, browser-only engine, persistence, preview/save/conflict, export, backup; no financial network requests"
    )


if __name__ == "__main__":
    main()
