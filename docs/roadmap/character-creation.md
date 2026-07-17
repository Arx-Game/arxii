# Character Creation & Identity

## Built (2026-07-17 — Arx beginnings authored: Caretaker / Sleeper / Misbegotten)

- The three Arx `Beginnings` are now real authored content (replacing the
  "Commoner"/"Noble" placeholders, which the seeder retires when untouched):
  full player-facing descriptions, species gates (Sleeper: Human + Nox'alfar +
  Sylv'alfar; Misbegotten: Human + Daeva + all elves via the new `Elf` parent
  species; `grants_species_languages=False`), heritage wiring, and
  `BeginningTradition` links to the three authored Arx traditions ("The Vigil"
  — renamed from "Caretakers" — "Metallic Order", "Fractals of the Abyss")
  when those lore-fixture rows exist. Canonical prose + rulings live in the
  lore repo's `beginnings/arx.md`; `Beginnings`/`CGExplanation` joined
  `CONTENT_MODELS` so the content round-trips to the lore repo.
- Still open from that authoring pass: "Arvani Common" (no `Language` rows
  exist yet, so `starting_languages` is unwired), elf/Daeva form traits, the
  Sleeper waking-tomb `starting_room_override`, and the Misbegotten orphanage
  ("the Cradle") + ghost-tutor training mechanics (issues filed from the
  lore-repo doc's follow-ups list).

## Built (2026-07-16, #2426 — CG magic revamp: Path → Tradition → Gift → Technique)

- The old "Magic" stage (freeform cantrip creation) is retired. Stage 5 **Path** is
  now explicitly the magical-Path pick (the Path of your Durance); Stage 6 **Gift**
  runs a guided funnel — Tradition → Gift → Technique picks → gift resonance →
  **Anima Check** (the stat + skill pair every cast rolls, replacing a silent
  Willpower + highest-skill default) — all against staff-authored catalogs instead
  of per-character cantrip creation. Skills moved in with Attributes as Stage 7.
- Every character has exactly one Tradition, including the self-taught `Unbound`
  tradition (no more NULL-tradition special-casing). `TraditionGiftGrant`
  (tradition × gift → signature technique extras) drives the CG gift list; the
  shared `PathGiftGrant.starter_techniques` pool (already used by
  `grant_path_magic` at the level-3 Durance crossing, ADR-0063 — unchanged) is
  reinterpreted as CG pick *availability*, not an automatic grant. The rankable
  **Tradition Training** distinction adds +1 starting technique pick per rank
  above the Unbound baseline of 1.
- `Organization.tradition` (nullable FK) lets orgs act as a tradition's teaching
  structure (chapters/academies); `Tradition.society` (no live consumer) is
  dropped. `Gift`/`Technique` gained `codex_entry` FKs so every CG catalog card
  can open a lore modal (#2410 pattern).
- Removed: the `Cantrip` model and its full API/admin/frontend stack, CG facet
  selection (`selected_facet_id` — verified dead at finalize), CG custom gift
  name/description, and the CG "Outcome Flavor" pick (`selected_consequence_pool_id`
  — only worked by baking a pool into a per-character technique row, which shared
  catalog techniques make impossible without new cast-path machinery).
- Rationale + rejected alternative (per-character gift/cantrip creation) recorded
  in ADR-0136. See `docs/systems/magic.md` and `docs/systems/character_creation.md`
  for the current model/endpoint shape.

## Built (2026-07-11, #2162 — CGExplanation stage copy seeded)

- The `character_creation` cluster seeder now writes real heading/intro/desc prose
  for every one of the 11 stages via `CG_EXPLANATION_COPY`
  (`world.seeds.character_creation._seed_cg_explanations`, called from
  `seed_character_creation_dev()`), covering all 28 `copy?.<key>` lookups the stage
  components read (`frontend/src/character-creation/components/*Stage.tsx`). Rows
  are re-synced (`update_or_create`) on every seeder run so in-repo copy fixes keep
  reaching already-seeded deploys; staff can still edit any row directly in the
  admin. `CGExplanation` is now listed under the `character_creation` cluster in
  `seeded_models_by_cluster()` (Game Setup inventory).

## Built (2026-07-09, #2121 — guaranteed starting room)

- Every seeded `StartingArea`/`Beginnings` now resolves to a real room. The dev-seeded
  "Arx City" `StartingArea` gets a canonical fallback `Room`
  (`world.seeds.character_creation.ensure_canonical_fallback_room`) wired onto its
  `default_starting_room` whenever that FK is unset. `CharacterDraft.get_starting_room()`
  gained a third, loud-logged fallback tier (the same canonical room, looked up by its
  stable `db_key`) for any hand-built `StartingArea`/`Beginnings` combo that's missing a
  room — a freshly approved character never spawns with `location=None`; the prior
  "valid for early testing" silent-`None` behavior is retired.

## Built (2026-07-07, #2062 — kinship graph; ADR-0097)

- Person-node genealogy replaces the FamilyMember stub: `Kinsperson` at five
  definition tiers (NPC-ladder aligned), typed parentage edges (biological /
  tree-of-souls / vampiric / adoptive / foster / acknowledged — N parents,
  any composition), `Union` edges (in-laws + step-parents DERIVED, never
  ambiguous again), `FamilyMembership` claims, and `Soul`/`SoulIncarnation`
  chains with per-life knowledge.
- Truth vs public record on every fact; hidden truths anchor Secrets
  (subject-unaware supported — the Misbegotten discovery loop rides
  investigation/clues natively).
- The app-in slot mountain: appable nodes with constraints + `KinSlotPool`
  fuzzy capacity; CG lineage stage claims a position (`KinSlotPicker`) and
  finalization binds the sheet, inheriting a living tree. Deferred
  definitions (leave parents blank, define later, review-gated).
- Surfaces: viewer-aware tree + slots REST, telnet `sheet/family`, staff
  admin, PLACEHOLDER ducal demo seed (cluster `kinship`).
- Consumed next by #1884 (recognition, succession law, fealty).


**Status:** skeleton
**Depends on:** Magic, Traits, Skills, Distinctions, Species, Paths

## Overview
The 11-stage character creation flow that takes a player from concept to approved character. CG is the first experience every player has with the game, so it must be polished, informative, and exciting — setting the tone for everything that follows.

## Key Design Points
- 11 stages: Origin, Heritage, Lineage, Distinctions, Path, Gift, Attributes & Skills, Appearance, Identity, Final Touches, Review (#2426 — Skills moved in with Attributes; the old standalone "Magic" stage split into Path + Gift)
- Draft system allows saving and resuming in-progress characters
- Application review workflow with staff conversation threads
- Admin-editable CG copy text (CGExplanation key-value system) so lore text can be updated without code changes
- Tradition-gated staff-authored catalogs (`TraditionGiftGrant`/`PathGiftGrant`), not per-character-authored magic — a guided Tradition → Gift → Technique funnel narrows a bounded pick from real content instead of freeform creation (#2426)
- Tarot card naming ritual for familyless characters (78-card deck with surname derivation)
- Points budget system configurable via admin

## What Exists
- **Models:** Full stage models, CharacterDraft with stage tracking, DraftApplication with review workflow, CGExplanation KV store, CGPointBudget, `BeginningTradition` (tradition-per-beginning gate, `required_distinction`)
- **APIs:** Complete viewsets and serializers for all stages, including the Gift-stage catalog reads (`gifts`, `technique-options`, #2426)
- **Frontend:** Full React components for all 11 stages — OriginStage, HeritageStage, LineageStage, DistinctionsStage, PathStage, GiftStage, AttributesStage, AppearanceStage, IdentityStage, FinalTouchesStage, ReviewStage. GiftStage runs the Tradition → Gift → Technique → Resonance → Anima Check funnel; CG Points widget, Species cards, Tarot selection
- **Tests:** Comprehensive coverage of stages, serializers, services, application workflow

## What's Needed for MVP
- Email verification and approval flow needs testing/completion
- Hundreds of distinctions still need to be authored as game content
- Roster character system integration (characters that change players need strong records)
- Polish pass on UX — the skeleton works but the experience needs to feel exciting and informative

## Notes
