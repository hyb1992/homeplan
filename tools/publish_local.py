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

from homeplan.updates import version_tuple

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
            content = response.read()
            return json.loads(content) if content else {}

    def git(*command: str, cwd: Path = ROOT) -> str:
        return subprocess.check_output(["git", *command], cwd=cwd, text=True).strip()

    revision = git("rev-parse", "HEAD")
    remote_revision = git("ls-remote", "origin", "refs/heads/main").split()[0]
    if revision != remote_revision:
        raise RuntimeError(
            "원격 main의 최신 소스를 먼저 받아 검증·빌드하세요. 오래된 소스의 게시는 중단했습니다."
        )
    if api("")["private"]:
        raise RuntimeError("공개 배포 저장소인지 먼저 확인하세요")
    if args.windows:
        metadata = json.loads((ROOT / "data/release-build.local.json").read_text("utf-8"))
        folder = Path(metadata["directory"])
        manifest = json.loads((folder / "release.json").read_text("utf-8"))
        if manifest["build"] != revision:
            raise RuntimeError("현재 공개 commit에서 다시 빌드하세요")
        version = importlib.metadata.version("homeplan")
        if manifest["version"] != version:
            raise RuntimeError("빌드와 설치된 패키지 버전이 다릅니다. 다시 빌드하세요.")
        releases = api("/releases?per_page=100")
        if any(
            not release.get("draft")
            and not release.get("prerelease")
            and version_tuple(str(release.get("tag_name", ""))) > version_tuple(version)
            for release in releases
        ):
            raise RuntimeError(
                "더 높은 버전이 이미 게시되어 있어 이전 버전의 최신 배포 지정을 중단했습니다."
            )
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
            ("SHA256SUMS.txt", "text/plain"),
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
        api("/pages/builds", "POST")
        print("Pages initial publication requested: https://hyb1992.github.io/homeplan/")


if __name__ == "__main__":
    main()
