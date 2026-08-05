"""Press-then-sample-topup helper for tests hit by the #3017 hard gate.

``seed_dev_database()`` now refuses ``SEED_SAMPLE_CONTENT`` once any
``CONTENT_MODELS`` row exists anywhere - including a row the SAME call's own
content load just created (``world.seeds.sample_content.assert_sampling_allowed``,
#3017). Several tests want BOTH the stub content root loaded (so
content-dependent seeders have something to find) AND unrelated content gaps
the stub doesn't cover sample-invented (e.g. a CheckType a battles/missions
seed looks up) - a single ``seed_dev_database()`` call can no longer do both.

The fix mirrors the exemption the hard gate itself carries: it only fires
inside ``seed_dev_database()``, never against a direct cluster-seeder call
(see ``sample_content.py``'s docstring). So press once with sampling off -
``authored_or_sample()`` skips and logs a missing row rather than raising, so
the press still completes - then re-run every cluster seeder directly with
sampling on. Cluster seeders are idempotent (``get_or_create`` /
``update_or_create``), so the second pass only fills in what the first pass
skipped; nothing already seeded is touched twice.
"""

from __future__ import annotations

from django.test import override_settings

from world.seeds.clusters import CLUSTER_SEEDERS
from world.seeds.database import seed_dev_database
from world.seeds.types import SeedReport


def seed_dev_database_with_sample_topup() -> SeedReport:
    """Press once (sampling off), then top up content gaps with sampling on.

    Returns the first press's :class:`SeedReport` (the topup pass's own
    per-cluster deltas aren't tracked - callers that need row-count deltas
    from the topup pass should call the specific cluster seeder directly
    instead of this helper).
    """
    report = seed_dev_database()
    with override_settings(SEED_SAMPLE_CONTENT=True):
        for seeder in CLUSTER_SEEDERS.values():
            seeder()
    return report
