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
fix): lore-repo ``Technique`` fixtures FK an ``ActionTemplate`` by natural
key (``["Technique Cast"]``), but that row is pure config seeded by
``world.magic.seeds_cast.ensure_technique_cast_content()`` — which used to
run only later, inside the cluster-seeder loop below. On a fresh database
``load_world_content``'s deferred-retry loop (which only retries against
rows the content/grid load itself creates) can never resolve that FK, so
every Technique row was silently skipped on the very first run. The fix:
config/lookup rows that content fixtures FK by natural key must exist
BEFORE the content load runs; content itself never lives here — only the
narrow, idempotent config prerequisite. See issue #2474 Decision 5.
"""

from __future__ import annotations

from core_management.content_fixtures import ContentError, load_world_content
from core_management.content_repo import resolve_content_root
from world.magic.seeds_cast import ensure_technique_cast_content
from world.narrative.ambient_trigger_content import ensure_ambient_reaction_content
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

    # Fail loud BEFORE writing anything (Decision 5) — checked first so the
    # config prerequisite below never runs on a call that's about to raise.
    content_root = resolve_content_root()
    if content_root is None:
        raise ContentError(_MISSING_CONTENT_ROOT_MSG)

    # Config prerequisite (#2474 first-run gap fix): the shared "Technique Cast"
    # ActionTemplate (+ its CheckType/ConsequencePool) must exist before the
    # content load, since lore-repo Technique fixtures FK it by natural key and
    # the content load's own deferred-retry loop cannot conjure config rows the
    # content/grid load never creates. Idempotent; not content — see the module
    # docstring's "Config prerequisites" section.
    ensure_technique_cast_content()
    # Config prerequisite (#2471): the shared MOVED TriggerDefinition + FlowDefinition
    # ambient room reactions dispatch through — one fixed row, not lore-repo content
    # (ADR-0142). Must exist before the grid-bundle import below installs per-room
    # Trigger rows against it (core_management.grid_import._ensure_ambient_trigger).
    ensure_ambient_reaction_content()

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
