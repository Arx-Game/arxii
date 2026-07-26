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

Config prerequisites come before EVEN the content load (#2474 first-run gap
fix; generalised into a registry in #2724): rows the code names by string
literal — e.g. lore-repo ``Technique`` fixtures FK an ``ActionTemplate`` by
natural key (``["Technique Cast"]``) — are pure config, not authored content,
yet used to be seeded only later, inside the cluster-seeder loop below (or,
for ``fatigue_willpower``/the fury check/the spread skills, only lazily on
first gameplay use). On a fresh database ``load_world_content``'s
deferred-retry loop (which only retries against rows the content/grid load
itself creates) can never resolve a config FK, so a Technique row could be
silently skipped on the very first run, and an undeclared config row (e.g.
``fatigue_willpower``) could be tidied out of a fixture with nothing to
notice. The fix: every such row is declared in
``world.seeds.config_prerequisites.CONFIG_PREREQUISITES`` and run BEFORE the
content load, so a lore fixture always wins over the code default and the
rows land outside ``test_no_content_slop``'s measurement window; content
itself never lives here — only the narrow, idempotent config prerequisites.
See issue #2474 Decision 5 and #2724.
"""

from __future__ import annotations

from core_management.content_fixtures import ContentError, load_world_content
from core_management.content_repo import resolve_content_root
from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models
from world.seeds.config_prerequisites import CONFIG_PREREQUISITES
from world.seeds.types import SeedReport

_MISSING_CONTENT_ROOT_MSG = (
    "CONTENT_REPO_PATH is not set or does not exist. Set it in src/.env "
    "pointing at your local checkout of the private content repository — "
    "seed_dev_database() loads lore content first and refuses to seed "
    "content-dependent clusters without it (no silent skip, no synthetic "
    "fallback)."
)


def load_content_first() -> int:
    """Run the config prerequisite, then load the content repo. Returns rows touched.

    The pre-cluster half of :func:`seed_dev_database`, split out so the
    seeders-create-no-content guard (#2698,
    ``world.seeds.tests.test_no_content_slop``) can snapshot row counts
    *between* the content load and the cluster loop. Measuring across the
    whole call would score the content repo's own rows as seeder growth, so
    every model the stub content root carries would look like slop and the
    ratchet could never reach zero.

    Raises ``ContentError`` when ``CONTENT_REPO_PATH`` is unset or invalid.
    """
    # Fail loud BEFORE writing anything (Decision 5) — checked first so the
    # config prerequisite below never runs on a call that's about to raise.
    content_root = resolve_content_root()
    if content_root is None:
        raise ContentError(_MISSING_CONTENT_ROOT_MSG)

    # Config prerequisites (#2474 first-run gap fix, generalised in #2724): rows the
    # code names by string literal must exist BEFORE the content load, so lore fixtures
    # can FK them by natural key and so an authored value upserts over the code default.
    for prerequisite in CONFIG_PREREQUISITES.values():
        prerequisite()

    content_result = load_world_content(content_root)
    return content_result.created + content_result.updated


def seed_dev_database(*, verbose: bool = False) -> SeedReport:
    """Seed every cluster's sane defaults. Idempotent; never overwrites.

    Loads the arx2-lore content repo before running any cluster seeder (see
    module docstring); raises ``ContentError`` loudly when
    ``CONTENT_REPO_PATH`` is unset/invalid, before any cluster seeder runs.
    """
    report = SeedReport()

    report.clusters["content"] = load_content_first()
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
