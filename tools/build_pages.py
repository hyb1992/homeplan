"""허용 목록으로 GitHub Pages 배포 파일만 생성한다. 사용자 데이터는 읽지 않는다."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    revision = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (ROOT / "dist").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"pages-{revision}-", dir=ROOT / "dist"))
    for path in (ROOT / "web").iterdir():
        if path.is_file() and path.suffix in {".html", ".js", ".mjs", ".css", ".svg", ".ico"}:
            shutil.copy2(path, output / path.name)
    for path in (ROOT / "web/browser").iterdir():
        shutil.copy2(path, output / path.name)
    archive = output / "engine.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted((ROOT / "src/homeplan").rglob("*.py")):
            package.write(path, path.relative_to(ROOT / "src"))
        for path in sorted((ROOT / "data/rules").glob("*.yaml")):
            package.write(path, "homeplan/bundled_rules/" + path.name)
        package.write(
            ROOT / "tests/fixtures/synthetic_household.json", "homeplan/demo_household.json"
        )
    fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
    assets = [path.name for path in output.iterdir() if path.suffix in {".js", ".mjs", ".css"}]
    for path in output.iterdir():
        if path.suffix in {".js", ".mjs"}:
            content = path.read_text("utf-8")
            for asset in assets:
                content = content.replace(f"'./{asset}'", f"'./{asset}?v={fingerprint}'")
            path.write_text(content, "utf-8")
    index = (output / "index.html").read_text("utf-8")
    index = index.replace('href="/', 'href="./').replace(
        '<script type="module" src="/app.js"></script>',
        f'<script type="module" src="./browser-boot.mjs?v={fingerprint}"></script>',
    )
    index = index.replace('src="/startup.js"', f'src="./startup.js?v={fingerprint}"')
    index = index.replace('href="./styles.css"', f'href="./styles.css?v={fingerprint}"')
    (output / "index.html").write_text(index, "utf-8")
    (output / ".nojekyll").touch()
    (output / "build.json").write_text(
        json.dumps({"revision": revision, "engine": fingerprint}), "utf-8"
    )
    (ROOT / "data/pages-build.local.json").write_text(
        json.dumps({"directory": str(output)}), "utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
