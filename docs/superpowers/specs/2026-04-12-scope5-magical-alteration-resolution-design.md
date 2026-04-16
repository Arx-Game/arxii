# Scope #5: Magical Alteration Resolution

## Purpose

Replace the `MAGICAL_SCARS` stub handler (`src/world/mechanics/effect_handlers.py:261-279`)
with a full resolution system where players author their own magical scars.
When a Soulfray stage consequence pool fires `MAGICAL_SCARS`, the system
queues a `PendingAlteration` that blocks advancement spending until the
player resolves it — either by selecting a staff-authored library entry or
by authoring a bespoke alteration from scratch.

This is where magic becomes *personal*. Two characters hitting the same
consequence pool walk away with different scars that reflect their magical
identity: origin affinity, triggering resonance, and the player's own
creative vision, constrained by tier-appropriate schema validation.

## Key Design Principles

- **Scars are conditions.** All runtime effects (check modifiers, capability
  effects, resistance modifiers, damage over time, properties, descriptions)
  live on a `ConditionTemplate` via the existing effect tables. No parallel
  "effect on character" system.
- **Three new tables, not a new runtime layer.** `MagicalAlterationTemplate`
  (OneToOne metadata extension on `ConditionTemplate`), `PendingAlteration`
  (queue + progression gate), `MagicalAlterationEvent` (provenance audit).
- **Player-authored with schema constraints.** Players fill a structured form;
  the server validates against tier caps. Creativity within bounds.
- **Library entries are staff-only.** Player-authored alterations are private
  to the authoring character. Players protect what makes their character
  unique — a public library of player scars would dilute that.
- **Scars are uncommon.** `MAGICAL_SCARS` is one weighted entry in Soulfray
  stage consequence pools. Low stages rarely or never select it; high stages
  weight it heavily. Characters who play conservatively may never get one.
- **One scar per scene, escalating.** Multiple `MAGICAL_SCARS` hits in the
  same scene upgrade the existing pending's tier rather than creating
  additional pendings. The player writes one scar per dramatic moment.
- **Passive effects only in Scope 5.** Reactive side effects ("walking on
  holy ground burns you") are deferred to Scope 5.5 (Reactive Foundations).
  The underlying `ConditionTemplate` will gain a `reactive_triggers` M2M
  to `flows.TriggerDefinition` in that scope — a condition-system feature,
  not magic-specific.
- **Constrained authoring as reusable pattern.** The structured-form →
  validate-against-ceiling → atomic-effect-creation pipeline established
  here is the reference implementation for future authoring systems
  (technique authoring, GM consequence authoring, magical effect authoring).

## What This Builds

### 1. MagicalAlterationTemplate

OneToOne extension on `ConditionTemplate`. The condition carries the runtime
effects; this carries the magic-specific authoring metadata.

Lives in `world/magic/`.

| Field | Type | Description |
|-------|------|-------------|
| `condition_template` | OneToOne(ConditionTemplate, CASCADE) | The underlying condition this extends |
| `tier` | PositiveSmallIntegerField (AlterationTier choices) | Severity tier 1-5 |
| `origin_affinity` | FK(Affinity, PROTECT) | Which affinity caused this alteration |
| `origin_resonance` | FK(Resonance, PROTECT) | The resonance channeled at overburn |
| `weakness_damage_type` | FK(DamageType, PROTECT, null) | Damage type the character is now vulnerable to |
| `weakness_magnitude` | PositiveSmallIntegerField (default 0) | Vulnerability magnitude, tier-bounded |
| `resonance_bonus_magnitude` | PositiveSmallIntegerField (default 0) | Bonus when channeling origin_resonance, tier-bounded |
| `social_reactivity_magnitude` | PositiveSmallIntegerField (default 0) | Reaction strength from magic-phobic observers, tier-bounded |
| `is_visible_at_rest` | BooleanField (default False) | Shows through normal clothing? Required True at tier 4+ |
| `authored_by` | FK(AccountDB, SET_NULL, null) | Who authored this. NULL = system/staff seed |
| `parent_template` | FK(self, SET_NULL, null) | If spun off from a library entry or own prior alteration |
| `is_library_entry` | BooleanField (default False) | If True, browsable by players at matching tier. Staff-only; non-staff attempts rejected in serializer |
| `created_at` | DateTimeField (auto_now_add) | |

`is_library_entry` help text: "If True, shown to players browsing for
tier-matched alterations. Only staff can set this flag; the player-facing
serializer rejects attempts by non-staff to enable it."

**No name or description fields here** — those live on the OneToOne'd
`ConditionTemplate`. Single source of truth.

**Authoring slots map to condition effect rows.** The `weakness_*`,
`resonance_bonus_*`, and `social_reactivity_*` fields are authoring
slots that map to `ConditionResistanceModifier`, `ConditionCheckModifier`,
and a magic-side modifier record (respectively) at template-finalization
time. The slots stay denormalized on the template for tier validation and
display, but the runtime effects live on the condition where the rest of
the system already reads them.

### 2. PendingAlteration

The progression-gate queue. One row per unresolved overburn-into-scar event.

Lives in `world/magic/`.

| Field | Type | Description |
|-------|------|-------------|
| `character` | FK(CharacterSheet, CASCADE) | Character who owes a scar |
| `status` | CharField (PendingAlterationStatus choices) | OPEN / RESOLVED / STAFF_CLEARED |
| `tier` | PositiveSmallIntegerField | Required tier for the resolved alteration. Upgradeable via same-scene escalation only |
| `triggering_scene` | FK(Scene, SET_NULL, null) | Scene where the overburn happened |
| `triggering_technique` | FK(Technique, SET_NULL, null) | Technique being cast at overburn |
| `triggering_intensity` | IntegerField (null) | Runtime intensity at overburn |
| `triggering_control` | IntegerField (null) | Runtime control at overburn |
| `triggering_anima_cost` | IntegerField (null) | What the technique tried to cost |
| `triggering_anima_deficit` | IntegerField (null) | How far over budget |
| `triggering_soulfray_stage` | PositiveSmallIntegerField (null) | Soulfray stage at trigger time |
| `audere_active` | BooleanField (default False) | Was the character in Audere |
| `origin_affinity` | FK(Affinity, PROTECT) | Locks the resolution to this affinity |
| `origin_resonance` | FK(Resonance, PROTECT) | Locks the resolution to this resonance |
| `resolved_alteration` | FK(MagicalAlterationTemplate, PROTECT, null) | Set on resolution |
| `resolved_at` | DateTimeField (null) | When resolution happened |
| `resolved_by` | FK(AccountDB, SET_NULL, null) | Who submitted (usually character owner; can be staff) |
| `created_at` | DateTimeField (auto_now_add) | |

Index: `(character, status)` for the progression gate query.

**Same-scene dedup:** when `_apply_magical_scars` fires and a
`PendingAlteration` already exists for the same character + scene:
- New tier higher → upgrade existing pending's tier, update snapshot fields
- New tier equal or lower → no-op

### 3. MagicalAlterationEvent

Provenance audit log. Created when a `PendingAlteration` resolves.

Lives in `world/magic/`.

| Field | Type | Description |
|-------|------|-------------|
| `character` | FK(CharacterSheet, CASCADE) | |
| `alteration_template` | FK(MagicalAlterationTemplate, PROTECT) | Cannot delete a template with applied events |
| `active_condition` | FK(ConditionInstance, SET_NULL, null) | Nullable — condition can be removed, event persists |
| `triggering_scene` | FK(Scene, SET_NULL, null) | |
| `triggering_technique` | FK(Technique, SET_NULL, null) | |
| `triggering_intensity` | IntegerField (null) | |
| `triggering_control` | IntegerField (null) | |
| `triggering_anima_cost` | IntegerField (null) | |
| `triggering_anima_deficit` | IntegerField (null) | |
| `triggering_soulfray_stage` | PositiveSmallIntegerField (null) | |
| `audere_active` | BooleanField (default False) | |
| `applied_at` | DateTimeField (auto_now_add) | |
| `notes` | TextField (blank) | Freeform staff/system notes |

Trigger snapshot fields are duplicated from `PendingAlteration` so the
event survives independently if the pending row is deleted (staff cleanup,
long-term archive pruning).

> **TODO(scope-5-revisit):** Once technique-use results become persisted
> records (likely via combat scene recording), replace the denormalized
> snapshot fields with an FK to the use-result record.

### 4. Tier Schema & Validation

Five tiers anchor all authoring constraints. The standard package every
alteration carries: social reactivity, a weakness/vulnerability, and a
resonance bonus (the counterbalance). All three are independent, all
scale with tier.

| Tier | Name | Social cap | Weakness cap | Resonance bonus cap | `is_visible_at_rest` |
|------|------|-----------|--------------|---------------------|----------------------|
| 1 | Cosmetic Touch | 1 | 1 | 1 | Optional |
| 2 | Marked | 2 | 2 | 2 | Optional |
| 3 | Touched | 3 | 3 | 3 | Typical (UI hint) |
| 4 | Marked Profoundly | 5 | 5 | 5 | **Required** |
| 5 | Remade | 8 | 8 | 7 | **Required** |

Resonance bonus cap at tier 5 is less than the others (7 vs 8) — at the
highest tier, the alteration costs more than it gives. You've been
*changed*, not power-leveled.

**Tone targets** (advisory, surfaced in UI as guidance text):
- Tier 1: faint glow in eyes, voice has soft echo, hair shifts color
- Tier 2: sigil on skin, pale streak in hair, voice deepens when emotional
- Tier 3: voice of many when speaking, eyes are obsidian mirrors, skin patterned with shifting sigils
- Tier 4: arm of living shadow with claws, body radiates faint cold, scent of ozone follows
- Tier 5: body partially made of shadow, eyes are voids of starlight, half the face is bone

**Cap values** are calibration starting points. They live in a constants
file or config model — easy to retune without migrations.

**Validation rules** (single source of truth in
`validate_alteration_resolution(pending, payload, request_user)`):

1. `pending.status == OPEN`
2. `payload.tier == pending.tier`
3. `payload.origin_affinity == pending.origin_affinity`
4. `payload.origin_resonance == pending.origin_resonance`
5. `weakness_magnitude` within tier weakness cap (may be 0; if > 0, `weakness_damage_type` required)
6. `social_reactivity_magnitude` within tier social cap (may be 0)
7. `resonance_bonus_magnitude` within tier resonance cap (may be 0)
8. `is_visible_at_rest == True` if tier >= 4
9. Description minimum length satisfied (single constant, e.g., `MIN_DESCRIPTION_LENGTH = 40`)
10. `is_library_entry == False` unless `request_user` is staff
11. If `library_entry_pk` provided (use-as-is path), the entry must be `is_library_entry=True` and not already active on the character (duplicate check)

### 5. Authoring & Resolution Flow

#### Handler Rewrite

`_apply_magical_scars` in `src/world/mechanics/effect_handlers.py` changes
from eagerly applying a condition to deferring:

1. Check for existing `PendingAlteration` for same character + scene
2. If exists and new tier > existing tier → upgrade existing pending
3. If exists and new tier <= existing tier → no-op, return
4. Otherwise → create new `PendingAlteration` with tier, origin, snapshot
5. Return — no condition applied yet

#### Resolution Screen

When the player opens the alteration resolution screen with an open pending:

**Context header:** "Your Soulfray during [Scene Name] while casting
[Technique Name] left a tier-T mark of [Affinity / Resonance]." Pulled
from the `triggering_*` snapshot fields.

**Two paths:** `[Browse Library]` and `[Author From Scratch]`.

#### Library Browse

- Server-side filtered: `is_library_entry=True`, `tier=pending.tier`
- Default sort: matching `origin_affinity` first, then matching
  `origin_resonance`, then everything else
- Card display: name, description excerpt, side-effect summary line,
  resonance bonus summary, visibility indicator
- Two actions per card:
  - `[Use as-is]` — resolves with `resolved_alteration=library_entry_pk`.
    Multiple characters can FK to the same staff-authored template.
  - `[Customize]` — spins off a new `MagicalAlterationTemplate` with
    `parent_template=library_entry`, `authored_by=current_player`,
    `is_library_entry=False`. Lands in the author-from-scratch form
    pre-populated. Affinity/resonance locked.

#### Author From Scratch

Form fields:
- **Name** — required, 3-60 chars
- **Player description** — required, minimum `MIN_DESCRIPTION_LENGTH`
- **Observer description** — required, minimum `MIN_DESCRIPTION_LENGTH`
- **Weakness damage type** — `DamageType` picker (required if weakness magnitude > 0)
- **Weakness magnitude** — slider, 0 to tier cap
- **Social reactivity magnitude** — slider, 0 to tier cap
- **Social reactivity target** — observer category picker (see Open Questions)
- **Resonance bonus magnitude** — slider, 0 to tier cap (always against `pending.origin_resonance`)
- **`is_visible_at_rest`** — checkbox, locked True at tier 4+

Live preview pane shows what the condition will look like with all three
effect summaries rendered.

#### Submit Flow (atomic transaction)

1. Validate all rules
2. Create `ConditionTemplate` with name, descriptions, base fields
3. Create effect rows: `ConditionResistanceModifier` (weakness),
   `ConditionCheckModifier` (social reactivity), magic-side resonance modifier
4. Create `MagicalAlterationTemplate` OneToOne'd to the new condition
5. Call `apply_condition(sheet.character, condition_template)` — where
   `sheet` is the `CharacterSheet` instance and `sheet.character` is its
   OneToOne FK to `ObjectDB`, matching `apply_condition()`'s existing
   signature which accepts `ObjectDB`. Instantiates `ConditionInstance`
6. Create `MagicalAlterationEvent` with trigger snapshot + FKs
7. Mark `PendingAlteration` as RESOLVED with `resolved_alteration`,
   `resolved_at`, `resolved_by`

Progression gate releases automatically.

### 6. Progression Gate

**Mechanism:**

```python
def has_pending_alterations(character: CharacterSheet) -> bool:
    return PendingAlteration.objects.filter(
        character=character,
        status=PendingAlterationStatus.OPEN,
    ).exists()
```

Every "spend points to make thing go up" endpoint calls this. If True,
raises `AlterationGateError` with a user-facing message directing the
player to the alteration resolution screen.

**Blocked (intentional spend actions):**
- XP spending
- Legend point spending
- Technique creation / upgrade
- Distinction acquisition
- Any future "click button, points go down, sheet goes up" endpoint

**NOT blocked (autonomous progression and gameplay):**
- Passive accumulation (XP gain, DP gain, Legend gain)
- Autonomous skill DP level-ups (check-based, fires when threshold crossed)
- AP spending (action economy, not progression)
- The alteration resolution flow itself
- Staff override (see below)

**Design principle:** the alteration gate blocks intentional spend actions,
not autonomous progression. Players should never be punished for playing
while the gate is up.

**Affected endpoint checklist:** produced during implementation by grepping
for current spend endpoints. New spend endpoints added later are responsible
for checking the gate themselves.

**Frontend UX:** spend buttons disabled with tooltip. Persistent banner on
character sheet links to alteration resolution screen.

### 7. Staff Tools

**Staff override:** set `PendingAlteration.status = STAFF_CLEARED` via
Django admin or staff-only API endpoint. `resolved_alteration` stays null,
`resolved_by` set to staff account, `notes` captures reason. No
`MagicalAlterationEvent` created. Gate releases immediately.

Use cases: bugs creating erroneous pendings, returning players with stale
gates, edge cases not yet anticipated.

### 8. Frequency & Rarity

Magical alterations are an uncommon consequence of sustained overburn, not
a routine cost of magic use. The Soulfray stage consequence pools control
how often `MAGICAL_SCARS` is selected:

- **Stage 1-2:** scars are rare or absent from the pool. Most consequences
  are temporary debuffs, anima feedback, or cosmetic mishaps.
- **Stage 3:** scars enter the pool at low weight. A character who pushes
  here occasionally might get one over several sessions.
- **Stage 4-5:** scars are weighted heavily. Characters who routinely push
  this deep *will* accumulate them — the intended cost of extreme power.

A conservative player may never receive a magical alteration. A character
who habitually pushes into Audere and deep Soulfray will collect several
over their arc — each one a dramatic marker of how far they've gone.

## Side-Effect Taxonomy (What Scope 5 Does and Doesn't Support)

Three buckets of possible alteration effects:

**1. Standard package (Scope 5 — full support):**
Social reactivity, weakness/vulnerability, resonance bonus. These are the
three magnitude fields on `MagicalAlterationTemplate`, all tier-bounded,
all mapped to existing condition effect rows at finalization time.

**2. Pure narrative texture (Scope 5 — full support):**
"Voice of many when speaking," "eyes are obsidian mirrors." Lives entirely
in `player_description` and `observer_description` on the `ConditionTemplate`.
No mechanical hook beyond the standard social reactivity.

**3. Discrete static mechanical effects (Scope 5 — staff-only via admin):**
ConditionCapabilityEffect rows granting capabilities (e.g., "arm of shadow
gives natural weapons"). The underlying `ConditionTemplate` already supports
this. Staff can author these via Django admin when creating library entries.
The player-authored form is constrained to the three standard magnitudes.
Future scope: expose capability effect authoring in the constrained-authoring
UI with tier-appropriate guards.

**4. Reactive environmental effects (deferred to Scope 5.5):**
"Walking on holy ground forces a save against bursting into flame." Requires
the reactive trigger infrastructure: event emission at movement/action
moments, service function surface for flows, `ConditionTemplate.reactive_triggers`
M2M to `flows.TriggerDefinition`. Documented in `docs/roadmap/magic.md`
Scope 5.5 and `docs/roadmap/ROADMAP.md` critical infrastructure gap section.

Eventually players and GMs should be able to author reactive triggers via
the same constrained-authoring pattern, with magnitude caps keyed to trust
level. Scope 5.5 should design with constraint tiers baked in from the start.

## Future: Constrained Authoring as Reusable Pattern

The structured-form → validate-against-ceiling → atomic-effect-creation
pipeline in this scope is the reference implementation for future authoring
systems:

- **Technique authoring** (post-CG) — player creates techniques within
  budget/level constraints
- **Magical effect authoring** — player/GM defines technique effects
  within effect type and intensity tier constraints
- **GM consequence authoring** — GM defines consequence pool entries
  within trust-level constraints

When building the next constrained-authoring system, reference how Scope 5
handles validation (single validator function), atomic creation (transaction
wrapping template + effect rows + application), and tier-bounded caps
(constants/config model).

**Exclusions:** covenant role effects are NOT player-authorable. Role
interdependencies are a core game balance concern; player authoring would
undermine group play requirements. Staff-only, always. Technique capability
grants via player authoring are still under discussion.

## Testing Strategy

### New Factories (`world/magic/factories.py`)

- `MagicalAlterationTemplateFactory` — creates ConditionTemplate +
  OneToOne extension with configurable tier, origin, magnitudes
- `PendingAlterationFactory` — creates OPEN pending with trigger snapshot
- `MagicalAlterationEventFactory` — creates resolved event

### Unit Tests (`world/magic/tests/`)

**Model tests:**
- Template creation with all field combinations
- PendingAlteration status transitions (OPEN → RESOLVED, OPEN → STAFF_CLEARED)
- Same-scene dedup: second hit upgrades tier, doesn't create new row
- Duplicate library entry rejection (character already has that condition)

**Service tests:**
- `create_pending_alteration()` — creates row, returns it
- Same-scene escalation — higher tier upgrades, lower tier no-ops
- `resolve_pending_alteration()` — atomic condition + event + mark resolved
- `has_pending_alterations()` — correct for OPEN/RESOLVED/STAFF_CLEARED
- Staff clear flow — status set, no event, gate releases

**Validation tests:**
- Tier mismatch rejected
- Origin mismatch rejected
- Magnitude exceeds tier cap rejected
- `is_visible_at_rest=False` at tier 4+ rejected
- Description below minimum length rejected
- Non-staff `is_library_entry=True` rejected
- Library entry duplicate-on-character rejected

**Progression gate tests:**
- Spend endpoint returns AlterationGateError when OPEN pending exists
- Succeeds when no pending exists
- Succeeds after resolution
- Succeeds after staff clear
- Autonomous skill DP level-up proceeds regardless

### Integration Tests (`integration_tests/pipeline/`)

**Core flow test:**
- Factory-build character with resonances, affinities, technique, Soulfray
  stage consequence pool with MAGICAL_SCARS entry
- Use technique, push into Soulfray, get pool to fire MAGICAL_SCARS
- Assert PendingAlteration created with correct tier/origin/snapshot
- Resolve via author-from-scratch with valid payload
- Assert ConditionTemplate + ConditionInstance + MagicalAlterationEvent created,
  pending RESOLVED, gate released

**Same-scene escalation test:**
- Two overburns in one scene, both hit MAGICAL_SCARS
- Assert one PendingAlteration at the higher tier

**Library browse test:**
- Seed staff library entries at multiple tiers
- Assert query returns only matching-tier entries
- Use-as-is: shared template FK, no new template
- Customize: new template with parent_template set

## Open Questions (Resolve During Implementation)

**1. Social reactivity observer target.** What does "magic-phobic" filter
against? Options: (a) Property tag on characters/personas, (b) Society
membership, (c) free-form category string. Lean toward (a) — verify
Properties can be applied to characters during implementation.

**2. Cap value tuning.** The Fibonacci-ish caps (1/2/3/5/8 and 1/2/3/5/7)
are starting points. Final tuning during playtesting.

**3. Technique-use result persistence.** Snapshot fields are denormalized
because technique uses don't persist today. Revisit when combat/scene
recording ships.

## Deferred Items

- **Scope 5.5 (Reactive Foundations)** — reactive triggers on conditions,
  event emission, service function surface for flows, constrained trigger
  authoring for players/GMs. Critical follow-up, documented in roadmap.
- **Body-part semantics** — structured `body_location` field deferred until
  items/equipment ships and defines the body location vocabulary.
  `is_visible_at_rest` covers the coarse visibility question for now.
- **Discrete mechanical effects in player form** — expose
  ConditionCapabilityEffect authoring with tier guards. Future scope.
- **Alteration removal / cure mechanics** — permanent for now. Removal via
  bespoke quests or powerful rituals is a future story-driven feature.
- **Magic app FK migration** — legacy `CharacterResonance.character` FK
  points to ObjectDB. New tables use CharacterSheet correctly; legacy FK
  is tech debt for a separate migration PR.
