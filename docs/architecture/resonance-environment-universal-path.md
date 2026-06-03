# Resonance-Environment Universal Path — Design

**Status:** Draft (brainstorm complete 2026-05-16)
**Owner:** Tehom (magic + core infrastructure)
**Supersedes:** the "Bounded slice scope" §1 ("Universal cast subscriber via a
ubiquitous baseline condition"), the "No infra change to the Trigger model"
section, and deferred item #3 ("'Magically Attuned' grant mechanism") of
`docs/architecture/resonance-environment-interaction.md`.
Deletes the roadmap's recommended next step #1 ("'Magically Attuned' production
grant") in `docs/roadmap/magic.md` — it is **removed, not implemented**.
**Builds on:** the `evaluate_resonance_environment()` primitive (evaluation
logic unchanged; its result dataclass gains two additive fields — see
"Primitive result change"), the `AffinityInteraction` 9-row tuning table, the
`ResonanceEnvironmentConfig` singleton, and the authored backfire
`ConditionTemplate`s (Tempered Against Light / Singed / Burning / Hallowed Burn
/ Cast Disrupted) shipped by the 2026-05-15 spec — all retained.

## Why this spec exists

The 2026-05-15 slice made the universal resonance-environment reaction fire by
applying a ubiquitous baseline `ConditionTemplate` ("Magically Attuned") to
every magic-capable character, whose `reactive_triggers` M2M carried a
`TECHNIQUE_CAST` `TriggerDefinition` that ran an authored `FlowDefinition`.

That shape is wrong by construction:

- A `ConditionInstance` row on **every** PC encodes "this is a PC." It has no
  contrast class among PCs, carries zero information, and is denormalized
  overhead. The fact is already derivable from data we store.
- A `FlowDefinition` + `TriggerDefinition` is being used to model a **normal,
  expected, universal** gameplay process. Flows/triggers are for *authored
  content with sequenced/branching logic* (rituals, techniques,
  challenge/combat consequences) and *genuine per-entity exceptions* (a unique
  scar on a specific character; a unique ward on a specific room). They must
  not model a baseline process that applies to all casters by default.
- The pipeline test applying that marker condition in `setUp` is itself the
  smell: the test exercised plumbing, not the production path.

This spec replaces the universal-subscriber mechanism. It does **not** redesign
the primitive, the tuning table, the config, or the authored injury conditions.

## The principle this encodes

1. **Magic-capability is derived, never asserted.** A character is magically
   active iff it has a related `CharacterAura`. `CharacterAura` is the object
   that holds magic stats; `CharacterAura.glimpse_story` literally records the
   character's first awakening ("The Glimpse"). It is created **unconditionally**
   for every finalized character by `finalize_magic_data()` during CG. NPCs and
   constructs go through no CG, so they have no aura — that *absence* is
   Quiescence. Nothing is granted, stored, backfilled, or made idempotent: the
   predicate is a relation lookup. The entire "grant mechanism / which
   characters qualify / existing-roster backfill / double-apply guard" problem
   dissolves because we stop storing a derivable fact.

2. **Universal magic-physics is a core service, not a flow/trigger.** The
   resonance-environment reaction is a peer of `accrue_corruption_for_cast` — a
   direct, gated call in the relevant core pipeline. No event, no trigger, no
   flow for the universal path.

3. **Authored ≠ flow, and a Condition is not required to carry a modifier.**
   The tunable content is *data*: consequence pools (`actions.ConsequencePool`)
   for the OPPOSED check, and an authored boon-tier table for ALIGNED. The
   condition/trigger/flow machinery remains correct and expected for authored
   content with sequencing (rituals, techniques, challenges) and for genuine
   per-entity exceptions (the deferred scar-gated presence-escalation), but not
   for this universal path.

## The predicate

```python
# world/magic/services/resonance_environment.py  (alongside the primitive)

def magical_profile(character_sheet: "CharacterSheet") -> "CharacterAura | None":
    """Return the character's CharacterAura, or None if not magically active.

    Magically active == the sheet's character has a related CharacterAura
    (every finalized PC; created unconditionally at CG by
    finalize_magic_data). A CharacterSheet may exist without an aura (an NPC
    sheet, a not-yet-finalized character) → that is Quiescent. This is the
    sole magic-capability gate; it stores nothing and is not granted.

    Resolves `character_sheet.character.aura` (CharacterAura is
    OneToOne(ObjectDB); `CharacterSheet.character` is the OneToOne to that
    same ObjectDB, identity-mapped). Returns None on
    `RelatedObjectDoesNotExist`.
    """
```

### Typed surface — extension models, not typeclasses (binding)

Every new function is typed to the **one-to-one extension model**, not the
Evennia typeclass and never bare `ObjectDB`/`DefaultObject`. The typeclass is
only the grid-permanence core; the extension model is the smallest, most
specific table that carries the data — and it matches the existing
`accrue_corruption_for_cast(*, caster_sheet: CharacterSheet)` sibling exactly.

| Function | Signature |
|---|---|
| predicate | `magical_profile(character_sheet: CharacterSheet) -> CharacterAura \| None` |
| cast service | `resonance_environment_for_cast(*, caster_sheet: CharacterSheet, room_profile: RoomProfile, technique: Technique \| None) -> ResonanceEnvironmentCastResult` |
| movement service | `refresh_resonance_alignment(*, character_sheet: CharacterSheet) -> None` |

`CharacterSheet` (`world.character_sheets.models`) is
`OneToOneField(ObjectDB, related_name="sheet_data", primary_key=True)`;
`RoomProfile` (`evennia_extensions`) has `room.room_profile` ↔
`room_profile.objectdb`.

**Conversion at the retained-primitive boundary (accepted, localized).** The
retained `evaluate_resonance_environment(caster: DefaultObject,
room: DefaultObject, …)` and `apply_condition(target: ObjectDB, …)` are
typeclass/ObjectDB-oriented. The new services down-convert at exactly that
call boundary — `caster_sheet.character` (the ObjectDB; identity-mapped,
PK-shared with the sheet) and `room_profile.objectdb` — never by widening the
public parameter type. A localized hop to satisfy a legacy callee is fine; a
broad public type is not. **Non-goal:** re-typing the retained primitive's
`DefaultObject` params (or `apply_condition`'s `ObjectDB` target) is a
pre-existing concern, explicitly out of scope here.

## Two integration points

The universal reaction has two halves with different timing and different
natural homes. Both are core services gated by `magical_profile`.

### A. OPPOSED backfire — cast pipeline (post-resolve)

Backfire is the place's response to a **completed working**: you only get
Singed/Burned if you *cast* opposed magic there. This is inherently cast-time.

`resonance_environment_for_cast(*, caster_sheet: CharacterSheet,
room_profile: RoomProfile, technique)` lives in
`world/magic/services/resonance_environment.py` and is called from the
technique-use orchestrator (`world/magic/services/techniques.py`) immediately
after the existing `accrue_corruption_for_cast(caster_sheet=sheet, …)` call
(the orchestrator already holds `sheet`; it resolves `room_profile` from
`caster_room.room_profile`, treating `RoomProfile.DoesNotExist` as inert —
no profile ⇒ no room resonance). It emits no event and runs no flow.

```
aura = magical_profile(caster_sheet)
if aura is None: return inert
caster = caster_sheet.character          # ObjectDB; identity-mapped, PK-shared
room   = room_profile.objectdb           # down-convert ONLY at the primitive boundary
effect = evaluate_resonance_environment(caster=caster, room=room, technique=technique)
if effect.magnitude == 0:                      return inert     # primitive short-circuit
if effect.kind == AffinityInteractionKind.CORRUPT: return inert # deferred (direction still computed)
if effect.valence == OPPOSED and effect.kind in (REJECT, REPEL):
    interaction = effect.interaction           # carried on the result; NO re-query
    pool = interaction.consequence_pool        # FK on a loaded instance (identity-mapped)
    if pool is None: return inert              # no authored content for this pairing yet
    pending = select_consequence(
        caster, endure_hallowed_ground_check_type,
        effect.backfire_difficulty, pool.cached_consequences,  # cached_property, not a query
    )
    apply_resolution(pending, ResolutionContext(... caster, room, technique ...))
# ALIGNED is NOT handled here — it is presence-tied (Integration point B).
```

- `backfire_difficulty` is the config-derived value
  `ResonanceEnvironmentConfig.backfire_base_difficulty +
  round(magnitude * backfire_difficulty_per_magnitude)`. **Correction to an
  earlier draft claim:** this is currently computed in the flow adapter
  `flows/service_functions/resonance_environment.py`
  (`flow_evaluate_resonance_environment`), *not* in the primitive — and that
  adapter is deleted by this spec. The computation **moves into the primitive**
  and is returned on the result dataclass (see "Primitive result change"
  below). The primitive already reads `ResonanceEnvironmentConfig`, so config
  access stays in one place and the service stays a thin consumer.
- The `Consequence` rows in the pool carry `ConsequenceEffect`s with
  `effect_type=APPLY_CONDITION` pointing at the **existing** Tempered Against
  Light / Singed / Burning / Hallowed Burn / Cast Disrupted templates, keyed by
  `CheckOutcome` tier (Critical Success → Tempered; Success → Singed; Failure →
  Burning; Critical Failure → Hallowed Burn + Cast Disrupted). These conditions
  are genuine lingering injuries (DoT, stages) — Conditions are the right
  vehicle here; this is unchanged authored content, now selected by the generic
  `select_consequence()` pipeline instead of a hand-built flow branch chain.

**Data-access contract (mandatory — see "Data-access discipline" below).** The
primitive already resolves the `AffinityInteraction` to compute valence / kind /
severity. Its result dataclass **must carry that resolved model instance** as
`effect.interaction` (the existing `source_affinity` / `environment_affinity`
fields stay for display, but consumers never re-derive the row from them). No
service, view, or serializer issues a query for an `AffinityInteraction`, a
`ConsequencePool`, its consequences, or `ResonanceAlignmentBoonTier` rows: the
instance is carried, and pool/tier collections are reached via `cached_property`
accessors on the models. This is not optional and not "either is acceptable" —
it is the project's SharedMemoryModel data-access rule.

#### Primitive result change (additive; required by this spec)

The live `ResonanceEnvironmentEffect` (frozen dataclass in
`world/magic/services/resonance_environment.py`) currently has six fields:
`valence, kind, direction, magnitude, source_affinity, environment_affinity`.
This spec adds **two** fields:

```python
@dataclass(frozen=True)
class ResonanceEnvironmentEffect:
    valence: str
    kind: str
    direction: str
    magnitude: int
    source_affinity: Affinity | None
    environment_affinity: Affinity | None
    interaction: AffinityInteraction | None   # NEW: resolved row (None when inert)
    backfire_difficulty: int                  # NEW: 0 when inert / not OPPOSED
```

- `evaluate_resonance_environment` already resolves the `AffinityInteraction`
  (via the cached `AffinityInteraction.objects.interaction_for(...)` accessor)
  to compute valence/kind/severity — it now also stores that instance on the
  result and computes `backfire_difficulty` from `ResonanceEnvironmentConfig`
  (the logic relocated out of the deleted flow adapter).
- `_inert()` returns `interaction=None, backfire_difficulty=0`.
- This is **additive and non-breaking** at the call sites: the only consumer of
  the *result fields* is `flow_evaluate_resonance_environment` (deleted here).
  The new callers (`resonance_environment_for_cast`,
  `refresh_resonance_alignment`, the reworked pipeline test) consume the new
  fields. No 2026-05-15 result-consumer survives that depends on the old
  6-field shape.
- However, the primitive's own unit tests
  (`world/magic/tests/test_evaluate_resonance_environment.py`) call
  `evaluate_resonance_environment` directly and may construct
  `ResonanceEnvironmentEffect` instances. Since the dataclass is
  `frozen=True` with no field defaults, **every** construction site
  (the primitive's non-inert return, `_inert()`, and any test) must pass the
  two new fields. The plan must decide explicitly: either give `interaction`
  and `backfire_difficulty` dataclass defaults (`= None` / `= 0`) so existing
  construction sites keep compiling, or update every construction site to pass
  them. Recommended: no defaults (frozen result objects should be fully
  explicit); update the primitive's two return paths and the unit tests.
- Implementation plan must therefore include a concrete task to: add the two
  fields, update `_inert()`, update the non-inert `evaluate_resonance_environment`
  return site, relocate the `backfire_difficulty` computation out of the
  deleted flow adapter into the primitive, and update
  `test_evaluate_resonance_environment.py` for the new shape.

### B. ALIGNED boon — movement pipeline (presence-tied)

Casting in an aligned place cannot retro-amplify a working that has already
resolved (the service runs post-resolve). The product intent is a **named,
player-visible buff that exists while you are in the resonant place** — "you
move here and can see you are empowered." That is a presence-tied Condition,
not a cast reaction and not a fixed-duration timer.

A core service re-evaluates alignment on **arrival**:

```python
# world/magic/services/resonance_environment.py
def refresh_resonance_alignment(*, character_sheet: "CharacterSheet") -> None:
    """Idempotently reconcile the character's resonance-alignment buff with
    the room they are now in. Called on arrival; safe to call repeatedly.
    Param is the CharacterSheet extension model, not a typeclass/ObjectDB."""
```

Wired from `Character.at_post_move`, which calls
`refresh_resonance_alignment(character_sheet=self.sheet_data)` (the established
typeclass→extension hop, already used by `Character.at_post_puppet`).
`obj = character_sheet.character` is the ObjectDB (identity-mapped, PK-shared)
used only where a legacy callee requires it. Logic:

1. Remove any existing resonance-alignment buff `ConditionInstance` on
   `obj` (`apply_condition`/`remove_condition` are `ObjectDB`-keyed —
   converted at that boundary only). Membership is data-derived but **not**
   re-queried in the service: the set of boon `ConditionTemplate`s is exposed
   by a cached lookup accessor
   `ResonanceAlignmentBoonTier.objects.boon_condition_templates()` (loads the
   small fixed set once into memory; the handler form of the rule for a fixed
   lookup table). The service intersects the character's already-cached
   condition instances with that cached set in Python. No marker/flag, no raw
   query. Idempotent.
2. `aura = magical_profile(character_sheet)`; if `None`, return (Quiescent).
3. `room_obj = character_sheet.character.location`; if `None`, return.
   `room_profile = room_obj.room_profile` — on `RoomProfile.DoesNotExist`,
   return (no profile ⇒ no room resonance; buff already cleared in step 1).
4. `effect = evaluate_resonance_environment(caster=character_sheet.character,
   room=room_obj, technique=None)` — presence-time evaluation (the primitive
   already supports `technique=None`; it is typeclass/ObjectDB-oriented, so it
   receives the down-converted objects here, the only boundary that does so).
5. If `effect.valence != ALIGNED` or `effect.magnitude == 0`, return (the
   buff was already cleared in step 1 — covers "left an aligned room" and
   "moved to a non-aligned room").
6. `interaction = effect.interaction` (carried on the result — the ALIGNED
   diagonal row; no query). Read `interaction.cached_alignment_boon_tiers`
   (a `cached_property` on `AffinityInteraction` →
   `list(self.alignment_boon_tiers.all())`). Select the highest-band tier
   **in Python** over that cached list:
   `max((t for t in interaction.cached_alignment_boon_tiers
   if t.min_magnitude <= effect.magnitude),
   key=lambda t: t.min_magnitude, default=None)`.
   If `None`, return (no authored boon for this affinity/band yet).
7. `apply_condition(target=character_sheet.character,
   condition=tier.condition_template, source_description=...)` — no
   `duration_rounds` (it persists until cleared on the next move). Idempotent
   by construction (step 1 cleared first).

This single arrival-time reconcile handles **enter** (apply), **leave to a
non-aligned room** (step 1 clears, steps 5 returns), and **swap** to a room
aligned with a different affinity (clear old, apply new) uniformly. An explicit
clear (the step-1 logic, also keyed on `self.sheet_data`) is invoked from
`at_pre_move` when the destination is `None`, and on unpuppet/logout via
`Character.at_post_unpuppet` (the project forbids Django signals, so the
typeclass hook is the expected seam), so a character does not retain the buff
while not present in any aligned room. The membership-derived clear makes it a
one-liner wherever it lands.

The buff `ConditionTemplate`s are a **family**: different authored
names/descriptions per affinity and per magnitude band, the description
narrating *why* a place of that resonance empowers the caster. The narrative
"why" lives in `ConditionTemplate.description` plus the room's own authored
resonance/description — **no new "why" field**.

## Authored data surfaces

Both poles hang authored content off the existing 9-row `AffinityInteraction`
tuning table — symmetric: OPPOSED selected by check outcome, ALIGNED by
magnitude band.

### `AffinityInteraction.consequence_pool` (new nullable FK)

```python
consequence_pool = models.ForeignKey(
    "actions.ConsequencePool",
    on_delete=models.PROTECT,
    null=True, blank=True,
    related_name="resonance_interactions",
    help_text="OPPOSED backfire pool for this pairing. Null = inert "
              "(CORRUPT-deferred pairs, or pairings with no authored content).",
)
```

`magic → actions` is a consumer→infrastructure dependency, the same direction
as `magic → checks.CheckType`; not a producer→consumer-domain FK, so it does
not implicate the bridge-table rule. `ConsequencePool` already uses
`NaturalKeyMixin` + `SharedMemoryModel`; no new SlugField.

`ConsequencePool` must expose a `cached_consequences` `cached_property`
(`from django.utils.functional import cached_property`) returning the resolved
`Consequence` list across its `ConsequencePoolEntry` rows (and parent-pool
inheritance), mirroring `ChallengeTemplate.cached_consequences`
(`return list(self.challenge_consequences.select_related("consequence"))`).
If it does not already have one, adding it is part of this work — the OPPOSED
service reads `pool.cached_consequences`, never `pool.entries.filter(...)`.

The primitive's own `(source_affinity, environment_affinity) →
AffinityInteraction` resolution must NOT be a per-cast
`AffinityInteraction.objects.get(...)`. Add a cached lookup accessor on the
manager — `AffinityInteraction.objects.interaction_for(source, environment)` —
that loads all 9 rows once into an in-memory `{(source_id, env_id): row}` map
and serves from it thereafter (the handler form of the data-access rule for a
fixed lookup table). The primitive uses that accessor and carries the resolved
row out as `effect.interaction`.

### `ResonanceAlignmentBoonTier` (new authored model)

```python
# world/magic/models/resonance_environment.py
class ResonanceAlignmentBoonTier(SharedMemoryModel):
    """Authored: which named buff ConditionTemplate an ALIGNED pairing grants
    at or above a magnitude threshold. Few rows, staff-tunable."""
    affinity_interaction = models.ForeignKey(
        "magic.AffinityInteraction",
        on_delete=models.CASCADE,
        related_name="alignment_boon_tiers",
        help_text="Must reference an ALIGNED (diagonal) interaction row.",
    )
    min_magnitude = models.PositiveIntegerField(
        help_text="Applies when evaluated magnitude >= this value. "
                  "Service picks the highest matching tier.",
    )
    condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        related_name="resonance_alignment_tiers",
        help_text="The named, player-visible buff applied while present.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["affinity_interaction", "min_magnitude"],
                name="unique_alignment_boon_tier_threshold",
            ),
        ]
```

No `Meta.ordering` (per project rule). Tier selection is **not** a DB
`.order_by().first()` in the service — it is a Python `max(...)` over the
cached list (see Integration point B step 6). `clean()` validates
`affinity_interaction.valence == ALIGNED`. `magic → conditions` FK is the
established direction (cf. `MagicalAlterationTemplate`).

Two cached accessors carry every related-row read for this model so no
consumer queries it directly:

- `AffinityInteraction.cached_alignment_boon_tiers` — `cached_property`
  (`from django.utils.functional import cached_property`) returning
  `list(self.alignment_boon_tiers.all())`. Supports `Prefetch(to_attr=...)`.
  The ALIGNED service reads this; it never calls
  `ResonanceAlignmentBoonTier.objects.filter(affinity_interaction=...)`.
- `ResonanceAlignmentBoonTier.objects.boon_condition_templates()` — a manager
  method that loads and caches the small fixed set of distinct boon
  `ConditionTemplate`s once (the handler form of the rule for a fixed lookup
  table). The movement service's clear step uses this cached set; it never
  re-queries the table per move.

The constant for the `endure_hallowed_ground` check type name and any new
TextChoices live in `world/magic/constants.py` (existing module).

## Data-access discipline (binding constraint)

This design adds two core services that traverse SharedMemoryModel
relationships. The project rule — and a hard constraint on the implementation
plan and review — is: **a Django query for rows related to a SharedMemoryModel
is never issued from a service function, view, or serializer.** Every
relationship traversal goes through a cached interface so it loads once and is
walked in Python thereafter.

Concretely, for this work:

| Related read | Forbidden | Required |
|---|---|---|
| `(source, env) → AffinityInteraction` | `AffinityInteraction.objects.get(source_affinity=…, environment_affinity=…)` in the primitive/service | `AffinityInteraction.objects.interaction_for(...)` cached map; primitive carries the row out as `effect.interaction` |
| interaction → backfire pool | `interaction` re-looked-up in the service | `effect.interaction` (carried instance); `.consequence_pool` FK on the loaded row |
| pool → consequences | `pool.entries.filter(...)` / `.all()` in the service | `pool.cached_consequences` (`cached_property`, like `ChallengeTemplate.cached_consequences`) |
| interaction → boon tiers | `ResonanceAlignmentBoonTier.objects.filter(affinity_interaction=…)` in the service | `interaction.cached_alignment_boon_tiers` (`cached_property`); Python `max()` for band selection |
| boon-template membership set | per-move query over `ResonanceAlignmentBoonTier` | `ResonanceAlignmentBoonTier.objects.boon_condition_templates()` cached set; intersect against the character's already-cached condition instances |

Any cached accessor that does not exist yet is built **before** the consuming
service, as part of this work. A spec/plan/PR that introduces a raw related-row
query in `resonance_environment_for_cast`, `refresh_resonance_alignment`, or the
primitive is rejected. `cached_property` is imported from
`django.utils.functional` (never `functools`).

## Deletions

- `ConditionTemplate` "Magically Attuned" — its seed
  (`_seed_resonance_environment_conditions` portion), its `reactive_triggers`
  wiring, and all references.
- The universal `TriggerDefinition` "Resonance Environment — technique cast"
  and its `_seed_resonance_environment_flow_and_trigger` seeding.
- The universal `FlowDefinition` "Resonance Environment reactive flow" + all its
  `FlowStepDefinition`s.
- The flow adapter `flows/service_functions/resonance_environment.py`
  (`flow_evaluate_resonance_environment`) and its tests, **if** no other caller
  exists (verify; the 2026-05-15 rework already removed the T6/T7 helpers, so
  this adapter is expected to be the sole remaining flow shim).
- The per-character `apply_condition(self.caster, "Magically Attuned")` in the
  pipeline test's `setUp` (and the second-earner apply).
- `RESONANCE_ENV_FLOW_NAME` / `RESONANCE_ENV_TRIGGER_NAME` constants and the
  RC2/RC3 seed-phase ordering comments that reference them.

The primitive, `AffinityInteraction` (the 9 rows), `ResonanceEnvironmentConfig`,
the `endure_hallowed_ground` `CheckType`/`ResultChart`, and the
Tempered/Singed/Burning/Hallowed Burn/Cast Disrupted templates are **retained**.

## Seed rework (`integration_tests/game_content/magic.py`)

- Drop the Magically Attuned condition, the universal trigger, and the universal
  flow seeding helpers.
- Seed, for the OPPOSED pairings used by the slice (the celestial-place pairs
  #4 abyssal-caster and #7 primal-caster), one `ConsequencePool` each with
  `ConsequencePoolEntry` → `Consequence` (one per `CheckOutcome` tier) →
  `ConsequenceEffect(effect_type=APPLY_CONDITION, condition_template=...)`
  mapping the existing injury templates; set `AffinityInteraction.consequence_pool`.
- Seed the ALIGNED boon family: at least the abyssal/abyssal pair (#5) with
  ≥2 `ResonanceAlignmentBoonTier` rows (low vs high magnitude band) → two named
  buff `ConditionTemplate`s with authored descriptions justifying the empowerment.
- Keep the 3 cascade rooms (`tag_room_resonance` + magnitude tiers) and the
  config singleton seeding from the 2026-05-15 rework.

## Test rework

`integration_tests/test_magic_story_pipeline.py`:

- `setUp` no longer applies any condition. The caster keeps its abyssal-dominant
  `CharacterAura` (already seeded) and casts — exercising the **real production
  path** through the orchestrator.
- OPPOSED subtests: cast the abyssal technique in the celestial cascade room at
  low and high magnitude tiers; assert the correct injury `ConditionInstance`
  per `CheckOutcome` (recomputed `expected_difficulty` from the config formula,
  as in the 2026-05-15 rework) is applied by `resonance_environment_for_cast`
  → `select_consequence`/`apply_resolution`.
- ALIGNED subtests: move the abyssal caster into the abyssal-aligned room;
  assert the correct named buff `ConditionTemplate` is applied by
  `refresh_resonance_alignment` per magnitude band; move them out and assert it
  is removed; move directly to a differently-aligned room and assert the buff
  swaps.
- Quiescent unit test: a `CharacterSheet` whose character has **no**
  `CharacterAura` (e.g. an NPC sheet, or a not-yet-finalized character) casts /
  moves; assert `magical_profile(character_sheet)` returns `None` and
  `resonance_environment_for_cast` / `refresh_resonance_alignment` no-op
  (inert; nothing applied). (A genuine non-character — the vase of flowers —
  has no `CharacterSheet` at all and cannot even be passed: the services are
  typed to `CharacterSheet`.)
- CORRUPT stub subtest: strong abyssal caster in a weak primal place →
  primitive returns `direction=CASTER_DOMINANT`, `kind=CORRUPT`; assert the
  cast service treats it as inert (the fill-in point for deferred defilement)
  and `direction` is still computed.
- Missing-`CharacterAura` → inert primitive unit test (retained from 2026-05-15,
  now also covered by the Quiescent service test).
- The second-earner Discovery test: drop the `apply_condition` setup; the
  second caster just needs an abyssal `CharacterAura`.

`game_content/tests/test_magic_seed.py`: replace the Magically-Attuned /
universal-trigger / universal-flow assertions with assertions on the seeded
`ConsequencePool`/`Consequence`/`ConsequenceEffect` rows, the
`AffinityInteraction.consequence_pool` FKs, and the `ResonanceAlignmentBoonTier`
rows.

## Out of scope — deferred (unchanged from 2026-05-15; still additive)

1. **Per-character scar-gated presence-escalation.** Heavily-scarred/corrupted
   characters harmed on mere *entry* (OPPOSED presence). This is a genuine
   per-entity exception → correctly a scar-gated MOVED `TriggerDefinition` via
   `ConditionTemplate.reactive_triggers` (the legitimate flow/trigger use). The
   universal ALIGNED presence path added here does **not** subsume it and does
   not block it; `evaluate_resonance_environment(technique=None)` serves both.
2. **Defilement (`CASTER_DOMINANT`).** The primitive still returns the correct
   `direction`; the cast service treats CORRUPT as inert. The deferred work must
   route caster→world corruption through the interceptable `CORRUPTION_ACCRUING`
   event (Soul Tether lever) — unchanged.
3. **Brother's richer formula.** Steps 5–7 of the v1 primitive formula stay
   simple; his follow-up enriches the primitive body. Call sites,
   `AffinityInteraction` data, `ResonanceEnvironmentConfig`, the new pool/tier
   surfaces, and authored content do not change.
4. **`TECHNIQUE_PRE_CAST` block/modify variant.** A true pre-cast intercept that
   could block or modify a working before it resolves still needs
   cancel/modify-payload semantics; out of scope.

## Design principles honored

- No marker condition asserting a universal property; magic-capability derived
  from `CharacterAura` presence.
- Universal magic-physics is a core service (peers of
  `accrue_corruption_for_cast`); no flow/trigger for the universal path. Flows
  and triggers remain for authored sequenced content and per-entity exceptions.
- A Condition is used only where it is the right vehicle: lingering injuries
  (OPPOSED) and a named, player-visible, presence-tied buff (ALIGNED). No
  "apply a condition just to read a modifier off it."
- Tuning is data: consequence pools + boon-tier rows hung off the existing
  `AffinityInteraction` table; staff-tunable, no code change to re-tune.
- **Data-access discipline:** no service/view/serializer issues a query for a
  SharedMemoryModel-related row. The primitive carries the resolved
  `AffinityInteraction` instance on its result; pools/tiers/boon-templates are
  reached via `cached_property` / cached manager accessors; band selection is a
  Python `max()` over a cached list. (See the binding-constraint section.)
- **Extension models, not typeclasses, in the new surface:** the predicate and
  both services are typed to `CharacterSheet` / `RoomProfile` (the smallest,
  most specific tables; matches `accrue_corruption_for_cast(caster_sheet=…)`),
  never the typeclass and never bare `ObjectDB`/`DefaultObject`. Down-convert
  (`sheet.character`, `room_profile.objectdb`) happens only at the retained
  typeclass-oriented callees' boundary; re-typing those is a non-goal here.
- No new SlugField. `SharedMemoryModel` on the new model. Explicit FK
  `on_delete`. New constants/TextChoices in `constants.py`. No `Meta.ordering`
  (selection is in-Python over a cached list, not a DB `.order_by`).
  `cached_property` from `django.utils.functional` (never `functools`).
- Bridge-direction dep stays magic → (actions/checks/conditions/locations),
  the consumer→infrastructure direction already used; no reverse coupling.
- The deferred pieces reuse already-built plumbing and the primitive's
  `technique=None` signature — no parallel systems, no architectural debt.
