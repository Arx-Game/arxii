# Thread Anchor Cap Fixes for Relationship-Anchored Threads

**Date:** 2026-05-09
**Status:** Approved (autonomous-mode design conversation; scope refined after investigating existing relationship primitives)
**Branch:** `relationship-driven-thread-growth`
**Related:**
- `docs/architecture/resonance-threads.md` — Spec A (Threads + Currency); origin of the anchor_cap formulas
- `docs/architecture/soul-tether.md` — Spec B (Soul Tether); existing consumer of `RELATIONSHIP_CAPSTONE` Threads
- `src/world/magic/services/threads.py:97-145` — `compute_anchor_cap` (the function we're modifying)
- `src/world/relationships/models.py` — `RelationshipTrackProgress`, `RelationshipCapstone`

---

## Goal

Two formula fixes on `compute_anchor_cap` so Thread strength on relationship-anchored Threads is genuinely downstream of relationship depth.

## Background

The current `compute_anchor_cap` arms for `RELATIONSHIP_TRACK` and `RELATIONSHIP_CAPSTONE` Threads are stubs that don't reflect the underlying relationship state:

```python
case TargetKind.RELATIONSHIP_TRACK:
    tier = thread.target_relationship_track.current_tier
    tier_number = tier.tier_number if tier is not None else 0
    return int(tier_number * 10)
case TargetKind.RELATIONSHIP_CAPSTONE:
    stage = _current_path_stage(thread.owner)
    return int(stage * 10)
```

- `RELATIONSHIP_TRACK` works but is piecewise — every developed_point under the next tier threshold yields zero anchor-cap progress.
- `RELATIONSHIP_CAPSTONE` is a placeholder copy of the path-cap formula that ignores the underlying capstone entirely. A Thread woven on a 50-point capstone gets the same anchor cap as a Thread woven on a 1-point capstone.

## Architecture decision

**The relationship system owns relationship state. Magic reads it via anchor caps; magic does not modify it.**

The magic system observes relationship state via Thread anchor caps. It does NOT introduce new gain surfaces, currencies, rate limits, or capstone gates. Relationship-side anti-spam mechanisms (if needed later) belong in the relationship system, not the thread system.

This rules out several things considered during brainstorming:

- A new "Shared Time" currency — relationship system already has Updates/Developments/Capstones as its growth model; we don't reinvent it
- Activity-driven auto-Updates from scenes/episodes/combat — relationship system owns when relationships grow
- Capstone gating via accumulated investment — capstones are explicitly unlimited per existing service intent ("Capstones are always allowed (unlimited). They represent monumental moments and are never gated.")
- Resonance grants on relationship events — Spec C already grants resonance for general RP via endorsements, scene entries, residence trickle, outfit trickle
- A separate pull-effect-magnitude multiplier from relationship depth — redundant with the existing `Thread.level → level_multiplier` chain, which already scales effects with Thread depth (which is itself downstream of relationship depth via the fixed anchor_cap)

The natural chain after the fix:

```
relationship depth (developed_points or capstone.points)
  → anchor_cap (this PR)
  → Thread.level cap = min(anchor_cap, path_cap)  (existing)
  → level_multiplier on effects (existing in CombatPullResolvedEffect)
  → effect magnitudes
```

`path_cap = max(stage, 1) × 10` remains the ultimate ceiling on Thread.level — staff-gated via path progression. For a path-stage-5 character, max Thread level = 50 regardless of relationship depth. Anchor_cap binds for relationships that haven't yet exceeded the character's magical maturity. The two caps create dual incentive: grow your relationship AND grow your path.

The mechanical progression of Threads — developed_points growth, level advancement, XP-locked boundaries, pull-effect magnitudes — remains entirely resonance-and-XP driven via the existing Imbuing pipeline. This PR does not add or modify any of that.

## In scope

1. **`compute_anchor_cap` for `RELATIONSHIP_TRACK`** — replace with `int(thread.target_relationship_track.developed_points)`.

   `target_relationship_track` is a FK to `RelationshipTrackProgress` (per `world/magic/models/threads.py:354-360`), which has `developed_points` as a direct field. No helper resolution needed; the Thread already points at the per-relationship progress row.

2. **`compute_anchor_cap` for `RELATIONSHIP_CAPSTONE`** — replace with `int(thread.target_capstone.points)`.

   The capstone's own `points` field is the natural cap signal. A Thread woven on a 50-point capstone caps at 50; a Thread woven on a 1-point capstone caps at 1. `path_cap` remains the absolute ceiling.

3. **Docstring update** — refresh the `compute_anchor_cap` docstring's `RELATIONSHIP_TRACK` and `RELATIONSHIP_CAPSTONE` lines to reflect the new formulas.

4. **Tests** — factory-driven coverage:
   - `RELATIONSHIP_TRACK`: anchor_cap reflects `developed_points` monotonically. Cases at 0, 5, 50, 500 verify continuous growth (not piecewise).
   - `RELATIONSHIP_CAPSTONE`: anchor_cap reflects `target_capstone.points`. Cases at 0, 5, 50, 500.
   - Edge cases: anchor_cap=0 when underlying value is 0.
   - Integration: existing Spec B Soul Tether tests continue to pass — formation capstones author non-zero `points` already, so `RELATIONSHIP_CAPSTONE` Threads keep working.

## Out of scope (explicit deferrals)

- **Auto-Updates from activity** — separate spec when scope demands it; not this PR.
- **Shared Time currency / new earning surfaces** — explored and rejected; relationship system already covers growth via Updates/Developments/Capstones.
- **Pull-effect magnitude multiplier on relationship depth** — redundant with `level_multiplier`; not added.
- **Capstone authoring changes / size gating** — capstones stay free per existing intent.
- **Resonance grants on tier crossings, capstone authoring, development echo** — relationship system owns its own rewards; Spec C handles general RP grants. Not this PR.
- **`RelationshipMagicConfig` knob model** — no knobs needed for two formula fixes.
- **UI of any kind** — backend formula changes only.
- **Anchor-pickers cleanup (originating prompt's Task B)** — separate small PR.
- **`WeaveThreadWizard` → `WeaveDesigner` rename** — separate small PR.
- **Anti-relationship-spam controls (capstone abuse, capacity inflation)** — relationship-system concern, not magic's concern.
- **`MAX_DEVELOPMENTS_PER_WEEK` per-character vs per-relationship inconsistency** — pre-existing relationship-system bug noticed during investigation; flag for relationship-system follow-up.
- **Vestigial `changes_this_week` field on `CharacterRelationship`** — never enforced; cleanup belongs in relationship system if at all.

## Migration / Rollout

- No model changes; no migration.
- Behavior change: Thread anchor caps on relationship-anchored Threads adjust based on actual relationship state. Existing Threads in the dev DB will see their `effective_cap` shift — usually upward for `RELATIONSHIP_CAPSTONE` Threads (since the old formula ignored the capstone) and either way for `RELATIONSHIP_TRACK` Threads (continuous instead of piecewise). Local dev DB is disposable; no data migration required.
- Existing Spec B Soul Tether formation capstones already author non-zero `points` — Sineater `RELATIONSHIP_CAPSTONE` Threads continue to work under the new formula and now correctly reflect formation capstone significance.

## Components

**Modified file (one):**
- `src/world/magic/services/threads.py` — two case arms in `compute_anchor_cap` plus docstring refresh.

**New tests:**
- `src/world/magic/tests/test_thread_anchor_cap.py` (or extension to existing test file) — coverage per §4.

**No new models, no new services, no new endpoints, no new exceptions, no new migrations, no new factories.**

That's the entire surface.

## Verification

- `arx test world.magic` passes (existing thread tests + new anchor_cap cases).
- `arx test world.magic world.relationships flows` passes (downstream consumers still work).
- Full `just regression` clean before merge per project policy.
- No `--keepdb` for the final pre-push run.
