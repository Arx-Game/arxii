# Combat ACTION + OUTCOME broadcast with data-driven narration (#557)

**Status:** design — decisions locked, ready for implementation plan
**Branch:** `feature-557-broadcast-submit-pose-over-websocket`
**Date:** 2026-05-30

## Goal

When a combat round resolves, every participant sees, live (no poll):
1. **ACTION** — each combatant's declaration ("Kira's Frost Bolt at the Pyromancer"),
   authored by the actor's own persona.
2. **OUTCOME** — a data-driven narrative of the result ("strikes the Pyromancer for 24 cold,
   leaving them Burning (2)"), **durably persisted** in the encounter's scene log so it is
   there for anyone re-reading the scene afterward.

Broadcast over Evennia's existing native WebSocket (`obj.msg(interaction=...)`). **No Django
Channels.** Coverage is uniform: PC actors, persona-bearing NPCs/bosses, **and** persona-less
mook opponents.

## Premise correction (verified against code)

There is no combat WS channel. But the **scene interaction** path already broadcasts over WS and
the combat UI already renders it:
- `push_interaction` → `obj.msg(interaction=...)` to the room (`scenes/interaction_services.py:232-299`).
- Frontend: `useGameSocket` → `handleInteractionPayload` → Redux → `useSceneInteractions` →
  `SceneInteractionPanel`, rendered by `PoseUnit`. `CombatEncounter.scene` FK +
  `CombatScenePage` rendering `SceneInteractionPanel` mean free RP poses during combat are
  already realtime.

Gaps: (a) combat **ACTION** interactions are created (`create_action_interaction`,
`combat/interaction_services.py:28-81`) but never pushed; (b) there is **no OUTCOME
representation** — outcomes exist only as the in-memory `ActionOutcome` dataclass.

## Author model — Narrator persona (not nullable persona)

Every `Interaction` requires a `persona` (`create_interaction`, `scenes/interaction_services.py`);
`mode` only controls routing/display, and consumers like `PoseUnit` read
`interaction.persona.name`/`.id` unconditionally. Outcomes are narration-of-result, the same
shape as an environmental emit — narration that displays differently, not authorless content.

Decision (user-approved 2026-05-30): outcomes are durable and cover mooks, achieved via a
**singleton "Narrator" system persona**:
- **OUTCOME interactions are authored by the Narrator persona**, lazily `get_or_create`'d on
  first use. `mode=OUTCOME` drives combat-log display.
- **ACTION declarations stay actor-authored** (already the case).
- **Mooks need no special case** — all outcomes flow through the one Narrator-authored path, so
  persona-less opponents are covered for free.

Making `Interaction.persona` nullable was considered and rejected: it would create the system's
first authorless interaction (null-guards in every consumer) and require editing the
hand-maintained range-partition SQL (`scenes/sql/partition_interaction_*.sql`) plus its drift
hook. The Narrator approach changes no `Interaction` schema and touches no partition DDL.

## Locked decisions

1. **Per-action** OUTCOME (one per resolved action), not a per-round summary.
2. **New `InteractionMode.OUTCOME`** (TextChoices value; `mode` is an existing column → trivial
   `AlterField` migration, no partition impact).
3. **Data-driven, deterministic narration** from effects (no RNG).
4. **PC + persona-bearing NPC/boss + persona-less mook** all covered, uniformly.
5. **Durable:** every outcome is a persisted `Interaction` in the encounter's scene, authored by
   the Narrator persona.
6. **No FK from `CombatRoundAction` to the outcome** — that would add another
   `db_constraint=False` + denormalized-timestamp column (the partition-coupling pattern). The
   outcome lives in the scene feed by timestamp, right after its ACTION line; per-action detail
   is already derivable via `views_outcome_details`. Revisit only if a hard link is later needed.

## Anti-reinvention ledger (code-verified)

| Surface | Verdict | Evidence |
|---|---|---|
| `push_interaction`, `_broadcast_to_location`, `_build_interaction_payload` | BUILT & WIRED | `scenes/interaction_services.py:180-299` |
| `create_interaction` (persona-required) | BUILT & WIRED | `scenes/interaction_services.py` |
| `create_action_interaction` (ACTION row, never pushed) | BUILT, NOT WIRED | `combat/interaction_services.py:28-81`; called `combat/services.py:1899-1907` |
| `render_action_declaration_label` (sibling renderer) | BUILT & WIRED | `combat/interaction_services.py:84-104` |
| `ActionOutcome` (damage/conditions/defeat/combo) | BUILT & WIRED | `combat/types.py:84-93`; vitals `types.py:13-24` |
| NPC data (`ThreatPoolEntry.name/attack_category/damage_type/conditions_applied`) | BUILT & WIRED | `combat/models.py` ThreatPoolEntry |
| `PoseUnit` mode rendering; WS→Redux→`SceneInteractionPanel` pipeline | BUILT & WIRED | `PoseUnit.tsx:92-198` |
| `CombatEncounter.room` (broadcast target, reliably set) | BUILT & WIRED | `combat/models.py` |
| `InteractionMode.OUTCOME` | ABSENT → add | `scenes/constants.py:20-28` |
| Narrator singleton persona (`get_or_create_narrator_persona()`) | ABSENT → add (lazy bootstrap) | none today |
| `render_action_outcome_narration(...)` | ABSENT → add (sibling to declaration renderer) | — |
| `broadcast_action_outcome(...)` service | ABSENT → add | — |
| `PoseUnit` `mode=outcome` render branch | ABSENT → add | `PoseUnit.tsx` |

**No change to `Interaction` schema and no change to the partition SQL.**

## Architecture / data flow

All changes hang off `resolve_round` (`combat/services.py`), inside its existing
`@transaction.atomic`. The loop already builds an `ActionOutcome` per action and already creates
the ACTION Interaction for PC actions in `_resolve_pc_action` (`combat/services.py:1899-1907`).

1. **ACTION broadcast.** In `_resolve_pc_action`, after the existing `create_action_interaction`
   block, call `push_interaction(interaction)` when `interaction is not None`. Clash
   contributions follow the same pattern at their creation site.
2. **OUTCOME narration.** `render_action_outcome_narration(*, actor_label, technique, outcome,
   target_label) -> str` — a pure, deterministic function beside `render_action_declaration_label`
   in `combat/interaction_services.py`. Composes clauses from data available today: technique
   name, damage amount + `damage_type`, target defeated/KO/dying, conditions applied
   (name/severity/duration), combo. Omits absent clauses; offense vs support inferred from
   opponent-vs-ally target; zero damage → "misses". NPC side reads `ThreatPoolEntry`.
3. **OUTCOME persist + broadcast.** `broadcast_action_outcome(*, encounter, narration)`:
   - `persona = get_or_create_narrator_persona()` (singleton; lazy).
   - `interaction = create_interaction(persona=narrator, content=narration,
     mode=InteractionMode.OUTCOME, scene=encounter.scene)`.
   - Broadcast to the room: `_broadcast_to_location(encounter.room, payload)` — the Narrator has
     no location, so we use the encounter room directly rather than `push_interaction`'s
     persona-location resolution.
   - Called once per resolved action (PC and NPC) from the resolution loop, given each action's
     `ActionOutcome` plus the actor/target labels already available there.

### Narrator persona bootstrap

`get_or_create_narrator_persona()`: `get_or_create` a dedicated `Persona` named "Narrator",
backed by a `get_or_create`'d `CharacterSheet` + `ObjectDB` narrator identity — analogous to how
ephemeral `CombatNPC` ObjectDBs are created in `add_opponent`. One row total, reused across all
encounters. No data migration, no fixture (per repo rules); created on first outcome.

## Narration function (deterministic, effect-driven)

Inputs available today (no #614 dependency): technique `name`/`effect_type`, `focused_category`,
damage amount + `damage_type`, target defeated/KO/dying, conditions applied, combo name; NPC side
from `ThreatPoolEntry`. Deterministic clause assembly, omitting absent clauses. Deferred to
post-#614: attack/defense *intent* phrasing and magic-vs-physical wording (axes not in the data
yet).

## Frontend

- Regenerate API types so `InteractionMode` includes `outcome` (no nullable-persona change —
  outcomes carry the Narrator persona, so existing `interaction.persona` access stays safe).
- `PoseUnit`: add a `mode === 'outcome'` branch — combat-log styling (e.g. italic/indented
  narration line), **no `PersonaContextMenu`/target affordance** (the Narrator is not a
  targetable character). ACTION + OUTCOME flow through the existing
  WS→Redux→`SceneInteractionPanel` pipeline unchanged.

## Testing

- **Backend unit** (`render_action_outcome_narration`): pure damage; damage+condition; defeat;
  KO/dying; ally support; combo; typed vs untyped; passives/no-technique; zero-damage miss.
- **Backend unit** (`get_or_create_narrator_persona`): returns a stable singleton across calls.
- **Backend integration**: resolving a round pushes ACTION (PC, actor-authored) + a
  Narrator-authored OUTCOME for a PC, a persona-bearing opponent, and a persona-less mook; each
  OUTCOME is a persisted `Interaction(mode=outcome)` in the encounter's scene; broadcast invoked.
- **Frontend**: `PoseUnit` renders `mode=outcome` distinctly (no context menu); a WS `outcome`
  payload appends to the feed.
- SQLite tier locally (`just test-fast combat scenes`); PG parity on CI.

## Scope / follow-ups

**In:** ACTION broadcast (PC + clash contributions); `InteractionMode.OUTCOME`; Narrator
singleton persona; deterministic narrator; per-action OUTCOME persist + room broadcast for PC +
persona-bearing NPC + persona-less mook (all Narrator-authored); frontend outcome branch; tests;
type regen.

**Deferred (file as GitHub issues, per the issues-over-memory rule):** clash/challenge *outcome*
narration (clash *declarations* already ride the ACTION path); richer post-#614 intent/magic
phrasing; optional hard FK from `CombatRoundAction` to its outcome if a direct link is later
wanted.
