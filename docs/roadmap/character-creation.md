# Character Creation & Identity

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
- 11 stages: Origin, Heritage, Lineage, Attributes, Skills, Distinctions, Path, Magic, Appearance, Identity, Review
- Draft system allows saving and resuming in-progress characters
- Application review workflow with staff conversation threads
- Admin-editable CG copy text (CGExplanation key-value system) so lore text can be updated without code changes
- Tradition templates reduce choice paralysis for new players by pre-filling magic selections
- Tarot card naming ritual for familyless characters (78-card deck with surname derivation)
- Points budget system configurable via admin

## What Exists
- **Models:** Full stage models, CharacterDraft with stage tracking, DraftApplication with review workflow, CGExplanation KV store, CGPointBudget, BeginningTradition templates
- **APIs:** Complete viewsets and serializers for all stages
- **Frontend:** Full React components for all 11 stages — OriginStage, HeritageStage, LineageStage, DistinctionsStage, PathStage, AttributesStage, MagicStage, AppearanceStage, IdentityStage, FinalTouchesStage, ReviewStage. Gift/Technique builders, Anima Ritual forms, Motif designers, CG Points widget, Species cards, Tarot selection
- **Tests:** Comprehensive coverage of stages, serializers, services, application workflow

## What's Needed for MVP
- Email verification and approval flow needs testing/completion
- Hundreds of distinctions still need to be authored as game content
- Roster character system integration (characters that change players need strong records)
- Polish pass on UX — the skeleton works but the experience needs to feel exciting and informative

## Notes
