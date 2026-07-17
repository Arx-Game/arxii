"""Production-callable seed orchestrator.

Composes the per-cluster ``seed_*_dev()`` masters into one idempotent call.
The cluster masters live in ``world.seeds.game_content`` (roadmap 3.2, #1220
— relocated from ``integration_tests.game_content``, which now keeps a thin
compatibility facade so existing test imports keep working unchanged).

Content-repo load comes FIRST (#2474 Decision 5): the arx2-lore content
repo's fixtures + grid bundles are loaded via
``core_management.content_fixtures.load_world_content`` before any cluster
seeder runs, since content-dependent clusters (e.g. the CG magic
Path/Tradition/Gift/Technique catalog) assume that content already exists.
``CONTENT_REPO_PATH`` missing or not a real directory is a loud failure — no
silent skip, no synthetic in-repo fallback — surfaced via ``ContentError``
(the same error type ``load_world_content``/``build_all`` already raise for
every other content-validation failure, matched here rather than inventing a
parallel exception type). Path resolution reuses
``core_management.content_repo.resolve_content_root`` (the canonical env/
``.env`` lookup) rather than re-parsing the environment here.
"""

from __future__ import annotations

from core_management.content_fixtures import ContentError, load_world_content
from core_management.content_repo import resolve_content_root
from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models
from world.seeds.types import SeedReport

_MISSING_CONTENT_ROOT_MSG = (
    "CONTENT_REPO_PATH is not set or does not exist. Set it in src/.env "
    "pointing at your local checkout of the private content repository — "
    "seed_dev_database() loads lore content first and refuses to seed "
    "content-dependent clusters without it (no silent skip, no synthetic "
    "fallback)."
)


def seed_dev_database(*, verbose: bool = False) -> SeedReport:
    """Seed every cluster's sane defaults. Idempotent; never overwrites.

    Loads the arx2-lore content repo before running any cluster seeder (see
    module docstring); raises ``ContentError`` loudly when
    ``CONTENT_REPO_PATH`` is unset/invalid, before any cluster seeder runs.
    """
    report = SeedReport()

    content_root = resolve_content_root()
    if content_root is None:
        raise ContentError(_MISSING_CONTENT_ROOT_MSG)
    content_result = load_world_content(content_root)
    report.clusters["content"] = content_result.created + content_result.updated
    if verbose:
        print(f"  content: +{report.clusters['content']} rows")

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
