"""Stable root entry point for Launcher API v1 and frozen Streamlit workers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def run_streamlit_worker() -> int:
    try:
        from streamlit.web import cli as streamlit_cli
    except ImportError as error:
        sys.stderr.write(f"[streamlit-worker] import failed: {error}\n")
        return 2
    sys.argv = ["streamlit", *sys.argv[2:]]
    try:
        streamlit_cli.main()
    except SystemExit as error:
        return int(error.code or 0)
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--streamlit-worker":
        return run_streamlit_worker()
    from guess_history.launcher.main import main as launcher_main

    return launcher_main()


if __name__ == "__main__":
    raise SystemExit(main())
