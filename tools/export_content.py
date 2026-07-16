#!/usr/bin/env python3
"""Export authored content from the database to the private content repo.

NOT a management command (repo rule) — a tools script wrapping
core_management.content_export. Writes one JSON file per content model
to CONTENT_REPO_PATH/fixtures/<app_label>/<model_name>.json.

Usage:
    uv run python tools/export_content.py            # export to content repo
    uv run python tools/export_content.py --check    # dry-run: show what would be written
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _load_dotenv_path() -> str | None:
    """Read CONTENT_REPO_PATH from the environment, falling back to src/.env."""
    value = os.environ.get("CONTENT_REPO_PATH")
    if value:
        return value
    env_file = SRC_ROOT / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("CONTENT_REPO_PATH="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _configure_django() -> None:
    """Import + configure Django."""
    import django  # noqa: PLC0415

    os.chdir(SRC_ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    django.setup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="dry-run: show what would be written, write nothing",
    )
    parser.add_argument(
        "--content-path",
        default=None,
        help="override the content checkout location (default: CONTENT_REPO_PATH)",
    )
    args = parser.parse_args()

    content_path = args.content_path or _load_dotenv_path()
    if not content_path:
        print(
            "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
            "local checkout of the private content repository.",
            file=sys.stderr,
        )
        return 2
    content_root = Path(content_path).expanduser()
    if not content_root.is_dir():
        print(f"Content path does not exist: {content_root}", file=sys.stderr)
        return 2

    _configure_django()

    from core_management.content_export import (  # noqa: PLC0415
        CONTENT_MODELS,
        export_to_content_repo,
    )

    if args.check:
        _run_check(CONTENT_MODELS)
        return 0

    result = export_to_content_repo(content_root)
    for path in result.written:
        print(f"wrote {path.relative_to(content_root)}")
    if result.skipped:
        print(f"\nSkipped {len(result.skipped)} model(s) with 0 rows:")
        for label in result.skipped:
            print(f"  {label}")
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  {err}", file=sys.stderr)
    print(f"OK: {result.total_records} records -> {len(result.written)} file(s).")
    return 0 if not result.errors else 1


def _run_check(content_models: frozenset[str]) -> None:
    """Dry-run: count rows per model, write nothing."""
    from django.apps import apps  # noqa: PLC0415

    total = 0
    for model_label in sorted(content_models):
        app_label, model_name = model_label.split(".")
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            print(f"  {model_label}: MODEL NOT FOUND")
            continue
        count = model.objects.count()
        if count > 0:
            print(f"  {model_label}: {count} rows -> fixtures/{app_label}/{model_name}.json")
            total += count
        else:
            print(f"  {model_label}: 0 rows (skip)")
    print(f"\nTotal: {total} records across {len(content_models)} content models.")
    print("Nothing written (--check).")


if __name__ == "__main__":
    raise SystemExit(main())
