# Spec A — Threads and Resonance Currency (Design)

**Status:** draft, in active brainstorming
**Date:** 2026-04-18
**Scope:** Spec A of a three-spec resonance-pivot decomposition. Sibling specs B and C
(Relational Resilience / Soul Tether / Ritual Capstones; and Resonance Gain Surfaces)
are referenced here but authored separately.

---

## 1. Scope & Core Pivot

### The pivot in one sentence

Resonance stops being a rank that passively boosts magic and becomes a per-resonance
**currency** you earn from identity-expressive RP, spend to develop **Threads** (which
anchor to specific stats/skills/techniques/items/places/relationships), and spend again
to **pull** on those Threads during actions for authored mechanical payoff.

### What this spec covers

The Thread + Resonance-currency system as the primary identity-expression and
magic-amplification lever. Data model, economy, pull mechanics, ThreadWeaving unlocks,
migration/cleanup of the old magic.Thread family, and the Magical Scars → Mage Scars
rename.

### What this spec does NOT cover

- **Spec B** — Relational Resilience (the aggregate survivability bonus from having many
  deep relationships), Soul Tether grounding/Sineater mechanics, Ritual Capstones (the
  authoring pipeline for ritual-flavored capstones like Ritual of Devotion / Ritual of
  Betrayal / Accepting a Soul Tether).
- **Spec C** — Resonance gain surfaces: social scenes, peer endorsement, environment/outfit
  tagging, and anything that *writes* to `ResonancePool.balance`. Spec A exposes the
  service function interface Spec C will call; Spec A does not author any gain sites.

### Consequences that fall out of the pivot

1. **Thread model replaced.** The existing `magic.Thread` 5-axis model (romantic, trust,
   rivalry, protective, enmity 0–100, plus `is_soul_tether`) is replaced with a uniform
   "thread attachment" model. The 5-axis emotional content is already captured better
   in the relationships app's tracks; `is_soul_tether` migrates to `CharacterRelationship`.
2. **Satellite magic models deleted.** `ThreadType`, `ThreadJournal`, `ThreadResonance`,
   and `CharacterResonanceTotal` go away. Rationale below.
3. **Resonance semantics change.** `CharacterResonance` no longer stores a rank/level;
   a new `ResonancePool` model stores per-character per-resonance currency balance.
   `CharacterResonance` continues to identify which resonances a character has
   personally developed (identity list), separate from pool balance.
4. **ThreadWeaving unlock family.** A new authored catalog of unlocks gates which
   categories/instances a character can weave threads into, with Path-based in-band
   pricing and out-of-Path penalties. Taught by Gift-specific teachers.
5. **Cosmetic rename.** Magical Scars → Mage Scars throughout strings, docs, and model
   verbose_names. No schema change.

### Journaling preservation

Deleting `ThreadJournal` does not lose journaling — the need is served by richer existing
systems:

- **Relationship-anchored threads** inherit evolution narrative from the relationships
  app's existing `RelationshipUpdate`, `RelationshipDevelopment`, `RelationshipCapstone`,
  and `RelationshipChange` writeup models. Each writeup is authored with title/body/author
  and IS the mechanism by which the track's points move — the narrative *why* for a thread
  anchored to a track or capstone is already stored alongside it.
- **Non-relationship threads** (traits, techniques, items, rooms) get narrative through
  the general `journals.JournalEntry` model, via a new optional M2M
  `JournalEntry.related_threads`. A player can tag an entry as "this is about my
  grandfather's sword" and the thread's sidebar aggregates it.
- **"Who I Am" character page** in the UI aggregates: each Thread's anchor + resonance +
  related narrative writeups. This is a feature gain over ThreadJournal's flat
  character-pair evolution log.

---

## 2. Data Model

### 2.1 New models

#### `Thread`

Replaces the existing magic.Thread entirely. Uses a **discriminator + typed FK columns**
pattern (not a GFK and not a pseudo-GFK with `(target_type, target_id)` ints).

```
owner                     FK CharacterSheet
resonance                 FK Resonance
target_kind               CharField choices:
                            TRAIT | TECHNIQUE | ITEM | ROOM |
                            RELATIONSHIP_TRACK | RELATIONSHIP_CAPSTONE
developed_points          PositiveIntegerField default=0
level                     PositiveSmallIntegerField default=0
created_at, updated_at

# Typed target FKs — exactly one populated, keyed by target_kind
target_trait              FK Trait                      null=True on_delete=PROTECT
target_technique          FK Technique                  null=True on_delete=PROTECT
target_object             FK ObjectDB                   null=True on_delete=PROTECT
                                                        # carries ITEM and ROOM
target_relationship_track FK RelationshipTrackProgress  null=True on_delete=PROTECT
target_capstone           FK RelationshipCapstone       null=True on_delete=PROTECT
```

**Six target_kinds, five FK columns.** STAT and SKILL collapse into TRAIT (the `Trait`
table's own `trait_type` disambiguates). ITEM and ROOM share `target_object` (ObjectDB)
and are split at the discriminator level for authorial intent — ThreadPullEffect rows
can be scoped differently for items vs. rooms without typeclass introspection at read
time. Gifts are NOT thread anchors; they appear only as unlock scopes in
`ThreadWeavingUnlock`.

**All deletes are PROTECT.** Nothing with character history gets hard-deleted in this
project; retirement flows through an explicit service, not cascades.

**Integrity enforced at three layers:**

1. **`clean()`** — asserts exactly one `target_*` FK is populated and matches `target_kind`.
   For ITEM and ROOM, additionally validates `target_object.db_typeclass_path` against
   the expected typeclass family.
2. **Database `CheckConstraint`s** — one `Q()` expression per `target_kind` value
   confirming the right column is not-null and the others are null. PostgreSQL enforces
   this even on raw writes.
3. **Partial unique indexes** — one per `target_kind`, e.g.
   `UniqueConstraint(fields=["owner","resonance","target_trait"],
   condition=Q(target_kind="TRAIT"), name="uniq_thread_trait")`. Prevents duplicate
   threads per kind without needing a composite across mutually-exclusive columns.

**Helper:** `Thread.target` property returns the populated FK object, picked by
`target_kind`. Django ORM `select_related("target_trait", "target_technique",
"target_object", ...)` works natively because each FK column is real.

#### `ResonancePool`

```
character        FK CharacterSheet
resonance        FK Resonance
balance          PositiveIntegerField default=0   # no cap — see economy decisions
lifetime_earned  PositiveIntegerField default=0   # audit/metrics, never decremented
class Meta: unique_together = (character, resonance)
```

Balance is the spendable currency. `lifetime_earned` supports analytics and potential
retro-unlocks. Rows are created lazily when a character first earns that resonance.

#### `ThreadPullCost` (lookup, SharedMemoryModel)

```
tier             PositiveSmallIntegerField unique   # 1, 2, 3
resonance_cost   PositiveSmallIntegerField          # 1, 3, 6 at launch
anima_per_thread PositiveSmallIntegerField          # flat per extra thread
label            CharField                          # "soft", "hard", "max"
```

Staff-tunable. Three rows at launch.

#### `ThreadLevelThreshold` (lookup, SharedMemoryModel)

```
level                PositiveSmallIntegerField unique   # 1..max
developments_needed  PositiveSmallIntegerField          # cumulative devs to qualify
resonance_cost       PositiveSmallIntegerField          # resonance to click level up
```

The development-threshold gate. A player's thread accumulates `developed_points`
passively from RP/interaction; at each threshold the level does not tick up until they
spend the row's `resonance_cost` from the matching `ResonancePool`.

#### `ThreadPullEffect` (authored templates, SharedMemoryModel)

```
target_kind        CharField choices (same 6 as Thread.target_kind)
resonance          FK Resonance null=True      # null = default fallback for target_kind
tier               PositiveSmallIntegerField   # 0, 1, 2, 3 — see tier-0 = passive note
effect_kind        CharField choices:
                     FLAT_BONUS | INTENSITY_BUMP | CAPABILITY_GRANT | NARRATIVE_ONLY

# Typed payload — no JSON. Resolver reads the field matching effect_kind.
flat_bonus_amount       SmallIntegerField   null=True
intensity_bump_amount   SmallIntegerField   null=True
capability_grant        FK Capability        null=True

# Optional inline prose for ANY effect_kind. Substituted into the action's
# narrative output when this row applies. Replaces the prior ThreadNarrativeTag
# model (which was a separate lookup just to hang a string on a row — overkill).
# A NARRATIVE_ONLY row's snippet IS its entire effect. Snippets on FLAT_BONUS,
# INTENSITY_BUMP, and CAPABILITY_GRANT rows are also collected and rendered
# alongside the mechanical payload — the snippet is additive, not exclusive.
narrative_snippet       TextField   blank=True
```

**Tier 0 is passive (always-on); tiers 1–3 are paid pulls.** When a thread's anchor
is involved in an action, tier-0 effects always apply — no pull, no cost. Pulls at
tier N additionally apply effects at tiers 1..N. `ThreadPullCost` has rows only for
paid tiers (1, 2, 3); tier 0 is implicit-zero.

Resolution order when an action lands: for each thread whose anchor is involved,
find ThreadPullEffect rows matching `(target_kind=thread.target_kind, tier in
0..chosen_tier)`, preferring rows with the matching resonance and falling back to
`resonance=NULL`. Apply every matching row's effect and substitute its snippet.

**Field-name note:** `target_kind` is used uniformly across `Thread`,
`ThreadPullEffect`, and `ThreadWeavingUnlock`. Avoid the synonym `target_type` to
keep query/serializer code consistent.

#### `ThreadWeavingUnlock` (authored catalog, SharedMemoryModel)

Same discriminator + typed FK pattern as `Thread`. Each anchor type has its natural
granularity — there's no uniform "scope" enum; the right FK is the right granularity.

```
ThreadWeavingUnlock
  name                    CharField unique         # "ThreadWeaving for Seduction"
  description             TextField
  target_kind             CharField choices        # same as Thread.target_kind minus
                                                    #   RELATIONSHIP_CAPSTONE
                                                    #   (subordinate to track unlock)

  # Discriminator-driven FKs — exactly one populated per target_kind
  unlock_trait              FK Trait              null=True   # TRAIT: per specific Trait
  unlock_gift               FK Gift               null=True   # TECHNIQUE: covers all
                                                              #   techniques under Gift
  unlock_item_typeclass_path CharField   blank=True            # ITEM: typeclass path,
                                                              #   e.g. "typeclasses.
                                                              #   weapons.Sword"
                                                              # validated against a
                                                              # module-level constant
                                                              # in world/magic/constants.py
                                                              # (THREADWEAVING_ITEM_TYPECLASSES)
                                                              # at save; covers all
                                                              # item subclasses by
                                                              # typeclass inheritance
  unlock_room_property      FK Property           null=True   # ROOM: any room with
                                                              #   this property
  unlock_track              FK RelationshipTrack  null=True   # RELATIONSHIP_TRACK:
                                                              #   per track type

  xp_cost                 PositiveIntegerField
  paths                   M2M Path                 # which Paths treat as in-band
  out_of_path_multiplier  DecimalField default=2.0
```

Granularity by target_kind:

- `TRAIT` — one unlock per specific Trait (Strength, Seduction, Agility, etc.). NPC
  teachers like "Path-of-Steel master teaches ThreadWeaving for Strength" or "succubus
  teaches ThreadWeaving for Seduction" map directly.
- `TECHNIQUE` — one unlock per Gift, covering all techniques under it. Buying
  "ThreadWeaving for the Gift of the Blade" lets the character weave into every
  blade-Gift technique they know.
- `ITEM` — one unlock per item typeclass path. "ThreadWeaving for Swords" maps to
  `typeclasses.weapons.Sword` and covers any subclass by typeclass inheritance. New
  item categories normally come into existence as new typeclasses, so this dimension
  is the natural fit. Allowed paths are registered (small registry) and validated at
  save. If we ever need orthogonal categories that don't match typeclass boundaries,
  add an `ItemCategory` model later — the discriminator can carry both.
- `ROOM` — one unlock per Property. "ThreadWeaving for Consecrated Spaces" lets the
  character weave threads into any room tagged with that property.
- `RELATIONSHIP_TRACK` — one unlock per RelationshipTrack type. "ThreadWeaving for
  Romantic Bonds" / "for Antagonistic Bonds" / "for Mentorship Bonds." Capstones
  inherit from the parent track's unlock.

`clean()` enforces discriminator/FK match exactly like `Thread.clean()`. Database
`CheckConstraint`s enforce the same at the row level.

#### `CharacterThreadWeavingUnlock` (record of purchase)

```
character        FK CharacterSheet
unlock           FK ThreadWeavingUnlock
acquired_at      DateTimeField auto_now_add=True
xp_spent         PositiveIntegerField    # actual cost paid (in-Path or out-of-Path)
teacher          FK RosterTenure null=True   # who taught it (audit, not enforcement)
class Meta: unique_together = (character, unlock)
```

A new model, parallel to `progression.CharacterUnlock` (which is class-level-only,
not a generic unlock catalog). Records that a character has bought the right to
weave threads against the unlock's anchor scope. Path multiplier (out-of-Path)
applies at acceptance time and is captured in `xp_spent`, not stored on the offer.

Eligibility check when a player attempts to weave a new thread on an anchor:

- TRAIT → `CharacterThreadWeavingUnlock(unlock__unlock_trait=anchor)` exists
- TECHNIQUE → `CharacterThreadWeavingUnlock(unlock__unlock_gift=anchor.gift)` exists
- ITEM → `CharacterThreadWeavingUnlock(unlock__unlock_item_typeclass_path=p)` exists
  for some `p` such that `anchor.db_typeclass_path` is `p` or a subclass of it
  (typeclass-inheritance walk)
- ROOM → `CharacterThreadWeavingUnlock(unlock__unlock_room_property in
  anchor.properties)` exists
- RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE →
  `CharacterThreadWeavingUnlock(unlock__unlock_track=anchor.track_type)` exists

### 2.2 Modified existing models

#### `CharacterRelationship` gets three new optional fields

- `is_soul_tether` BooleanField default=False (migrated concept from old Thread)
- `soul_tether_role` CharField choices (ABYSSAL | SINEATER | null) — Spec B uses this
- `magical_flavor` TextField blank — short player-authored descriptor of the bond's
  magical quality ("the weight of debts owed," "a shared dream we both remember").
  Distinct from journals; a one-line identity for the bond.

#### `CharacterResonance` — structural keep, semantic shift

Continues to track which resonances a character has personally developed; "developed"
post-pivot means "the player has explicitly claimed this resonance as part of their
identity," typically established at character creation or through a developmental
moment in play (Spec C will author when CharacterResonance rows are created). This
is distinct from `ResonancePool` rows, which are created lazily on first earn —
a player can earn resonance into a pool they never personally claimed (e.g., a
brief identity moment that didn't stick). The identity list governs what shows on
the character sheet's resonance section; the pool list governs what currency is
available to spend.

Its former "level" / numerical-rank semantics are dropped. If post-pivot the
distinction between CharacterResonance and `ResonancePool.lifetime_earned > 0`
proves too thin to justify two models, collapse into a simpler M2M on
CharacterSheet (see §8.5 follow-up).

#### `JournalEntry` gains `related_threads` M2M to `Thread`

Purely for UI aggregation on the "Who I Am" page. Optional, no mechanical effect.

### 2.3 Deletions

- `magic.Thread` (5-axis model) — axis values discarded (no live data confirmed by user);
  `is_soul_tether` migrates to CharacterRelationship.
- `magic.ThreadType` — superseded by `RelationshipTrack` for relationship flavor.
- `magic.ThreadJournal` — replaced by relationships-app writeups + `JournalEntry.related_threads`.
- `magic.ThreadResonance` — superseded by `Thread.resonance` single-FK.
- `magic.CharacterResonanceTotal` — obsolete (no rank).

### 2.4 Constraint summary

- `Thread.level ≤ anchor_cap(target_kind, target)` — enforced in `clean()`.
  Anchor cap rules (see economy section):
    - TRAIT: cap = the character's current trait value for that Trait
    - TECHNIQUE: cap = number of related Techniques the character knows under the
      parent Gift (placeholder; may shift to Gift-level once Gifts get levels)
    - ITEM: cap = item's magical significance tier (staff-authored on ItemTemplate /
      ItemInstance)
    - ROOM: cap = room's magical significance tier (staff-authored on RoomProfile)
    - RELATIONSHIP_TRACK: cap = current tier index on the track
    - RELATIONSHIP_CAPSTONE: cap = 10 (high; capstones are rare and earned)
- `ResonancePool.balance ≥ 0` — enforced at spend sites.
- `Thread` uniqueness: one thread per (owner, target, resonance) triple, via partial
  unique indexes keyed to `target_kind`. Six partial uniques in total — one per
  `target_kind` value, each constraining the matching `target_*` FK column. ITEM
  and ROOM both key off `target_object` but with different `target_kind` discriminator
  values, so a player can simultaneously have an ITEM thread on object X and a (very
  unusual) ROOM thread on the same object X without colliding. In practice ObjectDB
  has one typeclass and only one of those reads as valid, but the constraint is
  per-discriminator anyway.

---

## 3. Resonance Economy

### 3.1 Earn interface

Spec C will author the gain surfaces (social scenes, peer endorsement, environment/outfit
tagging). Spec A exposes the service function those gain surfaces will call:

```python
def grant_resonance(
    character: CharacterSheet,
    resonance: Resonance,
    amount: int,
    source: str,           # short audit label, e.g. "social_scene_endorsement"
    source_ref: int | None = None,   # optional FK pk to the originating event
) -> ResonancePool:
    """
    Atomically grant `amount` of `resonance` to `character`'s pool.
    Creates the ResonancePool row lazily if it doesn't exist.
    Increments both `balance` and `lifetime_earned`.
    Emits a `ResonanceGranted` event.
    """
```

`ResonancePool.balance` has no cap (decision from Q13). The pool grows freely; the
strategic tension is over allocation, not over hitting a ceiling.

### 3.2 Spend interface

Two distinct spend paths:

#### Threshold spend (level-up via Imbuing ritual)

```python
def spend_resonance_for_threshold(
    character: CharacterSheet,
    thread: Thread,
) -> Thread:
    """
    Cross the next ThreadLevelThreshold for `thread`.
    Validates:
      - character owns thread
      - developed_points >= threshold's developments_needed
      - pool.balance >= threshold's resonance_cost
      - thread.level + 1 <= anchor_cap(thread.target_kind, thread.target)
        (per §2.4 anchor cap rules — TRAIT cap = current trait value, etc.)
    Atomic (select_for_update on the pool row): decrements balance,
    increments thread.level. Emits a `ThreadImbued` event.
    Raises `ResonanceInsufficient`, `ThresholdNotReached`, or `AnchorCapExceeded`
    on failure.
    """
```

This is the function `Ritual("Rite of Imbuing")` dispatches to. Called only via
`PerformRitualAction`, never directly from the My Threads page.

#### Pull spend (in-action amplification)

```python
def spend_resonance_for_pull(
    character: CharacterSheet,
    resonance: Resonance,
    tier: int,                          # 1, 2, or 3 from ThreadPullCost
    threads: list[Thread],              # the threads being pulled this action
    action_context: ActionContext,      # for anchor-involvement validation
) -> ResonancePullResult:
    """
    Atomically debit the pool for the chosen tier's `resonance_cost`,
    plus `anima_per_thread * (len(threads) - 1)` anima from the character's
    `CharacterAnima` row (the first thread is "free" beyond the resonance cost).
    Validates:
      - all threads owned by `character`
      - all threads share `resonance`
      - anchor-involvement per §5.2 (system check for non-relationship anchors;
        player-asserted for relationship anchors — caller passes the assertion
        through `action_context`)
      - pool.balance and CharacterAnima.current sufficient
    Returns a structured ResonancePullResult dataclass (defined in
    `world/magic/types.py`) with:
        - resonance_spent: int
        - anima_spent: int
        - resolved_effects: list[ThreadPullEffect]   # for the action layer to apply
    Emits a `ThreadsPulled` event.
    """
```

Both spend functions wrap the relevant ResonancePool row in `select_for_update()` so
two simultaneous spends from the same pool serialize. The pull spend additionally
locks the `CharacterAnima` row for the same reason. This matters for pulls in
overlapping turns (multi-actor scenes).

**Dependency note:** `CharacterAnima` (current/maximum) is the existing magic-system
anima model in `world/magic/models.py`. Spec A reuses it directly — no new pool
model is introduced for anima.

### 3.3 Allocation is player-driven

There's no automatic allocation of incoming resonance to specific threads. Resonance
accumulates in the pool; the player decides via Imbuing rituals which threads to spend
on. This makes specialization a deliberate choice (lean hard into one resonance →
develop fewer threads more deeply, or spread → many shallow threads).

The dashboard surfaces decision-support (which thresholds are reachable, which threads
are close to a threshold) but never auto-spends.

### 3.4 Lifetime metrics

`ResonancePool.lifetime_earned` is monotonically incremented and never debited. Useful
for:

- Achievements ("earned 1000 lifetime Celestial resonance")
- Soft retro-unlocks if we ever want to gate something on cumulative identity work
- Analytics on which resonances different player archetypes converge on

### 3.5 Concurrency model

All spends use `select_for_update()` on the ResonancePool row; grants use atomic
transactions but don't need to lock (only one writer matters per row at a time, and
gains are commutative). The pessimistic lock is at the row level (per character per
resonance), so a character pulling on Celestial doesn't block a different character's
Primal grant.

### 3.6 Resonance Pool service helpers

```python
def get_or_create_pool(character, resonance) -> ResonancePool: ...
def affordable_thresholds(character) -> list[tuple[Thread, ThreadLevelThreshold]]:
    """Threads where pool.balance >= next threshold's cost AND
       developed_points >= developments_needed."""
def near_threshold_threads(character, within: int = 3) -> list[Thread]:
    """Threads within `within` developments of their next threshold —
       UI hint surface."""
```

These power the My Threads page. None mutate.

---

## 4. UX, API, and Ritual Foundation

### 4.1 The two UI surfaces

**ThreadWeaving unlock acquisition** does NOT live in a generic XP-spend UI. It happens
through the in-game teaching system — players must be in the same scene as a teacher
who offers the unlock.

**Thread management** lives on a dedicated "My Threads" page that is inspection +
planning, not transactional. Direct level-ups don't happen here; the page surfaces
"this thread is ready to imbue" and routes the player to perform the Rite of Imbuing
in-world.

### 4.2 ThreadWeavingTeachingOffer

Mirrors the existing `CodexTeachingOffer` model exactly:

```
ThreadWeavingTeachingOffer
  teacher       FK RosterTenure
  unlock        FK ThreadWeavingUnlock
  pitch         TextField                  # what the teacher offers narratively
  gold_cost     PositiveIntegerField default=0
  banked_ap     PositiveIntegerField       # teacher's AP commitment
  created_at    DateTimeField auto_now_add=True
```

NPC Academy teachers are seeded as RosterTenure-backed offers tied to specific
ThreadWeaving unlocks. Path multiplier (in-band vs. out-of-band) is computed at
acceptance time, not stored on the offer.

### 4.3 Ritual foundation

#### `Ritual` (registry)

```
Ritual
  name                    CharField unique
  description             TextField
  hedge_accessible        BooleanField default=False
  glimpse_eligible        BooleanField default=False
  narrative_prose         TextField     # template with variable substitution

  # Execution dispatch — exactly one populated, enforced in clean()
  execution_kind          CharField choices: SERVICE | FLOW
  service_function_path   CharField blank
  flow                    FK FlowDefinition null=True on_delete=PROTECT

  # Atmosphere
  site_property           FK Property null=True on_delete=SET_NULL
                          # optional matching room-tag for a soft bonus per Q15b
```

No `kind` discriminator. Rituals can do anything a Flow or service function can do;
categorizing them up front would be the same anti-pattern as categorizing Techniques
by effect.

#### `RitualComponentRequirement` (join)

```
RitualComponentRequirement
  ritual                FK Ritual
  item_template         FK ItemTemplate
  quantity              PositiveSmallIntegerField default=1
  min_quality_tier      FK QualityTier null=True
  authored_provenance   TextField blank   # GM-facing note on narrative weight
```

All components are items. Narrative-weight components ("a liar's promise") become
ItemTemplates whose creation rules carry the narrative requirement. The authoring
machinery for ritual-grade items is **deferred to Spec D**; Spec A's Ritual model
just declares "consumes N of this template" and trusts the items system.

#### `PerformRitualAction` (ephemeral)

Runtime action object. Not a model. Composed when a ritual is invoked, executes,
emits events, exits.

```
PerformRitualAction(
    actor: CharacterSheet,
    ritual: Ritual,
    components_provided: list[ItemInstance],
    kwargs: dict,                      # ritual-specific parameters
)

execute():
    1. Validate components_provided satisfy all ritual.requirements
       (matches template, quantity, min_quality_tier)
    2. Atomically consume the components
    3. Apply site_property bonus if room property matches (Q15b)
    4. Dispatch:
        SERVICE: import path, call(actor=actor, **kwargs)
        FLOW:    trigger ritual.flow with (actor=actor, **kwargs)
    5. Emit RitualPerformed event
    6. Render narrative_prose with substitution
```

Authoring a new ritual is data + (optionally) a Flow. No code change required for
content-authored rituals.

#### Imbuing ritual concrete authoring

```
Ritual(
    name="Rite of Imbuing",
    description="A focused meditation in which you pour your earned resonance "
                "into a thread, hardening it into deeper magical purchase.",
    hedge_accessible=False,
    glimpse_eligible=False,
    execution_kind=SERVICE,
    service_function_path="world.magic.services.imbue_resonance_into_thread",
    site_property=None,    # any room works; the site-bonus mechanism for
                           # matching properties is deferred to Spec D's
                           # broader ritual-site-bonus design (see §8.3)
    narrative_prose="<varied per resonance + anchor kind, see prose template>",
    requirements=[],       # no components for Imbuing
)
```

#### `ImbuingProseTemplate` (lookup, SharedMemoryModel)

Authored prose for the Rite of Imbuing, indexed by the resonance and the anchor's
kind. PerformRitualAction selects the matching row at execution time and falls
back to a generic prose if no specific row exists.

```
ImbuingProseTemplate
  resonance     FK Resonance null=True       # null = any resonance (fallback)
  target_kind   CharField choices null=True  # null = any kind (fallback)
  prose         TextField                    # template with {actor}, {anchor}, etc.
  class Meta:
    unique_together = (resonance, target_kind)
```

Selection precedence at runtime: exact (resonance, target_kind) match → match on
resonance only → match on target_kind only → both null (universal fallback).
Authored content; no schema migration carries content (factories seed test data,
out-of-band script seeds dev/prod).

### 4.4 The "My Threads" page

Layout:

- **Header strip** — character's aura (existing `CharacterAura` prose, not numbers) +
  per-resonance pool tiles showing balance + lifetime_earned + a soft "this resonance
  is hungry" indicator.
- **Threads list**, default-grouped by resonance (toggle to anchor type — see Q16).
  Each row:
  - Anchor name + kind icon
  - Resonance tag + level
  - `developed_points` progress bar to next threshold
  - State-aware action button:
    - "Begin Imbuing Ritual" — if affordable and at threshold (links to in-game
      ritual flow)
    - "Find a Teacher" — if anchor kind isn't unlocked (links to teaching-offer
      discovery filtered to that anchor type)
    - No button — if developing toward next threshold
  - Pull-tier cost preview (informational only; pulls happen in action UI)
  - Anchor link (jumps to relationship/item/room/technique detail)
- **Relationship-anchored threads also appear inside the relationship page itself**
  as a sidebar card with the same affordances.

The page never mutates threads directly. All level-ups route through
`PerformRitualAction("Rite of Imbuing", thread_id=N)`.

### 4.5 API surface

```
GET    /api/magic/threads/                       own threads + display data
GET    /api/magic/threads/{id}/                  single thread detail
POST   /api/magic/threads/                       weave a new thread (gated by
                                                  CharacterThreadWeavingUnlock for
                                                  the anchor's kind+target — see
                                                  §6.1; weaving itself is free,
                                                  the strategic spend is Imbuing)
DELETE /api/magic/threads/{id}/                  soft retire (kept for history)

GET    /api/magic/resonance-pools/               own pool balances + lifetime

POST   /api/magic/rituals/perform/               body: {ritual_id, kwargs,
                                                        components: [item_ids]}
                                                  invokes PerformRitualAction
                                                  Imbuing uses kwargs={thread_id}

GET    /api/magic/teaching-offers/               extends codex teaching-offer
                                                  discovery surface (Q17 lean)
                                                  filterable by anchor type
```

`/api/magic/aura/` already exists; the page consumes it.

### 4.6 Carry-over questions still open

- **Q16** — Default grouping on My Threads page (resonance vs. anchor type). Lean:
  resonance.
- **Q17** — Whether the teaching-offer discovery surface is extended in Spec A or
  deferred. Lean: extend, since landing on a teacher should show all their offers
  in one place.

These are UX details that don't block the data/service layer; can be confirmed at
implementation time.

---

## 5. Pull Mechanics in Detail

### 5.1 Pull commitment timing

Pulls are **pre-roll commitment** (Q21=a). The player chooses a resonance, picks
threads to pull, picks a tier (1/2/3), commits the spend, and *then* the action
resolves. No mid-action or post-roll pulls. Reasons:

- Predictable: a player knows what they paid for before the dice land.
- Dramatic: pre-commitment is the "I'm going all-in" moment, not a hedge after seeing
  the result.
- Matches existing magic-system intensity-tier resolution (intensity is set before
  resolution, not after).
- Removes mid-resolution decision paralysis.

The pull-preview endpoint (`/api/magic/thread-pull-preview/`) lets the player see the
resolved effect list *before* committing — informed pre-commitment, not blind.

### 5.2 Anchor-involvement rules per target_kind

A thread's tier-0 passive auto-applies, and a player may declare a pull on a thread,
only when the thread's anchor is "involved in the action." Definitions per kind:

- **TRAIT** — the trait is checked or contributes to the check. Direct.
- **TECHNIQUE** — the technique is being used in the action. Direct.
- **ITEM** — the item is wielded/equipped/being used in the action. Direct.
- **ROOM** — the action is happening in the room. Direct.
- **RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE** — hybrid (Q20=d):
  - **Tier-0 passive** auto-applies when the relationship's other party is a
    participant in the scene (present and engaged). Clean system trigger.
  - **Pulls** are player-asserted: the player declares the relationship is relevant
    ("I channel my dead mentor's resolve as I make this stand") with no system
    presence/target check. Maximum narrative agency. Pull cost is the throttle.

### 5.3 GM audit-trail backstop

Every pull emits a `ThreadsPulled` event recording: actor, action, threads pulled,
tier, resonance/anima spent. Player-asserted relationship pulls are reviewable
post-hoc. Staff can intervene narratively if a player treats pulls as a slot
machine; no upfront enforcement code is needed. Trust + audit + remediation, not
gatekeeping. (Pre-empting Arx-1-era over-engineering for abuse cases that may
never arise.)

### 5.4 Pull resolution algorithm

Given an action with the pulling character, the chosen resonance, the chosen tier,
and the list of threads to pull:

```
1. Validate:
   - All pulled threads are owned by the actor.
   - All pulled threads share the chosen resonance.
   - For non-relationship anchors: anchor is involved (per 5.2).
   - For relationship anchors: player has asserted involvement (no system check).
   - Pool balance >= ThreadPullCost(tier).resonance_cost.
   - CharacterAnima.current >= ThreadPullCost(tier).anima_per_thread *
     max(0, len(threads) - 1).

2. Atomically debit (select_for_update on pool and CharacterAnima rows):
   - ResonancePool.balance -= ThreadPullCost(tier).resonance_cost
   - CharacterAnima.current -= anima_total

3. For each pulled thread:
   For each effect_tier in 0..tier:
     Find ThreadPullEffect rows matching:
       (target_kind=thread.target_kind, tier=effect_tier)
       preferring resonance match, falling back to resonance=NULL
     Add matched rows to the active effect list.

4. Also collect tier-0 effects from any non-pulled threads whose anchors are
   involved in the action (passive layer fires regardless of pulls).

5. Resolve and apply effects per stacking rules (5.5).

6. Emit ThreadsPulled event with full audit payload.

7. Return ResonancePullResult dataclass to the action resolver, which applies
   the effects to the action's check / intensity / capabilities at pre-roll time.
```

### 5.5 Stacking rules by effect_kind

When multiple effects apply to the same action:

- **FLAT_BONUS** — sum. Three threads contributing +2 each = +6. No cap (designer
  authoring restraint is the throttle).
- **INTENSITY_BUMP** — sum, capped at the system's highest IntensityTier. The pull
  preview displays the effective (capped) outcome so players never spend anima for
  intensity past the cap; they can downsize their pull or shift to other resonances.
- **CAPABILITY_GRANT** — union. All granted capabilities are available for this
  action. Capabilities are categorical, not numerical; granting the same capability
  twice is a no-op.
- **NARRATIVE_ONLY** — collect all `narrative_snippet` strings; the action's
  narrative output presents them all (deduplicated, in pull order).

The user's principle: stacking should feel good. Sum-and-union is the rule;
take-highest creates "wasted anima" traps and is rejected.

### 5.6 Pre-commitment preview API

```
POST /api/magic/thread-pull-preview/
Body: {
  resonance_id: int,
  tier: int (1..3),
  thread_ids: [int],
  action_context: {                    # action this pull would attach to
    action_kind: str,
    anchors_in_play: [...]             # for relationship-pull validation
  }
}
Response: {
  resonance_cost: int,
  anima_cost: int,
  affordable: bool,                    # pool/anima sufficient
  resolved_effects: [
    {kind, value, source_thread_id, source_tier, narrative_snippet?}
  ],
  capped_intensity: bool,              # warns if INTENSITY_BUMP hit cap
}
```

Pure read-only. No state mutation. The player's UI calls this whenever a tier or
thread selection changes; the player commits via the action endpoint that triggers
the actual debit.

### 5.7 Failure handling

- **Pool exhausted between preview and commit.** The atomic commit re-checks balance
  in the same transaction; if insufficient, returns an error and no debit occurs.
  Player retries with a lower tier or different threads.
- **CharacterAnima exhausted.** Same — re-check at commit. Player picks fewer threads.
- **Anchor uninvolvement detected at commit** (for non-relationship pulls). Returns
  an error; no debit. Edge case: anchor fell out of play between preview and commit.
- **Relationship pull on a relationship that no longer exists** (deleted between
  preview and commit). Returns an error; no debit. PROTECT on the FK makes this
  rare in practice.

### 5.8 Integration with action resolution

The action resolver (existing/future check/action machinery) receives the
`ResonancePullResult` and applies effects pre-roll:

- `FLAT_BONUS` is added to the check's modifier total.
- `INTENSITY_BUMP` is added to the action's effective intensity tier.
- `CAPABILITY_GRANT` capabilities are added to the action's capability set for the
  duration of the resolution.
- `narrative_snippet`s are appended to the action's narrative output buffer for
  rendering.

The action resolver's API contract for receiving pull results is a downstream
consumer concern — Spec A delivers the dataclass; the resolver knows how to apply
it. Coordination point with the broader action-system work.

---

## 6. ThreadWeaving Unlocks and Path Gating

### 6.1 Acquisition pipeline

A character acquires a `ThreadWeavingUnlock` by:

1. **Finding a teacher.** A `ThreadWeavingTeachingOffer` exists for that unlock,
   posted by a teacher (NPC or PC) whose character is in the same scene. Discovery
   uses the extended teaching-offer surface (codex + threadweaving) per Q17 lean.
2. **Accepting the offer.** Spends gold (per offer) + AP (per offer) + XP at the
   computed cost (per Path-multiplier rule below).
3. **A `CharacterThreadWeavingUnlock` row is created** linking the character to
   the unlock, with `xp_spent` recording the actual cost paid (in-Path or
   out-of-Path) and `teacher` recording the offer's teacher.

**Out-of-Path purchasing is allowed but gated** (Q23=b):
- The character must still find a teacher willing to teach them.
- The XP cost is multiplied by `unlock.out_of_path_multiplier` (default 2.0).
- The unlock is *usually* less relevant in play because the character's Path-aligned
  actions don't intersect the out-of-Path anchor often (a Path-of-Steel character
  who buys Seduction-weaving rarely makes Seduction checks, so the thread's passive
  rarely fires and its pull is rarely declarable). This is emergent specialization,
  not an extra mechanic.

### 6.2 Cost formula

```python
def computed_xp_cost(unlock: ThreadWeavingUnlock, learner: CharacterSheet) -> int:
    unlock_paths = set(unlock.paths.all())
    # Path-neutral unlocks (no paths assigned) cost everyone the base — these are
    # authored as "available to anyone" and should not be penalized.
    if not unlock_paths:
        return unlock.xp_cost
    # Character paths come from progression.CharacterPathHistory (FK to ObjectDB
    # with FK to classes.Path). Latest selection per stage is the "current" path;
    # for in-Path checks we accept any historically selected path as in-Path,
    # because progression is forward-only and a character's full path arc is
    # part of their identity.
    # CharacterSheet.character is the OneToOne FK to ObjectDB; path_history
    # reverse-relates from progression.CharacterPathHistory.
    learner_paths = {
        h.path
        for h in learner.character.path_history.select_related("path")
    }
    if learner_paths & unlock_paths:
        return unlock.xp_cost
    return int(unlock.xp_cost * unlock.out_of_path_multiplier)
```

Once unlocked, threads behave identically regardless of in-Path or out-of-Path
acquisition. The Path coupling lives entirely at the purchase layer; runtime
treatment is uniform. (Avoiding the parallel "in-Path effects" / "out-of-Path
effects" authoring burden.)

### 6.3 Granularity rules summary

(Recap of Section 2 for cross-reference.)

| target_kind | unlock granularity | example |
|---|---|---|
| TRAIT | per specific Trait | "ThreadWeaving for Seduction" |
| TECHNIQUE | per Gift (covers all techniques under it) | "ThreadWeaving for the Gift of the Blade" |
| ITEM | per item typeclass path (with inheritance) | "ThreadWeaving for Swords" |
| ROOM | per Property | "ThreadWeaving for Consecrated Spaces" |
| RELATIONSHIP_TRACK | per RelationshipTrack type | "ThreadWeaving for Romantic Bonds" |
| RELATIONSHIP_CAPSTONE | (no separate unlock — inherits from track) | n/a |

### 6.4 Path-affinity catalog (initial authoring suggestions)

This is a starter catalog for the five Prospect Paths. Authors can extend.

**Steel (Manifestation style)** — physical/combat:
- TRAIT: Strength, Stamina, Endurance
- TECHNIQUE: Gift of the Blade, Gift of the Bow, Gift of Endurance
- ITEM: Swords, Polearms, Heavy Armor
- ROOM: Battlefield (Property), Training Grounds (Property)

**Whispers (Subtle style)** — intrigue/social manipulation:
- TRAIT: Seduction, Subterfuge, Intuition
- TECHNIQUE: Gift of Veiled Words, Gift of Shadow
- ITEM: Daggers, Concealable Items
- ROOM: Salons (Property), Crossroads (Property)
- RELATIONSHIP_TRACK: Romantic Bonds, Antagonistic Bonds

**Voice (Performance style)** — oratory/influence:
- TRAIT: Charisma, Performance, Composure
- TECHNIQUE: Gift of Voice, Gift of Presence
- ROOM: Courts (Property), Stages (Property)
- RELATIONSHIP_TRACK: Mentorship Bonds, Followership Bonds

**Chosen (Prayer style)** — religious/divine:
- TRAIT: Faith, Theology, Composure
- TECHNIQUE: Gift of Prayer, Gift of Sacrament
- ITEM: Holy Symbols, Vestments
- ROOM: Consecrated (Property), Ancestral (Property)

**Tome (Incantation style)** — scholarly/arcane:
- TRAIT: Intellect, Lore, Memory
- TECHNIQUE: Gift of Symbol, Gift of Cipher
- ITEM: Tomes, Foci
- ROOM: Libraries (Property), Sanctums (Property)

These are starter authoring; staff add/remove unlocks freely. The 5×N catalog is
**authored content seeded via FactoryBoy** (for tests) and an **out-of-band seeding
script** (for dev/prod), per §7.1's no-data-migrations rule. The catalog above is
the design intent for that authoring pass; no migration carries the data.

### 6.5 Capstone-weaving inheritance

A character with `CharacterThreadWeavingUnlock(unlock__unlock_track=Romantic)` can
weave threads on:
- `RelationshipTrackProgress` rows whose track is Romantic
- `RelationshipCapstone` rows whose parent track is Romantic

No separate capstone unlock is required. Capstones are subordinate to their parent
track's unlock. This keeps the catalog tractable (5 track types × N relationship
unlocks, not 5 + 5 doubled).

---

## 7. Migration and Cleanup

### 7.1 No data migrations

There is no live magic data — no players, no authored magic content, no production
state to preserve. Following the project's "no data migrations, dev DB is disposable"
guidance:

- All migrations in this spec are **schema-only**.
- **Lookup seed data lives in FactoryBoy factories**, not in data migrations.
- Out-of-band seeding for dev/prod environments (one-shot scripts run when the schema
  is ready) is a future concern — not part of Spec A.

### 7.2 Schema migration order

Migrations are written and applied in this order. Each is a single self-contained
schema migration with no data steps.

#### Step 1 — Add new models

In `world/magic`:
- `Thread` (new model — replaces old Thread completely)
- `ResonancePool`
- `ThreadPullCost` (lookup, SharedMemoryModel)
- `ThreadLevelThreshold` (lookup, SharedMemoryModel)
- `ThreadPullEffect` (lookup, SharedMemoryModel)
- `ThreadWeavingUnlock` (lookup, SharedMemoryModel)
- `CharacterThreadWeavingUnlock` (purchase record)
- `ThreadWeavingTeachingOffer`
- `Ritual` (registry, SharedMemoryModel)
- `RitualComponentRequirement` (join, SharedMemoryModel)
- `ImbuingProseTemplate` (lookup, SharedMemoryModel)

In `world/relationships`:
- Add fields to `CharacterRelationship`: `is_soul_tether`, `soul_tether_role`,
  `magical_flavor`.

In `world/journals`:
- Add `related_threads` M2M to `JournalEntry`.

#### Step 2 — Delete obsolete models (runs BEFORE Step 1's new `Thread` creation)

Because the new `Thread` reuses the table name, the deletion migration is sequenced
**first** to drop the old table, then Step 1's create-`Thread` migration creates the
new table cleanly. No `RunPython` data step is needed because no data exists.

Single migration in `world/magic`:
- `Thread` (the old 5-axis model)
- `ThreadType`
- `ThreadJournal`
- `ThreadResonance`
- `CharacterResonanceTotal`

The actual migration order applied is therefore: Step 2 (delete-old) → Step 1
(create-new + add fields elsewhere) → Step 3 (CharacterResonance trim) → Step 4
(rename strings).

#### Step 3 — Adjust `CharacterResonance`

Drop any `level` field (if present); the model continues to exist as the
identity-list of resonances a character has personally developed.

#### Step 4 — Mage Scars rename

Pure string/verbose_name change, no schema delta in most places. Touchpoints:
- `MagicalAlterationTemplate` model `verbose_name` and class docstring
- `PendingAlteration` model `verbose_name` and class docstring
- `world/magic/CLAUDE.md` references
- `docs/roadmap/magic.md` references (Scope 5 entry)
- `docs/systems/INDEX.md` magic system entry
- `docs/systems/magic.md` "Scars" section heading and prose
- Frontend strings (any UI labels rendering "Magical Scars")
- API serializer field labels (if any are user-facing)

This is a single PR's worth of find-and-replace plus verbose_name edits, applied
alongside (or right after) the Spec A migrations.

### 7.3 Factories for lookup data

The old `ThreadFactory`, `ThreadJournalFactory`, and `ThreadResonanceFactory` (which
build instances of the deleted models) are **removed first**. The new factories
below replace them — same module path (`world/magic/factories.py`), names reused
where appropriate (the new `ThreadFactory` replaces the old one with the new
discriminator-aware shape).

- `ThreadPullCostFactory` — three preset rows: `tier=1` (resonance_cost=1),
  `tier=2` (resonance_cost=3), `tier=3` (resonance_cost=6), each with a matching
  `anima_per_thread` value (staff-tunable defaults — exact anima numbers are an
  authoring decision at seed time, not encoded in this spec)
- `ThreadLevelThresholdFactory` — preset thresholds at level 1..N
- `ThreadPullEffectFactory` — flexible factory for authoring sample effects per test
- `ThreadWeavingUnlockFactory` — flexible factory for authoring sample unlocks per
  test, with traits for in-Path / out-of-Path examples and discriminator-aware
  traits (`as_trait_unlock`, `as_gift_unlock`, `as_item_unlock`, `as_room_unlock`,
  `as_track_unlock`)
- `CharacterThreadWeavingUnlockFactory` — records a character's purchase
- `ThreadWeavingTeachingOfferFactory` — wraps the existing teaching pattern
- `RitualFactory` — preset for "Rite of Imbuing" + flexible for hedge/binding
  rituals authored later
- `RitualComponentRequirementFactory` — empty by default, flexible for component-rich
  rituals
- `ImbuingProseTemplateFactory` — flexible by (resonance, target_kind), plus a
  catch-all fallback row trait
- `ResonancePoolFactory` — flexible balance/lifetime
- `ThreadFactory` (new) — discriminator-aware traits (`as_trait_thread`,
  `as_item_thread`, `as_room_thread`, `as_technique_thread`, `as_track_thread`,
  `as_capstone_thread`) to set the right FK and `target_kind` together

### 7.4 Service-layer migrations

Service functions to add in `world/magic/services.py`:
- `grant_resonance(character, resonance, amount, source, source_ref=None)`
- `spend_resonance_for_threshold(character, thread)`
- `spend_resonance_for_pull(character, resonance, tier, threads, action_context)`
- `imbue_resonance_into_thread(actor, thread_id)` — the Imbuing-ritual dispatch target
- `weave_thread(character, target_kind, target, resonance)` — eligibility check
  (CharacterThreadWeavingUnlock for the anchor's kind+target) + Thread row creation;
  no resonance cost (weaving is free, Imbuing carries the strategic spend)
- `accept_thread_weaving_unlock(learner, offer)` — mirrors codex teaching-acceptance;
  creates the `CharacterThreadWeavingUnlock` row
- `compute_thread_weaving_xp_cost(unlock, learner)` — Path-multiplier resolver
- `compute_anchor_cap(thread)` — returns the §2.4 cap for a Thread's anchor;
  used by `spend_resonance_for_threshold` and surfaced on the My Threads page

Dataclasses in `world/magic/types.py`:
- `ResonancePullResult(resonance_spent: int, anima_spent: int,
   resolved_effects: list[ThreadPullEffect])`
- `ActionContext(...)` — at minimum carries `anchors_in_play` (for non-relationship
  involvement check) and `asserted_relationship_anchors` (player declarations);
  exact shape coordinates with the action-system work

Service functions to remove (tied to deleted models):
- Anything that mutates the old Thread's 5-axis fields
- ThreadJournal / ThreadResonance creation helpers

### 7.5 Test migration

- Existing tests touching the old Thread/ThreadType/ThreadJournal/ThreadResonance
  models are deleted (alongside their factories).
- New tests cover:
  - thread weaving eligibility (per anchor kind, including typeclass-inheritance
    walk for ITEM)
  - threshold spend (success, insufficient resonance, threshold not reached,
    anchor cap exceeded)
  - pull cost + stacking (FLAT_BONUS sum, INTENSITY_BUMP cap, CAPABILITY_GRANT
    union, NARRATIVE_ONLY collection, mixed-kind snippet collection)
  - pull anchor-involvement (system-checked for non-relationship, asserted for
    relationship; commit re-validation when anchor falls out of play)
  - ritual dispatch — both the SERVICE path (Imbuing) AND the FLOW path (a sample
    flow-driven ritual) so both execution kinds are exercised
  - `is_soul_tether` flag round-trip on CharacterRelationship
  - `CharacterThreadWeavingUnlock` purchase + idempotency (same offer twice
    rejected)
  - in-Path / out-of-Path / Path-neutral cost paths in `computed_xp_cost`

---

## 8. Open Deferrals

### 8.1 Handoff to Spec B (Relational Resilience + Soul Tether + Ritual Capstones)

Inheriting from Spec A:

- `CharacterRelationship.is_soul_tether`, `soul_tether_role`, `magical_flavor`
  fields exist and are settable but have no mechanical effect yet.
- `Ritual` model and `PerformRitualAction` are usable for authoring Soul Tether
  and other ritual-flavored capstone moments.

Spec B owns:

- Aggregate relational-resilience formula (using existing
  `CharacterRelationship.mechanical_bonus = cube_root(developed_value)` as a starting
  point; deciding which `ModifierTarget` entries it adjusts).
- Soul Tether grounding scaling formula (depth × caster tier; vulnerability of
  Abyssal-side and burden of Sineater-side).
- Soul Tether break consequences and societal-gating expression (some societies
  *require* Soul Tether for Abyssal magic — how that's enforced).
- The Ritual Capstone authoring pipeline (Capstones can optionally point to a
  Ritual; rituals like Ritual of Devotion / Ritual of Betrayal / Accepting a Soul
  Tether are authored as Ritual rows + companion FlowDefinitions).

### 8.2 Handoff to Spec C (Resonance Gain Surfaces)

Inheriting from Spec A:

- `grant_resonance(character, resonance, amount, source, source_ref)` service
  function is the universal entry point for awarding resonance.
- `ResonancePool` model has `lifetime_earned` for cumulative tracking.

Spec C owns:

- Social-scene endorsement mechanics (peer upvote, gain rate per scene).
- Environment/outfit Resonance tagging (atmospheric gain surfaces).
- Spec C may be a smaller scope than originally framed, since "threads as designed
  now are really just expanding" and the gain surfaces are largely additive
  authoring against a stable Spec A foundation. Possible to fold into a single
  Spec B+C if size warrants.

### 8.3 Handoff to Spec D (Rituals + Ritual-Grade Items)

Inheriting from Spec A:

- `Ritual` registry model with `hedge_accessible` and `glimpse_eligible` flags
  (already structurally present, defaulting to False).
- `RitualComponentRequirement` join model FK'd to ItemTemplate.
- `PerformRitualAction` dispatcher (handles SERVICE and FLOW execution kinds).

Spec D owns:

- Ritual-grade item authoring — the ItemTemplate provenance system that makes
  "a Liar's Promise" authorable as an item with creation requirements.
- Hedge-magic rules for Quiescent characters (when hedge_accessible rituals are
  attemptable, what they can do, what they cost a Quiescent).
- Glimpse-triggering integration (when does a glimpse_eligible ritual actually
  trigger awakening; coordination with the progression/awakening design).
- The catalog of witchy rituals (binding, summoning, divination, etc.).
- Scavenger-hunt Situations targeting ritual components (uses the existing
  Situation/Challenge architecture).

### 8.4 Open UX questions (non-blocking)

- **Q16 — Default grouping on the My Threads page.** Resonance grouping (lean) vs.
  anchor type. Both should be toggleable; the question is which renders by default.
  Decide at frontend implementation.
- **Q17 — Teaching-discovery surface scope.** Whether to extend the codex
  teaching-discovery surface to include ThreadWeaving offers within Spec A or defer
  to a broader teaching-discovery refactor. Lean: extend within Spec A's frontend
  work for the "Find a Teacher" button to land somewhere useful.
- **TECHNIQUE-anchor cap is a placeholder.** §2.4 caps TECHNIQUE-anchored thread
  level at "number of related Techniques the character knows under the parent Gift,"
  which is a working stand-in. When the Gift system gains its own level/rank
  mechanic, swap to a Gift-level-derived cap. Track this so the cap formula gets
  revisited rather than ossified.
- **Ritual site-property bonus mechanism.** Both Ritual and PerformRitualAction
  declare `site_property` and an "apply site-property bonus if room property
  matches" step, but the bonus's actual mechanic (XP-cost reduction? extra
  developed_points? success-chance bump on hedge rituals?) is unspecified in
  Spec A. Defer to Spec D, which will design ritual outcomes generally and can
  give site-property a uniform meaning across all rituals. For Imbuing
  specifically, `site_property=None` so this is dormant in Spec A.

### 8.5 Possible future expansion (not blocking)

- **`ItemCategory` model.** If we ever need item-unlock categories that don't match
  typeclass boundaries (e.g., "magical heirlooms" cutting across sword/dagger/staff),
  add an ItemCategory model and extend `ThreadWeavingUnlock` with
  `unlock_item_category FK ItemCategory null=True`. Not anticipated for Spec A
  launch.
- **Per-Path runtime effects.** Currently in-Path vs out-of-Path matters only at
  unlock-purchase time; runtime treatment is uniform. If playtest reveals players
  feel out-of-Path threads should *also* mechanically underperform (in addition to
  emergent irrelevance), add a Path-aware modifier in pull resolution. Not planned
  for Spec A launch.
- **CharacterResonance collapse.** If post-pivot CharacterResonance has no role
  beyond "identity list of which resonances a character has developed," collapse
  into a simpler M2M on CharacterSheet. Followup, not blocking.
