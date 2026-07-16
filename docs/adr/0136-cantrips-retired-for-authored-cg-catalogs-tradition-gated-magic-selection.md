# Cantrips retired for authored CG catalogs; tradition-gated magic selection

Character creation no longer lets a player author a personal starter Technique (the
`Cantrip` model + its finalize-time mint into a per-character `Technique` row); CG now
runs a guided **Tradition → Gift → Technique** funnel that *links* the character to
staff-authored catalog `Gift`/`Technique` rows (`TraditionGiftGrant` for tradition-gated
gift availability, the reinterpreted `PathGiftGrant.starter_techniques` for the pick
pool), the same shape `grant_path_magic` already mints from at the level-3 Durance
semi-crossing (ADR-0063, unaffected — it still grants the *new* path's gift and
techniques, not a top-up of the old one). We also dropped the CG "Outcome Flavor" pick
(`selected_consequence_pool_id`): it only worked by baking a `ConsequencePool` into a
per-character technique row, which shared catalog techniques make structurally
impossible without new cast-path machinery. **Rejected: keep per-character gift/cantrip
creation** (custom gift name/description, a personally-authored starter technique) —
it produces uneven, un-vetted starting kits, blocks the tradition-gating and pick-budget
mechanics this spec needed, and duplicates authoring effort real catalog content already
does better. The underlying design premise: **pre-level-3 personalization is narrative
agency, not mechanical customization** — the system never specifies how a character's
magic *appears* when cast; players describe their own manifestations, and the new
**Anima Check** (the CG-chosen stat + skill every cast rolls) shapes casting's fictional
register without touching mechanics. Mechanical personalization of magic's *effects*
still exists — it just starts at level 3 (threads, `Signature`/`SignatureMotifBonus`,
`TechniqueVariant` — ADR-0072, ADR-0055), not at CG.

> Status: accepted · Source: #2426, Tehom design ruling 2026-07-16 · Confidence: built
> and wired — `TraditionGiftGrant`/`cg_catalog` services/`GiftStage` funnel; `Cantrip`
> model and its API/admin/frontend stack fully removed.
