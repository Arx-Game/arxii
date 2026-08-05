#!/usr/bin/env python3
"""Report how much player-facing prose is still a placeholder (#2980).

Runs against a content-repo checkout with no database:

    uv run python tools/prose_report.py
    uv run python tools/prose_report.py --content-path /path/to/checkout
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core_management.content_repo import load_dotenv_content_path  # noqa: E402
from core_management.prose_report import render_report, scan_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-path", default=None, help="Content repo checkout path.")
    args = parser.parse_args()

    raw = args.content_path or load_dotenv_content_path()
    if not raw:
        print("CONTENT_REPO_PATH is not set and --content-path was not given.", file=sys.stderr)
        return 2
    root = Path(raw).expanduser()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    for line in render_report(scan_corpus(root)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
