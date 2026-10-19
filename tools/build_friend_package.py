"""개인 폴더를 읽지 않고 공개 리소스만으로 Windows 전달용 패키지를 만든다."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def license_files(destination: Path) -> None:
    queue = ["homeplan", "pyinstaller"]
    seen: set[str] = set()
    notices = []
    while queue:
        name = queue.pop()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        dist = importlib.metadata.distribution(name)
        notices.append(f"{dist.metadata['Name']} {dist.version}")
        for item in dist.files or []:
            if any(word in item.name.lower() for word in ("license", "copying", "notice")):
                source = Path(dist.locate_file(item))
                if source.is_file() and source.suffix.lower() not in {".py", ".pyc", ".pyd"}:
                    target = destination / "licenses" / name / item.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        for item in dist.requires or []:
            requirement = Requirement(item)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                queue.append(requirement.name)
    (destination / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(sorted(notices)), "utf-8")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows 실행 패키지는 Windows에서 빌드하세요.")
    version = importlib.metadata.version("homeplan")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = ROOT / "dist" / f"friend-{version}-{stamp}"
    work = ROOT / "build" / f"friend-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    build = (
        os.environ.get("GITHUB_SHA")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    )
    build_info = work / "build-info.json"
    build_info.write_text(json.dumps({"build": build, "version": version}), "utf-8")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "HomePlan",
        "--icon",
        str(ROOT / "web/homeplan.ico"),
        "--distpath",
        str(output),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        "--paths",
        str(ROOT / "src"),
        "--add-data",
        f"{ROOT / 'web'};homeplan/web_assets",
        "--add-data",
        f"{ROOT / 'data/rules'};homeplan/bundled_rules",
        "--add-data",
        f"{ROOT / 'tests/fixtures/synthetic_household.json'};homeplan",
        "--add-data",
        f"{build_info};homeplan",
        "--collect-submodules",
        "uvicorn",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "playwright",
        "--exclude-module",
        "hypothesis",
        "--exclude-module",
        "tkinter",
        str(ROOT / "tools/portable_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    app = output / "HomePlan"
    (app / "fresh-start.flag").write_text(
        "Create an empty plan only when no database exists.\n", "utf-8"
    )
    for name, setting in {
        "업데이트 없이 실행.cmd": "HOMEPLAN_DISABLE_UPDATES=1",
        "기본 브라우저로 실행.cmd": "HOMEPLAN_BROWSER_MODE=default",
    }.items():
        (app / name).write_text(
            f'@echo off\nset "{setting}"\nstart "" "%~dp0HomePlan.exe"\n', encoding="ascii"
        )
    (app / "처음 읽어주세요.txt").write_text(
        "우리집 매수계획 · 친구 전달용\n\n"
        "1. ZIP 전체를 문서 또는 바탕화면의 새 폴더에 압축 해제하세요.\n"
        "2. HomePlan 폴더의 HomePlan.exe를 실행하세요. Python 설치는 필요하지 않습니다.\n"
        "3. 처음 열리는 새 계획 입력에서 본인의 현금·소득·생활비·일정을 입력하세요.\n"
        "4. 입력을 바꾼 뒤 변경사항 저장을 눌러 보관하세요.\n\n"
        "실행 파일만 따로 꺼내지 말고 _internal 폴더와 함께 두세요.\n"
        "Windows 64비트용이며 화면은 Edge 또는 Chrome으로 열립니다.\n"
        "본인의 데이터와 백업은 이 폴더의 data에 새로 만들어집니다.\n"
        "재실행할 때 초기화되지 않습니다. 폴더를 옮길 때 data도 함께 옮기세요.\n"
        "가상 테스트는 공개 예시이며 전달자의 개인 데이터는 포함하지 않습니다.\n"
        "앱이 열린 뒤 새 버전을 백그라운드에서 자동으로 받아 검증합니다.\n"
        "새 버전은 versions에 별도 설치되며 기존 data 폴더·저장 이력·프로필은 유지됩니다.\n"
        "편집 중에는 적용을 미룹니다. 저장 후 자동 적용하거나 다음 실행에서 사용합니다.\n\n"
        "상단 백업·복구에서 별도 백업 폴더를 지정할 수 있습니다.\n",
        "utf-8-sig",
    )
    (app / "사용안내.md").write_text(
        "# Windows 실행 파일 버전\n\nHomePlan.exe를 실행하세요. Python이나 uv 설치는 필요하지 않습니다.\n"
        "아래 설치 명령은 소스로 개발할 때만 사용합니다. 재전달할 때는 처음 받은 ZIP을 전달하세요.\n\n"
        + (ROOT / "README_PUBLIC.md").read_text("utf-8"),
        "utf-8",
    )
    license_files(app)
    paths = sorted(path for path in app.rglob("*") if path.is_file())
    forbidden = []
    for path in paths:
        relative = path.relative_to(app)
        if (
            path.suffix.lower() in {".sqlite", ".db", ".xlsx", ".xls", ".bak"}
            or ".local." in path.name
            or ".git" in relative.parts
            or "backups" in relative.parts
            or path.name in {"scenarios.json", "units.json"}
        ):
            forbidden.append(str(relative))
    if forbidden:
        raise SystemExit(f"전달 금지 자료가 포함되어 있습니다: {forbidden}")
    manifest = {
        "version": version,
        "files": len(paths),
        "personal_data_included": False,
        "initial_state": "empty-plan",
        "platform": "Windows x64",
    }
    (app / "package-info.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    archive = ROOT / "dist" / f"우리집_친구전달용_{version}_{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(output))
    print(f"PACKAGE={archive}", flush=True)
    print(f"EXECUTABLE={app / 'HomePlan.exe'}", flush=True)
    (ROOT / "data/friend-package.local.json").write_text(
        json.dumps({"archive": str(archive), "executable": str(app / "HomePlan.exe")}), "utf-8"
    )
    release_dir = output / "release"
    release_dir.mkdir()
    stable_archive = release_dir / "HomePlan-Windows-x64.zip"
    shutil.copy2(archive, stable_archive)
    (release_dir / "release.json").write_text(
        json.dumps(
            {
                "build": build,
                "version": version,
                "sha256": hashlib.sha256(stable_archive.read_bytes()).hexdigest(),
            }
        ),
        "utf-8",
    )
    (release_dir / "SHA256SUMS.txt").write_text(
        hashlib.sha256(stable_archive.read_bytes()).hexdigest() + "  HomePlan-Windows-x64.zip\n",
        "ascii",
    )
    (ROOT / "data/release-build.local.json").write_text(
        json.dumps({"directory": str(release_dir)}), "utf-8"
    )


if __name__ == "__main__":
    main()
