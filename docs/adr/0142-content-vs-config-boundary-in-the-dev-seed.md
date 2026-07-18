# The Big Button loads all real content from arx2-lore; arxii seeds keep only non-lore config/lookup tables

Before #2474, the CG magic starter catalog (`Gift`/`Technique`/`PathGiftGrant`/`TraditionGiftGrant`,
including the "Unbound" `Tradition`) was synthetic in-repo seed data authored by
`seed_starter_gift_catalog()` — the same shape real lore content would eventually need to replace,
duplicating authoring effort and risking drift between the placeholder and the real catalog. The
fix: those five models gained natural keys and joined `CONTENT_MODELS`
(`core_management/content_export.py`), so the catalog now ships as arx2-lore fixtures loaded by the
existing content pipeline. `world.seeds.database.seed_dev_database()` (the "Big Button") now
sequences (1) resolve `CONTENT_REPO_PATH` — raise `ContentError` immediately if unset/missing, before
writing anything; (2) seed the narrow, idempotent config prerequisites content fixtures FK by natural
key (currently just `ensure_technique_cast_content()`, since lore-repo `Technique` rows FK the shared
"Technique Cast" `ActionTemplate` and the content load's own deferred-retry loop can't conjure a
config row the content/grid load itself never creates); (3) `load_world_content()`; (4) the ordinary
`CLUSTER_SEEDERS` loop, which now only seeds non-lore config/lookup tables (tuning singletons, rituals,
check types, thread-pull catalogs) and never authors catalog content again — one known remnant,
`ensure_portal_travel_content()`'s "Mirrorwalking" `Gift`/`Technique`, still violates this and is
flagged for lore-repo curation (#2474 Task 5 notes). Rejected: a synthetic
sample-content fallback baked into arxii seeds for third-party instances that never clone the private
lore repo — deferred as a someday-aspiration, deliberately undesigned, since no such instance exists
yet and building it now would resurrect exactly the drift problem this decision closes.

> Status: accepted · Source: issue #2474 Decision 5 · Related: ADR-0136 (CG catalog shape),
> ADR-0140 (the sibling grid content-export pipeline this reuses the natural-key/`load_world_content`
> machinery from)
