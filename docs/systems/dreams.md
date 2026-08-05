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

`get_dream_space(room)` (`world/dreams/services.py`) takes the waking room's ObjectDB and returns the dream room's **`ObjectDB`** — the DreamReflection's dream_room if one exists (dereferenced via `.objectdb`, since #2608 retargeted `DreamReflection.dream_room` onto `RoomProfile`), or the liminal placeholder room (#2287) as fallback. It stays the room-level primitive — "what is this room's dreamspace" — and is the one thing `dreamspace_for()` below delegates to.

`dreamspace_for(sheet)` (`world/dreams/services.py`, #3003) is the character-level resolution point — "whose dreamspace does this character perceive" — layered on top of `get_dream_space()`. It honours an active `DreamwalkPresence` row: a dreamwalking sheet perceives its host's dreamspace (following the host if the host moves) rather than its own room's, falling back to its own room when there is no active dreamwalk or the host is no longer dreamside. `co_dreamers_for(sheet)` lists the other dreamside sheets sharing that resolution (the host plus any other visitors) with a single bulk query, never a query per candidate. Every viewer-facing caller — `LookAction`'s dreamside look-at-room branch, `Character.send_room_state()`'s web push, and `is_dream_engaged()`'s wake-danger gate — routes through `dreamspace_for()` so telnet and web never disagree; `DreamwalkAction`/`WakeAction` write/read the anchor via `start_dreamwalk`/`end_dreamwalk`. `has_dream_bond(source_sheet, target_sheet)` checks the RELATIONSHIP_TRACK/CAPSTONE-thread-or-soul-tether gate `DreamwalkAction` requires; `dreamwalk_candidates_for(sheet)` (#3003) lists everyone `sheet` could dreamwalk to right now — narrows to currently-dreaming sheets with one bulk query, then applies `has_dream_bond` per remaining candidate — feeding the web dreamwalk-target picker.

## Danger: Mental Fatigue + Dream Peril Pool

Dream damage accrues as **mental fatigue** (the existing `FatiguePool.mental_current`). Dream-specific damage types (Nightmare, Dread, Confusion) feed into this pool. When mental fatigue collapses (OVEREXERTED/EXHAUSTED), the collapse branches to `resolve_dream_peril_collapse()` (`world/dreams/peril.py`) instead of the standard exhaustion damage path.

The Dream Peril consequence pool has four outcomes:
- **Wake shaken** — recover, mental fatigue partially resets
- **Nightmares** — persistent debuff condition (treatable)
- **Madness** — severe persistent condition (behavior-altering, `alters_behavior=True`)
- **Death** — physical death (PC-source gated per ADR-0023; only environmental/deep-dreaming hazards can kill)

`DreamPerilConfig` singleton (pk=1) stores the resist check type (stability-based) and difficulty.

`resolve_dream_peril_collapse()` returns a `DreamPerilResult` carrying a player-facing `message` alongside `died`/`outcome_label`; its caller in `resolve_fatigue_collapse()` (`world/fatigue/services.py`) sends it straight to the character via `character.msg(result.message)`, so the outcome — waking shaken, nightmares, madness, or death — is narrated to the player in the moment, not just recorded as a condition/state change discovered after the fact.

## Dreamwalking

`DreamwalkAction` (key `"dreamwalk"`) — requires Sleeping/Unconscious (must be dreamside). Gated by:
- RELATIONSHIP_TRACK or RELATIONSHIP_CAPSTONE thread to the target
- Soul Tether bond (`CharacterRelationship.is_soul_tether=True`)
- Same-room sleepers share a dreamspace automatically (no dreamwalk needed)

`DreamwalkAction` anchors the walker via `start_dreamwalk(dreamer=sheet, host=target_sheet)` — a persisted `DreamwalkPresence` row (#3003; see ADR-0198), replacing the earlier process-local `actor.ndb.dreamwalk_destination` stash. That row does more than back the escape lever: for as long as it exists, every viewer-facing perception call (`look`, the web room-state push, the wake-danger gate) routes through `dreamspace_for()` and resolves to the host's dreamspace instead of the walker's own room, so the walker actually experiences the host's dream — shares the same co-dreamer list (`co_dreamers_for`), sees the same peril, and follows the host if the host's physical body moves while the walk is active.

**Escape lever**: when the dreamwalker wakes, `WakeAction` calls `end_dreamwalk(sheet)` to pop the row and moves their body to the host's *current* location (resolved fresh at wake time, not the location stored at dreamwalk-start) — an escape from physical confinement.

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
| `DreamReflection` | Links a physical room to its dream-layer reflection | `waking_room` (OneToOne `RoomProfile`), `dream_room` (OneToOne `RoomProfile`), `descent_target` (nullable FK `RoomProfile`), `is_active` — all three retargeted off ObjectDB in #2608 |
| `DreamPerilConfig` | Singleton config for Dream Peril resist check | `resist_check_type` (FK CheckType), `resist_difficulty` (PositiveInt) |
| `DreamwalkPresence` | Persisted dreamwalk anchor (#3003) — replaces the process-local `ndb.dreamwalk_destination` stash | `dreamer` (OneToOne `CharacterSheet`), `host` (FK `CharacterSheet`, `related_name="dream_visitors"`), `created_at` |

## Actions

| Action | Key | Purpose |
|--------|-----|---------|
| `SleepAction` | `sleep` | Apply Sleeping condition (voluntary dream entry) |
| `WakeAction` | `wake` | Wake from Sleeping (voluntary) or Unconscious (#2287 wake arc). Escape lever moves body to dreamwalk destination. |
| `DreamwalkAction` | `dreamwalk` | Thread-gated travel to bonded dreamer's dreamspace |
| `DescendAction` | `descend` | Descend from dream reflection into deep dreaming |
| `AscendAction` | `ascend` | Return from deep dreaming to dream reflection |

## Surfaces (#3003)

- REST: `GET /api/dreams/<character_id>/` (`CharacterDreamStateView`, read-only) —
  `is_dreamside`, the current `dream_room` (id/key/description), `co_dreamers` (via
  `co_dreamers_for`), `dreamwalk_host` (the anchor, if any), `dreamwalk_candidates` (via
  `dreamwalk_candidates_for`), `can_descend`/`descent_name`, `can_ascend`, and
  `wake_blocked` (via `is_dream_engaged`). Visibility: staff, or an account with an
  active tenure on the character — otherwise 404 (never 403, to avoid confirming the
  character exists).
- FE: `frontend/src/dreams/` — `DreamspacePanel` takes over the play view's Room tab
  while a character is dreamside (mirrors the server's own dreamside room-swap rule),
  reading the state above via `useDreamState` and surfacing the dreamwalk-candidate
  picker and descend/ascend controls.

## Integration Points

- **Vitals (#2287)**: extends `perceives_dreamside()` and `get_dream_room()` → `get_dream_space()`
- **Fatigue**: mental fatigue collapse branches to Dream Peril pool
- **Magic/Threads**: dreamwalking gated by RELATIONSHIP_TRACK/CAPSTONE threads
- **Soul Tether**: bonded pairs can always find each other in dreams
- **Conditions**: Nightmare/Madness conditions applied by Dream Peril pool outcomes
- **Consequence Pools**: Dream Peril pool follows the ADR-0049 guarded mortality pattern
