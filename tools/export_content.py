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

from core_management.content_repo import load_dotenv_content_path  # noqa: E402


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

    content_path = args.content_path or load_dotenv_content_path()
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

    from core_management.content_export import CONTENT_MODELS  # noqa: PLC0415

    if args.check:
        _run_check(CONTENT_MODELS)
        _run_grid_check()
        return 0

    model_ok = _run_model_export(content_root)
    grid_ok = _run_grid_export(content_root)
    return 0 if (model_ok and grid_ok) else 1


def _run_model_export(content_root: Path) -> bool:
    """Export content models; print the report. Returns True iff no errors."""
    from core_management.content_export import export_to_content_repo  # noqa: PLC0415

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
    return not result.errors


def _run_grid_export(content_root: Path) -> bool:
    """Export grid bundles; print the report. Returns True iff no errors."""
    from core_management.grid_export import export_grid_bundles  # noqa: PLC0415

    grid_result = export_grid_bundles(content_root)
    for path in grid_result.written:
        print(f"wrote {path.relative_to(content_root)}")
    if grid_result.reports:
        print(f"\nGrid export reports ({len(grid_result.reports)}):")
        for line in grid_result.reports:
            print(f"  {line}")
    if grid_result.errors:
        print(f"\nGrid export errors ({len(grid_result.errors)}):")
        for err in grid_result.errors:
            print(f"  {err}", file=sys.stderr)
    print(
        f"OK: grid — {grid_result.area_count} area(s), {grid_result.room_count} room(s) -> "
        f"{len(grid_result.written)} file(s)."
    )
    return not grid_result.errors


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


def _run_grid_check() -> None:
    """Dry-run: count authored areas/rooms, write nothing."""
    from django.db.models import Count  # noqa: PLC0415

    from core_management.grid_export import find_unhoused_authored_rooms  # noqa: PLC0415
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    areas = list(Area.objects.filter(origin=GridOrigin.AUTHORED).order_by("slug"))
    print(f"\nGrid: {len(areas)} authored area(s):")
    room_counts_by_area = {
        row["area_id"]: row["n"]
        for row in RoomProfile.objects.filter(area__in=areas, origin=GridOrigin.AUTHORED)
        .values("area_id")
        .annotate(n=Count("pk"))
    }
    for area in areas:
        room_count = room_counts_by_area.get(area.pk, 0)
        slug = area.slug or "MISSING SLUG"
        print(f"  {slug}: {room_count} authored room(s) -> fixtures/grid/{slug}.json")

    unhoused = find_unhoused_authored_rooms()
    if unhoused:
        print(f"\nWARNING: {len(unhoused)} unhoused AUTHORED room(s) — export will FAIL:")
        for line in unhoused:
            print(f"  {line}", file=sys.stderr)

    print("Nothing written (--check).")


if __name__ == "__main__":
    raise SystemExit(main())
