# Character Creation System

Multi-stage character creation flow with draft persistence, CG point budgets, catalog gift/technique magic selection, and staff review workflow.

**Source:** `src/world/character_creation/`
**API Base:** `/api/character-creation/`

---

## Enums (constants.py)

```python
from world.character_creation.constants import (
    Stage,                    # ORIGIN(1) through REVIEW(11)
    StartingAreaAccessLevel,  # ALL, TRUST_REQUIRED, STAFF_ONLY
    ApplicationStatus,        # SUBMITTED, IN_REVIEW, REVISIONS_REQUESTED, APPROVED, DENIED, WITHDRAWN
    CommentType,              # MESSAGE, STATUS_CHANGE
)
```

## Types (types.py)

```python
from world.character_creation.types import (
    StatAdjustment,      # TypedDict: stat, old_display, new_display, reason
    ResonanceSource,     # Dataclass: distinction_name, value
    ProjectedResonance,  # Dataclass: resonance_id, resonance_name, total, sources
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CGPointBudget` | Global CG point budget config | `name`, `starting_points`, `is_active`, `xp_conversion_rate` |
| `StartingArea` | Selectable origin locations | `name`, `realm` (FK), `description`, `crest_image`, `default_starting_room`, `is_active`, `sort_order`, `access_level`, `minimum_trust` |
| `Beginnings` | Worldbuilding paths per area | `name`, `starting_area` (FK), `description`, `allowed_species` (M2M), `starting_languages` (M2M), `societies` (M2M), `traditions` (M2M via `BeginningTradition`), `cg_point_cost`, `social_rank` |
| `OriginTemplate` | The Upbringing a player picks within a Beginning (#3617) | `beginning` (FK), `name`, `frame_narrative`, `is_active`, `sort_order`, `cg_point_cost`, `trust_required`, `allows_claim_family`, `allows_name_family`, `allows_no_family`, `claimable_kinds` (M2M `FamilyKind`; empty = every kind), `named_family_kind` (FK `FamilyKind`, required when naming is allowed) |
| `OriginTemplateSlot` | An authored prompt within an Upbringing (#2478, #3617) | `template` (FK), `name`, `prompt`, `example`, `sort_order`, `is_required`, `applies_to` (`FamilyPath`: claimed/named/none/any), `allows_text` |
| `OriginTemplateSlotChoice` | One authored pick-list answer, with its price (#3617) | `slot` (FK), `name`, `description`, `cg_point_cost`, `cost_per_influence`, `is_active`, `sort_order` |

**Content vs seeds:** the real, authored `Beginnings` rows (e.g. the Arx trio —
Caretaker/Sleeper/Misbegotten) are **lore-repo content fixtures**
(`fixtures/character_creation/beginnings.json` + `beginningtradition.json`,
prose + rulings in the lore repo's `beginnings/arx.md`), loaded by
`load_world_content` (natural-key upserts — the fixture also retires the
seeded placeholders via `is_active: false` rows) and exported back by
`content_export` (`Beginnings`/`CGExplanation` are in `CONTENT_MODELS`). The
rows seeded below are generic bootstrap placeholders only; real content never
expands seed data in this public repo (TehomCD ruling, 2026-07-17).

### Template/Configuration Tables

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `BeginningTradition` | Maps traditions to beginnings with optional required distinction | `beginning`, `tradition`, `required_distinction`, `sort_order` |

### Draft State (models.Model - per-player)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDraft` | In-progress creation state | `account`, `current_stage`, `selected_area`, `selected_beginnings`, `selected_species`, `selected_gender`, `age`, `selected_origin_template` (FK `OriginTemplate`, the chosen Upbringing, #3617), `family_path` (`FamilyPath`: claimed/named/none, #3617), `family`, `selected_path`, `selected_tradition`, `height_band`, `height_inches`, `build`, `draft_data` (JSON) |
| `CharacterOriginSlot` | A character's authored answer to an Upbringing prompt (instance data, not content) | `sheet` (FK), `slot` (FK `OriginTemplateSlot`), `value`, `choice` (FK `OriginTemplateSlotChoice`, nullable; the picked answer on a pick-list prompt, null for a pure write-in, #3617) |

**Note:** Magic selections during CG (gift, techniques, gift resonance, Anima Check stat/skill, aura distribution) are stored in `draft_data` JSON, not in separate Draft* models. The old DraftGift, DraftTechnique, DraftMotif, DraftMotifResonance, DraftMotifResonanceAssociation, DraftAnimaRitual, TraditionTemplate, TraditionTemplateTechnique, and TraditionTemplateFacet models have been removed.

### Application/Review

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DraftApplication` | Review lifecycle for a draft | `draft` (OneToOne), `status`, `submitted_at`, `reviewer`, `reviewed_at`, `submission_notes`, `expires_at` |
| `DraftApplicationComment` | Comment or status change event | `application`, `author`, `text`, `comment_type`, `created_at` |

---

## CG Stages

| # | Stage | Completion Criteria |
|---|-------|-------------------|
| 1 | Origin | `selected_area` is set |
| 2 | Heritage | Beginnings, species, gender selected; family/tarot complete; CG points >= 0; species allowed by beginnings |
| 3 | Lineage | Upbringing chosen and accessible; family path resolved (claim: playable family of an offered kind in the area's realm; name: unique name; none: tarot card); every required prompt on that path answered (`get_lineage_errors`, #3617) |
| 4 | Distinctions | `traits_complete` flag set; CG points >= 0 |
| 5 | Path | Path selected (`get_path_errors`) |
| 6 | Gift | Tradition, gift, >=1 technique(s), gift resonance, and Anima Check stat/skill all selected and valid (`compute_magic_errors`, 5-branch return-first gate); renders the `GiftStage` funnel component (#2426 Task 10) |
| 7 | Attributes & Skills | All 12 primary stats present, valid range (1-5), points remaining = 0; skill point allocation validated against budget (moved in from Path, #2426 Task 9). Draft allocations are display-scale; finalization stores stats ×10 and bridges each CG skill into a matching `CharacterTraitValue` row so checks and DP progression read them (ADR-0193, #2894) |
| 8 | Appearance | Age, height band, height inches, build all set |
| 9 | Identity | `first_name` in draft_data |
| 10 | Final Touches | Always complete (goals are optional) |
| 11 | Review | Never "complete" -- final submission step |

---

## Key Methods

### CGPointBudget

```python
from world.character_creation.models import CGPointBudget

CGPointBudget.get_active_budget()          # Returns int (default 100)
CGPointBudget.get_active_conversion_rate() # Returns int (default 2 XP per CG point)
```

### CharacterDraft

```python
from world.character_creation.models import CharacterDraft

draft.is_expired                        # True if > 60 days inactive (staff exempt)
draft.get_starting_room()               # Beginnings override -> area default -> canonical
                                         # fallback room (logged loudly) -> None (#2121);
                                         # see world.seeds.character_creation.
                                         # ensure_canonical_fallback_room
draft.get_stage_completion()            # Dict[int, bool] for all stages
draft.can_submit()                      # True if all stages (except Review) complete
draft.calculate_cg_points_remaining()   # starting_budget - total_spent
draft.calculate_cg_points_breakdown()   # itemized [{category, item, cost}, ...]:
                                         # "heritage" (Beginnings.cg_point_cost),
                                         # "upbringing" (OriginTemplate.cg_point_cost +
                                         # choices priced by Family.influence, #3617),
                                         # "distinction" (per draft_data distinction),
                                         # "species" (SpeciesGiftGrant.cg_point_cost summed
                                         # across the selected species + ancestors -
                                         # see docs/systems/species.md)
draft.calculate_final_stats()           # Dict[str, int] with bonuses applied
draft.enforce_stat_caps()               # Clamp stats after distinction changes
draft.get_expected_gift_count()         # Base 1 + bonus from distinctions
```

### DraftApplication

```python
from world.character_creation.models import DraftApplication

application.is_locked     # True when submitted or in_review
application.is_terminal   # True when approved, denied, or withdrawn
application.is_editable   # True when revisions_requested
```

---

## Service Functions

```python
from world.character_creation.services import (
    finalize_character,           # Create Character from completed draft (atomic); stamps
                                  #   RosterEntry provenance (STAFF if add_to_roster else
                                  #   PLAYER) + created_by_account (#1506)
    finalize_gm_character,        # GM path: full character + Available RosterEntry (GM_TABLE
                                  #   provenance + created_for_table) + Story/StoryParticipation
    get_accessible_starting_areas,# Filter areas by account access
    can_create_character,         # Check eligibility (email verification, trust, limits)
    submit_draft_for_review,      # Create DraftApplication in SUBMITTED
    unsubmit_draft,               # Return to REVISIONS_REQUESTED
    resubmit_draft,               # Re-submit after revisions
    withdraw_draft,               # Withdraw with soft-delete expiry
    claim_application,            # Staff: claim for IN_REVIEW
    approve_application,          # Staff: approve and finalize (atomic)
    request_revisions,            # Staff: send back with feedback
    deny_application,             # Staff: deny with 14-day soft-delete
    add_application_comment,      # Add message to thread
    finalize_magic_data,          # Link the draft's chosen catalog Gift/Techniques to the character
)
```

**`can_create_character` eligibility gates (#3046):** staff bypass all three
checks. (1) Email verification is real: it reuses
`PlayerData.can_apply_for_characters()` (allauth `EmailAddress`, primary +
verified), the same check that drives the frontend's `can_create_characters`
field, rejecting with "Verify your email address to create a character." (2)
Trust level defaults to 0 until the trust system lands. (3) `max_characters`
is `settings.CG_MAX_CHARACTERS` (`CG_MAX_CHARACTERS` env var, default 3),
counted against `account.character_drafts`.

**`StartingArea.is_accessible_by` fails closed on `TRUST_REQUIRED`** (#3046):
non-staff accounts have no `.trust` attribute yet (trust system unimplemented),
so a `TRUST_REQUIRED` area is simply inaccessible to them rather than raising
`NotImplementedError` — mirrors `Beginnings.is_accessible_by`'s existing
fail-closed behavior. `get_accessible_starting_areas` therefore never 500s on
a `TRUST_REQUIRED` area.

`finalize_magic_data` also creates the CG-finalize Golden Hare Academy obligation
row (#2428 Task 3, `_finalize_academy_entrance_obligation`): resolves the
"Shroudwatch Academy" `Organization` by name (seeded by
`world.seeds.character_creation.ensure_shroudwatch_academy`) and creates an
`OWED` `OrganizationObligation` when `draft.selected_tradition.name == "Unbound"`,
else a `SETTLED_BY_SPONSOR` row (`settled_at` stamped, `settled_by_token` left
`NULL` — the sponsor's Hare is lore-recorded, not minted at CG time). Defensive
logged skip if the Academy isn't seeded. See `docs/systems/societies.md`'s
Obligations section for the model/service detail.

`finalize_character`'s `_apply_character_mechanics` also stamps a level-1 primary
`CharacterClassLevel` on every finalized character (#3038,
`_stamp_default_class_level`, called right after `_create_path_history`), via
`world.classes.services.set_primary_class_level(character,
ensure_default_character_class(), 1)`. Before this, no production path ever wrote
a `CharacterClassLevel` for a player character, so `advance_class_level_via_session`
(the Ritual of the Durance) raised `AdvancementRequirementsNotMet` unconditionally
and the class term of `derive_base_max_health` was always 0.
`ensure_default_character_class` (`world/classes/services.py`) get-or-creates the
same single shared placeholder `CharacterClass` (`DEFAULT_CHARACTER_CLASS_NAME`,
"Adventurer") the #2121 seeded Durance officiants and the level-2
`ClassLevelUnlock` gate already anchor on — no class-selection UI exists yet, and
advancement only ever reads `current_level`/Path lineage, never a specific
`CharacterClass` name. The #2121 `select_initial_path` recovery seam
(`world.progression.services.advancement`, for CG-bypassing characters) stamps the
same level-1 class level when one is missing, without clobbering an existing one.

---

## Email Notifications (#2162)

`world.character_creation.email_service.CGEmailService` sends plain-text notifications at every
review-state transition, called (best-effort, exceptions logged not raised) from the corresponding
service function:

- `handle_submission` — confirmation to the applicant + notification to staff; called from
  `submit_draft_for_review`
- `send_application_approved` — called from `approve_application`
- `send_revisions_requested` — called from `request_revisions`
- `send_application_denied` — called from `deny_application`

`CGEmailService` extends `world.roster.email_service.EmailServiceBase` (not `RosterEmailService`
itself) — `EmailServiceBase` was split out of `RosterEmailService` in the same change so sibling
domain services can reuse `_send_email`/`_get_staff_emails` without subclassing a service whose
`send_application_approved`/`send_application_denied` take a roster-specific `tenure` arg CG
applications don't have (subclassing would have meant a narrower override, an LSP violation caught
by `ty`'s `invalid-method-override`). The applicant's email comes from `DraftApplication.player_account`
(survives draft deletion); `_character_name` falls back to the draft's staged first name before
`character_name` is populated at approval.

---

## API Endpoints

### Lookup Data
- `GET /api/character-creation/starting-areas/` - Starting areas filtered by access level
- `GET /api/character-creation/beginnings/` - Beginnings filtered by `starting_area` and trust
- `GET /api/character-creation/species/` - Species with parent hierarchy
- `GET /api/character-creation/families/` - Playable families, filterable by `area_id`
  and `kind=` (one or more `FamilyKind` ids, #3617)
- `GET /api/character-creation/origin-templates/?beginning=X` - Upbringings for a beginning,
  trust-filtered; each row carries its `slots` (prefetched) and `claimable_kind_ids`, batched
  with one flat query grouped in Python and passed through serializer context rather than a
  per-instance `.claimable_kinds.all()` or a bare `prefetch_related` (ADR-0263; #3617)
- `GET /api/character-creation/genders/` - Gender options
- `GET /api/character-creation/pronouns/` - Pronoun sets
- `GET /api/character-creation/cg-budgets/` - Active CG point budget
- `GET /api/character-creation/paths/` - Active Prospect-stage paths
- `GET /api/character-creation/traditions/?beginning_id=X` - Traditions for a beginning
- `GET /api/character-creation/tarot-cards/` - Tarot cards for naming ritual
- `GET /api/character-creation/form-options/{species_id}/` - Form traits for a species
- `GET /api/character-creation/can-create/` - Eligibility check
- `GET /api/character-creation/beginnings/{id}/perspectives/` - That beginning's
  `is_perspective=True` codex grants, ungated by codex knowledge (CG shop window,
  ADR-0224, #3281)
- `GET /api/character-creation/traditions/{id}/perspectives/` - Same shop-window read
  for a tradition's perspective grants (ADR-0224, #3281)

### Draft Management
- `GET/POST /api/character-creation/drafts/` - List/create drafts
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Read/update/delete draft
- `GET /api/character-creation/drafts/{id}/cg-points/` - CG points breakdown
- `POST /api/character-creation/drafts/{id}/select-tradition/` - Select/clear tradition
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff: finalize directly to roster (STAFF provenance)
- `POST /api/character-creation/drafts/{id}/finalize-gm/` - Player-GM: finalize onto the Available roster for a table they own (GM_TABLE provenance; body `target_table`, `story_title`, optional `story_description`) (#1506). Gated by
  `require_draft_complete` (#3268), the same completeness check `finalize_character`
  applies at submit, now factored out so `add-to-roster` and `finalize-gm` share it
  instead of each re-deriving stage completion. A 400 with `{"detail": "Cannot finalize:
  incomplete stages: <label>, ..."}` means the draft isn't ready; a
  `GiftResonanceUnresolvable` from `finalize_gm_character` is caught the same way
  `add-to-roster` catches it (logged, `{"detail": "Character creation failed."}`, 400)
  rather than surfacing a 500.

### Magic (Gift/Technique Selection, #2426)
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's chosen tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- Magic selections (`selected_gift_id`, `selected_technique_ids`, `selected_gift_resonance_id`,
  `anima_check_stat_id`, `anima_check_skill_id`, `anima_ritual_name`, `motif_description`,
  `glimpse_story`) are stored in `draft_data` JSON via draft PATCH — see `GiftStage` (frontend)
  and `compute_magic_errors` (validation)

### Application Workflow (Player)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/unsubmit/` - Un-submit to resume editing
- `POST /api/character-creation/drafts/{id}/resubmit/` - Resubmit after revisions
- `POST /api/character-creation/drafts/{id}/withdraw/` - Withdraw application
- `GET /api/character-creation/drafts/{id}/application/` - Get application with thread
- `POST /api/character-creation/drafts/{id}/application/comments/` - Add comment

### Staff Review
- `GET /api/character-creation/applications/` - List all applications (filterable by status)
- `GET /api/character-creation/applications/{id}/` - Application detail with thread
- `POST /api/character-creation/applications/{id}/claim/` - Claim for review
- `POST /api/character-creation/applications/{id}/approve/` - Approve
- `POST /api/character-creation/applications/{id}/request-revisions/` - Request revisions
- `POST /api/character-creation/applications/{id}/deny/` - Deny
- `POST /api/character-creation/applications/{id}/comments/` - Staff comment
- `GET /api/character-creation/applications/pending-count/` - Pending count

### Staff-Only
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Bypass review, add to roster

---

## Admin

Registered admin classes: `StartingAreaAdmin`, `BeginningsAdmin` (with `BeginningTraditionInline`), `OriginTemplateAdmin` (with `OriginTemplateSlotInline`), `OriginTemplateSlotAdmin` (with `OriginTemplateSlotChoiceInline`), `CharacterOriginSlotAdmin`, `CharacterDraftAdmin` (stage tracking and JSON draft data), `DraftApplicationAdmin` (review status with `DraftApplicationCommentInline`). CGPointBudget is not registered in admin.

## Lineage step (#3617, #3648)

Per-beginning Upbringings replaced the old single family-known/orphan split: each
`OriginTemplate` carries its own CG cost, trust gate, and choice of family paths
(claim a staff-authored family, name a new one, or none), with typed prompts
(`OriginTemplateSlot`) and costed pick-list choices (`OriginTemplateSlotChoice`)
authored underneath it. See the authoring recipes in
[family-authoring-recipes.md](family-authoring-recipes.md), ADR-0268 (family standing
uses existing organisation mechanisms), ADR-0269 (Upbringings price standing as
family influence x position), and ADR-0272 (family entry is a Vacancy).

**Page order:** Upbringing picker, `scope: 'any'` prompts, the family block (path
picker when the Upbringing allows more than one path, then the path body), then
`scope: 'path'` prompts.

**Name path:** pick a Family Template (`draft.resolve_family_template()`; the sole
offered template, else `draft_data.family_template_id`), name the family (checked
against `HouseTemplate.name_pattern`, a full-match regex; a malformed pattern is a
staff authoring bug and surfaces as a soft "tell staff" error, never an uncaught
`re.error`), answer the template's aspect picks (`draft_data.family_aspect_picks`,
fenced by `houses.creator._validate_aspect_picks`), and optionally declare a served
house from `family_template.served_house_choices`.

**Claim path:** claiming a staff family with an open kin Vacancy requires taking one
(`_get_vacancy_errors`); the Service panel (a retainer Vacancy) is available on any
resolved path except when a kin Vacancy is already chosen.

**Vacancies:** `GET /api/character-creation/vacancies/?draft=<id>[&organization=<id>]`
returns the open, reachable, per-draft-priced `Vacancy` rows (bare list) via
`vacancy_services.reachable_vacancies`. Validation re-checks an already-selected
Vacancy with `require_open=False`: openness is enforced only at finalize by
`take_vacancy`, so a Vacancy filled between pick and staff approval degrades
through `VacancyExhaustedError` instead of blocking re-validation on approval.
Pricing adds `vacancy.cost_for(<the Vacancy's family's influence>)` (ADR-0269
extended to a second consumer).

**Finalize order:** `_materialize_named_family` (name path) before the character is
named, then `_bind_vacancy` (takes the Vacancy, claims/mints its kin link, joins the
org) before `_bind_kinship_node`, so a kin Vacancy's node exists when the self-serve
kinship fallback looks. `finalize_gm_character` mirrors both calls for GM drafts.

## Seeded content + Game Setup hub

The `"character_creation"` cluster (`seed_character_creation_dev()`) seeds the CG *config* a fresh DB needs to run `finalize_character` — never authored content:

```python
from world.seeds.character_creation import seed_character_creation_dev
# also runs as part of seed_dev_database() (the "Load sane defaults" Big Button)
seed_character_creation_dev()  # idempotent: get_or_create, never overwrites edits
```

**`Species`, `Gender`, `HeightBand`/`Build`, `FormTrait`/`FormTraitOption`/`SpeciesFormTrait`, `Distinction`/`DistinctionCategory`/`DistinctionEffect`, and `CGExplanation` are all `CONTENT_MODELS` — content-repo-owned (#2698, ADR-0168).** Each is looked up via `world.seeds.sample_content.authored_or_sample()` and invented only when `SEED_SAMPLE_CONTENT` (`ARXII_SEED_SAMPLE_CONTENT`, default off) is on — a maintainer clone with a real content repo gets nothing from this seeder for these models; a contentless third-party clone gets a sample "Human"/"Khati" `Species`, the four `Gender` rows, an `average_band`/`average_build`, the appearance `FormTrait`/`FormTraitOption`/`SpeciesFormTrait` set, and the seeded `Distinction`s below. `_seed_cg_explanations()` (#2162) is the same shape: most of `CG_EXPLANATION_COPY`'s 28 keys already have an authored counterpart, but the five `*_lore_intro`/`path_lore_durance` keys don't yet — those five are skipped (logged) until authored, or invented under `SEED_SAMPLE_CONTENT`. Unlike the pre-#2698 `update_or_create` shape, a staff edit to an already-seeded `CGExplanation` row now survives a re-run, same as every other content row.

`Realm`/`StartingArea`/`Beginnings`/`TarotCard`/`Path` are *not* `CONTENT_MODELS`, but are still open-ended world content rather than config — `_seed_sample_cg_world()` and the tail of `seed_character_creation_dev()` gate them behind `SEED_SAMPLE_CONTENT` too (an earlier #2698 slice), for the same reason: seeding a "Commoner"/"Noble"/"Arx City" here is indistinguishable from authored content once `export_to_content_repo` runs. What always seeds unconditionally regardless of the flag: the 12 stat `Trait` rows (content-repo-owned too, `authored_or_sample`'d), and the two `Roster` rows ("Available"/"Active Characters") — genuine config with no content-repo equivalent.

`seed_beginning_traditions()` (#2426 whole-branch-review fix) links every seeded `Beginnings` row to the "Unbound" `Tradition` — real lore-repo content, loaded via `core_management.content_fixtures.load_world_content()` before any `CLUSTER_SEEDERS` entry runs (#2474 Decision 5) — via a `BeginningTradition` row whose `required_distinction` is the "Unbound" drawback `Distinction` seeded by `ensure_unbound_drawback_distinction()` (itself gated behind `SEED_SAMPLE_CONTENT` since #2698) — without it, `TraditionViewSet` and `select_tradition` have nothing to offer and CG's Tradition step is uncompletable on a fresh DB, even the tradition-agnostic Unbound path. `ensure_shroudwatch_academy()` (#2428 Task 3) then seeds the "Shroudwatch Academy" `Organization` (`tradition=None` — deliberate NULL, #2426 ruling; `org_type` "guild"; description/rank titles PLACEHOLDER and content-overridable) that `finalize_magic_data`'s Golden Hare hook resolves by name. `ensure_orphaned_tradition_distinction()` and `seed_metallic_order_tradition()` (#2428 Task 5) then seed the "Orphaned Tradition" drawback `Distinction` (slug `orphaned-tradition`, cost −2, no `DistinctionEffect` — its teeth are trainerlessness, #2440) and the "Metallic Order" example orphaned tradition (starter-gift `TraditionGiftGrant` rows mirroring Unbound's; `BeginningTradition` rows for Arx-realm Beginnings only, each with `required_distinction=orphaned-tradition` — the story-mutable shape staff edit when a recovery quest restores its teachers). Registered last in `CLUSTER_SEEDERS` — after `magic` (which seeds the non-content magic tuning/ritual/thread substrate `finalize_character` depends on) and after the content-repo load itself provides the catalog `Gift`/`Technique`/`Resonance` rows and the Unbound `Tradition` row (#2474 — see `docs/systems/magic.md`'s "CG Starter Gift/Technique Catalog" section). Verified by `test_playable_slice.py::TestSeededCharacterCreation` (finalize + the real Tradition-step gates run on a seeded-only DB), `test_character_creation_magic_seed.py` (`seed_beginning_traditions` idempotency + defensive skip, `EnsureOrphanedTraditionDistinctionTests`, `SeedMetallicOrderTraditionTests`), `test_traditions.py::OrphanedTraditionSelectionTests` (the drawback gate through the real select-tradition endpoint), `test_idempotency.py::test_edited_cg_row_survives_reseed`, and `test_clusters.py::test_cg_explanations_seeded_and_nonempty`.

The admin **Game Setup** hub (`admin_game_setup` view, `_game_setup/` URL) is a superuser-only landing page for clone hosts: the clone→seed→tweak→export flow, a per-cluster content inventory (via `seeded_models_by_cluster()`) with live row counts, and links to the Big Button, Export/Import, and the World authoring apps. See `src/web/admin/CLAUDE.md`.
