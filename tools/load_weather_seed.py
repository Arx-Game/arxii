#!/usr/bin/env python3
"""Re-seed the weather corpus idempotently from the seed-data store (#1522).

NOT a management command (repo rule) — a tools script wrapping ``world.weather.seed``. Unlike
``loaddata``, this UPSERTs by natural identity, so it both seeds a fresh DB and re-seeds an
edited corpus without duplicating the keyless ``WeatherEmit`` rows (see ``seed.py`` docstring).

The weather fixtures live in the seed-data store (gitignored / a separate repo), located via the
``WEATHER_SEED_PATH`` env var (set it in ``src/.env``) or ``--fixtures-dir``. The directory holds
``weather_types.json``, ``weather_type_exposures.json``, ``weather_emits.json``, and optionally
``feast_days.json`` — the same Django-fixture files ``loaddata`` consumes for a fresh seed.

Usage:
    uv run python tools/load_weather_seed.py                          # uses WEATHER_SEED_PATH
    uv run python tools/load_weather_seed.py --fixtures-dir <path>
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _seed_path_from_env() -> str | None:
    """Read WEATHER_SEED_PATH from the environment, falling back to src/.env."""
    value = os.environ.get("WEATHER_SEED_PATH")
    if value:
        return value
    env_file = SRC_ROOT / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("WEATHER_SEED_PATH="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-dir",
        default=None,
        help="weather fixtures directory (default: WEATHER_SEED_PATH)",
    )
    args = parser.parse_args()

    seed_path = args.fixtures_dir or _seed_path_from_env()
    if not seed_path:
        print(
            "WEATHER_SEED_PATH is not set. Add it to src/.env pointing at your local checkout of "
            "the weather seed-data directory, or pass --fixtures-dir.",
            file=sys.stderr,
        )
        return 2
    fixtures_dir = Path(seed_path).expanduser()
    if not fixtures_dir.is_dir():
        print(f"Fixtures directory does not exist: {fixtures_dir}", file=sys.stderr)
        return 2

    # Upsert path (NOT loaddata — see seed.py docstring). Needs the Django env; settings
    # resolve .env relative to src/.
    import django  # noqa: PLC0415

    os.chdir(SRC_ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    django.setup()
    from world.weather.seed import load_weather_seed  # noqa: PLC0415

    counts = load_weather_seed(fixtures_dir)
    for model, (created, updated) in counts.items():
        print(f"{model}: {created} created, {updated} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
