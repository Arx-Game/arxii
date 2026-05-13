# Covenants Slice D — Covenant Legend, Story Integration, Sub-roles

**Date:** 2026-05-12
**Status:** Draft (post-brainstorm; awaiting spec review)
**Branch:** `covenants-slice-d-progression`
**Related:**
- `docs/roadmap/covenants.md` — domain roadmap; Slice D owns covenant Legend, Story integration, and sub-role authoring per the slice decomposition
- `docs/superpowers/specs/2026-05-09-covenants-slice-a-design.md` — Slice A entity / membership / anchor cap formula this spec composes with
- `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md` — Slice B lifecycle and engagement infrastructure this spec composes with
- `docs/systems/stories.md` — Story / Episode / Beat / consequence-pool surface this spec extends
- `docs/systems/progression.md` — XP vs Legend framing; Legend is the right parallel here (XP is the OOC reward currency)
- `src/world/societies/models.py` — existing `LegendEntry` / `LegendEvent` / `LegendSpread` / materialized-view machinery this spec extends
- `src/world/checks/models.py` — `Consequence` / `ConsequenceEffect` to be extended with a new `LEGEND_AWARD` effect type
- `src/actions/models/consequence_pools.py` — `ConsequencePool` referenced by beats per outcome

---

## Goal

Land the progression loop for covenants. Slice A built the entity and the anchor-cap formula that already reads `Covenant.level`. Slice B let players form, join, and engage covenants in play. Slice D makes the level field move.

After this slice:

- A covenant earns **Legend** — not XP — as its members accomplish legendary deeds together. Naming matters: XP is the OOC "you made content for other players" currency; Legend is the IC "you achieved something notable" currency. Covenants advance via Legend.
- The credit flow is **engagement-driven and never exclusionary**: when a participant earns a `LegendEntry`, every covenant they are currently engaged with (Durance + Battle, additively) gets full credit for that deed. Big shared moments accumulate credit across many entities by design.
- **Story integration is two-sided**: beats can author **structured consequence packages** keyed on outcome (SUCCESS / FAILURE / EXPIRED), forcing GMs to plan reward and fallout up front; Legend awards live inside those packages as a new `ConsequenceEffect` type. And a Story can optionally be declared a covenant's storyline via a `Story.covenant` FK.
- **Sub-roles** become real authored content: a sub-role is a `(parent CovenantRole × Resonance)` pair unlocked when the character's Thread (anchored on the parent role, with that resonance) reaches level 3. The Thread anchor cap already scales with covenant level via Slice A, so high-level covenants uncap their members' Threads, which in turn unlock sub-roles — but **no auto-promotion**: Thread investment still has to be earned after the cap rises.

Group-ability unlocks remain in Slice F. Battle-vs-Durance combat precedence remains in Slice E. Use-based Thread mechanics remain in Slice G.

---

## Background

### What's shipped

- **Slice A:** `Covenant`, `CovenantRole`, `CharacterCovenantRole`, `GearArchetypeCompatibility`. Anchor cap formula reads `max(covenant.level)` across the character's all-time memberships for the role. Modifier pipeline sums engaged-role bonuses. `Covenant.level` is a stored integer (default 1) that the cap formula already consumes — Slice D's job is to drive it.
- **Slice B:** `RitualSession` primitive, covenant formation + induction rituals, manual engage/disengage endpoints, scene auto-engage subscribers, Soul Tether `BILATERAL` retrofit, frontend pages.
- **Legend system (`world.societies`):** `LegendEntry` (per persona, with `base_value` + spreads), `LegendEvent` (group event with `source_type`/`scene`/`story` FKs), `LegendSpread` (clamped to spread cap), `LegendSourceType`, `LegendDeedStory`. Materialized views `CharacterLegendSummary` and `PersonaLegendSummary` for fast totals, refreshed by `refresh_legend_views()`. Service functions: `create_solo_deed`, `create_legend_event`, `spread_deed`, `spread_event`.
- **Stories system:** Beats with discriminator predicates, `BeatCompletion` audit, `BeatOutcome` (UNSATISFIED / SUCCESS / FAILURE / EXPIRED / PENDING_GM_REVIEW), `evaluate_auto_beats`, `record_gm_marked_outcome`, `record_aggregate_contribution`.
- **Checks / consequences:** `Consequence` (weighted, tied to a `CheckOutcome`), `ConsequenceEffect` (typed children: condition / property / damage), `ConsequencePool` in `actions/` (named, reusable, single-depth inheritance), `select_consequence` + `apply_resolution` (weighted-pick path).

### What's missing

- No path from a covenant's deeds to its level. `Covenant.level` is `1` everywhere.
- No way for a story beat to award anything mechanical. `Beat.player_resolution_text` is the only outcome surface; `Episode.consequences` is free-text GM notes.
- Sub-roles exist conceptually but `CovenantRole` has no parent / resonance / unlock fields. Promotion has no service.
- No covenant-side Legend totals or materialized view.

### Naming reframe (important)

Earlier roadmap drafts of Slice D used "covenant XP." That framing was wrong. In Arx II, XP is the OOC currency for creating positive content for other players (per `world/progression`). The right parallel for "achieved something noteworthy" is **Legend**, which already exists at persona granularity. This spec extends the existing Legend system to credit covenants too. No new currency model, no new XP curve.

### Slice D's place in the multi-slice buildout

| Slice | Scope | Status |
|---|---|---|
| A | Covenant entity + membership FK + engagement context + anchor cap + COVENANT_ROLE pull gating | **Shipped** |
| B | RitualSession primitive + formation + induction + Soul Tether BILATERAL + engagement UI | **Shipped** |
| C | (Dropped — sworn_objective stays free-text per durable design decision in the roadmap) | n/a |
| **D** | **Covenant Legend credit + level mapping + Story FK + Beat consequence packages with LEGEND_AWARD + sub-role authoring framework + promotion service** | **This spec** |
| E | Battle Covenants + Durance × Battle combat precedence | Future |
| F | Group abilities (techniques/rituals gated by ≥N members present) | Future |
| G | Use-based Thread weave gate + use-based anchor cap | Future |

---

## Design

### §1. Covenant Legend credit (`world.societies`)

Covenant Legend is not a separate currency. It is **derived** from the existing per-persona `LegendEntry` rows via a new join table that snapshots covenant engagement at deed time. Spreads on the underlying entry flow through to the covenant total automatically.

#### §1.1 `CovenantLegendCredit` model

New SharedMemoryModel in `world.societies.models` (lives alongside the existing Legend models):

| Field | Type | Notes |
|---|---|---|
| `entry` | FK → `LegendEntry` (CASCADE, `related_name="covenant_credits"`) | The persona's deed this credit derives from. CASCADE because the credit is meaningless without its source deed. |
| `covenant` | FK → `world.covenants.Covenant` (PROTECT, `related_name="legend_credits"`) | The covenant being credited. PROTECT because deleting a covenant with credit history should be a deliberate operation. |
| `created_at` | DateTimeField, `auto_now_add` | Audit timestamp. |

**Constraint:** `UniqueConstraint(fields=["entry", "covenant"])` — a given deed credits each covenant at most once.

**No denormalized `covenant_type` column.** Queries that filter by Durance vs Battle JOIN to `Covenant.covenant_type`.

#### §1.2 Snapshot service

New service `world.societies.services.legend_fanout`:

```python
def credit_engaged_covenants(*, entry: LegendEntry) -> list[CovenantLegendCredit]:
    """Snapshot the persona's currently-engaged covenants and create credit rows.

    Idempotent on retry: uses get_or_create per (entry, covenant) so a partial
    failure can be safely re-run inside the same transaction.
    """
```

Called from the end of `create_solo_deed`, `create_legend_event` (for every `LegendEntry` row the event creates), and any future LegendEntry-creating path. Fan-out rules:

- The persona's character is resolved via the existing `Persona.character_sheet` FK.
- The cached `character.covenant_roles` handler exposes `active_memberships` (a `list[CharacterCovenantRole]`). Filter to `engaged=True` to get the engaged membership rows. (Note: the existing `currently_engaged_roles()` helper returns `list[CovenantRole]` — role templates, not memberships — so it is the wrong call here. The fan-out needs the membership row's `covenant` FK.)
- One `CovenantLegendCredit` row per `(entry, membership.covenant)`. Full deed value flows to each covenant — no fractional split. Multi-covenant participation is additive (a member engaged with both a Durance and a Battle covenant credits both).
- If the persona has no engaged covenant memberships at deed time, zero credits are created. The entry still exists at persona level.

#### §1.3 Spread integration

`LegendSpread` rows already accumulate against an entry's `base_value` via the existing `LegendSpread.value_added` field. The covenant total is computed as `sum(entry.base_value + entry.spread_total)` across that covenant's `CovenantLegendCredit` rows. Spreading does NOT create new credit rows — the existing rows reference the entry, and the total view recomputes naturally.

#### §1.4 `CovenantLegendSummary` materialized view

Mirrors the existing `PersonaLegendSummary` pattern. SQL view in `world.societies.sql/covenant_legend_summary.sql`:

```sql
SELECT
    c.id AS covenant_id,
    COALESCE(SUM(le.base_value + COALESCE(spreads.total, 0)), 0) AS legend_total
FROM covenants_covenant c
LEFT JOIN societies_covenantlegendcredit clc ON clc.covenant_id = c.id
LEFT JOIN societies_legendentry le ON le.id = clc.entry_id
LEFT JOIN (
    SELECT legend_entry_id, SUM(value_added) AS total
    FROM societies_legendspread
    GROUP BY legend_entry_id
) spreads ON spreads.legend_entry_id = le.id
GROUP BY c.id
```

Column name note: `LegendSpread.legend_entry` is the FK field, so the underlying DB column is `legend_entry_id` (not `entry_id`). The view above uses the correct column name.

`managed=False` Django model `CovenantLegendSummary` provides ORM access. The materialized view ships in a **new numbered migration** in `world/societies/migrations/` (a sibling of the existing `0002_create_legend_materialized_views.py`, NOT a modification to that file — once-applied migrations are immutable). The new migration creates the `CovenantLegendSummary` view, adds a CONCURRENTLY-capable unique index, and extends the existing `refresh_legend_views()` helper to refresh it alongside the two existing views.

`refresh_legend_views()` is extended to refresh `CovenantLegendSummary` after every mutation that already triggers the persona/character refresh.

#### §1.5 Backfill

**None.** Pre-Slice-D `LegendEntry` rows do not retroactively credit covenants — we don't have historical engagement data, and the existing legend data is entirely seed/test (the game has no live players yet). Covenants start fresh and accrue Legend from the moment Slice D ships. The roadmap entry for this slice documents this explicitly.

---

### §2. Legend → `Covenant.level` (`world.covenants`)

#### §2.1 `CovenantLevelThreshold` model

New SharedMemoryModel in `world.covenants.models`:

| Field | Type | Notes |
|---|---|---|
| `level` | PositiveIntegerField, `unique=True` | The covenant level reached at this threshold. |
| `required_legend` | PositiveIntegerField | Legend total required to reach this level. |

Constraint: `level >= 1`. Authored row for `level=1` is `required_legend=0` (starting state). Staff authors the curve as content; bulk tuning is downstream of this slice.

#### §2.2 Recomputation service

New module `world.covenants.services.legend`:

```python
def recompute_covenant_level(*, covenant: Covenant) -> int | None:
    """Look up current legend total, find max threshold satisfied, update
    Covenant.level if changed. Returns the new level on change, None otherwise.

    Atomic. Fires a NarrativeMessage to engaged members on level change.
    """

def get_covenant_legend_total(covenant: Covenant) -> int:
    """Thin wrapper around the CovenantLegendSummary view."""
```

`Covenant.level` stays a stored integer (not a `cached_property`) because the anchor-cap formula and many other call sites already read it directly. Recomputing on every read would be wasteful; instead, the recomputation service runs at the end of every legend-mutating path.

#### §2.3 Mutation wiring

The following services in `world.societies.services` call `recompute_covenant_level` for every affected covenant at the end of their atomic transaction (after `refresh_legend_views`):

- `create_solo_deed`
- `create_legend_event`
- `spread_deed`
- `spread_event`

"Affected covenants" = the set of `CovenantLegendCredit.covenant_id` values touched by this mutation. For a brand-new entry, that's the snapshot from §1.2. For a spread, it's the covenants credited by the spread's entry.

#### §2.4 Level-up notification

New `NarrativeCategory.COVENANT` enum value added to the existing `NarrativeCategory` TextChoices class in `world.narrative.constants`. When `recompute_covenant_level` raises the stored level, it fires one `NarrativeMessage` per currently-engaged member:

- `category=COVENANT`
- `recipient=member.character_sheet.account` (or whatever the existing narrative-message recipient resolution expects)
- `body=f"The Covenant '{covenant.name}' has reached level {new_level}."`

No further automatic effects. **In particular, no auto-sub-role offers.** Thread level does NOT change when covenant level rises — the cap simply unlocks further investment. Members have to weave Threads up to the new cap themselves.

---

### §3. Beat outcome → Legend awards (consequence packages)

GMs author structured consequence packages per Beat outcome. Legend awards are one effect type within those packages, alongside future consequence types (condition application, property change, codex unlock, etc., none of which ship in this slice but the framework supports them).

#### §3.1 New `EffectType.LEGEND_AWARD`

`world.checks.constants.EffectType` gains a new member: `LEGEND_AWARD`. `world.checks.models.ConsequenceEffect` gains three nullable fields, validated by `clean()` against `effect_type`:

| Field | Type | Notes |
|---|---|---|
| `legend_base_value` | PositiveIntegerField (nullable) | The `LegendEntry.base_value` to create on each participant persona. Required when `effect_type=LEGEND_AWARD`. |
| `legend_source_type` | FK → `world.societies.LegendSourceType` (PROTECT, nullable) | Categorizes the deed (typically `STORY`). Required when `effect_type=LEGEND_AWARD`. |
| `legend_description_template` | TextField, blank | Optional GM-authored deed description. Falls back to `beat.player_resolution_text` if blank, then to a generic "Legendary deed" if the beat has no resolution text either. The `LegendEvent.title` field is derived from the same chain (truncated to fit). |

`clean()` enforces: when `effect_type=LEGEND_AWARD`, `legend_base_value > 0` and `legend_source_type` is set. When any other effect type, all three legend fields must be null.

#### §3.2 New beat outcome FKs

`world.stories.models.Beat` gains three nullable FKs, all `on_delete=SET_NULL` to `actions.ConsequencePool`:

| Field | Notes |
|---|---|
| `success_consequences` | Pool fired on SUCCESS outcome. |
| `failure_consequences` | Pool fired on FAILURE outcome. |
| `expired_consequences` | Pool fired on EXPIRED outcome. |

All nullable — authoring is opt-in; existing beats keep working unchanged.

#### §3.3 Deterministic pool application

The existing `world.checks.consequence_resolution.select_consequence` does **weighted random selection** of one consequence from a pool, used by challenges and magic mishaps. Beats need a different shape: fire all consequences in the pool deterministically.

New function `world.checks.consequence_resolution.apply_pool_deterministically`:

```python
def apply_pool_deterministically(
    *, pool: ConsequencePool, context: ResolutionContext
) -> list[AppliedEffect]:
    """Run every Consequence in the pool (including inherited parent rows that
    aren't excluded), applying each one's effects via apply_resolution. No
    weighted pick. Returns the flattened list of applied effects for caller
    introspection / tests / audit.
    """
```

The existing `apply_resolution(pending, context)` already dispatches `ConsequenceEffect` rows to handlers; deterministic application just iterates the pool's consequences and applies each. Inheritance + exclusion semantics from `ConsequencePool.parent` and `ConsequencePoolEntry.is_excluded` are honored by walking the pool the same way `select_consequence` does.

#### §3.4 LEGEND_AWARD handler

New file `world.checks.effects.legend.py`, registered in the existing handler dispatcher:

```python
def handle_legend_award(
    *, effect: ConsequenceEffect, context: ResolutionContext
) -> AppliedEffect:
    """Create a LegendEvent for the resolution's participants.

    Pulls participants from ResolutionContext.participants (new field added
    for this handler — see §3.5). For each participant Persona, the existing
    create_legend_event service is called with the effect's base_value and
    source_type, which in turn fires the §1.2 covenant credit fan-out.
    """
```

#### §3.5 `ResolutionContext` extension and participant resolution

`world.checks.types.ResolutionContext` gains a new optional field `participants: list[Persona] | None`. **`BeatCompletion` has no `scene` FK**, so participants must be resolved at the call site (in `world.stories.services.beats`) before building the context. The resolution rules:

1. **CHARACTER-scope, auto-evaluated beat (`evaluate_auto_beats`):** participants = the primary `Persona` of `progress.character_sheet` (the one character whose state satisfied the predicate). Single-element list.
2. **CHARACTER-scope, `GM_MARKED` beat:** same as (1), plus any additional personas the GM provides via the mark-action serializer's new `extra_participants: list[int]` field.
3. **GROUP-scope, `GM_MARKED` beat:** the resolving GM provides the participant list explicitly via the mark-action serializer's `participants: list[int]` field (required for pools containing `LEGEND_AWARD`). The system does NOT auto-derive participants for GROUP scope — too ambiguous, and the user's earlier guidance was that GMs explicitly think through who deserves the deed.
4. **GROUP-scope, `AGGREGATE_THRESHOLD` beat:** participants = the primary Personas of every `CharacterSheet` with a non-zero `AggregateBeatContribution` row on this beat at threshold-crossing time. (`AggregateBeatContribution` is keyed on `character_sheet`, so the resolution layer maps `character_sheet → primary_persona` via the existing `Persona.persona_type=PRIMARY` lookup before building the participant list.)
5. **GLOBAL-scope:** out of scope for this slice — GLOBAL beats with `LEGEND_AWARD` are unusual and best deferred until a real use case appears. Pool authors targeting GLOBAL beats with `LEGEND_AWARD` will get a typed `LegendAwardScopeError` at apply-time.

The existing `world.stories.services.beats` callers (`_evaluate_and_record_beat`, `record_gm_marked_outcome`, `record_aggregate_contribution`) each know their scope and outcome at the moment of beat resolution, so each constructs its `ResolutionContext.participants` per the rule above before calling `apply_pool_deterministically`.

If a pool contains a `LEGEND_AWARD` effect and the resolved participant list is empty, the handler raises a typed `LegendAwardParticipantMissingError` — a deed without an actor is meaningless and indicates either a misauthored pool or a missing `participants` payload from the GM. This is a hard error, not a silent skip.

#### §3.6 Beat-resolution wiring

In `world.stories.services.beats`, after a `BeatCompletion` row is created (in `_evaluate_and_record_beat`, `record_gm_marked_outcome`, and `record_aggregate_contribution`), if the beat has a consequence pool for the resulting outcome, build a `ResolutionContext` and call `apply_pool_deterministically`. All atomic with the BeatCompletion.

#### §3.7 Authoring guidance

Different magnitudes of success are authored as **different beats**, not as a tunable knob on one beat. "Save half the city" and "save the whole city" are two beats with two consequence pools. The user explicitly chose this shape over a weighted-check inside a single beat — it keeps the consequence model deterministic and forces GMs to think through outcome variation at beat authoring time.

---

### §4. Sub-roles (`world.covenants`)

#### §4.1 Schema additions on `CovenantRole`

| Field | Type | Notes |
|---|---|---|
| `parent_role` | FK → `CovenantRole` (self, PROTECT, nullable, `related_name="sub_roles"`) | Null for primary roles. Set for sub-roles. |
| `resonance` | FK → `magic.Resonance` (PROTECT, nullable) | Null for primary roles. Set for sub-roles. |
| `unlock_thread_level` | PositiveIntegerField, default 0 | 0 for primary roles. Sub-roles ship at 3 in MVP; higher tiers are future scope. |

`clean()`:

- `parent_role` and `resonance` are both null (primary role) or both non-null (sub-role).
- `unlock_thread_level > 0` requires both FKs.
- When sub-role: `parent_role.covenant_type == self.covenant_type` and `parent_role.archetype == self.archetype`.
- `parent_role.parent_role` must be null (single-depth inheritance — sub-roles cannot have sub-sub-roles in MVP).

**Unique constraint:** `(parent_role, resonance, unlock_thread_level)` where `parent_role IS NOT NULL`. `covenant_type` is omitted from the key because it is implied by `parent_role`. `unlock_thread_level` is part of the key so future higher-tier sub-roles (level 6, level 11) for the same (parent, resonance) pair can coexist with the level-3 row.

#### §4.2 Promotion service

New service in `world.covenants.services`:

```python
def promote_to_subrole(
    *, membership: CharacterCovenantRole, target_subrole: CovenantRole
) -> CharacterCovenantRole:
    """Promote a character from their current parent role to a sub-role.

    Validates:
    - target_subrole.parent_role == membership.covenant_role (must promote
      from the parent role currently held in this covenant).
    - The character has at least one Thread anchored on
      target_subrole.parent_role with resonance=target_subrole.resonance
      and level >= target_subrole.unlock_thread_level.

    Atomic. Closes the existing membership row (sets left_at) and creates
    a new active row with target_subrole, preserving the engaged flag.
    Reuses the existing change_role mechanics underneath. Invalidates the
    character.covenant_roles handler cache.
    """
```

#### §4.3 Typed exceptions

New exception class in `world.covenants.exceptions`:

```python
class SubrolePromotionError(CovenantError):
    """Base for sub-role promotion failures. Subclasses below."""

class SubroleParentMismatchError(SubrolePromotionError): ...
class SubroleThreadLevelInsufficientError(SubrolePromotionError): ...
class SubroleResonanceMismatchError(SubrolePromotionError): ...
```

All carry `user_message` plus a `SAFE_MESSAGES` allowlist per the project pattern.

#### §4.4 API

New action on `CharacterCovenantRoleViewSet`:

```
POST /api/covenants/character-roles/{pk}/promote/
Body: {"target_subrole_id": int}
```

Serializer `PromoteSubroleSerializer` does validation (target exists, character owns this membership via the existing roster-tenure permission check, target is a sub-role of the current role). Service does the atomic swap. Returns the updated `CharacterCovenantRoleSerializer` payload.

#### §4.5 Anchor cap formula

**Unchanged.** A character's Thread anchor cap remains `max_covenant_level_for_role(role) × 10`, taken across all covenants where the character has held that role (active or ended). Holding a sub-role in covenant X does NOT change the cap for Threads anchored on the parent role in covenant Y. The Thread is anchored on the parent role; the sub-role is a per-membership specialization.

#### §4.6 Authored content scope

The framework ships in this slice. Authoring concrete sub-role names ("Vanguard of Flame", "Sentinel of Earth", …) is **bulk content work for a later seed pass**, outside this slice's scope. Test fixtures will author a handful of canonical sub-roles to drive integration tests.

---

### §5. Story ↔ Covenant linkage (`world.stories`)

#### §5.1 `Story.covenant` FK

New field on `world.stories.models.Story`:

```python
covenant = models.ForeignKey(
    "covenants.Covenant",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="storylines",
)
```

**Semantic:** "this story is the covenant's storyline." Set by the table's GM when a Story is explicitly framed as a covenant's. Does NOT change credit fan-out rules — engagement at deed time remains the credit source. A Story with no covenant FK still credits engaged covenants of participants; a Story with a covenant FK plus participants engaged with a different covenant credits both.

#### §5.2 Surfaces

- `CovenantSerializer` detail gains a `storylines` field (reverse-lookup list of `Story` IDs / titles).
- `StorySerializer` gains a writable nullable `covenant` PK field.
- No new permissions. The existing Story edit permission covers setting the FK. The FK is informational only — it does NOT gate joining, GMing, or playing the Story.

#### §5.3 M2M deferred

Per the brainstorm, M2M for "stories with multiple related covenants" is deferred. The engagement fan-out already handles cross-covenant participation in open stories; the single FK exists for the "this covenant owns this storyline" use case, which is the only case that needs a stable pointer.

---

### §6. Consolidated API surface

| Method | Path | Notes |
|---|---|---|
| POST | `/api/covenants/character-roles/{pk}/promote/` | Sub-role promotion. Body: `{target_subrole_id}`. |
| GET | `/api/covenants/level-thresholds/` | Read-only ViewSet over `CovenantLevelThreshold`. Small lookup table; no pagination. |
| GET | `/api/covenants/{pk}/` | Detail gains `legend_total` (from `CovenantLegendSummary` view) and `storylines` (reverse FK list). |
| GET, PATCH | `/api/stories/{pk}/` | Story serializer gains writable nullable `covenant` PK. |
| GET, PATCH | `/api/beats/{pk}/` | Beat serializer gains writable nullable `success_consequences`, `failure_consequences`, `expired_consequences` PKs. |
| POST | `/api/beats/{pk}/mark/` | Existing endpoint; serializer gains optional `participants: [persona_id, ...]` for GROUP-scope `GM_MARKED` beats whose consequence pool contains a `LEGEND_AWARD` effect. |

All ViewSet permission classes follow the project pattern (`IsGMOrStaff` / story-owner / membership-scoped, etc.). No new permission classes are introduced.

---

### §7. Migrations

Four apps gain additive migrations in this slice. None are data migrations.

- `world/covenants/migrations/` — `CovenantLevelThreshold` model, three new `CovenantRole` fields with the new clean/constraint definitions.
- `world/societies/migrations/` — `CovenantLegendCredit` model, `CovenantLegendSummary` SQL materialized view alongside the existing two views.
- `world/stories/migrations/` — three nullable FKs on `Beat`, one nullable FK on `Story`.
- `world/checks/migrations/` — three nullable fields on `ConsequenceEffect`, new `EffectType.LEGEND_AWARD` enum value.
- `world/narrative/migrations/` — new `NarrativeCategory.COVENANT` enum value.

---

## Test Plan

Tests live in each app's `tests/` directory, focused on application logic (not Django CRUD). All factories live in `factories.py` and are reused across unit + integration tests per the project's seed-and-integration-test pattern.

### `world.societies.tests`

- **`test_covenant_legend_credit.py`** — creating a `LegendEntry` for a persona engaged in two covenants creates two credit rows; engaged-in-zero creates zero rows; full deed value flows to each covenant additively; spreading the entry does NOT create new credit rows but DOES grow the covenant total via the view.
- **`test_covenant_legend_summary.py`** — materialized view returns correct totals after creation + spread; Durance + Battle stacking returns additive totals; refresh after mutation is idempotent.

### `world.covenants.tests`

- **`test_recompute_covenant_level.py`** — level rises when threshold crosses; idempotent when nothing changed; fires one `NarrativeMessage` per engaged member on rise; emits no message when unchanged.
- **`test_promote_to_subrole.py`** — promotes when Thread level + resonance + parent role all align; raises `SubroleParentMismatchError` / `SubroleResonanceMismatchError` / `SubroleThreadLevelInsufficientError` for each failure mode; preserves `engaged` flag; closes old membership cleanly.
- **`test_subrole_constraints.py`** — `clean()` enforces both-or-neither (parent_role + resonance); unique constraint blocks duplicate `(parent_role, resonance, unlock_thread_level)`; single-depth invariant rejects sub-sub-roles.
- **`test_anchor_cap_unchanged.py`** — regression: anchor cap still reads `max_covenant_level_for_role`; sub-role promotion in covenant X does not change Thread cap for parent role anchored across other covenants.

### `world.checks.tests`

- **`test_apply_pool_deterministically.py`** — fires every consequence in the pool regardless of weight; inheritance + exclusion honored; transactional rollback covers partial failure.
- **`test_legend_award_handler.py`** — `LEGEND_AWARD` effect creates `LegendEvent` with correct base_value + source_type; participants pulled from `ResolutionContext`; empty participants raises `LegendAwardParticipantMissingError`; GLOBAL-scope application raises `LegendAwardScopeError`.

### `world.stories.tests`

- **`test_beat_consequences.py`** — beat resolution with `success_consequences` pool fires the pool on SUCCESS only; `failure_consequences` on FAILURE; `expired_consequences` on EXPIRED; no pool → no consequence fire (existing behavior preserved); pool with `LEGEND_AWARD` actually creates LegendEntries.
- **`test_story_covenant_fk.py`** — serializer round-trip on the new FK; reverse lookup `covenant.storylines` returns linked stories.

### Integration

- **`src/integration_tests/test_covenant_slice_d_flow.py`** — full path:
  1. Create covenant + members via factories, engage them.
  2. Run a story to a beat with `success_consequences` pool containing a `LEGEND_AWARD` effect.
  3. Resolve the beat with SUCCESS.
  4. Assert: `LegendEntry` rows created for participants; `CovenantLegendCredit` rows fanned out; `Covenant.legend_total` (via the view) grew; `Covenant.level` recomputed; `NarrativeMessage` delivered to each engaged member.
  5. Set a member's Thread on the parent role with matching resonance to level 3.
  6. Call `promote_to_subrole`; assert the new membership row exists with the sub-role, engaged preserved, old row closed.

### Pre-push regression

Substrate changes touch ≥4 apps. Per the project rule, run the full suite without `--keepdb` before pushing.

---

## Non-Goals / Out of Scope

- **Group-ability unlocks** at covenant level. Slice F.
- **Battle-vs-Durance combat-side precedence.** Slice E.
- **Use-based Thread mechanics** (weave gate / anchor cap from time-in-role or legend-in-role rather than `has_ever_held` + `max_covenant_level`). Slice G.
- **Sub-role authoring content** (concrete names like "Vanguard of Flame"). Authored as seed content in a later pass; test fixtures cover the canonical set needed for integration tests.
- **Higher-tier sub-role promotions** (level 6, 11, …). The unique constraint accommodates them; authoring is future scope.
- **Backfilling pre-Slice-D `LegendEntry` rows with covenant credit.** Engagement history isn't preserved; covenants start fresh.
- **Story M2M** with covenants. Deferred until a use case appears.
- **Per-effect-type weighted overrides inside consequence pools.** The existing `ConsequencePoolEntry.weight_override` field continues to apply only to weighted selection; `apply_pool_deterministically` ignores it.
- **Frontend UI for any of this slice's surfaces.** A later slice handles covenant-story display, sub-role promotion dialog, level-up celebration, and consequence-pool authoring tooling. Slice D ships backend + API only.

---

## Open Questions

- **`NarrativeCategory.COVENANT` recipient resolution.** Existing categories address recipients by `Account` (via `RosterTenure → AccountDB`). Confirm during implementation that the covenant-level-up message uses the same path; if engaged member recipients ever need to address an explicit persona, that's a future refinement.
- **`LegendAwardScopeError` placement.** This exception fires when a `LEGEND_AWARD` effect is applied via a pool attached to a GLOBAL-scope beat (§3.5 rule 5). Lives in `world.checks.exceptions` next to other consequence-resolution errors, but could also live in `world.societies.exceptions` since the actual error case is in the legend-award handler. Choose at implementation time based on import dependency direction.
