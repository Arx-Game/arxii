"""Weather content cluster (#2845 gap close).

The authored weather corpus — types, exposures, shelters, the transition graph
(ADR-0181), feast days — shipped with only an out-of-band loader
(``tools/load_weather_seed.py``) and no cluster entry, so pressing the Big
Button gave you the ``weather.roll`` cron running against an empty transition
graph: weather that could never change.

Resolution order for the fixtures directory, first hit wins:
1. ``WEATHER_SEED_PATH`` (env or ``src/.env``) — an explicit override.
2. ``<content repo>/weather`` — where the corpus lives by convention.

Absent both, this is a no-op with a warning: weather content is authored
content, and a missing corpus is a content-authoring gap, not a seeder bug
(the same stance the mission board takes about an empty board).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

WEATHER_SUBDIR = "weather"


def _explicit_path() -> str | None:
    """``WEATHER_SEED_PATH`` from the environment, else from ``src/.env``."""
    value = os.environ.get("WEATHER_SEED_PATH")
    if value:
        return value
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.is_file():
        return None
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("WEATHER_SEED_PATH="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def resolve_weather_fixtures_dir() -> Path | None:
    """The weather fixtures directory, or None when the corpus is unavailable."""
    explicit = _explicit_path()
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_dir() else None
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        return None
    candidate = Path(content_root) / WEATHER_SUBDIR
    return candidate if candidate.is_dir() else None


def seed_weather_content() -> None:
    """Load the authored weather corpus, if it is reachable (idempotent)."""
    from world.weather.seed import load_weather_seed  # noqa: PLC0415

    fixtures_dir = resolve_weather_fixtures_dir()
    if fixtures_dir is None:
        logger.warning(
            "Weather corpus not found (set WEATHER_SEED_PATH or add a 'weather' "
            "directory to the content repo). The weather cron will run against "
            "an empty transition graph until it is authored."
        )
        return
    counts = load_weather_seed(fixtures_dir)
    logger.info("Weather corpus loaded: %s", counts)
