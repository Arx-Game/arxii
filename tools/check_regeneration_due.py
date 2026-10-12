"""Report whether the ``arxii`` migration chain is due for regeneration (ADR-0276).

A regeneration (``arx manage squashmigrations arxii``) folds every migration into
a fresh generation of ``_g{N}_`` files. Everything added after it is an
*incremental*, applied with Django's stock per-operation state re-rendering,
which is what made generation 1 slow. This counts the incrementals since the
current generation and calls the chain due at ``THRESHOLD`` (ruled 2026-10-12,
#4250: about the size of generation 2 itself).

Run monthly by ``.github/workflows/migration-regeneration-due.yml``, which opens
an issue when the chain is due. Deliberately free of Django and the database: the
nightly replay it replaced needed both, broke on an unrelated settings change,
and stayed red for five weeks with nobody looking. ``tools/tests`` runs this
against the real chain on every PR, so a rename that would break it fails there.

    python tools/check_regeneration_due.py [--github-output PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
MIGRATIONS_DIR = SRC_DIR / "world" / "migrations"
THRESHOLD = 100
_MIGRATION_FILE = re.compile(r"^\d{4}_.+\.py$")

sys.path.insert(0, str(SRC_DIR))

from core_management.migration_generations import load_generations  # noqa: E402


def incremental_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Names of the migrations added since the current generation was cut, in order."""
    current = load_generations(migrations_dir / "_generations.py").current
    marker = f"_g{current}_"
    names = sorted(p.stem for p in migrations_dir.iterdir() if _MIGRATION_FILE.match(p.name))
    incrementals = [name for name in names if marker not in name]
    if len(incrementals) == len(names):
        msg = f"no migration in {migrations_dir} is named {marker}; is CURRENT right?"
        raise ValueError(msg)
    return incrementals


def is_due(count: int) -> bool:
    return count >= THRESHOLD


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--github-output", type=Path, help="append due=/count= lines here")
    args = parser.parse_args()

    incrementals = incremental_migrations()
    count = len(incrementals)
    due = is_due(count)
    verdict = "DUE" if due else "not due"
    print(f"{count} incremental migrations since the current generation: {verdict}")
    print(f"threshold: {THRESHOLD}")
    if incrementals:
        print(f"oldest: {incrementals[0]}  newest: {incrementals[-1]}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as out:
            out.write(f"due={str(due).lower()}\ncount={count}\n")


if __name__ == "__main__":
    main()
