# Spec A — Threads and Resonance Currency (Design)

**Status:** draft, in active brainstorming
**Date:** 2026-04-18
**Scope:** Spec A of a four-spec resonance-pivot decomposition. Sibling specs B
(Relational Resilience / Soul Tether / Ritual Capstones), C (Resonance Gain
Surfaces), and D (Rituals + Ritual-Grade Items) are referenced here but authored
separately.

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
  tagging, and anything that *writes* to `CharacterResonance.balance`. Spec A exposes the
  service function interface Spec C will call; Spec A does not author any gain sites.

### Consequences that fall out of the pivot

1. **Thread model replaced.** The existing `magic.Thread` 5-axis model (romantic, trust,
   rivalry, protective, enmity 0–100, plus `is_soul_tether`) is replaced with a uniform
   "thread attachment" model. The 5-axis emotional content is already captured better
   in the relationships app's tracks; `is_soul_tether` migrates to `CharacterRelationship`.
2. **Satellite magic models deleted.** `ThreadType`, `ThreadJournal`, `ThreadResonance`,
   and `CharacterResonanceTotal` go away. Rationale below.
3. **Resonance semantics change.** `CharacterResonance` collapses identity and
   currency into one model. The old rank/level semantics are dropped; the row now
   carries `balance` (spendable currency) and `lifetime_earned` (monotonic audit)
   in addition to identifying which resonances a character has personally
   developed. A separate `ResonancePool` model was considered and rejected — it
   would key identically on `(character, resonance)` and need to stay in lockstep
   with CharacterResonance, which is bad-smell parallel modeling. See §2.2.
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

# Player-authored narrative — optional but UI-encouraged
name                      CharField max_length=120 blank=True
                          # If blank at render time, defaults to
                          # "{Resonance} thread on {anchor display name}".
                          # Not unique — players can have two "Promise" threads
                          # on different anchors.
description               TextField blank=True
                          # Player's prose: why I'm good at this, what this
                          # bond means, the story behind the imbuement.

# Progression — mirrors the skills system
developed_points          PositiveIntegerField default=0
                          # Bucket of unspent progress toward the next level,
                          # earned by spending resonance via Imbuing. Decrements
                          # when a level increments.
level                     PositiveSmallIntegerField default=0
                          # Current thread level. Internal scale matches skills
                          # (10, 20, 30... — see §3.2 / §5.5 for resolution).
                          # Capped per §2.4.

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

#### `ThreadPullCost` (lookup, SharedMemoryModel)

```
tier             PositiveSmallIntegerField unique   # 1, 2, 3
resonance_cost   PositiveSmallIntegerField          # 1, 3, 6 at launch
anima_per_thread PositiveSmallIntegerField          # flat per extra thread
label            CharField                          # "soft", "hard", "max"
```

Staff-tunable. Three rows at launch.

#### `ThreadXPLockedLevel` (lookup, SharedMemoryModel)

```
level     PositiveSmallIntegerField unique   # 20, 30, 40, ... (every 10, internal scale)
xp_cost   PositiveIntegerField               # XP required to cross this boundary
```

The set of internal levels at which thread advancement is XP-locked, mirroring
the skills system. Internal scale matches skills: every multiple of 10 is a
boundary (internal 20 = display 2, internal 30 = display 3, etc.). At an
XP-locked level the character must additionally spend XP (per this row) to
permit the thread to advance into that level. Between XP-locked levels,
advancement is paid for purely with resonance via `developed_points`.

#### `ThreadLevelUnlock` (per-thread record)

```
thread          FK Thread on_delete=PROTECT
unlocked_level  PositiveSmallIntegerField    # which boundary the player has crossed
xp_spent        PositiveIntegerField         # actual XP paid (audit)
acquired_at     DateTimeField auto_now_add=True
class Meta: unique_together = (thread, unlocked_level)
```

Records that the character has paid the XP cost for a specific thread to be
permitted to cross a specific XP-locked level. Without this row, accumulating
`developed_points` past the boundary is rejected by the spend service.

#### Thread development cost formula

Identical structure to skills: between XP-locked boundaries, the resonance cost
to advance from level N → N+1 is `(N - 9) × 100` developed_points. The
`developed_points` bucket on `Thread` is filled by spending resonance via the
Imbuing ritual (Imbuing converts pool resonance into developed_points at a
1:1 ratio at launch — staff-tunable). When the bucket reaches the cost of
the next level, the level ticks up and the bucket decrements by that cost
(overflow carries). At an XP-locked boundary, the level cannot tick up
unless a `ThreadLevelUnlock(thread, unlocked_level=boundary)` row exists.

#### `ThreadPullEffect` (authored templates, SharedMemoryModel)

```
target_kind        CharField choices (same 6 as Thread.target_kind)
resonance          FK Resonance                # required; matches the pulled
                                                # thread's resonance exactly at
                                                # lookup time (no fallback)
tier               PositiveSmallIntegerField   # 0, 1, 2, 3 — see tier-0 = passive note
min_thread_level   PositiveSmallIntegerField default=0
                                                # Authored gate on the thread's level.
                                                # Effect applies only when
                                                # thread.level >= min_thread_level.
                                                # Internal scale: 0, 10, 20, 30...
                                                # Lets authors back-load powerful
                                                # effects behind investment without
                                                # adding a separate "tier 4+" axis.
effect_kind        CharField choices:
                     FLAT_BONUS | INTENSITY_BUMP | VITAL_BONUS |
                     CAPABILITY_GRANT | NARRATIVE_ONLY

# Typed payload — no JSON. Resolver reads the field matching effect_kind.
flat_bonus_amount       SmallIntegerField   null=True
intensity_bump_amount   SmallIntegerField   null=True
vital_bonus_amount       SmallIntegerField   null=True
vital_target             CharField choices null=True   # required for VITAL_BONUS
                          # MAX_HEALTH | DAMAGE_TAKEN_REDUCTION | future enum values
                          # (e.g. MAX_ANIMA, DAMAGE_DEALT_BONUS) — added as
                          # downstream specs need them. Authored constants live
                          # in world/magic/constants.py VitalBonusTarget.
capability_grant        FK Capability        null=True

# Optional inline prose for ANY effect_kind. Substituted into the action's
# narrative output when this row applies. Replaces the prior ThreadNarrativeTag
# model (which was a separate lookup just to hang a string on a row — overkill).
# A NARRATIVE_ONLY row's snippet IS its entire effect. Snippets on FLAT_BONUS,
# INTENSITY_BUMP, VITAL_BONUS, and CAPABILITY_GRANT rows are also collected and
# rendered alongside the mechanical payload — the snippet is additive, not
# exclusive.
narrative_snippet       TextField   blank=True
```

**Tier 0 is passive (always-on); tiers 1–3 are paid pulls.** When a thread's anchor
is involved in an action, tier-0 effects always apply — no pull, no cost. Pulls at
tier N additionally apply effects at tiers 1..N. `ThreadPullCost` has rows only for
paid tiers (1, 2, 3); tier 0 is implicit-zero.

Resolution order when an action lands: for each thread whose anchor is involved,
find ThreadPullEffect rows matching `(target_kind=thread.target_kind,
resonance=thread.resonance, tier in 0..chosen_tier,
min_thread_level <= thread.level)`. The resonance match is exact — no fallback
row exists. If a (target_kind, resonance, tier) triple has no authored row,
that combination simply produces no effect at that tier. Apply every matching
row's effect (scaled per §5.4) and substitute its snippet.

**Authoring expectation:** every (target_kind, resonance) pair that should
have meaningful pull behavior needs explicit ThreadPullEffect rows authored
for it. Factories and admin bulk-create patterns make per-resonance
duplication cheap. The benefit is no surprise behavior at runtime — what
you author is exactly what fires.

**`clean()` enforces payload/effect_kind alignment**: exactly one of
`flat_bonus_amount`, `intensity_bump_amount`, `vital_bonus_amount`,
`capability_grant` must be populated, matching `effect_kind`; for
`VITAL_BONUS`, `vital_target` is required AND `tier` must be 0; for
`NARRATIVE_ONLY`, all numeric payloads must be null and
`narrative_snippet` must be non-blank. Database `CheckConstraint`s
mirror this.

**Why VITAL_BONUS is tier-0 only:** vital bonuses are durable passives that
scale with thread level, not per-action paid spends. A per-action
MAX_HEALTH bump is incoherent (an offensive action gets +max_health…
why? what happens after?), and a per-action damage-reduction pull would
ride a duration model the action layer doesn't yet have. The natural
investment lever for vital pools is the thread's level itself: imbue
the thread higher → its tier-0 VITAL_BONUS scales linearly per §5.4.
If playtest later wants short-lived defensive boosts, that's a separate
TEMP_BUFFER concept introduced as new infrastructure, not retrofit onto
the pull system.

**Why VITAL_BONUS exists in Spec A:** Spec B (Relational Resilience + Soul Tether)
needs to express "this thread grants +N max_health" and "this thread reduces
incoming damage by N." Rather than retrofit the schema later, VITAL_BONUS is
introduced now with `MAX_HEALTH` and `DAMAGE_TAKEN_REDUCTION` as the launch
enum values. Spec A authors **no** `VITAL_BONUS` rows itself; the column and
enum exist so Spec B's authoring lands as data, not migration. Resolution at
runtime uses existing infrastructure: `MAX_HEALTH` is folded into
`vitals.recompute_max_health()` as a thread-derived addend; `DAMAGE_TAKEN_REDUCTION`
is applied by a subscriber to combat's existing `DamagePreApply.modify_amount`
hook (see §5.8).

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

#### `CharacterResonance` — identity + currency, unified

CharacterResonance becomes the single per-character per-resonance row. It is both
the identity anchor (the row's existence = "this character is associated with
this resonance") and the currency bucket (the row carries spendable balance and
monotonic lifetime).

```
character_sheet  FK CharacterSheet      on_delete=CASCADE
resonance        FK Resonance           on_delete=PROTECT
balance          PositiveIntegerField default=0   # spendable; no cap
lifetime_earned  PositiveIntegerField default=0   # audit/metrics, never decremented
claimed_at       DateTimeField auto_now_add=True
flavor_text      TextField blank                  # player-authored manifestation
class Meta: unique_together = (character_sheet, resonance)
```

Field changes from the existing model:
- **Add** `balance`, `lifetime_earned`, `claimed_at` (the merged-in pool fields).
- **Drop** `scope`, `strength`, `is_active`, `created_at` — the old `is_active`
  flag was the only field with consumers (`_apply_magical_scars`); post-merge,
  row existence replaces the flag (deleting the row is the deactivation path).
  `scope`, `strength`, and the old `created_at` had no code reading them
  (serializer-only), and are dropped. `claimed_at` replaces `created_at` with
  clearer naming.
- **Re-FK** `character` (was `FK ObjectDB`) → `character_sheet` (FK CharacterSheet).
  Aligns with the project rule "Avoid direct FKs to ObjectDB" and matches every
  other per-character model in this spec.

Rows are created either:
- explicitly at character creation / through a Spec C identity moment
  (with `balance=0`, `lifetime_earned=0`), OR
- lazily on first `grant_resonance` call (the row is the bucket — the bucket
  *is* the identity).

The semantic shift from the prior spec draft: there is no longer a distinction
between "claimed identity without earned currency" and "earned currency without
claimed identity" — earning currency *is* claiming the identity. Chargen and
Spec C author rows-with-zero-balance to express claim-without-earn; the inverse
(currency-without-claim) is impossible by construction.

Mage Scars (`world/mechanics/effect_handlers.py::_apply_magical_scars`) updates
its origin-derivation query: previously `CharacterResonance.objects.filter(
character=character, is_active=True).order_by("-pk").first()`, now
`character.resonances.most_recently_earned()` (handler method that picks the
row with the highest `lifetime_earned`, ties broken by `-pk`). The `is_active`
filter is dropped because row existence replaces it.

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

- `Thread.level ≤ effective_cap(thread)` — enforced in `clean()` and at every
  spend site (§3.2). All caps share a **common internal scale matching skills**
  (10/20/30…), so the math composes uniformly.

#### Anchor cap rules (per `target_kind`)

The `compute_anchor_cap(thread)` helper normalizes each anchor's "how much
investment can this carry?" to the common scale:

  - **TRAIT** — `cap = CharacterTraitValue.value` for that Trait. Trait/skill
    internal values are already 1–100 on the same scale; no conversion needed.
  - **TECHNIQUE** — `cap = Technique.level × 10`. Techniques are 1–5 internal
    today; multiplying by 10 lands them on the common scale (level-3 technique
    → cap of 30, matching a level-3 skill). When the Technique system gains a
    finer-grained level, the multiplier adjusts; the formula stays.
  - **RELATIONSHIP_TRACK** — `cap = RelationshipTrackProgress.tier_index × 10`.
    Tracks are tier-driven (1–N); multiplier matches the technique normalization.
    If `tier_index` exposes a finer internal value in the future, drop the
    multiplier accordingly.
  - **RELATIONSHIP_CAPSTONE** — `cap = path_stage × 10` (path-derived). Capstones
    are rare and earned; the path stage is the only meaningful gate beyond the
    fact of having earned the capstone at all.
  - **ITEM** — TBD (deferred to Spec D). Spec D's ritual-grade item authoring
    introduces "magical significance" as a first-class concept; the cap formula
    lands there. Until Spec D ships, the spend service rejects ITEM-anchored
    Imbuing with `AnchorCapNotImplemented`. Threads may still be woven on items
    (free) and pulled (existing tier-0/1/2/3 mechanics work because effects are
    authored, not derived from level), but level is pinned at 0.
  - **ROOM** — TBD (deferred to Spec D), same rationale and behavior as ITEM.

#### Path cap (universal ceiling)

Independently of the anchor cap, every thread is also capped by the character's
current Path stage:

```
path_cap = (latest CharacterPathHistory entry's path.stage) × 10
         (defaults to 10 if the character has no path history yet —
          a level-1 character can carry a level-10 thread at most)
```

Path stages are 1, 2, 3, … in the existing `classes.Path` model; Stage-1
characters are capped at thread level 10, Stage-2 at 20, etc. This guarantees
no thread can outpace the character's structural maturity even if the anchor
itself (e.g., a high-tier trait inherited from CG) would permit higher.

#### Effective cap

```
effective_cap(thread) = min(path_cap(thread.owner), anchor_cap(thread))
```

The spend service uses `effective_cap`. The My Threads page surfaces both
component values so players see *which* gate is the active one ("path-locked"
vs. "anchor-locked").
- `CharacterResonance.balance ≥ 0` — enforced at spend sites.
- `Thread` uniqueness: one thread per (owner, target, resonance) triple, via partial
  unique indexes keyed to `target_kind`. Six partial uniques in total — one per
  `target_kind` value, each constraining the matching `target_*` FK column. ITEM
  and ROOM both key off `target_object` but with different `target_kind` discriminator
  values, so a player can simultaneously have an ITEM thread on object X and a (very
  unusual) ROOM thread on the same object X without colliding. In practice ObjectDB
  has one typeclass and only one of those reads as valid, but the constraint is
  per-discriminator anyway. **Note:** Capstone *threads* still get their own partial
  unique (`target_capstone` keyed to `target_kind="RELATIONSHIP_CAPSTONE"`) even
  though capstone *unlocks* are inherited from the parent track per §6.5 — unlock
  inheritance and thread uniqueness are independent concerns.

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
) -> CharacterResonance:
    """
    Atomically grant `amount` of `resonance` to `character`'s row.
    Creates the CharacterResonance row lazily if it doesn't exist
    (earning currency claims the identity — see §2.2).
    Increments both `balance` and `lifetime_earned`.
    Emits a `ResonanceGranted` event.
    """
```

`CharacterResonance.balance` has no cap (decision from Q13). The balance grows freely;
the strategic tension is over allocation, not over hitting a ceiling.

### 3.2 Spend interface

Two distinct spend paths:

#### Imbue spend (development-point bucket fill via Imbuing ritual)

```python
def spend_resonance_for_imbuing(
    character: CharacterSheet,
    thread: Thread,
    amount: int,                 # resonance to convert into developed_points
) -> ThreadImbueResult:
    """
    Convert `amount` of resonance from the matching pool into
    `amount` developed_points on `thread` (1:1 at launch — staff-tunable
    via a single config row). Then advance `thread.level` greedily as
    long as the bucket affords the next level's cost AND the level isn't
    blocked by an XP-locked boundary.

    Validates:
      - character owns thread
      - character_resonance.balance >= amount
      - thread.level < effective_cap(thread)   (per §2.4)
      - amount > 0

    Within the greedy advancement loop, for each candidate next level N+1:
      cost = (N - 9) * 100        (skill-system formula; same shape)
      if developed_points < cost:
          stop — bucket holds remainder
      if (N + 1) % 10 == 0:       # crossing an XP-locked boundary
          if not ThreadLevelUnlock(thread, unlocked_level=N+1).exists():
              stop — XP gate not paid; bucket holds remainder
      if (N + 1) > effective_cap(thread):
          stop — capped; bucket holds remainder
      thread.level = N + 1
      thread.developed_points -= cost

    Atomic (single transaction, in-memory mutation of the SharedMemoryModel
    instances): decrements character_resonance.balance, increments
    thread.developed_points, advances thread.level as far as the bucket and
    gates allow.

    Returns a ThreadImbueResult dataclass with:
        - resonance_spent: int
        - developed_points_added: int
        - levels_gained: int
        - new_level: int
        - new_developed_points: int
        - blocked_by: Literal[
              "NONE", "XP_LOCK", "ANCHOR_CAP", "PATH_CAP", "INSUFFICIENT_BUCKET"
          ]
    Emits a `ThreadImbued` event.
    Raises `ResonanceInsufficient`, `AnchorCapExceeded`, `PathCapExceeded`,
    or `InvalidImbueAmount` on failure.
    """
```

This is the function `Ritual("Rite of Imbuing")` dispatches to. Called only via
`PerformRitualAction`, never directly from the My Threads page.

#### Cross XP-locked boundary (separate spend)

```python
def cross_thread_xp_lock(
    character: CharacterSheet,
    thread: Thread,
    boundary_level: int,         # the XP-locked level being unlocked, e.g. 20
) -> ThreadLevelUnlock:
    """
    Pay XP to permit `thread` to advance into `boundary_level`.

    Validates:
      - character owns thread
      - boundary_level matches a ThreadXPLockedLevel row
      - boundary_level == thread.level + (some increment that the bucket
        could currently reach)  — UI prevents pre-paying boundaries the
        thread has no near-term shot at, but the service only enforces
        "boundary_level > thread.level" (no double-unlock; idempotency
        via unique_together on ThreadLevelUnlock)
      - character.xp_balance >= ThreadXPLockedLevel.xp_cost
      - boundary_level <= effective_cap(thread)

    Atomic: decrements XP, creates ThreadLevelUnlock row.
    Emits a `ThreadXPLockUnlocked` event.
    Raises `XPInsufficient` or `AnchorCapExceeded` on failure.
    """
```

This is the function the "Unlock next tier" UI button calls (separate from
the Imbuing ritual flow). Players unlock a boundary *before* attempting to
imbue past it; in practice the UI surfaces the unlock as the next-step CTA
when a thread's bucket is approaching the boundary.

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
    Atomically debit the matching CharacterResonance row's `balance` for
    the chosen tier's `resonance_cost`, plus
    `anima_per_thread * (len(threads) - 1)` anima from the character's
    `CharacterAnima` row (the first thread is "free" beyond the resonance cost).
    Validates:
      - all threads owned by `character`
      - all threads share `resonance`
      - anchor-involvement per §5.2 (system check for non-relationship anchors;
        player-asserted for relationship anchors — caller passes the assertion
        through `action_context`)
      - character_resonance.balance and CharacterAnima.current sufficient
    Returns a structured ResonancePullResult dataclass (defined in
    `world/magic/types.py`) with:
        - resonance_spent: int
        - anima_spent: int
        - resolved_effects: list[ResolvedPullEffect]
            # Each ResolvedPullEffect carries the source ThreadPullEffect plus
            # `level_multiplier`, `scaled_value`, and source-thread metadata
            # so the action layer can apply the per-effect scaled outcome
            # without re-deriving it from the raw row.
    Emits a `ThreadsPulled` event.
    """
```

Both spend functions run in a single Django transaction and mutate the
SharedMemoryModel-cached `CharacterResonance` and `CharacterAnima` instances
in-memory before saving. Because Evennia runs as a single process and
all spend paths route through the same identity-mapped instances, no
row-level locking (`select_for_update`) is needed — concurrent spend
calls from different actors in overlapping turns serialize naturally
on the GIL and the in-memory state is the source of truth.

This is consistent with the project-wide "Trust the Identity Map"
principle (see CLAUDE.md): SharedMemoryModel instances are the canonical
Python objects for these rows; once loaded, every reader/writer in the
process sees the same instance. We would only need `select_for_update`
if (a) writes happened via raw queryset `.update()` calls bypassing the
identity map, or (b) the project moved to a multi-process worker model.
Neither applies. If either becomes true later, lock semantics get
revisited then.

**Dependency note:** `CharacterAnima` (current/maximum) is the existing magic-system
anima model in `world/magic/models.py`. Spec A reuses it directly — no new pool
model is introduced for anima.

### 3.3 Allocation is player-driven

There's no automatic allocation of incoming resonance to specific threads. Resonance
accumulates as `CharacterResonance.balance`; the player decides via Imbuing rituals
which threads to spend on. This makes specialization a deliberate choice (lean hard
into one resonance → develop fewer threads more deeply, or spread → many shallow
threads).

The dashboard surfaces decision-support (which threads are imbue-ready, which are
near an XP-locked boundary, which are at effective_cap) but never auto-spends.

### 3.4 Lifetime metrics

`CharacterResonance.lifetime_earned` is monotonically incremented and never debited. Useful
for:

- Achievements ("earned 1000 lifetime Celestial resonance")
- Soft retro-unlocks if we ever want to gate something on cumulative identity work
- Analytics on which resonances different player archetypes converge on

### 3.5 Concurrency model

All spends and grants run in single Django transactions and mutate the
SharedMemoryModel-cached `CharacterResonance` / `CharacterAnima` instances
in-memory before saving. Single-process Evennia + identity-mapped instances
means concurrent reads/writes converge on the same Python object and
serialize naturally on the GIL — no row-level locks (`select_for_update`)
needed. See §3.2 for the full rationale and the conditions under which
locks would need to come back.

### 3.6 CharacterResonance service helpers

```python
def get_or_create_character_resonance(
    character, resonance
) -> CharacterResonance: ...

def imbue_ready_threads(character) -> list[Thread]:
    """Threads whose matching character_resonance.balance > 0 and whose
       level < effective_cap — i.e. threads the player could productively
       imbue right now."""

def near_xp_lock_threads(
    character, within: int = 100
) -> list[ThreadXPLockProspect]:
    """Threads whose developed_points are within `within` of crossing
       the next XP-locked boundary AND that boundary isn't already
       unlocked. UI hint surface — the 'Unlock next tier' CTA appears
       on these. ThreadXPLockProspect is a small dataclass:
         (thread, boundary_level, xp_cost, dev_points_to_boundary)."""

def threads_blocked_by_cap(character) -> list[Thread]:
    """Threads at effective_cap — no more imbuing helps until either
       the anchor advances (e.g., underlying trait improves) or the
       character's path stage increases. UI shows 'capped' badge."""
```

These power the My Threads page. None mutate.

### 3.7 Caching and character handlers

Pull resolution is on the hot path of every action with thread involvement.
Per-action queries against `Thread`, `CharacterResonance`, and the lookup tables
would grind the system to a halt; caching is required, not optional.

Two tiers of caching, both following established project conventions.

#### Lookup-table caching (free via SharedMemoryModel)

Every config/lookup model in this spec uses `SharedMemoryModel` (project
default) and rides the Evennia identity map. After the first read, all
rows are persistent Python objects — subsequent reads are pure dict
lookups, no SQL. Models in this category:

- `ThreadPullCost` (3 rows)
- `ThreadPullEffect` (authored content; expected order ~10²–10³ rows)
- `ThreadXPLockedLevel` (~10 rows)
- `ThreadWeavingUnlock` (authored content; expected order ~10²)
- `ImbuingProseTemplate` (authored content; expected order ~10¹–10²)
- `Ritual`, `RitualComponentRequirement` (authored content)
- `Resonance`, `Affinity` (existing — already SharedMemoryModel)

The pull-resolution algorithm (§5.4) walks these in-memory dictionaries
indexed by `(target_kind, resonance, tier)` — no per-action queries.
Index helpers on the Effect lookup model preload the
`(target_kind, resonance, tier) → list[ThreadPullEffect]` map at first
access via `@cached_property` on a manager method, populated from the
identity-mapped queryset.

#### Per-character handlers (mirror existing pattern)

Per-character data hangs off character handlers, matching the project's
established pattern (`character.traits` → `TraitHandler`, etc.).

- **`character.threads`** → `CharacterThreadHandler`
  - `.all()` — `Thread.objects.filter(owner=...).select_related(resonance,
    target_trait, target_technique, target_object,
    target_relationship_track, target_capstone)` cached as a list on first
    access via `@cached_property`
  - `.by_resonance(resonance)` — filtered view, cached per resonance
  - `.with_anchor_involved(action_context)` — returns the threads whose
    anchors are in scope for an action (per §5.2 rules); used by both
    pull resolution and tier-0 passive collection
  - `.passive_vital_bonuses(vital_target)` — sum of scaled VITAL_BONUS
    contributions for `MAX_HEALTH` recomputation and `DAMAGE_TAKEN_REDUCTION`
    subscription (called from outside the action loop, but still wants the
    cache for hot-loop combat)
  - `.invalidate()` — called by `weave_thread`, `spend_resonance_for_imbuing`,
    `cross_thread_xp_lock`, `update_thread_narrative`, and any future
    mutation; clears the `@cached_property` slots

- **`character.resonances`** → `CharacterResonanceHandler`
  - `.balance(resonance)` — returns `int` from the cached `{resonance:
    CharacterResonance}` dict (0 if no row exists yet)
  - `.lifetime(resonance)` — same shape, returns `lifetime_earned`
  - `.get_or_create(resonance)` — returns the SharedMemoryModel instance,
    creating with balance=0/lifetime_earned=0 if absent
  - `.most_recently_earned()` — returns the row with the highest
    `lifetime_earned` (ties broken by `-pk`); used by Mage Scars
    `_apply_magical_scars` to derive origin (affinity, resonance)
  - `.all()` — list of `CharacterResonance` rows for the character;
    used by the character-sheet "Who I Am" identity surface
  - `.invalidate()` — called by `grant_resonance`,
    `spend_resonance_for_imbuing`, `spend_resonance_for_pull`

Both handlers follow the project's "mutation invalidates the cache, reads
trust the cache" rule. Service functions are the only callers that
mutate; they always invalidate after mutation.

#### Why this matters

A naïve implementation of pull resolution would issue queries per
thread × per tier × per stacking pass. With caching:
- First action of the scene: ~3-5 queries to warm the per-character
  handler caches.
- Every subsequent action: zero queries on the read path. Pull commit
  issues `UPDATE` statements only for the rows that actually changed
  (the character_resonance, anima, thread).

Combat in particular hits damage-reduction subscribers per
`DamagePreApply` event; the `passive_vital_bonuses` cache is what
keeps that subscriber from being a query-per-hit disaster.

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
    service_function_path="world.magic.services.spend_resonance_for_imbuing",
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
  - Player-authored `name` (defaulted to "{Resonance} thread on {anchor}" if
    blank) + anchor name + kind icon
  - Resonance tag + display level (`level / 10`, e.g. internal 30 → "Lv 3")
  - Player-authored `description` collapsed by default; "✎" affordance to
    edit in place
  - `developed_points` progress bar — fill = `developed_points / next-level cost`,
    plus a tick mark on the bar at the position of the next XP-locked boundary
    (so the player can see "I'm 60 dev points away from needing to spend XP")
  - Cap badges: shows `effective_cap` and which gate is active
    ("Path-locked at 30" or "Anchor-locked at 50")
  - State-aware action button (one CTA at a time, prioritized in this order):
    - "Find a Teacher" — if anchor kind isn't unlocked (links to teaching-offer
      discovery filtered to that anchor type)
    - "Unlock Lv N" — if `developed_points` is within sight of an XP-locked
      boundary AND the player has enough XP for it (calls
      `cross_thread_xp_lock`)
    - "Begin Imbuing Ritual" — if pool has spendable balance and the thread
      is below `effective_cap` (links to in-game ritual flow which calls
      `spend_resonance_for_imbuing`)
    - "Capped" badge — if at `effective_cap`, with hover text explaining the
      gate (path stage / anchor value / Spec D pending for ITEM/ROOM)
  - Pull-tier cost preview (informational only; pulls happen in action UI),
    annotated with "scales with thread level (Lv {n} = ×{n} multiplier)" so
    players see the level investment paying off
  - Anchor link (jumps to relationship/item/room/technique detail)
- **Relationship-anchored threads also appear inside the relationship page itself**
  as a sidebar card with the same affordances.

The page never mutates threads directly except for in-place edits to `name` and
`description` (pure narrative, no mechanical effect). All level-ups route
through `PerformRitualAction("Rite of Imbuing", thread_id=N, amount=X)`;
all XP-lock crossings route through `cross_thread_xp_lock`.

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

GET    /api/magic/character-resonances/          own per-resonance balance +
                                                  lifetime_earned (the existing
                                                  CharacterResonance endpoint,
                                                  reshaped per §2.2)

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
   - character_resonance.balance >= ThreadPullCost(tier).resonance_cost.
   - CharacterAnima.current >= ThreadPullCost(tier).anima_per_thread *
     max(0, len(threads) - 1).

2. Atomically debit (single transaction, in-memory mutation of the
   SharedMemoryModel-cached character_resonance and anima instances):
   - CharacterResonance.balance -= ThreadPullCost(tier).resonance_cost
   - CharacterAnima.current -= anima_total

3. For each pulled thread:
   For each effect_tier in 0..tier:
     Find ThreadPullEffect rows matching:
       (target_kind=thread.target_kind, resonance=thread.resonance,
        tier=effect_tier, min_thread_level <= thread.level)
     For each matched row, scale its authored amount by the thread's
     display level (`scaled = authored × max(1, thread.level // 10)`).
     The level-scaling rule is **linear** and applies to all numeric
     effect_kinds (FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS).
     CAPABILITY_GRANT and NARRATIVE_ONLY do not scale (granting a
     capability is binary; a narrative snippet is text). For
     CAPABILITY_GRANT, `min_thread_level` is the gating mechanism
     instead of scaling.
     A thread at level 0 (just-woven, never imbued) applies effects at
     ×1 baseline so freshly-woven threads still feel like something.
     Add (effect_row, scaled_amount, source_thread) tuples to the active
     effect list.

4. Also collect tier-0 effects from any non-pulled threads whose anchors are
   involved in the action (passive layer fires regardless of pulls). Same
   `min_thread_level` filter and level-scaling apply.

5. Resolve and apply effects per stacking rules (5.5).

6. Emit ThreadsPulled event with full audit payload (including per-effect
   scaled amounts and source thread IDs for transparency in scene logs).

7. Return ResonancePullResult dataclass to the action resolver, which applies
   the effects to the action's check / intensity / capabilities at pre-roll time.
```

### 5.5 Stacking rules by effect_kind

When multiple effects apply to the same action (after per-effect level-scaling
from §5.4):

- **FLAT_BONUS** — sum the **scaled** amounts. Three level-3 threads each
  authoring +2 = three contributions of +6 = +18 total. No cap (designer
  authoring restraint is the throttle).
- **INTENSITY_BUMP** — sum the scaled amounts, capped at the system's highest
  IntensityTier. The pull preview displays the effective (capped) outcome so
  players never spend anima for intensity past the cap; they can downsize their
  pull or shift to other resonances.
- **VITAL_BONUS** — tier-0 only (per §2.1). Sum the scaled amounts **per
  `vital_target`** across all the character's threads whose anchors are
  passively in scope. Effects with different `vital_target`s do not stack
  with each other (a `MAX_HEALTH` row and a `DAMAGE_TAKEN_REDUCTION` row
  are independent contributions to two different consumers). For `MAX_HEALTH`,
  the sum is added to the character's
  `vitals.max_health` recomputation. For `DAMAGE_TAKEN_REDUCTION`, the sum
  is supplied to combat's `DamagePreApply.modify_amount` subscriber. No cap
  in Spec A; Spec B owns any per-stat ceilings if playtest demands them.
- **CAPABILITY_GRANT** — union. All granted capabilities are available for this
  action. Capabilities are categorical, not numerical; granting the same capability
  twice is a no-op. **`min_thread_level` is the gating mechanism for capability
  power tiering** — author "minor capability X at min_thread_level=10, full
  capability X at min_thread_level=30" if you want graduated unlocks.
- **NARRATIVE_ONLY** — collect all `narrative_snippet` strings; the action's
  narrative output presents them all (deduplicated, in pull order).

The user's principle: stacking should feel good. Sum-and-union is the rule;
take-highest creates "wasted anima" traps and is rejected. Level investment
must matter — that's why all numeric effects scale linearly with thread level.

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
    {
      kind,                            # FLAT_BONUS | INTENSITY_BUMP |
                                       #   VITAL_BONUS | CAPABILITY_GRANT |
                                       #   NARRATIVE_ONLY
      authored_value,                  # raw value on the authored row
      level_multiplier,                # source thread's display level (×1, ×2…)
      scaled_value,                    # authored × level_multiplier
      vital_target,                     # populated for VITAL_BONUS only
      source_thread_id,
      source_thread_level,             # internal level (10/20/30…)
      source_tier,
      narrative_snippet?
    }
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

- `FLAT_BONUS` (scaled) is added to the check's modifier total.
- `INTENSITY_BUMP` (scaled) is added to the action's effective intensity tier.
- `CAPABILITY_GRANT` capabilities are added to the action's capability set for the
  duration of the resolution.
- `narrative_snippet`s are appended to the action's narrative output buffer for
  rendering.

`VITAL_BONUS` effects do NOT route through the action resolver — they target
character-level vital pools, not per-action checks. Routing per `vital_target`:

- **`MAX_HEALTH`** — `vitals.recompute_max_health(character)` is the canonical
  recomputation entry point (already invoked when stats change). Spec A adds
  one new addend source: `sum(scaled_amount for VITAL_BONUS rows with
  vital_target=MAX_HEALTH on every active passive thread for this character)`.
  "Active passive" means tier-0 ThreadPullEffect rows on threads whose anchor
  is currently in scope — for relationship anchors that means the relationship
  exists; for trait anchors that means the trait exists; etc. `recompute_max_health`
  is invoked when a thread is woven, imbued, retired, or its anchor's
  involvement-state changes (the thread-mutation service functions emit the
  recompute call; no Django signals).
- **`DAMAGE_TAKEN_REDUCTION`** — a subscriber registers against combat's
  existing `DamagePreApply` event and uses the `modify_amount` hook (already
  used by combat's reactive system; see `src/world/combat/tests/
  test_reactive_integration.py::DamageModifyPayloadTest`). On the
  damage-pre-apply event, the subscriber computes the active-passive sum for
  the target character and reduces incoming damage by that amount (clamped
  at 0). No new event types; no combat-system changes; the integration is
  purely subscribing to an existing reactive hook.

Spec A authors **zero** VITAL_BONUS rows — these routes exist as installed
plumbing for Spec B (Relational Resilience). The implementation plan should
include a smoke-test row authored only in tests to prove the wiring.

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
- `Thread` (new model — replaces old Thread completely; includes
  `name`/`description`/`developed_points`/`level`)
- `ThreadPullCost` (lookup, SharedMemoryModel)
- `ThreadXPLockedLevel` (lookup, SharedMemoryModel)
- `ThreadLevelUnlock` (per-thread record of XP-lock crossings)
- `ThreadPullEffect` (lookup, SharedMemoryModel; includes `min_thread_level`,
  `VITAL_BONUS` effect_kind constrained to tier=0 only, `vital_target`,
  `vital_bonus_amount`)
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

#### Step 3 — Reshape `CharacterResonance` (identity + currency merge)

The existing `CharacterResonance` model is reshaped per §2.2 in a single
schema migration:
- **Add fields**: `balance` (PositiveIntegerField default=0), `lifetime_earned`
  (PositiveIntegerField default=0), `claimed_at` (DateTimeField auto_now_add).
- **Drop fields**: `scope`, `strength`, `is_active`, `created_at` (no consumers
  for the first three; `claimed_at` replaces `created_at`).
- **Re-FK**: `character` (was FK ObjectDB) → `character_sheet` (FK CharacterSheet,
  on_delete=CASCADE). Aligns with project rule against direct ObjectDB FKs.
- **Update `unique_together`**: `(character_sheet, resonance)`.
- **Update related_name**: `resonances` (read from CharacterSheet).

Knock-on edits in the same migration / commit:
- `_apply_magical_scars` in `world/mechanics/effect_handlers.py` switches from
  `CharacterResonance.objects.filter(character=character, is_active=True)
  .order_by("-pk").first()` → `character.resonances.most_recently_earned()`.
- `CharacterResonanceSerializer` and `CharacterResonanceViewSet` in
  `world/magic/serializers.py` / `views.py` drop the dropped fields from
  `Meta.fields` and add `balance`, `lifetime_earned`, `claimed_at`.
- `CharacterResonanceFactory` in `world/magic/factories.py` updates field
  defaults; the `is_active=True` kwarg used in
  `integration_tests/pipeline/test_alteration_pipeline.py` is removed
  (existence of the row is the activation signal post-merge).
- `CharacterResonanceAdmin` in `world/magic/admin.py` updates
  `list_display` / `fields`.

No `RunPython` data step — the dev DB is disposable per CLAUDE.md, and there
is no production data to preserve.

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
- `ThreadXPLockedLevelFactory` — preset rows at internal levels 20, 30, 40,
  50… with placeholder xp_costs (parallels skill XP-lock authoring)
- `ThreadLevelUnlockFactory` — per-thread record of an XP-lock crossing;
  flexible by (thread, unlocked_level)
- `ThreadPullEffectFactory` — flexible factory for authoring sample effects per
  test, with traits `as_flat_bonus`, `as_intensity_bump`, `as_capability_grant`,
  `as_narrative_only`, and `as_vital_bonus(vital_target=...)` to exercise the
  VITAL_BONUS payload schema for Spec B's eventual authoring
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
- `CharacterResonanceFactory` — existing factory, updated for the merged shape:
  flexible `balance` / `lifetime_earned`, drops the removed `scope` / `strength`
  / `is_active` kwargs. Add traits `with_balance(amount)` and `claimed_only`
  (balance=0, lifetime_earned=0) for chargen-style identity claims.
- `ThreadFactory` (new) — discriminator-aware traits (`as_trait_thread`,
  `as_item_thread`, `as_room_thread`, `as_technique_thread`, `as_track_thread`,
  `as_capstone_thread`) to set the right FK and `target_kind` together

**Implementation note:** The Mage Scars rename in Step 4 has zero overlap with
Steps 1–3 and the rest of Spec A's data-layer work. The implementation plan
should split it into its own commit/PR for cleaner review — bundling it here
is purely for spec organization.

### 7.4 Service-layer migrations

Service functions to add in `world/magic/services.py`:
- `grant_resonance(character, resonance, amount, source, source_ref=None)`
- `spend_resonance_for_imbuing(character, thread, amount)` — bucket-fill +
  greedy advancement; the Imbuing-ritual dispatch target (called by
  `PerformRitualAction("Rite of Imbuing", thread_id, amount)`)
- `cross_thread_xp_lock(character, thread, boundary_level)` — pays XP for
  the next XP-locked boundary; called by the My Threads "Unlock Lv N" CTA
- `spend_resonance_for_pull(character, resonance, tier, threads, action_context)`
- `weave_thread(character, target_kind, target, resonance, *, name="", description="")`
  — eligibility check (CharacterThreadWeavingUnlock for the anchor's
  kind+target) + Thread row creation; no resonance cost (weaving is free,
  Imbuing carries the strategic spend); accepts optional name/description
- `update_thread_narrative(thread, *, name=None, description=None)` — pure
  narrative edit, no mechanical effect; used by the My Threads in-place edit
- `accept_thread_weaving_unlock(learner, offer)` — mirrors codex teaching-acceptance;
  creates the `CharacterThreadWeavingUnlock` row
- `compute_thread_weaving_xp_cost(unlock, learner)` — Path-multiplier resolver
- `compute_anchor_cap(thread)` — returns the §2.4 anchor cap for a Thread,
  with per-`target_kind` normalization to the common scale (TRAIT direct,
  TECHNIQUE × 10, etc.). Raises `AnchorCapNotImplemented` for ITEM/ROOM
  pending Spec D.
- `compute_path_cap(character)` — `path_stage × 10`, defaulting to 10 for
  characters with no path history yet
- `compute_effective_cap(thread)` — `min(compute_path_cap(owner),
  compute_anchor_cap(thread))`; used by both spend services and the My Threads
  page
- `recompute_max_health_with_threads(character)` — wrapper that calls
  `vitals.recompute_max_health` with thread-derived MAX_HEALTH VITAL_BONUS
  contributions folded in (sourced from
  `character.threads.passive_vital_bonuses(MAX_HEALTH)`). Invoked from
  the thread mutation services (weave/imbue/retire) and from any
  anchor-state change that would alter which threads are passively
  contributing.
- `apply_damage_reduction_from_threads(character, incoming_damage)` — the
  subscriber body for combat's `DamagePreApply.modify_amount` hook; reads
  `character.threads.passive_vital_bonuses(DAMAGE_TAKEN_REDUCTION)` and
  reduces incoming damage by the sum (clamped at 0). Cache hit on every
  call after the first per scene.

Handler classes in `world/magic/handlers.py`:
- `CharacterThreadHandler` — exposed via `character.threads`. See §3.7
  for full method list. Mutation methods on `Thread` go through the
  service functions, which call `.invalidate()` after writes.
- `CharacterResonanceHandler` — exposed via `character.resonances`.
  See §3.7 for method list. Same invalidation pattern as the thread handler.
  Replaces the prior draft's `CharacterResonancePoolHandler` /
  `character.resonance_pools` since `CharacterResonance` is now the single
  identity+currency model (§2.2).

Both handlers wire onto the existing `Character` typeclass alongside the
established handlers (`character.traits`, etc.) — no new typeclass machinery,
just added handler attributes.

Dataclasses in `world/magic/types.py`:
- `ResonancePullResult(resonance_spent: int, anima_spent: int,
   resolved_effects: list[ResolvedPullEffect])`
- `ResolvedPullEffect(...)` — per-effect record carrying `kind`,
  `authored_value`, `level_multiplier`, `scaled_value`, `vital_target`,
  `source_thread`, `source_thread_level`, `source_tier`, `narrative_snippet`
- `ThreadImbueResult(resonance_spent: int, developed_points_added: int,
   levels_gained: int, new_level: int, new_developed_points: int,
   blocked_by: str)` — return shape for `spend_resonance_for_imbuing`
- `ThreadXPLockProspect(thread, boundary_level: int, xp_cost: int,
   dev_points_to_boundary: int)` — return shape for `near_xp_lock_threads`
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
    walk for ITEM); name/description optional; default-name rendering when blank
  - bucket-fill imbue spend (success at sub-boundary level, no XP needed;
    success crossing a boundary that has a `ThreadLevelUnlock`; rejection
    at an unlocked boundary; greedy multi-level advancement when bucket
    overflows; insufficient resonance; anchor cap exceeded; path cap exceeded;
    `blocked_by` field correctly set per case)
  - XP-lock crossing (`cross_thread_xp_lock`): success, insufficient XP,
    boundary already crossed (idempotency), boundary above effective_cap
  - cap normalization (`compute_anchor_cap`):
    TRAIT cap = trait_value (no multiplier), TECHNIQUE cap = level × 10,
    RELATIONSHIP_TRACK cap = tier_index × 10, RELATIONSHIP_CAPSTONE cap =
    path_stage × 10, ITEM/ROOM raise `AnchorCapNotImplemented`
  - `compute_path_cap`: stage 0 → 10, stage N → N × 10, no path history → 10
  - `compute_effective_cap`: chooses the tighter of path/anchor; surfaces
    which gate is active
  - pull cost + stacking (FLAT_BONUS sum-of-scaled, INTENSITY_BUMP cap,
    CAPABILITY_GRANT union, NARRATIVE_ONLY collection, mixed-kind snippet
    collection)
  - **level-scaling** — three threads at levels 10/20/30 each with the same
    authored +2 FLAT_BONUS produce contributions of +2/+4/+6 (sum = +12);
    `min_thread_level` correctly filters effects below the gate (a level-2
    thread doesn't trigger a `min_thread_level=30` row)
  - **VITAL_BONUS routing** — a tier-0 VITAL_BONUS row with
    `vital_target=MAX_HEALTH` increases `vitals.max_health` after weaving;
    a tier-0 VITAL_BONUS row with `vital_target=DAMAGE_TAKEN_REDUCTION`
    reduces damage in a `DamagePreApply` flow (smoke test using a sample
    authored row, not real Spec B authoring)
  - **VITAL_BONUS tier-0 enforcement** — `clean()` rejects a `VITAL_BONUS`
    row authored with `tier > 0`; database `CheckConstraint` rejects the
    same at the row level
  - **handler caching** — `character.threads.all()` issues one query then
    serves repeats from the cache; `weave_thread` / `spend_resonance_for_imbuing`
    invalidate the cache so the next read sees the mutation; same for
    `character.resonances.balance(resonance)` after `grant_resonance` /
    `spend_resonance_for_pull`. Includes a "no queries on the hot path"
    assertion using `assertNumQueries(0)` after warmup
  - **CharacterResonance merged shape** — `grant_resonance` creates the row
    on first call (lazy) and increments both `balance` and `lifetime_earned`
    on subsequent calls; `most_recently_earned()` picks the row with the
    highest `lifetime_earned`; `_apply_magical_scars` derives origin
    `(affinity, resonance)` from that row (no `is_active` filter)
  - pull anchor-involvement (system-checked for non-relationship, asserted for
    relationship; commit re-validation when anchor falls out of play)
  - ritual dispatch — both the SERVICE path (Imbuing) AND the FLOW path (a sample
    flow-driven ritual) so both execution kinds are exercised
  - `is_soul_tether` flag round-trip on CharacterRelationship
  - `CharacterThreadWeavingUnlock` purchase + idempotency (same offer twice
    rejected)
  - in-Path / out-of-Path / Path-neutral cost paths in `computed_xp_cost`
  - `update_thread_narrative` round-trip (name/description edits persist;
    no level/cap changes)

---

## 8. Open Deferrals

### 8.1 Handoff to Spec B (Relational Resilience + Soul Tether + Ritual Capstones)

Inheriting from Spec A:

- `CharacterRelationship.is_soul_tether`, `soul_tether_role`, `magical_flavor`
  fields exist and are settable but have no mechanical effect yet.
- `Ritual` model and `PerformRitualAction` are usable for authoring Soul Tether
  and other ritual-flavored capstone moments.
- **`ThreadPullEffect.VITAL_BONUS` effect_kind with `vital_target` enum**
  (`MAX_HEALTH`, `DAMAGE_TAKEN_REDUCTION`) is installed and wired,
  **constrained to tier=0 (passive)**: `MAX_HEALTH` rows feed
  `vitals.recompute_max_health`; `DAMAGE_TAKEN_REDUCTION` rows feed combat's
  `DamagePreApply.modify_amount` subscriber. Spec B authors resilience as
  tier-0 VITAL_BONUS rows on relationship-anchored ThreadPullEffects —
  no schema changes required. The investment lever is the thread's level
  itself: tier-0 VITAL_BONUS scales linearly with `thread.level` per §5.4,
  so a level-3 relationship thread with an authored "+5 max_health" row
  contributes +15. Combine with `min_thread_level` for graduated unlocks
  (small bonus from the start, larger bonus only after the thread is
  imbued past a threshold). Per-action paid-pull VITAL_BONUS is explicitly
  disallowed (§2.1 rationale) — durability is a passive, not a one-shot.

Spec B owns:

- Aggregate relational-resilience formula expressed as authored VITAL_BONUS
  rows on relationship-anchored ThreadPullEffects, gated by `min_thread_level`
  for the meaningful tiers (modest tier-0 passive, larger gated bonuses at
  higher thread levels). Existing `CharacterRelationship.mechanical_bonus =
  cube_root(developed_value)` may still play a role for the always-on
  ungated baseline, but the *meaningful* survivability (the part the user
  flagged as needing to be xp/resonance-gated) lives on threads.
- Soul Tether grounding scaling formula (depth × caster tier; vulnerability of
  Abyssal-side and burden of Sineater-side).
- Soul Tether break consequences and societal-gating expression (some societies
  *require* Soul Tether for Abyssal magic — how that's enforced).
- The Ritual Capstone authoring pipeline (Capstones can optionally point to a
  Ritual; rituals like Ritual of Devotion / Ritual of Betrayal / Accepting a Soul
  Tether are authored as Ritual rows + companion FlowDefinitions).
- Any new `vital_target` enum values Spec B needs beyond `MAX_HEALTH` and
  `DAMAGE_TAKEN_REDUCTION` (e.g. `MAX_ANIMA`, type-specific resistances).
  These are additive enum values, not schema changes.

### 8.2 Handoff to Spec C (Resonance Gain Surfaces)

Inheriting from Spec A:

- `grant_resonance(character, resonance, amount, source, source_ref)` service
  function is the universal entry point for awarding resonance.
- `CharacterResonance` model carries `balance` (spendable) and
  `lifetime_earned` (cumulative tracking) on the same row that identifies
  the character's resonance affiliation. Earning currency lazily creates
  the row — see §2.2 for the identity-claims-via-earning semantics.

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
- **ITEM and ROOM anchor-cap formulas** — Spec D's "magical significance"
  authoring (on ItemTemplate / ItemInstance / RoomProfile) is the natural
  source for these caps. Spec A's `compute_anchor_cap` implementation raises
  `AnchorCapNotImplemented` for ITEM and ROOM; Spec D extends it with the
  appropriate normalized formula (matching the common × 10 scale used by
  TECHNIQUE / RELATIONSHIP_TRACK so the math composes uniformly).
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
- **TECHNIQUE-anchor cap multiplier may need revisiting.** §2.4 caps
  TECHNIQUE-anchored thread level at `Technique.level × 10`. Techniques are
  1–5 today; if the Technique system gains finer-grained levels (1–100,
  matching skills), drop the multiplier. The formula stays; the multiplier
  is the only thing that floats with the underlying scale.
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
