# Investigation & Discovery

The mystery core loop, built as one reusable spine over existing systems. Players
discover hidden things — lore (codex entries), missions, and held captives to rescue —
by **acquiring clues** and **resolving** them. Lives in `src/world/clues/`. Epic: #1143.

## The model: a clue is a pointer, on three independent axes

A `Clue` is a pointer defined by three orthogonal things:

1. **Target** — *what it points at.* `target_kind` (DiscriminatorMixin) ∈ `CODEX` /
   `MISSION` / `RESCUE`, with a matching per-kind FK (`target_codex_entry`,
   `target_mission`, `target_captivity`). **Invariant:** a clue cannot save without a
   target (`clean()` enforces exactly one) — no red herrings, no empty clues. The target
   also drives the "you already know this" flag (`target_already_known`) — a known-target
   clue is surfaced, not hidden.
2. **Acquisition** — *how you come to hold it.* A room **search** (`RoomClue` + the Search
   action) or a passive **trigger** (`ClueTrigger`, fired on room entry). Both record the
   holding via `CharacterClue` (roster-scoped, idempotent `acquire_clue`).
3. **Resolution** — *how holding it becomes having the target.* `resolution_mode` ∈
   `AUTOMATIC` (granted on acquisition — `grant_clue_target`) or `RESEARCH` (won through a
   collaborative research project).

## Acquisition surfaces

- **Search (active):** `RoomClue` anchors a clue to a room with a `detect_difficulty`.
  `SearchAction` (`actions/definitions/investigation.py`) charges AP + mental fatigue (via
  the declarative cost on the `Action` base) and calls `search_room`, which rolls the
  seeded **Search** CheckType (Perception+Investigation) against each hidden clue's
  difficulty and acquires the ones spotted.
- **Trigger (passive):** `ClueTrigger` anchors a clue to a room; `maybe_grant_clue_triggers`
  fires from `Character.at_post_move` (alongside the mission ROOM_TRIGGER dispatch) and
  grants eligible, not-yet-held clues with no roll — the world reveals it because of who you
  are / where you are. The player is told via the clue's authored description
  (`send_narrative_message`).

## Resolution paths

- **AUTOMATIC** (`grant_clue_target`): CODEX → the character learns the entry
  (`CharacterCodexKnowledge.add_progress`, firing the codex KNOWN reactivity hook); RESCUE →
  the finder is handed the rescue mission (`grant_rescue_mission`, captive as
  `rescue_target`).
- **RESEARCH** (`world/clues/research.py`): a `ProjectKind.RESEARCH` project (on the shared
  `world/projects` framework) targeting a clue. Contributors spend AP to make Research rolls
  (`contribute_research`); progress scales with the outcome, **floored at 0** (a failed help
  never detracts). A weekly cron setback (`apply_research_setbacks`) is the only negative.
  On completion, `resolve_research` grants the clue's target to every contributor.

## Two-layer gating

Every placement gates on two independent things (via `world.predicates`; the epic's "gating
is layered"):

- **Capability / skill** — the detect (Search) check, against `detect_difficulty`.
- **Access** — an `eligibility_rule` predicate (`JSONField`, same shape as
  `MissionTemplate.visibility_rule`) on `RoomClue` / `ClueTrigger`. Empty `{}` = open to
  anyone (the clue default, unlike missions' default-locked); a rule restricts on identity /
  org / resonance / species via `world.predicates`.

## Rescue-as-clue (#931)

Capture plants discovery, reusing the whole spine. Authored at mission-design time: the
CAPTURE consequence effect and `CaptivityConfig` carry the rescue clue's name / description /
detect difficulty + the rescue mission template (override-then-default). On capture,
`_apply_capture` stamps `Captivity.rescue_template` and `plant_rescue_clue`s a RESCUE clue at
the capture site; allies who `search` there are handed the rescue. `resolve_captivity` calls
`clear_rescue_clues` when the captive is freed.

## Build constraint (authoring vs. mechanism)

Everything player-facing is **authored data**, never agent-generated: clue text, detect
difficulties, eligibility rules, research magnitudes, the Search/Research CheckTypes, and the
Investigation skill are all staff-editable rows (admin), with sane defaults. Code ships the
mechanism + schema; *which* clues exist and *how much* each adds are deferred to author
passes.

## Reuse ledger (what this is built on)

| Concern | Reuses |
|---|---|
| Clue → codex pointer | absorbed the old `codex.CodexClue` (now generalized `Clue`) |
| Hidden room-anchored findable | mirrors `room_features.Trap` |
| Research projects | `world/projects` `Project`/`Contribution` + a `RESEARCH` kind |
| Check resolution | `perform_check` + data `CheckType`/`CheckTypeTrait` |
| AP / fatigue | declarative cost on `Action` base → `ActionPointPool` + fatigue pipeline |
| Access gating | `world/predicates` rule trees |
| Rescue grant | `missions.grant_rescue_mission` (#1134) |
| Player notification | `narrative.send_narrative_message` |

## Status

Shipped: clue model, Investigation skill + CheckTypes (seed), search action + declarative
cost, eligibility gating, RESEARCH kind, rescue-as-clue (closes #931), passive enter-room
triggers. Remaining (see `docs/roadmap/investigation-discovery.md`): more trigger sources
(item / resonance / soul-tie), the clue journal UI, and the error-handling service (#1164)
that replaces the interim log-and-continue in the trigger hooks.
