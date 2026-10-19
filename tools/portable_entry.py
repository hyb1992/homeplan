"""Windows 배포 실행 진입점. --serve는 동일 실행 파일의 로컬 서버 모드다."""

import multiprocessing
import os
import sys
from pathlib import Path


def main() -> None:
    multiprocessing.freeze_support()
    if "--restart-update" in sys.argv:
        from homeplan.updates import restart_server

        restart_server(int(sys.argv[sys.argv.index("--restart-update") + 1]))
        return
    if "--serve" in sys.argv:
        sys.argv.remove("--serve")
        root = Path(
            os.environ.get("HOMEPLAN_DATA_ROOT", str(Path(sys.executable).resolve().parent))
        )
        if "--seed-root" in sys.argv:
            root = Path(sys.argv[sys.argv.index("--seed-root") + 1]).resolve()
        logs = root / "data/gui.local.log"
        logs.parent.mkdir(parents=True, exist_ok=True)
        if sys.stdout is None:
            sys.stdout = logs.open("a", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = sys.stdout
        from homeplan.server import main as serve

        serve()
    else:
        if not os.environ.get("HOMEPLAN_MANAGED_CHILD"):
            from homeplan.updates import managed_launch

            os.environ.setdefault("HOMEPLAN_BASE_EXE", str(Path(sys.executable).resolve()))
            managed_launch(
                Path(
                    os.environ.get("HOMEPLAN_DATA_ROOT", str(Path(sys.executable).resolve().parent))
                )
            )
            return
        from homeplan.gui_launcher import main as launch

        launch()


if __name__ == "__main__":
    main()
