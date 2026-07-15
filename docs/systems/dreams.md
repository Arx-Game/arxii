# Dreams System

The dream realm — a parallel layer on the physical room graph where sleeping and unconscious characters perceive dream spaces, interact with other dreamers, face dream-specific danger, and dreamwalk to bonded dreamers across physical distance.

**Source:** `src/world/dreams/`

---

## Architecture

Three layers of dream space:

1. **Dream reflections** — each physical room can have an optional dream reflection (a real ObjectDB room). Dreamers in the same physical room share a dreamspace.
2. **Dreamwalking** — thread-gated traversal between dreamspaces, letting bonded characters bridge physical distance.
3. **Deep dreaming** — a PLANE-level Area with its own rooms and exits, entered via descents in dream reflections. Getting lost here is lethal.

## Entry: Sleeping Condition

The `Sleeping` ConditionTemplate (`world/vitals/seeds.py`) mirrors `Unconscious` — same capability-zeroing (awareness, movement, limb_use → 0) — but is voluntarily applied by `SleepAction` (key `"sleep"`). No guaranteed-wake deadline; the character wakes when they choose via `wake`, unless dream-engaged.

`perceives_dreamside()` (`world/vitals/services.py`) returns True for Sleeping OR Unconscious characters. The dead never dreamside (ghosts watch the waking room).

`get_dream_space(room)` (`world/dreams/services.py`) returns the dream room (ObjectDB) for a physical room — the DreamReflection's dream_room if one exists, or the liminal placeholder room (#2287) as fallback.

## Danger: Mental Fatigue + Dream Peril Pool

Dream damage accrues as **mental fatigue** (the existing `FatiguePool.mental_current`). Dream-specific damage types (Nightmare, Dread, Confusion) feed into this pool. When mental fatigue collapses (OVEREXERTED/EXHAUSTED), the collapse branches to `resolve_dream_peril_collapse()` (`world/dreams/peril.py`) instead of the standard exhaustion damage path.

The Dream Peril consequence pool has four outcomes:
- **Wake shaken** — recover, mental fatigue partially resets
- **Nightmares** — persistent debuff condition (treatable)
- **Madness** — severe persistent condition (behavior-altering, `alters_behavior=True`)
- **Death** — physical death (PC-source gated per ADR-0023; only environmental/deep-dreaming hazards can kill)

`DreamPerilConfig` singleton (pk=1) stores the resist check type (stability-based) and difficulty.

## Dreamwalking

`DreamwalkAction` (key `"dreamwalk"`) — requires Sleeping/Unconscious (must be dreamside). Gated by:
- RELATIONSHIP_TRACK or RELATIONSHIP_CAPSTONE thread to the target
- Soul Tether bond (`CharacterRelationship.is_soul_tether=True`)
- Same-room sleepers share a dreamspace automatically (no dreamwalk needed)

**Escape lever**: dreamwalk destination stored on `actor.ndb.dreamwalk_destination`. When the dreamwalker wakes, `WakeAction` moves their body to the destination room — an escape from physical confinement.

## Deep Dreaming

A PLANE-level Area ("The Deep Dreaming") with its own rooms and exits. Entered via `DescendAction` (key `"descend"`) from a dream reflection with a `descent_target`. Returns via `AscendAction` (key `"ascend"`).

Deep dreaming uses real ObjectDB movement — standard exit traversal, scene rounds, and combat all work. Environmental hazards deal dream damage (mental fatigue). Getting lost means navigating the room graph to find an exit back to a dream reflection.

## Seed Content

`ensure_dream_content()` (`world/dreams/seeds.py`) seeds:
- Sleeping ConditionTemplate
- Nightmares + Madness ConditionTemplates
- DreamPerilConfig singleton
- Dream Peril consequence pool
- Dream damage types (Nightmare, Dread, Confusion)
- Deep dreaming Area + starter room

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DreamReflection` | Links a physical room to its dream-layer reflection | `waking_room` (OneToOne ObjectDB), `dream_room` (OneToOne ObjectDB), `descent_target` (nullable FK ObjectDB), `is_active` |
| `DreamPerilConfig` | Singleton config for Dream Peril resist check | `resist_check_type` (FK CheckType), `resist_difficulty` (PositiveInt) |

## Actions

| Action | Key | Purpose |
|--------|-----|---------|
| `SleepAction` | `sleep` | Apply Sleeping condition (voluntary dream entry) |
| `WakeAction` | `wake` | Wake from Sleeping (voluntary) or Unconscious (#2287 wake arc). Escape lever moves body to dreamwalk destination. |
| `DreamwalkAction` | `dreamwalk` | Thread-gated travel to bonded dreamer's dreamspace |
| `DescendAction` | `descend` | Descend from dream reflection into deep dreaming |
| `AscendAction` | `ascend` | Return from deep dreaming to dream reflection |

## Integration Points

- **Vitals (#2287)**: extends `perceives_dreamside()` and `get_dream_room()` → `get_dream_space()`
- **Fatigue**: mental fatigue collapse branches to Dream Peril pool
- **Magic/Threads**: dreamwalking gated by RELATIONSHIP_TRACK/CAPSTONE threads
- **Soul Tether**: bonded pairs can always find each other in dreams
- **Conditions**: Nightmare/Madness conditions applied by Dream Peril pool outcomes
- **Consequence Pools**: Dream Peril pool follows the ADR-0049 guarded mortality pattern
