"""로컬에서 검증한 공개 빌드의 초기 게시. 토큰은 Git credential helper에서만 읽는다."""

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "hyb1992/homeplan"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", action="store_true")
    parser.add_argument("--windows", action="store_true")
    args = parser.parse_args()
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "GCM_INTERACTIVE": "never", "GIT_TERMINAL_PROMPT": "0"},
    )
    credential = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    headers = {
        "Authorization": "Bearer " + credential["password"],
        "User-Agent": "HomePlan-Publisher",
        "Accept": "application/vnd.github+json",
    }

    def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
        request = urllib.request.Request(
            "https://api.github.com/repos/" + REPO + path,
            headers=headers,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def git(*command: str, cwd: Path = ROOT) -> str:
        return subprocess.check_output(["git", *command], cwd=cwd, text=True).strip()

    revision = git("rev-parse", "HEAD")
    if api("")["private"]:
        raise RuntimeError("공개 배포 저장소인지 먼저 확인하세요")
    if args.windows:
        metadata = json.loads((ROOT / "data/release-build.local.json").read_text("utf-8"))
        folder = Path(metadata["directory"])
        manifest = json.loads((folder / "release.json").read_text("utf-8"))
        if manifest["build"] != revision:
            raise RuntimeError("현재 공개 commit에서 다시 빌드하세요")
        version = importlib.metadata.version("homeplan")
        tag = f"v{version}-initial-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        release = api(
            "/releases",
            "POST",
            {
                "tag_name": tag,
                "target_commitish": revision,
                "name": f"HomePlan {version}",
                "body": (ROOT / "RELEASE_NOTES.md").read_text("utf-8"),
                "draft": True,
            },
        )
        for name, content_type in [
            ("HomePlan-Windows-x64.zip", "application/zip"),
            ("release.json", "application/json"),
        ]:
            url = release["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(name)
            request = urllib.request.Request(
                url,
                data=(folder / name).read_bytes(),
                method="POST",
                headers={**headers, "Content-Type": content_type},
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                json.load(response)
        published = api(
            f"/releases/{release['id']}", "PATCH", {"draft": False, "make_latest": "true"}
        )
        print("Windows release:", published["html_url"])
    if args.pages:
        site = Path(
            json.loads((ROOT / "data/pages-build.local.json").read_text("utf-8"))["directory"]
        )
        with tempfile.TemporaryDirectory(prefix="homeplan-pages-publish-") as directory:
            destination = Path(directory)
            git("init", "-b", "gh-pages", cwd=destination)
            git("remote", "add", "origin", f"https://github.com/{REPO}.git", cwd=destination)
            if git("ls-remote", "--heads", "origin", "gh-pages", cwd=destination):
                git("fetch", "--depth=1", "origin", "gh-pages", cwd=destination)
                git("checkout", "-B", "gh-pages", "FETCH_HEAD", cwd=destination)
            shutil.copytree(site, destination, dirs_exist_ok=True)
            git("add", ".", cwd=destination)
            git(
                "-c",
                "user.name=HomePlan",
                "-c",
                "user.email=homeplan@local",
                "commit",
                "-m",
                f"Publish public web {revision[:7]}",
                cwd=destination,
            )
            git("push", "origin", "gh-pages", cwd=destination)
        api(
            "/pages", "PUT", {"build_type": "legacy", "source": {"branch": "gh-pages", "path": "/"}}
        )
        print("Pages initial publication requested: https://hyb1992.github.io/homeplan/")


if __name__ == "__main__":
    main()
