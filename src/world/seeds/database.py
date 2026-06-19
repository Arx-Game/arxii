"""Production-callable seed orchestrator.

Composes the per-cluster ``seed_*_dev()`` masters into one idempotent call.
INTERIM (Phase A): cluster functions are imported from
``integration_tests.game_content`` until roadmap 3.2 relocates the helpers
here. Tracked in the #1220 epic.
"""

from __future__ import annotations

from world.seeds.clusters import CLUSTER_SEEDERS
from world.seeds.types import SeedReport


def seed_dev_database(*, verbose: bool = False) -> SeedReport:
    """Seed every cluster's sane defaults. Idempotent; never overwrites."""
    report = SeedReport()
    for name, seeder in CLUSTER_SEEDERS.items():
        before = _row_count()
        seeder()
        after = _row_count()
        report.clusters[name] = max(0, after - before)
        if verbose:
            print(f"  {name}: +{report.clusters[name]} rows")
    return report


def _row_count() -> int:
    """Coarse global row count across seeded content models (created-delta proxy)."""
    from world.seeds.clusters import seeded_models  # noqa: PLC0415

    return sum(model.objects.count() for model in seeded_models())
