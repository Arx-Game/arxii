# Relationship-Driven Thread Growth: Shared Time Currency + Capstone Investment

**Date:** 2026-05-09
**Status:** Draft (autonomous-mode design conversation)
**Related:**
- `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` — Spec A (Threads + Currency)
- `docs/superpowers/specs/2026-04-23-resonance-pivot-spec-c-gain-surfaces-design.md` — Spec C (Resonance Gain Surfaces)
- `docs/superpowers/specs/2026-05-03-resonance-pivot-spec-b-soul-tether-design.md` — Spec B (Soul Tether), which already builds on RELATIONSHIP_CAPSTONE Threads
- `src/world/relationships/services.py` — `create_first_impression`, `create_development`, `create_capstone`, `redistribute_points`
- `src/world/magic/services/threads.py` — `compute_anchor_cap`, `compute_path_cap`, `compute_effective_cap`
- `src/world/magic/services/resonance.py` — `resolve_pull_effects`, `spend_resonance_for_pull`
- `src/world/magic/services/gain.py` — `grant_resonance`, the typed-FK gain pipeline
- `src/world/magic/models/grant.py` — `ResonanceGrant` audit ledger pattern (template for `SharedTimeGrant`)
- `src/world/relationships/models.py` — `CharacterRelationship`, `RelationshipTrackProgress`, `RelationshipCapstone`, `RelationshipTier`

---

## Goal

Make magical Threads on relationships respond to actual relationship investment.

Today, weaving a Thread on a `RELATIONSHIP_TRACK` or `RELATIONSHIP_CAPSTONE` anchor produces a magical container that grows from currency earned via *unrelated* surfaces — pose endorsements, residence trickle, outfit trickle. The relationship itself, the substrate the Thread is anchored to, has no feedback loop. You can have a deep Thread on a relationship you've barely played, and a shallow Thread on a relationship that defines your character.

This spec closes that loop. It introduces a per-pair currency (**Shared Time**) that accrues from co-activity between two characters, can be spent on `RelationshipCapstone` events to give them mechanical weight, and ties Thread strength on relationship anchors to the depth of the underlying relationship.

The design also resolves a long-standing internal tension about capstone limits: **capstone authoring is never blocked**, but **mechanical reward requires investment**. Players can always record a moment; the system decides whether it carries weight based on what the players have actually played together.

## Background

### What exists today

**Relationship advancement primitives (`src/world/relationships/`):**
- `RelationshipUpdate` — unlimited; adds temporary points + capacity. Decays over `DECAY_DAYS`.
- `RelationshipDevelopment` — 7/week per author across all relationships; adds permanent (developed) points up to capacity; awards XP via `world.progression.services.awards.award_xp`.
- `RelationshipCapstone` — unlimited; adds permanent points + capacity simultaneously. The most-powerful event. **Currently the only mechanical limit is "the player decides what `points` value to pass."**
- `RelationshipChange` — moves developed points between tracks; weekly counter limit on `CharacterRelationship.changes_this_week`.
- `RelationshipTier` — point-threshold milestones within a track. Computed property `RelationshipTrackProgress.current_tier` returns the highest tier whose `point_threshold ≤ developed_points`. **No event fires on tier crossing today**; it's a derived read.
- `CharacterRelationship` is **directional** — Alice→Bob and Bob→Alice are separate rows, each with its own state (deceit, displayed_track, conditions).

**Magic-side anchoring (`src/world/magic/`):**
- `Thread.target_relationship_track` (FK to `RelationshipTrack`) — Thread anchored to a track in the owner's relationship history.
- `Thread.target_capstone` (FK to `RelationshipCapstone`) — Thread anchored to a specific capstone event.
- `compute_anchor_cap`:
  - `RELATIONSHIP_TRACK` → `current_tier.tier_number × 10`. Tied to track depth via tier crossings, but only crudely — every developed point under the next threshold yields zero anchor-cap progress.
  - `RELATIONSHIP_CAPSTONE` → `_current_path_stage(thread.owner) × 10`. **Placeholder** — same formula as the path cap; ignores the underlying capstone entirely.
- `resolve_pull_effects` for `RELATIONSHIP_*` Threads applies authored `ThreadPullEffect` rows verbatim — no relationship-strength multiplier.

**Resonance currency surfaces (`world/magic` Spec C):**
- `grant_resonance(sheet, resonance, amount, *, source, **typed_fk_kwargs)` — typed-FK gain pipeline.
- `GainSource` TextChoices: `POSE_ENDORSEMENT`, `SCENE_ENTRY`, `RESIDENCE_TRICKLE`, `OUTFIT_TRICKLE`, `STAFF_GRANT`. Each source has a matching typed FK on `ResonanceGrant`.
- No existing source ties to relationship events.

### What's missing

- **No currency or surface tying co-activity to relationship depth.** Shared scenes, shared stories, shared combats are recorded structurally (`SceneParticipation` etc.) but produce no relationship-side accrual.
- **No mechanical limit on capstone authoring.** A player can author a 1000-point capstone today; the only restraint is social.
- **`compute_anchor_cap` for `RELATIONSHIP_CAPSTONE`** is a stub that ignores the capstone.
- **`compute_anchor_cap` for `RELATIONSHIP_TRACK`** uses tier_number which loses information between thresholds.
- **`resolve_pull_effects`** treats RELATIONSHIP_* Threads identically to TRAIT/TECHNIQUE/etc.; no signal that a stronger relationship produces stronger pulls.
- **No resonance grant fires on relationship events** — capstone, tier crossing, deep development.
- **No event fires on tier crossing.** Tracking the highest tier reached is needed to grant exactly once per crossing.

## Scope

**In scope:**

1. **Shared Time currency.** New per-directional-pair fields on `CharacterRelationship`: `shared_time_balance`, `shared_time_lifetime`. Mirrors `CharacterResonance` shape.
2. **`SharedTimeGrant` audit ledger.** Typed-FK discriminator pattern matching `ResonanceGrant`. New TextChoices `SharedTimeSource`.
3. **Earning hooks.** Per-service grant calls in:
   - Scene closure
   - `RelationshipDevelopment` authoring
   - Story episode closure
   - Combat encounter end
   - `STAFF_GRANT` admin path
4. **Capstone investment.** `create_capstone` accepts an `invested_amount` parameter. `RelationshipCapstone.shared_time_invested` records what was spent. `RelationshipCapstone.points` derives from `shared_time_invested` via a knob-driven formula. `invested_amount=0` records the capstone narratively (`points=0`) without firing magical kickbacks.
5. **Thread feedback formulas.**
   - `compute_anchor_cap` for `RELATIONSHIP_TRACK` rewritten to use `developed_points` directly.
   - `compute_anchor_cap` for `RELATIONSHIP_CAPSTONE` rewritten to use `target_capstone.points`.
   - `resolve_pull_effects` applies a relationship-strength multiplier for `RELATIONSHIP_*` Threads.
6. **Resonance grants on invested events.** Three new `GainSource` values:
   - `RELATIONSHIP_CAPSTONE_INVESTED` — bilateral grant when a capstone fires with `points > 0`.
   - `RELATIONSHIP_TIER_CROSSED` — bilateral grant on first crossing of any `RelationshipTier.point_threshold`.
   - `RELATIONSHIP_DEVELOPMENT_ECHO` — author-only grant alongside `RelationshipDevelopment` records that exceed a threshold (knob).

   Each gets a typed FK on `ResonanceGrant`.
7. **Tier-crossing tracking.** New `RelationshipTrackProgress.highest_tier_crossed` FK to `RelationshipTier`. Detection logic in capstone + development services.
8. **Free Thread development on invested capstones.** When a capstone fires with `points > 0` and the character has a woven `RELATIONSHIP_TRACK` Thread on the relevant track or a `RELATIONSHIP_CAPSTONE` Thread on the new capstone, that Thread receives free `developed_points` (knob-driven amount).
9. **`RelationshipMagicConfig` singleton.** All knobs.
10. **API + serializers** for capstone authoring with investment, plus filterable read access to `SharedTimeGrant`.
11. **Comprehensive test coverage** — factory seeds, unit tests per service, integration tests covering full earn → spend → capstone-fires → resonance-grants → Thread-development chains.

**Out of scope (explicit deferrals):**

- **No UI in this PR.** Per project bikeshedding redirect: foundational system work only. UI follows once systems settle.
- **No RL-time or IC-time passive trickle.** AFK doesn't grow bonds.
- **No AP-spend-targeting plumbing.** Per discussion: AP is implicit in activity participation. We hook on activity completion, not on AP spend. If/when relationship-targeted AP-spend tagging exists as a generic concept, that hook can be added without breaking the design.
- **No mission system integration.** Mission system isn't built. Hook surface (`grant_shared_time` with appropriate source) is ready when missions ship.
- **No retroactive seeding.** Existing relationships, capstones, scenes, etc. produce no Shared Time. The system starts accruing from PR-merge forward. Local dev DB is disposable.
- **No bulk operations.** One capstone authored at a time.
- **No anchor-pickers cleanup** (Task B from the originating prompt). Separate small PR.
- **No `RelationshipChange`-driven grants.** Changes redistribute existing points; they don't represent new shared time.
- **No grants on `RelationshipUpdate`.** Updates are unlimited and represent emotional spikes; granting Shared Time on updates would be the easy farm vector.
- **No interaction-favorite or reaction-driven grants.** Too granular; too easy to game.

## Design Decisions

### 1. Shared Time is per-directional-pair on `CharacterRelationship`

`CharacterRelationship` is already directional (Alice→Bob and Bob→Alice are separate rows). Shared Time fields go on the relationship row. Each character independently tracks "my Shared Time invested in this bond" and spends it on capstones they author.

Storage: two `PositiveIntegerField`s on `CharacterRelationship`:

```python
shared_time_balance = models.PositiveIntegerField(
    default=0,
    help_text="Spendable Shared Time accrued from co-activity with the target."
)
shared_time_lifetime = models.PositiveIntegerField(
    default=0,
    help_text="Monotonic lifetime Shared Time earned. Audit only; never decreases."
)
```

Symmetric earning: when a scene closes with both Alice and Bob in it, both rows (`A→B` and `B→A`) receive the same grant. They spend independently.

Why not `CharacterRelationship`-pair-shared (one bucket)? Because directional state already exists on this model (deceit, conditions, displayed_track) and capstones are authored by one character at a time. Splitting balance per direction matches the per-author authoring model.

### 2. `SharedTimeGrant` audit ledger mirrors `ResonanceGrant`

```python
class SharedTimeGrant(SharedMemoryModel):
    relationship = models.ForeignKey(CharacterRelationship, on_delete=CASCADE,
                                     related_name="shared_time_grants")
    amount = models.PositiveIntegerField()
    source = models.CharField(max_length=32, choices=SharedTimeSource.choices)
    granted_at = models.DateTimeField(auto_now_add=True)

    # Typed FKs — exactly one populated per source kind. CheckConstraints enforce.
    source_scene = models.ForeignKey("scenes.Scene", on_delete=SET_NULL,
                                     null=True, related_name="+")
    source_development = models.ForeignKey("relationships.RelationshipDevelopment",
                                           on_delete=SET_NULL, null=True, related_name="+")
    source_episode = models.ForeignKey("stories.Episode", on_delete=SET_NULL,
                                      null=True, related_name="+")
    source_combat_encounter = models.ForeignKey("combat.CombatEncounter", on_delete=SET_NULL,
                                                null=True, related_name="+")
    source_staff_account = models.ForeignKey("accounts.AccountDB", on_delete=SET_NULL,
                                             null=True, related_name="+")
```

`SharedTimeSource` TextChoices: `SHARED_SCENE`, `RELATIONSHIP_DEVELOPMENT`, `STORY_EPISODE`, `COMBAT_ENCOUNTER`, `STAFF_GRANT`.

CheckConstraints (per existing `ResonanceGrant` pattern): exactly the typed FK matching `source` is non-null; all others are null.

Lives in `src/world/relationships/models/shared_time.py` (new submodule). Not in `world/magic` because the currency belongs to the relationship layer; magic consumes it via the resonance-grant fan-out (§7).

### 3. Earning sources, all knob-weighted

#### 3.1 Scene closure (`SHARED_SCENE`)

Hook: `world.scenes.services.close_scene` (verify exact path during implementation; if no service-level hook exists, add one — closing a scene is already a discrete operation).

For every pair `(A, B)` of characters where both have a `SceneParticipation` row in the closing Scene with `is_active=True` (or the existing equivalent), grant Shared Time to both `A→B` and `B→A`. Amount:

```
amount = config.scene_grant_per_pair × scene_intensity_multiplier(scene)
```

`scene_intensity_multiplier` is a function (registered, not stored) that reads scene metadata to apply weights — examples from user discussion: 1:1 scenes weight more than group scenes; AP-cost-heavy scenes weight more than casual; combat scenes might weight differently than social. v1 implementation: `1.0` flat multiplier with the scene_grant_per_pair knob. Real intensity weighting is a v2 concern; the function-pluggable design lets us add weights without schema changes.

Daily anti-spam cap per pair: `config.scene_grant_daily_cap_per_pair` — at most this much Shared Time from `SHARED_SCENE` per `(A→B)` row per UTC day.

#### 3.2 Relationship development (`RELATIONSHIP_DEVELOPMENT`)

Hook: directly inside `create_development` in `world/relationships/services.py`. After the development is created and XP is awarded, before returning, call `grant_shared_time(relationship=A→B, amount=X, source=RELATIONSHIP_DEVELOPMENT, source_development=development)`.

This is the **explicit cultivation** surface — players use a Development to deliberately deepen a relationship. Grant amount knob: `config.development_grant_amount`. Larger than scene_grant_per_pair to reflect explicit choice.

Symmetric? **No — author-only.** Developments are reflective writeups by one character about a specific relationship; they don't represent shared activity, they represent the author's investment of attention. The author earns; the target does not.

(Memo: this is the closest thing to "AP allocated to cultivating this relationship" since Developments are 7-per-week-budgeted on the author's time.)

#### 3.3 Story episode closure (`STORY_EPISODE`)

Hook: episode closure in `world/stories/services.py` (verify path — if no closure service exists yet, add a hook; episodes already have a closure concept per `Episode`). For every pair `(A, B)` where both have `StoryParticipation` rows on the closing Episode, grant `config.episode_grant_per_pair` to both `A→B` and `B→A`.

Episode closure is naturally bounded (episodes don't close every minute), so no daily cap needed.

#### 3.4 Combat encounter end (`COMBAT_ENCOUNTER`)

Hook: combat encounter resolution in `world/combat/services/`. For every pair `(A, B)` where both are participants in the resolved encounter (regardless of side — sparring an enemy you respect builds bond too), grant `config.combat_grant_per_pair` to both directions.

No daily cap; combat encounters are heavy events.

#### 3.5 Staff grant (`STAFF_GRANT`)

Admin override. `grant_shared_time(relationship=R, amount=N, source=STAFF_GRANT, source_staff_account=acct)` callable from Django admin or services tests.

### 4. Capstone investment model

`create_capstone` gains a new keyword argument:

```python
def create_capstone(
    *,
    relationship: CharacterRelationship,
    author: CharacterSheet,
    title: str,
    writeup: str,
    track: RelationshipTrack,
    invested_amount: int = 0,           # NEW — replaces points
    visibility: UpdateVisibility,
    linked_scene: Scene | None = None,
    is_ritual_capstone: bool = False,
    ritual: Ritual | None = None,
) -> RelationshipCapstone:
```

The existing `points` parameter is **removed**. Points are now derived from `invested_amount`.

Service body sketch:

```python
@transaction.atomic
def create_capstone(*, relationship, author, ..., invested_amount, ...):
    if author.id != relationship.source_id:
        raise CapstoneAuthorMismatch(...)

    if invested_amount < 0:
        raise ValidationError("invested_amount cannot be negative")

    config = get_relationship_magic_config()

    # Atomic spend with select_for_update; capstone with 0 invested is the
    # narrative-only path — recorded but no mechanical effect.
    if invested_amount > 0:
        rel = CharacterRelationship.objects.select_for_update().get(pk=relationship.pk)
        if rel.shared_time_balance < invested_amount:
            raise SharedTimeInsufficient(
                f"Need {invested_amount} Shared Time; have {rel.shared_time_balance}."
            )
        rel.shared_time_balance -= invested_amount
        rel.save(update_fields=["shared_time_balance"])

    # Derive mechanical points from invested amount.
    capstone_points = compute_capstone_points(invested_amount, config)

    capstone = RelationshipCapstone.objects.create(
        relationship=relationship,
        author=author,
        track=track,
        title=title,
        writeup=writeup,
        points=capstone_points,
        shared_time_invested=invested_amount,
        visibility=visibility,
        linked_scene=linked_scene,
        is_ritual_capstone=is_ritual_capstone,
        ritual=ritual,
    )

    if capstone_points > 0:
        # Apply mechanical effects.
        progress = _get_or_create_track_progress(relationship, track)
        old_developed = progress.developed_points
        progress.developed_points += capstone_points
        progress.capacity += capstone_points
        progress.save(update_fields=["developed_points", "capacity"])

        # Tier crossing detection (§5).
        _check_and_grant_tier_crossings(progress, old_developed)

        # Resonance grants on invested capstone (§7).
        _grant_capstone_invested_resonances(capstone)

        # Free Thread development on woven RELATIONSHIP_TRACK / _CAPSTONE
        # threads (§8).
        _grant_thread_development_on_capstone(capstone)

    return capstone
```

`compute_capstone_points(invested_amount, config)` is the conversion formula. v1 design: `floor(invested_amount × config.capstone_points_per_shared_time)` with `capstone_points_per_shared_time = 1.0` as the default knob. Future tuning can apply diminishing returns curves (e.g., square-root scaling) without changing the call shape.

**Why not allow `invested_amount > balance` and clamp?** Because narrative capstones are an explicit option (`invested_amount=0`). If a player wants to spend everything they have, they can pass `relationship.shared_time_balance` explicitly. Clamping silently would hide the trade-off.

**Why not a per-spend cap?** Per user: "this is THE moment of our lives" should be permitted. Hoarding is bounded by `config.shared_time_balance_cap` (a knob, default high; a soft ceiling above which further accruals are dropped on the floor with a logged audit row).

### 5. Tier crossing detection

`RelationshipTrackProgress` gains a new field:

```python
highest_tier_crossed = models.ForeignKey(
    RelationshipTier,
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="+",
    help_text="Highest tier whose threshold has been crossed for this track. "
              "Used to fire RELATIONSHIP_TIER_CROSSED resonance grants exactly once.",
)
```

`_check_and_grant_tier_crossings(progress, old_developed)`:

```python
def _check_and_grant_tier_crossings(progress, old_developed):
    new_developed = progress.developed_points
    if new_developed <= old_developed:
        return
    candidate_tiers = (
        progress.track.tiers.filter(point_threshold__lte=new_developed)
        .filter(point_threshold__gt=old_developed)
        .order_by("tier_number")
    )
    for tier in candidate_tiers:
        # Strict-greater-than ensures we don't re-grant if highest_tier_crossed
        # is already at or past this tier_number (e.g., someone backtracked
        # via a Change and then re-advanced).
        if (progress.highest_tier_crossed_id is None
                or tier.tier_number > progress.highest_tier_crossed.tier_number):
            _grant_tier_crossed_resonances(progress.relationship, progress.track, tier)
            progress.highest_tier_crossed = tier
    progress.save(update_fields=["highest_tier_crossed"])
```

Important: tier crossings fire from any service that increments `developed_points` — `create_capstone` (when invested) and `create_development`. `redistribute_points` (RelationshipChange) can also affect `developed_points` on both source and target tracks; it should call the same detector for the target track to fire one-time grants if a Change pushes a track over a new threshold for the first time. No grants on retreat.

### 6. Thread feedback formulas (anchor cap + pull multiplier)

#### 6.1 `compute_anchor_cap` rewrites

```python
case TargetKind.RELATIONSHIP_TRACK:
    progress = _get_track_progress(thread.owner, thread.target_relationship_track)
    return int(progress.developed_points if progress else 0)

case TargetKind.RELATIONSHIP_CAPSTONE:
    return int(thread.target_capstone.points)
```

Rationale:
- For `RELATIONSHIP_TRACK`: developed_points is the most direct depth signal. Currently the formula uses `current_tier.tier_number × 10`, which loses information between tier thresholds. Using developed_points directly is monotonically increasing with relationship depth and gives Threads exactly as much room as the relationship has earned.
- For `RELATIONSHIP_CAPSTONE`: the capstone's own `points` field (now investment-driven) is the natural cap. A Thread woven on a 50-point capstone caps at 50; a Thread woven on a narrative-only capstone (`points=0`) is locked at 0 until the capstone is later re-invested (out of scope) or the player weaves on a different capstone.

Soul Tether (Spec B) writes Sineater RELATIONSHIP_CAPSTONE Threads via `accept_soul_tether`. The new cap formula means freshly-formed Soul Tethers get Thread caps based on the formation capstone's `points`. Spec B's formation already creates a capstone via the formation ritual; this spec doesn't change Spec B but does require Spec B's formation capstone to be authored with `invested_amount > 0` (or with a staff override) to produce a non-zero Thread cap. Migration note: existing Soul Tether capstones from prior PRs will have `shared_time_invested=0`; their Thread caps reset to 0. **Documented as expected** — local dev DB is disposable, and Spec B's tests author capstones via factories which are updated to seed appropriate investment.

#### 6.2 Pull-value multiplier

`resolve_pull_effects` for `RELATIONSHIP_TRACK` and `RELATIONSHIP_CAPSTONE` Threads multiplies the resolved-effect magnitude (the post-`level_multiplier` `scaled_value`) by a relationship-strength factor:

```python
def _relationship_pull_multiplier(thread: Thread, config: RelationshipMagicConfig) -> float:
    """Scale pull-effect magnitudes by relationship strength.

    Returns 1.0 baseline plus a knob-driven contribution from underlying depth.
    """
    if thread.target_kind == TargetKind.RELATIONSHIP_TRACK:
        progress = _get_track_progress(thread.owner, thread.target_relationship_track)
        depth = progress.developed_points if progress else 0
    elif thread.target_kind == TargetKind.RELATIONSHIP_CAPSTONE:
        depth = thread.target_capstone.points
    else:
        return 1.0
    return 1.0 + (depth * config.pull_multiplier_per_depth_point)
```

Where `config.pull_multiplier_per_depth_point` is a small float (default e.g. 0.005 — 100 depth points → 1.5× multiplier; tuneable). Applied multiplicatively to FLAT_BONUS, INTENSITY_BUMP, and VITAL_BONUS payloads. NARRATIVE_ONLY and CAPABILITY_GRANT are unaffected.

A hard ceiling on the multiplier prevents runaway scaling: `config.pull_multiplier_max` (default 3.0).

### 7. Resonance grants on invested events

Three new `GainSource` values added to `world.magic.constants.GainSource`:

- `RELATIONSHIP_CAPSTONE_INVESTED` — bilateral grant when a capstone fires with `points > 0`
- `RELATIONSHIP_TIER_CROSSED` — bilateral grant on first crossing of a tier threshold
- `RELATIONSHIP_DEVELOPMENT_ECHO` — author-only grant alongside Developments where `points_earned ≥ config.development_echo_threshold`

`ResonanceGrant` gains three new typed FKs (one per source). Per existing pattern, CheckConstraints enforce that exactly the matching FK is populated for the source kind, and all others are null.

```python
source_relationship_capstone = models.ForeignKey(
    "relationships.RelationshipCapstone", on_delete=SET_NULL, null=True, related_name="+",
    help_text="Set when source=RELATIONSHIP_CAPSTONE_INVESTED."
)
source_relationship_tier_crossing = models.ForeignKey(
    "relationships.RelationshipTier", on_delete=SET_NULL, null=True, related_name="+",
    help_text="Set when source=RELATIONSHIP_TIER_CROSSED. Tier whose threshold was crossed."
)
source_relationship_development = models.ForeignKey(
    "relationships.RelationshipDevelopment", on_delete=SET_NULL, null=True, related_name="+",
    help_text="Set when source=RELATIONSHIP_DEVELOPMENT_ECHO."
)
```

#### 7.1 Which resonance is granted?

Per CharacterResonance Spec C precedent: the grant must specify exactly one Resonance per write. For relationship events, resonance selection follows this resolution order:

1. **Woven Thread on the relevant anchor.** If the recipient has a `RELATIONSHIP_TRACK` or `RELATIONSHIP_CAPSTONE` Thread woven on the relevant track/capstone, grant to that Thread's resonance. This makes Thread weaving directly steer where future relationship rewards land.
2. **Most-recently-earned `CharacterResonance`.** Fallback when no relevant Thread exists. Uses the existing `CharacterResonanceHandler.most_recently_earned` pattern.
3. **No grant.** If the recipient has no `CharacterResonance` rows at all (extremely unlikely post-CG but possible for staff test characters), skip silently with an audit log row.

Bilateral grants (capstone + tier crossing) compute resonance independently per recipient — Alice's grant might land on a different Resonance than Bob's, depending on each one's woven Threads.

#### 7.2 Amount per source

All knobs:
- `config.capstone_invested_resonance_grant` — flat amount granted to each side per invested capstone. Multiplied by `min(1.0, capstone.points / config.capstone_grant_normalization)` to scale with investment magnitude.
- `config.tier_crossed_resonance_grant_by_tier_number` — JSONField? No: dedicated lookup model `RelationshipTierResonanceGrant(tier_number → amount)` (SharedMemoryModel) so per-tier granularity is queryable and admin-editable. (No JSONField for referencing other models per project rules; numeric tier_number → amount is simple enough that a flat `(tier_number, amount)` table works.)
- `config.development_echo_threshold` — minimum `RelationshipDevelopment.points_earned` to fire an echo grant.
- `config.development_echo_amount` — flat amount granted to author when echo fires.

### 8. Free Thread development on invested capstones

When a capstone fires with `points > 0`, find the author's woven Threads matching either:
- `RELATIONSHIP_TRACK` Thread on `(thread.target_relationship_track == capstone.track)` AND `(the underlying CharacterRelationship matches, derived via the Thread's resonance + the author's persona context)` — actually simpler: the Thread's owner is the capstone author, and we filter by track only. Threads aren't tied to a specific relationship row on the model; they're tied to a track, which spans all that author's relationships on that track.
- `RELATIONSHIP_CAPSTONE` Thread on `(thread.target_capstone == capstone)`. This is the freshly-authored capstone; only Threads woven on it explicitly qualify, which means this clause only matters for *previously-authored* capstones being re-rewarded — and we don't re-reward, so this clause is **a no-op for new capstones** but covered for robustness in case the order of operations ever changes.

Practically v1: only the `RELATIONSHIP_TRACK` clause matters. Free development amount: `config.capstone_thread_dev_per_invested_point × capstone.shared_time_invested`. Capped by the Thread's `effective_cap` so we never push past the cap.

```python
def _grant_thread_development_on_capstone(capstone):
    config = get_relationship_magic_config()
    author = capstone.author  # CharacterSheet
    track_threads = author.threads.active_filter(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        target_relationship_track=capstone.track,
    )
    for thread in track_threads:
        cap = compute_effective_cap(thread)
        free_amount = capstone.shared_time_invested * config.capstone_thread_dev_per_invested_point
        room = max(0, cap - thread.developed_points)
        granted = int(min(free_amount, room))
        if granted > 0:
            thread.developed_points += granted
            # Re-derive thread.level if developed_points crossed a level threshold
            # (existing imbue logic does this — extract a helper).
            _advance_thread_level_from_developed_points(thread)
            thread.save(update_fields=["developed_points", "level"])
```

The level-advancement helper is extracted from the existing `spend_resonance_for_imbuing` flow so the same XP-lock and cap-stop semantics apply. **Important:** XP-locks at level boundaries (20, 30, 40) are NOT auto-paid by free development. If free development would push the Thread past an unpaid XP-lock boundary, it caps at the boundary and the player must still pay XP to cross. This preserves the XP economy.

### 9. `RelationshipMagicConfig` singleton

```python
class RelationshipMagicConfig(SharedMemoryModel):
    """Singleton (pk=1). All knobs for relationship-driven Thread growth."""

    # Earning rates
    scene_grant_per_pair = models.PositiveIntegerField(default=2)
    scene_grant_daily_cap_per_pair = models.PositiveIntegerField(default=10)
    development_grant_amount = models.PositiveIntegerField(default=15)
    episode_grant_per_pair = models.PositiveIntegerField(default=8)
    combat_grant_per_pair = models.PositiveIntegerField(default=5)

    # Capstone investment
    capstone_points_per_shared_time = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("1.000"))
    shared_time_balance_cap = models.PositiveIntegerField(default=10000)

    # Resonance grants on relationship events
    capstone_invested_resonance_grant = models.PositiveIntegerField(default=4)
    capstone_grant_normalization = models.PositiveIntegerField(default=20)
    development_echo_threshold = models.PositiveIntegerField(default=10)
    development_echo_amount = models.PositiveIntegerField(default=2)

    # Thread feedback
    pull_multiplier_per_depth_point = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0050"))
    pull_multiplier_max = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("3.00"))
    capstone_thread_dev_per_invested_point = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00"))

    # Tier-crossing grants by tier_number lookup
    # (separate table — see RelationshipTierResonanceGrant)

    @classmethod
    def get_singleton(cls) -> "RelationshipMagicConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

Lives in `src/world/relationships/models/config.py` (new submodule).

Lookup table for tier-crossing grants:

```python
class RelationshipTierResonanceGrant(SharedMemoryModel):
    """Per-tier-number resonance grant amount. Look up by tier_number, not FK."""
    tier_number = models.PositiveIntegerField(unique=True)
    amount = models.PositiveIntegerField()
```

Seeded via factory with sensible defaults (tier 1 → 2, tier 2 → 4, tier 3 → 8, tier 4 → 16, tier 5+ → 25 or wherever the curve plateaus). Admin-editable.

### 10. API endpoints

Minimal new surface — most of the system is internal. Two API touchpoints:

#### 10.1 Modify capstone authoring endpoint

If a `POST /api/relationships/<id>/capstones/` endpoint exists today (verify), extend the request serializer to accept `invested_amount: int` (default 0). Remove `points` from the request — clients shouldn't set it directly anymore. Add `@extend_schema` for the new request/response shape. Serializer-level validation catches negative invested_amount and `SharedTimeInsufficient` — both surfaced as 400 with `user_message`.

If no capstone-authoring endpoint exists yet, create one in this PR: `POST /api/relationships/<relationship_id>/capstones/` with serializer-level validation and `@extend_schema`. (This is the most likely state — capstones may today only be staff-authored or admin-only. **Verify during implementation.**)

#### 10.2 `SharedTimeGrant` read-only ViewSet

`SharedTimeGrantViewSet` — read-only, user-scoped. Exposes the audit ledger so future UI can show "your Shared Time history with X." Filter by relationship, source, date range via FilterSet. Pagination + `IsAuthenticated`. Staff bypass for audit.

URL: `GET /api/relationships/shared-time-grants/`.

### 11. Permissions

- Capstone authoring: requires `request.user.account == relationship.source.account` (the author owns the source side of the directional relationship). Existing alt-guard helper `_resolve_actor_sheet` (or equivalent) handles multi-tenure cases.
- `SharedTimeGrantViewSet`: read-only, scoped to grants where the relationship's source character belongs to the user.
- Admin staff_grant: Django admin only.

### 12. Error handling

All new typed exceptions in `src/world/relationships/exceptions.py` (new file) or `src/world/magic/exceptions.py` if magic-side:

- `SharedTimeInsufficient(amount, balance)` — capstone investment exceeds balance.
- `CapstoneAuthorMismatch` — the author is not the source character of the relationship row.
- `RelationshipMagicConfigMissing` — singleton not initialized; `get_singleton()` makes this practically impossible but raises a typed exception for unit-test edge cases rather than silently failing.

Each carries a `user_message` and is in the `SAFE_MESSAGES` allowlist per project pattern. Views map to HTTP 400 via serializer-level validation; no view-level `try/except`.

### 13. Testing

#### Backend unit tests

- `world/relationships/tests/test_shared_time.py`
  - `grant_shared_time` happy paths per source (5 sources)
  - Daily cap enforcement on `SHARED_SCENE`
  - Balance cap enforcement
  - Bilateral vs author-only grant logic
  - CheckConstraints enforce typed-FK shape per source
  - `RelationshipMagicConfig` singleton lazy-create
- `world/relationships/tests/test_capstone_investment.py`
  - Capstone with `invested_amount=0` — narrative only, no points, no kickbacks
  - Capstone with `invested_amount > 0` — points derived, balance debited, audit row written
  - `SharedTimeInsufficient` raised when invested > balance
  - Re-running `create_capstone` twice atomically (no double-debit on race)
- `world/relationships/tests/test_tier_crossing.py`
  - Tier crossing fires `RELATIONSHIP_TIER_CROSSED` on first crossing only
  - Multi-tier-jump crossings fire grants for each tier passed
  - Backtracking via Change and re-crossing does not re-fire
  - `highest_tier_crossed` updated correctly
- `world/relationships/tests/test_development_echo.py`
  - Echo fires when `points_earned >= threshold`
  - Echo does not fire below threshold
  - Author-only grant; target gets nothing
- `world/magic/tests/test_relationship_thread_feedback.py`
  - `compute_anchor_cap` for `RELATIONSHIP_TRACK` reflects `developed_points`
  - `compute_anchor_cap` for `RELATIONSHIP_CAPSTONE` reflects `target_capstone.points`
  - Pull multiplier scales correctly with depth, capped at `pull_multiplier_max`
  - Free Thread development on capstone respects effective_cap and XP-locks
- `world/magic/tests/test_relationship_resonance_grants.py`
  - `RELATIONSHIP_CAPSTONE_INVESTED` resonance grant — bilateral, per-resonance resolution
  - `RELATIONSHIP_TIER_CROSSED` resonance grant — bilateral, per-tier amount lookup
  - `RELATIONSHIP_DEVELOPMENT_ECHO` resonance grant — author-only
  - Resonance resolution: woven thread first, most-recently-earned fallback, silent skip when no resonances
- API tests:
  - Capstone authoring endpoint accepts `invested_amount`, validates, returns 400 on insufficient balance, 200 on success
  - `SharedTimeGrantViewSet` paginated, filterable, scoped to user

#### Integration tests

`src/integration_tests/pipeline/test_relationship_thread_growth.py` — end-to-end pipeline:

1. Set up two characters with a mutual relationship and woven `RELATIONSHIP_TRACK` Threads on a track.
2. Run a series of co-activities (close 3 scenes, author 2 developments, complete 1 episode, end 1 combat encounter).
3. Assert Shared Time accruals on both directions match expected sums (with knob math).
4. Assert daily cap enforcement on consecutive same-day scenes.
5. Author capstone with `invested_amount = current_balance / 2`.
6. Assert balance debited, capstone.points derived correctly, Thread free development fired, resonance grant landed on the woven Thread's resonance, tier crossing detected and resonance-granted on first crossing.
7. Pull on the Thread; assert pull multiplier reflects the new developed_points.
8. Author second capstone with `invested_amount=0`; assert narrative-only path (no debit, no kickbacks).

#### Factory updates

- `SharedTimeGrantFactory`
- `RelationshipMagicConfigFactory` (default knobs)
- `RelationshipTierResonanceGrantFactory` (one per default tier)
- `wire_relationship_magic_content()` — orchestrator factory that ensures config + tier grants are seeded.
- `RelationshipCapstoneFactory.shared_time_invested` parameter wired through.
- Soul Tether factories updated to author formation capstones with non-zero `invested_amount` so existing Spec B tests don't break.

#### No E2E / no UI tests

Per scope: no UI in this PR. E2E deferred to a future UI PR.

## Architecture

```
EARN side (per-pair Shared Time)
─────────────────────────────────────────────────────────────────
  Scene close hook ────┐
  Story close hook ────┤    grant_shared_time(
  Combat close hook ───┼─→     relationship=A→B,
  Development service ─┤       amount=X,
  Staff admin ─────────┘       source=<source>,
                                **typed_fk_kwargs)
                              │
                              ▼
                        CharacterRelationship
                          .shared_time_balance ↑
                          .shared_time_lifetime ↑
                        + SharedTimeGrant audit row

SPEND side (capstone investment)
─────────────────────────────────────────────────────────────────
  POST /api/relationships/<id>/capstones/
   { track, title, writeup, invested_amount=N, ... }
                              │
                              ▼
  create_capstone(invested_amount=N)
   → spend N from CharacterRelationship.shared_time_balance
   → capstone.points = compute_capstone_points(N, config)
   → capstone.shared_time_invested = N
   → if points > 0:
      → progress.developed_points += points  (and capacity)
      → check_and_grant_tier_crossings()  # §5
      → grant_capstone_invested_resonances()  # §7
      → grant_thread_development_on_capstone()  # §8
   → if points == 0: narrative-only, no kickbacks

THREAD FEEDBACK (read-only — Thread power scales with relationship)
─────────────────────────────────────────────────────────────────
  compute_anchor_cap(thread):
    RELATIONSHIP_TRACK    → developed_points on the track
    RELATIONSHIP_CAPSTONE → target_capstone.points

  resolve_pull_effects(thread, ...):
    RELATIONSHIP_*  → magnitude × (1.0 + depth × pull_multiplier_per_depth_point)
                    → capped at pull_multiplier_max

TIER CROSSING (separate from capstone — bilateral)
─────────────────────────────────────────────────────────────────
  Triggered from any service that increments developed_points.
  When developed_points crosses RelationshipTier.point_threshold for the
  first time on this track:
    → grant_resonance(both directions, RELATIONSHIP_TIER_CROSSED)
    → progress.highest_tier_crossed = tier

DEVELOPMENT ECHO (author-only — flat, threshold-gated)
─────────────────────────────────────────────────────────────────
  In create_development:
    → if points_earned >= config.development_echo_threshold:
       → grant_resonance(author only, RELATIONSHIP_DEVELOPMENT_ECHO)
```

## Components Inventory

### Backend

#### New models
- `world/relationships/models/shared_time.py`:
  - `SharedTimeGrant` — typed-FK ledger
  - `SharedTimeSource` TextChoices — moved or duplicated to `world/relationships/constants.py`
- `world/relationships/models/config.py`:
  - `RelationshipMagicConfig` (singleton)
  - `RelationshipTierResonanceGrant` (per-tier-number lookup)

#### New fields on existing models
- `CharacterRelationship.shared_time_balance` (`PositiveIntegerField`, default 0)
- `CharacterRelationship.shared_time_lifetime` (`PositiveIntegerField`, default 0)
- `RelationshipTrackProgress.highest_tier_crossed` (FK to `RelationshipTier`, nullable)
- `RelationshipCapstone.shared_time_invested` (`PositiveIntegerField`, default 0)

#### Modified models / fields
- `RelationshipCapstone.points` — semantics change (still field, still set, now derived from `shared_time_invested`). Existing code-paths that read `.points` are unaffected; only the *write* path (`create_capstone`) changes.

#### New `GainSource` values + typed FKs on `ResonanceGrant`
- `RELATIONSHIP_CAPSTONE_INVESTED` + `source_relationship_capstone`
- `RELATIONSHIP_TIER_CROSSED` + `source_relationship_tier_crossing`
- `RELATIONSHIP_DEVELOPMENT_ECHO` + `source_relationship_development`
- New CheckConstraints per source.

#### New services
- `world/relationships/services.py` (extended) or new submodule:
  - `grant_shared_time(*, relationship, amount, source, **typed_fk_kwargs)` — atomic write to balance + lifetime + audit row, with cap enforcement and per-source-typed-FK validation
  - `_grant_capstone_invested_resonances(capstone)` — bilateral fan-out
  - `_grant_tier_crossed_resonances(relationship, track, tier)` — bilateral fan-out using lookup table
  - `_grant_development_echo_resonance(development)` — author-only
  - `_check_and_grant_tier_crossings(progress, old_developed)` — detector
  - `_grant_thread_development_on_capstone(capstone)` — Thread free-dev
  - `_advance_thread_level_from_developed_points(thread)` — extracted helper from existing imbue logic
  - `compute_capstone_points(invested_amount, config) -> int` — formula
  - `_resolve_resonance_for_relationship_grant(sheet, target_kind, target) -> Resonance | None` — woven-thread → most-recently-earned fallback chain
  - `get_relationship_magic_config() -> RelationshipMagicConfig`

#### Modified services
- `world/relationships/services.py`:
  - `create_capstone` — signature change (`invested_amount` replaces `points`), full body refactor per §4
  - `create_development` — adds Shared Time grant + tier-crossing detection + echo-resonance grant
  - `redistribute_points` — adds tier-crossing detection on the target track
- `world/magic/services/threads.py`:
  - `compute_anchor_cap` — rewritten arms for `RELATIONSHIP_TRACK` and `RELATIONSHIP_CAPSTONE`
- `world/magic/services/resonance.py`:
  - `resolve_pull_effects` — adds `_relationship_pull_multiplier` application for RELATIONSHIP_* threads

#### New hooks
- Scene close service — verify or add hook calling `grant_shared_time` for each pair
- Story episode close service — same
- Combat encounter resolution service — same

#### New typed exceptions
- `world/relationships/exceptions.py` (new file):
  - `SharedTimeError` (base)
  - `SharedTimeInsufficient`
  - `CapstoneAuthorMismatch`
  - `RelationshipMagicConfigMissing`

All inherit from a base with `user_message` + `SAFE_MESSAGES` per project pattern.

#### New serializers
- `world/relationships/serializers.py`:
  - `RelationshipCapstoneCreateSerializer` — accepts `invested_amount`, `track`, `title`, `writeup`, `visibility`, `linked_scene` (optional), `is_ritual_capstone` (default False), `ritual` (optional). `validate()` resolves `relationship`, calls `create_capstone`, surfaces typed exceptions as `serializers.ValidationError` with `user_message`.
  - `SharedTimeGrantSerializer` — read-only audit row.

#### New views
- `world/relationships/views.py`:
  - `RelationshipCapstoneCreateView` (or extension to existing) — POST endpoint. `@extend_schema` on the new request/response shapes.
  - `SharedTimeGrantViewSet` — read-only ViewSet with FilterSet, pagination, IsAuthenticated.

#### New URLs
```python
path("relationships/<int:relationship_id>/capstones/", RelationshipCapstoneCreateView.as_view(), name="relationship-capstone-create"),
# SharedTimeGrantViewSet via DRF router
```

#### Migrations
- One migration adds: new fields on `CharacterRelationship`, `RelationshipTrackProgress`, `RelationshipCapstone`; new models `SharedTimeGrant`, `RelationshipMagicConfig`, `RelationshipTierResonanceGrant`; new `GainSource` choices on `ResonanceGrant` + new FKs + new CheckConstraints.

### Frontend

**None.** Per scope: no UI in this PR.

## Data Flow Examples

### Earning Shared Time from a closed scene

1. `world.scenes.services.close_scene(scene)` runs after final pose / participant sign-off.
2. Hook iterates all unique unordered pairs `{A, B}` of active `SceneParticipation` characters.
3. For each pair, hook calls (twice — once per direction):
   ```python
   grant_shared_time(
       relationship=CharacterRelationship.objects.get(source=A, target=B),
       amount=config.scene_grant_per_pair,
       source=SharedTimeSource.SHARED_SCENE,
       source_scene=scene,
   )
   ```
4. Service checks daily cap by querying `SharedTimeGrant.objects.filter(relationship=..., source=SHARED_SCENE, granted_at__date=today).aggregate(Sum("amount"))`. If amount + existing > daily_cap, clamp.
5. Writes balance/lifetime increments and audit row in one transaction.

### Spending Shared Time on a capstone

1. Player POSTs `/api/relationships/<id>/capstones/` with `invested_amount=30, track=Trust, title="..."`.
2. Serializer validates auth + relationship ownership + invested_amount ≥ 0.
3. Calls `create_capstone(...)`.
4. Service: `select_for_update` on relationship, debits balance, computes `capstone_points = floor(30 × 1.0) = 30`, creates `RelationshipCapstone(points=30, shared_time_invested=30)`.
5. Increments `progress.developed_points` and `progress.capacity` by 30.
6. Detects tier crossings: if developed_points crossed `point_threshold=50` (first time), fires `RELATIONSHIP_TIER_CROSSED` resonance grant bilaterally.
7. Fires `RELATIONSHIP_CAPSTONE_INVESTED` resonance grant bilaterally.
8. Finds author's `RELATIONSHIP_TRACK` Thread on Trust; grants `30 × 1.0 = 30` developed_points (capped by effective_cap, level-advanced via helper).
9. Returns capstone via response serializer.

### Thread pull on a relationship-anchored Thread

1. `spend_resonance_for_pull(...)` is invoked per existing flow.
2. `resolve_pull_effects` looks up the matching `ThreadPullEffect` rows.
3. For each effect, the magnitude is computed as before, then for `RELATIONSHIP_*` Threads multiplied by `_relationship_pull_multiplier(thread, config)`.
4. Resolved effect magnitudes ride through to `CombatPullResolvedEffect` (combat path) or the runtime modifier registry (ephemeral path) with the multiplied values.

## Migration / Rollout

- **Single migration** introduces all new fields, models, GainSource values, FKs, and CheckConstraints.
- **Default values** ensure existing rows are valid: balances default to 0, `highest_tier_crossed` is nullable, `shared_time_invested` defaults to 0.
- **No data migration.** Existing capstones keep their current `points` values (legacy authored without investment); they simply have `shared_time_invested=0`. They were authored under the old free-points model and remain valid mechanically.
- **Existing Soul Tether (Spec B) capstones** authored with the old `points` parameter retain their points but have `shared_time_invested=0`. Their RELATIONSHIP_CAPSTONE Threads' anchor caps will now read from `target_capstone.points` (which is non-zero from legacy authoring), so they continue to work.
- **Soul Tether factories updated** to pass appropriate `invested_amount` when authoring formation capstones in tests, ensuring the new code paths see realistic data.
- **Local dev DB** is disposable per project memory; no data migration risks.
- **CI fresh-DB tests** cover the new shape.
- **No feature flag.** Backend system; player-visible effects start accruing on PR merge.

## Out of Scope / Follow-ups

- **UI surfaces** — Hub display of Shared Time balance per relationship, capstone authoring UI with invested_amount slider, ledger viewer.
- **Mission-system hook** — wire `grant_shared_time(..., source=MISSION_COMPLETION)` when missions ship.
- **AP-spend tagging** — generic mechanism to attribute AP spends to relationship targets (separate from this spec; invoked when AP system grows that capability).
- **Anchor-pickers cleanup (Task B from originating prompt)** — wire TRAIT/TECHNIQUE/ROOM/RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE pickers in WeaveDesigner. Separate small PR.
- **Rename `WeaveThreadWizard` → `WeaveDesigner`** — naming hygiene; bundle with anchor pickers PR.
- **Diminishing-returns curve on capstone_points formula** — v1 ships linear; tuneable post-launch by changing `compute_capstone_points` body without schema change.
- **Per-relationship Shared Time decay** — anti-shelf mechanic. Not in v1; add only if hoarding becomes a problem.
- **Pull-multiplier weighting differs per effect_kind** — v1 multiplies all of FLAT_BONUS/INTENSITY_BUMP/VITAL_BONUS uniformly. If specific effect kinds should scale differently with relationship depth, that's a v2 tuning pass.
- **Tier-crossing kickback to Threads** — currently no Thread free-dev fires on tier crossings (only on invested capstones). Adding that is a knob away.
- **Activity intensity weighting** — `scene_intensity_multiplier` is a flat 1.0 in v1. Per-scene metadata weighting (1:1 vs group, AP cost, action types) is a follow-up.
