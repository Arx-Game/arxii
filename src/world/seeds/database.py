"""Production-callable seed orchestrator.

Composes the per-cluster ``seed_*_dev()`` masters into one idempotent call.
The cluster masters live in ``world.seeds.game_content`` (roadmap 3.2, #1220
— relocated from ``integration_tests.game_content``, which now keeps a thin
compatibility facade so existing test imports keep working unchanged).
"""

from __future__ import annotations

from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models
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
    return sum(model.objects.count() for model in seeded_models())
