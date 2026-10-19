"""공개 파일 허용 목록으로 별도 Git 루트를 만든다. 기존 이력/데이터를 복사하지 않는다."""

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL = {
    ".gitignore",
    ".pre-commit-config.yaml",
    "README_PUBLIC.md",
    "RELEASE_NOTES.md",
    "pyproject.toml",
    "uv.lock",
}
DIRECTORIES = {"src", "web", "tools", ".github"}


def allowed(name: str) -> bool:
    path = Path(name)
    if ".local." in name or path.suffix.lower() in {".sqlite", ".db", ".xlsx", ".xls", ".bak"}:
        return False
    return (
        name in TOP_LEVEL
        or path.parts[0] in DIRECTORIES
        or name.startswith("data/rules/")
        and path.suffix == ".yaml"
        or name.startswith("tests/")
        and path.suffix in {".py", ".mjs"}
        or name
        in {
            "tests/fixtures/synthetic_household.json",
            "tests/golden/synthetic.json",
            "tests/golden/units_public.json",
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    destination = parser.parse_args().destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in names:
        if name and allowed(name):
            source = ROOT / name
            if source.is_symlink():
                raise ValueError("공개 소스에 심볼릭 링크가 있습니다")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.copy2(destination / "README_PUBLIC.md", destination / "README.md")
    (destination / "AGENTS.md").write_text(
        "# Repository guidance\n\n"
        "Keep financial inputs, exports, databases, backups and browser profiles out of Git.\n"
        "Use synthetic fixtures for tests. SQLite is authoritative; Excel is import-only.\n"
        "Keep core calculations free of I/O and clocks. Use integer won and Decimal.\n"
        "Validate with uv run ruff check ., uv run ruff format --check ., "
        "uv run mypy src/homeplan, uv run pytest -q, and node --test tests/web/test_form_inputs.mjs.\n"
        "Publish Pages and Windows manually after checks. Detect new releases but download only on user click; never auto-install. Preserve user data.\n",
        "utf-8",
    )
    print(f"Public source: {destination}; no original Git history copied")


if __name__ == "__main__":
    main()
