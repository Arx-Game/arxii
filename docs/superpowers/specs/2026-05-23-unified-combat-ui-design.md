# Unified Combat UI — Design

**Date:** 2026-05-23
**Status:** Design spec. Implementation deferred to its own plan.
**Branch context:** Authored on `clash-cleanup-notes`. Companion to the clash
post-ship cleanup backlog (`docs/plans/2026-05-23-clash-post-ship-cleanup-notes.md`).

## Overview

A unified player-facing UI for combat that coherently presents the multiple
overlapping mechanical systems (action declaration, thread pulls, clash
contributions, combo upgrades, conditions, resources) alongside the narrative
pose log, without colliding-concept parallel panels.

The design's core architectural move is recognizing that **the in-round action
surface is the same primitive used by non-combat scene actions** —
technique + target + effort + thread pulls + cost — and that combat is a
specialization layered on top, not a parallel system. This drives a reusable
`<ActionDeclarationCard>` shared between contexts, with a `<CombatTurnPanel>`
wrapper that adds combat-specific surfaces (slot constraints, fatigue, combatants,
active state, round flow).

### How this spec came about

The clash mechanic shipped (PR #493) with backend complete but no frontend. The
cleanup backlog flagged the unified player UI as the largest remaining piece for
clash to be playable. A 2026-05-23 brainstorm reframed the problem from
"clash UI" to "unified action surface" once it surfaced that clash and combos
already share dispatch primitives (`PlayerAction` descriptors) and that combos
can be gated on clash state (`ComboDefinition.required_clash_flavor`,
`required_clash_window_condition`) — so they cannot be independent panels.

### Design pillars

- **Narrative-first.** Arx II is a narrative RP game with combat mechanics, not
  a tactical game with prose flavor. The pose log is the spine; mechanical
  affordances live alongside it, never block pose composition.
- **Mechanics-first execution.** Players typically declare mechanically, see the
  outcome, then write a pose elaborating it. Prep poses are optional. The
  mechanical UI is what kicks off the prose.
- **Pose ↔ action is a first-class link.** Legacy MUDs treat poses and mechanical
  actions as unrelated log entries; this design enforces the link via the
  existing `Interaction` model + a new `InteractionAction` bridge so a pose
  carries explicit FKs to the actions it elaborates.
- **Reuse the substrate.** The scenes app already has `Interaction.mode=ACTION`,
  `ActionPanel`, `ActionAttachment`, `ActionResult`, the `PlayerAction`
  descriptor API, and the magic app already ships `PullEffectPreview`,
  `ResonanceBalanceCard`, the `CombatPull` envelope, and the thread query
  infrastructure. The combat UI composes these, doesn't reinvent them.
- **Shared core, specialized wrappers.** `<ActionDeclarationCard>` is the
  shared primitive. `<CombatTurnPanel>` adds combat surfaces. A future
  `<SceneActionPanel>` adopts the same card. The combat-side ships in this
  spec's plan; the scene-side adoption is deferred.

## Scope

**In scope:**

- The C-frame layout (pose log + composer on left; stratified right rail).
- The combined pose-unit rendering: one log card per pose with linked-action
  chips inline, reactions/favorites footer.
- The `<ActionDeclarationCard>` shared component contract.
- The `<ThreadPullPicker>` reusable widget (contextual filtering, tier 0 default,
  details modal, search, "show inapplicable" toggle).
- The `<CombatTurnPanel>` wrapper: slot constraints, fatigue, combatants list,
  active-state cards, round flow, vital pools.
- `InteractionAction` bridge model (the only new backend model required).
- Auto-linking of poses to actions by temporal scope (actions since the
  persona's last POSE in this scene).
- Backend API contract for applicable-thread lookup with inapplicable reasons.
- File organization: new `frontend/src/actions/` module for the shared card.

**Out of scope (deferred):**

- Scene-side action submission envelope for non-combat thread pulls. No
  `ScenePull` / `ActionPull` model exists yet; the widget is built reusable
  but the scene-side wiring is its own brainstorm.
- Positioning / zones integration in the combatants list — pending the
  positioning spec (`docs/plans/2026-05-21-positioning-zones-design-notes.md`).
- Clash-contribution dispatch handler — the spec calls for it; the cleanup-notes
  backlog tracks it as a separate small piece of work.
- WebSocket push for real-time state updates — existing scene WebSocket
  patterns apply; no new design.
- Mobile responsive layout.
- Combat encounter setup, joining, opponent picking — those are admin/GM
  surfaces, separately scoped.

## §1 — Layout (the C frame)

Pose log + composer dominates the left pane (~60-65% width). Right rail
(~35-40%) carries combat-specific state. Both always visible; rail sections
collapsible.

```
┌─────────────────────────────────────────┬──────────────────────────┐
│ Scene header                            │ ⚡ Your Turn — Round N   │
│ ─────────                               │   (Decisions, highlighted)│
│ Pose log (scrolling)                    │                          │
│   • GM pose                             ├──────────────────────────┤
│   • Player combined pose-units          │ Resonance budget         │
│       [action chip · GREAT · +N]        ├──────────────────────────┤
│       Prose body                        │ Vital pools              │
│       ❤ 3  💬 1  ⭐ 2                    ├──────────────────────────┤
│                                         │ Combatants               │
│ Composer (always available)             ├──────────────────────────┤
│   📎 Attaching: <Action> → <Target> ✕   │ Active state             │
│                                         │   (clash/ward/break)     │
│                                         ├──────────────────────────┤
│                                         │ Round flow               │
└─────────────────────────────────────────┴──────────────────────────┘
```

### Pose log rendering

Each log entry is one combined unit (card) containing:

- **Attribution header** — persona **thumbnail** + name + scene timestamp +
  optional round/phase context. Player-attributed (blue accent),
  GM-attributed (amber accent), system-attributed (grey, lower opacity).
  Thumbnail source: `Persona.thumbnail` FK (to `evennia_extensions.PlayerMedia`)
  takes precedence over `Persona.thumbnail_url` (legacy URLField). Fallback
  when neither is set: initial-letter avatar with persona-name-derived color.
  Both fields already exist on the model
  (`world/scenes/models.py:193-201`); no schema change.
- **Action chip(s)** — when the entry has linked actions: one chip per action
  showing technique name + outcome tier + delta (e.g., `Tidal Fury · GREAT · +4 to clash`).
  Color-coded by outcome (success tiers in greens, mishaps in oranges/reds).
- **Prose body** — full pose text, no truncation by default. Click-to-expand
  for extremely long poses (TBD threshold; not a default behavior).
- **Reactions footer** — `InteractionReaction`, `InteractionFavorite`,
  `vote_count`. Same affordances as any scene pose.

Three rendering states per unit:
- Pose with linked action(s) — the common case; both rendered together.
- Pose without action (prep pose) — narrative only, no chip.
- Action without pose — chip only with placeholder text *("Mirelle hasn't posed yet")*.

### Action outcome details — expandable

The terse action chip on a pose unit is a one-line summary. The *actual*
outcome of an action can be rich:

- Damage results per target (PCs hurt, NPCs killed, sub-tier "scratched"
  outcomes)
- Conditions applied per target (Burning ×2, Held, Probed +1)
- Achievement progress fired
- Discoveries triggered (a persona unmasked, a covenant-role revealed)
- Reactive trigger fires (Soul Tether redirect drained N from the Hollow, a
  resonance environment AMPLIFY proc'd, Soulfray severity accrued)
- Resource changes (anima spent, fatigue accrued, resonance spent on pulls)
- Clash meter contribution + tier
- Combo upgrade triggered (and its own bundle of effects)

Surfacing all of this inline would overwhelm the pose log. Hiding it entirely
loses context players actively want. The rule:

- **Default:** the chip alone (terse one-line summary). Pose log stays
  scannable.
- **Expandable:** a small ▾ affordance on the chip (or on the pose unit's
  header) toggles an inline detail panel listing all outcome effects.
- **Per-effect deep links:** each effect row in the expanded view can link to
  a focused modal (the wound detail, the condition's source explanation, the
  achievement's full description, the discovery's narrative reveal). Effects
  that don't have a meaningful deeper view are display-only.
- **Pose-level vs chip-level expand:** when a pose has multiple linked
  actions, the pose-level expand reveals every action's detail panel; each
  chip can also be expanded individually. Both behaviors point at the same
  per-action detail block — only the entry point differs.
- **State persistence:** expand/collapse state is local UI state, not
  persisted server-side. Refreshing the page returns to the collapsed default.

#### Data path

The ACTION-mode `Interaction.content` stays terse (the format
`ActionResult.tsx` already parses). The detail panel is fetched on-demand
from the underlying mechanical models via the bridge:

- Frontend asks: "give me outcome details for action records [N, M, …]"
- Backend returns a structured shape: a list of effects per action, each
  effect tagged with kind (`damage`, `condition`, `achievement`,
  `discovery`, `trigger_fire`, `resource_change`, …), a one-line label, an
  optional deep-link target (URL or modal-key + ID).

The per-effect shape is enumerated in the plan phase — see the existing
`ActionOutcome` / `ParticipantDamageResult` / `AppliedConditionResult` etc.
types in `world/combat/types.py` for the source shapes. The API serializes
those into a display-friendly shape with stable kind tags the frontend
renders consistently.

Lazy-fetch: detail data is requested only when the player expands the chip
(or the pose). The pose log payload stays light by default.

#### Skim-vs-detail UX

Players reading scene history primarily want narrative. The terse chip
preserves that. When something feels load-bearing ("wait, what did Aerande
actually do to the Knight in round 3?") the expand affordance gives them the
full mechanical picture without taking them away from the scene flow. Critical
events (KO, death, dramatic conditions) may also surface auto-expanded the
first time they render in a session — TBD by player preference settings in
implementation; default is collapsed.

### Composer

Standard scene composer (existing `SceneInteractionPanel`) plus an
`ActionAttachment` chip when an action is queued or recently resolved:

```
📎 Attaching: Tidal Fury → Mire Knight  [✕]
```

Submission creates an `Interaction` row (`mode=POSE`) and auto-links to all of
this persona's unlinked actions since their last POSE in this scene (see §3).

## §2 — Right rail composition

Top to bottom, all sections collapsible (▾ header control):

### ⚡ Your Turn (Decisions) — highlighted, prominent

Hosts up to three `<ActionDeclarationCard>` instances:
- **Focused slot** — one card. Required for the round.
- **Passive slot(s)** — 0-2 cards, one per category *not* used by the focused
  slot. The category matching the focused slot's category is **hidden entirely**
  (the disabled-slot rendering pattern is rejected — it wastes real estate and
  confuses).

Below the slots: "other options" row (clash-contribution opt-in, combo upgrades
when available) and a `Submit declarations · mark ready` button.

### Resonance budget

Per-resonance row showing **current balance** + **committed-this-round** in one
bar, with numeric (`10 −4`). Hover surfaces lifetime-earned and flavor text via
the existing `ResonanceBalanceCard` HoverCard. Separate from Vital pools because
resonance is scarce per-resonance currency (not a per-tick regenerating vital).

### Vital pools

Bars for: **Health**, **Anima**, **Physical fatigue**, **Social fatigue**,
**Mental fatigue**. Health at the top (most precious). Color-coded by category.
Overload warning surfaces when fatigue >50% (e.g., "Mental fatigue high — Mental
actions cost extra"). Health bar shifts to amber when wounded.

### Combatants

List of all participants (PCs and NPCs visually distinct), each with:
- Compact persona **thumbnail** (same source resolution as the pose log:
  `Persona.thumbnail` → `Persona.thumbnail_url` → initial-letter avatar).
  NPCs use whatever portrait/asset their `CombatOpponent` carries; if none,
  fall back to the initial-letter avatar with NPC color treatment.
- Name
- HP mini-bar (color-coded; NPC HP in orange tones to match enemy framing)
- Condition icon row (clickable for details)
- Active-clash indicator (⚡)

Reuse note: the thumbnail rendering is the **same component** used by the
pose log attribution header. Both surfaces (and any future scene UI showing
a persona) share one `<PersonaAvatar>` component so the source-resolution
order and fallback behavior stays consistent.

### Active state

Cards per active mechanic instance:
- **CLASH** — title, round + meter, side favored, contributors list
- **WARD** — sustained-attack title, duration remaining, current absorbed/passed
- **BREAK** — barrier title, meter remaining
- **Suppress** — held title, meter, who's sustaining

Each card has a meter visualization and the same contribution affordances
surfaced by the action card (Commit / Lend).

### Round flow

- Declaration progress: "1 of 3 PCs ready"
- Initiative-order chips (acted ✓ / current … / pending)
- Resolution-order line for the upcoming resolution phase

## §3 — Pose ↔ action linkage

### Data model

Combat actions become `Interaction` rows with `mode=ACTION` — the `Interaction`
model already supports this (`world/scenes/constants.py` lists `ACTION` as a
choice; the docstring at `world/scenes/models.py:357` explicitly mentions
"or takes a mechanical action").

The system-generated ACTION-mode Interaction's `content` follows the format
`ActionResult.tsx` already parses:
```
[ActionKey] using TechniqueName -- OutcomeName (ConsequenceLabel)
```

The player's elaborating pose is a separate `Interaction` with `mode=POSE`.
A new bridge model links them:

```python
class InteractionAction(SharedMemoryModel):
    """Links a pose Interaction to the mechanical action(s) it elaborates."""

    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.CASCADE,
        related_name="action_links",
    )
    # The underlying combat action this link references.
    # See "Open: bridge target shape" below for the chosen approach.
    action = models.ForeignKey(...)
    ordering = models.PositiveSmallIntegerField(default=0)
```

#### Open: bridge target shape

The bridge needs to point at the underlying mechanical action. There are
several plausible action sources (`CombatRoundAction`, `ClashContribution`,
`CombatPull`, future scene actions). Two patterns to choose between in the
plan phase:

- **(A) FK to the ACTION-mode Interaction** — `action` becomes
  `action_interaction` (FK to Interaction), and the system-generated ACTION
  Interaction is the join point. The mechanical row's metadata is reachable via
  whatever `content_object`-style or per-source linkage already lives on the
  ACTION Interaction (or new fields on it). Keeps the bridge truly polymorphic
  without contenttypes. Recommended.
- **(B) Bridge per action type** — `InteractionCombatActionLink`,
  `InteractionClashContributionLink`, etc. Type-safe but proliferates
  tables. Considered and rejected unless (A) hits problems.

Pattern (A) is the working assumption; the plan should confirm by sketching
the query path for "give me all actions linked to this pose" and verify it
stays a single join.

### Auto-linking

When a player submits a `mode=POSE` Interaction in a scene, the backend
auto-attaches any actions taken by that persona in this scene since the
persona's last POSE (or since the scene started, if no prior poses).

Behavior:
- **Prep pose** (player poses before any action) → no actions linked.
- **Acted but didn't pose** → ACTION Interaction stands alone (still
  attributable, still react-able).
- **Multiple poses in a round** → first pose attaches actions taken before it;
  later poses attach actions taken after it.
- **Advanced override** — the API accepts an optional explicit action-link list
  on submission so power users can correct the auto-linking. Not exposed in the
  default UI. **Explicit override wins** — when a pose is submitted with an
  explicit `action_link_ids` list, the auto-link step is skipped entirely. The
  affected actions are marked as already-linked so subsequent poses won't
  re-attach them.

### Rendering

The pose log fetches `Interaction` rows for the scene as usual (existing
`useSceneMessages`-style query); the new addition is that POSE rows carry their
linked-action records (via the bridge) and ACTION rows know whether they have
been linked. Rendering rules:

- **POSE with N actions linked** → render one combined unit (header + N chips
  + prose + reactions).
- **POSE with no actions linked** → narrative-only card (prep pose).
- **ACTION not linked yet** → standalone card with placeholder body
  ("Aerande hasn't posed yet"). Once a pose links to it, it disappears from the
  log as a standalone row and reappears collapsed inside the pose's card.

The render-collapse is a frontend choice that follows from the data model —
no special backend coordination required.

### Inheriting affordances

Because the data primitive is `Interaction`, all existing scenes-app
affordances work without change:
- `InteractionFavorite` toggle on either the pose or the action
- `InteractionReaction` (emoji reactions) on either
- `vote_count` (weekly Memorable Poses) — combat poses compete for the same
  recognition system
- `target_personas` for thread/reply derivation
- `visibility` (DEFAULT / VERY_PRIVATE)
- `scene` container — combat happens inside a scene

## §4 — `<ActionDeclarationCard>` (shared core)

Lives at `frontend/src/actions/ActionDeclarationCard.tsx` (new top-level module
because it's used by both scenes and combat).

### Contract

```tsx
<ActionDeclarationCard
  characterSheetId={...}
  actionContext={{
    slot: "focused" | "passive-physical" | "passive-social" | "passive-mental" | "scene",
    technique?: Technique,
    target?: PersonaRef | CombatantRef,
    targetKind: "opponent" | "ally" | "social" | "self",
    effort: EffortLevel,
    strainCommitment: number,
    // ...context flags as needed
  }}
  onContextChange={(newContext) => ...}
  onCommitPulls={(pullsPayload) => ...}    // wired by parent
  onSubmit={(action) => ...}
  readOnly?: boolean
/>
```

### Sub-sections

- **Picker rows** — Technique + Target (filterable; existing technique-picker
  patterns from `ActionPanel` reused).
- **Stats** — Intensity / Control display as a chip (`I:8 / C:5`). When
  `intensity > control`, chip turns amber-warn with tooltip explaining the
  cost-spike risk. A `Strain +N` chip shows current strain commitment.
- **Effort selector** — pills (Very Low → Very High). Selecting an effort
  recomputes the cost preview live.
- **Cost line** — `Cost: −N anima` (or `0 anima · (Control > Intensity, low effort → comfortable cast)`
  when the formula yields zero). Color-coded amber for non-zero cost.
- **`<ThreadPullPicker>`** — embedded subsection (see §5).
- **Pose-attachment hook** — when the parent wires it, the composer's
  `ActionAttachment` widget is auto-populated with this action on submit.

### Reuse map

- Technique-picker — extracted from `ActionPanel.tsx`
- Target-picker — uses `PersonaContextMenu.tsx` patterns + combatant lists
- Effort selector — new (no existing component fits)
- Intensity/Control display — new (small)
- `<ActionAttachment>` — used as-is from `scenes/components/`

## §5 — `<ThreadPullPicker>` (reusable widget)

Lives at `frontend/src/magic/components/threads/ThreadPullPicker.tsx`.

### Contract

```tsx
<ThreadPullPicker
  characterSheetId={...}
  actionContext={{
    technique?: Technique,
    effectType?: EffectType,
    target?: ObjectRef,
    scene?: SceneRef,
    // ...any other applicability-relevant context
  }}
  selectedPulls={{ [threadId]: tier }}
  onPullsChange={(newPulls) => ...}
  showInapplicable={boolean}
  onToggleInapplicable={(next) => ...}
/>
```

### Layout

- **Header:** "Thread pulls — N applicable" + small counts ("M pulled · K passive").
- **Toolbar:** filter-by-name search input + single "Show inapplicable" toggle
  chip (checkbox). No multi-chip filter set; the toggle is the only on/off.
- **Scroll body:** list of pull rows (applicable first, then a divider, then
  inapplicable rows when toggled).
- **Footnote:** ⓘ note about focused-action change behavior (see §5.4).

### Row design

Each applicable row:
- **Head** — thread name (bold) + anchor description (small, uppercase, e.g.,
  "Facet · Primal").
- **Tier strip** — `Tier  [0]  [1]  [2]  [3]` pills. Tier 0 is the
  always-selected default (green chip — "passive always-on"). Tiers 1/2/3 are
  selectable when affordable; **unaffordable tiers are greyed with a tooltip
  explaining why** (e.g., "Need 5 Sworn; have 4"). **No cost is shown on
  unselectable tiers.**
- **Active line** — terse summary of what the currently-selected tier gives
  ("Pulled: +3 intensity bump (Tidal Fury) · +1 flat" or "Passive: +1 to
  defensive checks (always-on)").
- **Cost line** — only when a paid tier is selected: `−4 Tide · −3 anima` +
  `▸ details` affordance.

Each inapplicable row (when toggled visible):
- Same head (name + anchor)
- **No tier strip** (dropped entirely — pills would all be greyed and
  meaningless)
- **Reason chip** explaining inapplicability ("Abyssal-only — your focused
  action is Primal" / "Bonded character not present in scene")
- Dashed border, lower opacity

### Modal — full details

Triggered only by the explicit `▸ details` affordance on the row (not by a
click-anywhere — selecting tiers and viewing details are separated). The modal
shows:
- Thread name, anchor, level
- Full tier 0 effects (always-on passive)
- Per-tier (1/2/3) effects with: cost, resolved-effects list, narrative snippet,
  inactive-reason where applicable

Internally, the modal re-uses the full `PullEffectPreview` component — the
inline row is a compact mode of the same underlying data.

### Auto-revert on focused-action change

When the focused action changes, applicable threads recompute. Any pulls
selected at tier 1/2/3 that become inapplicable **silently revert to tier 0**
and the picker surfaces a one-line notice:
> *Two pulls (Endless Tide, Vow to the Drowned) reverted to tier 0 — they no
> longer apply to your new focused action.*

No modal interrupt; the notice clears on the next interaction.

### Backend contract

The widget needs an API that takes `(character, action_context)` and returns
per-thread `applicable: bool` + `inapplicable_reason: string`. The `reason`
field must be a **stable enum** (not free text from the backend) so the
frontend can render consistent reason chips.

Two options for delivery:
- Extend the existing `previewPull` to accept an `action_context` and return
  applicability info.
- Add a new endpoint `GET /api/magic/threads/applicable-pulls/?action_context=...`.

The plan should pick one. The widget's contract is the same either way.

## §6 — `<CombatTurnPanel>` (combat wrapper)

Lives at `frontend/src/combat/CombatTurnPanel.tsx` (new top-level `combat/`
module).

### Composes

- **Focused slot** — one `<ActionDeclarationCard>` with `slot: "focused"`.
- **Passive slots** — up to 2 `<ActionDeclarationCard>`s with
  `slot: "passive-<category>"`, one per non-focused category. The matching
  passive slot is hidden when `focused_category` is set.
- **Combo upgrades** — surfaces `AvailableCombo` results from the existing
  `detect_available_combos` service. The "Combo: Tidewall" button-row in
  mockups is rendered here.
- **Clash contribution mode** — when an active `Clash` has the player as a
  current contributor (or eligible), the focused card displays "→ Commit to
  clash" as the action target and exposes a Strain commitment slider. When the
  player is eligible but not yet contributing, the action menu surfaces "Lend
  to clash" as an opt-in (uses a passive slot).
- **Vital pools, Combatants, Active state, Round flow** — each its own rail
  section.

### `PlayerAction` descriptors

The submission path uses the existing `PlayerAction` descriptor API. The clash
spec §4 already specifies that clash-contribution actions appear in
`get_player_actions`; combo upgrades likewise. No new descriptor types are
introduced — the panel consumes whatever the backend emits.

### Slot constraint enforcement

The category-gating rule (`focused_category != passive_category`) is enforced
both server-side (existing constraint on `CombatRoundAction`) and client-side
(the matching passive slot is not rendered). Switching the focused category
clears any conflicting passive selection with a one-line notice.

## §7 — Reuse map

Components and APIs consumed without modification:

**Frontend (scenes app):**
- `SceneHeader` — scene title + metadata
- `SceneMessages` — pose log container (extended to handle the combined
  pose-unit rendering)
- `SceneInteractionPanel` — composer
- `ActionPanel` — refactored: its popover form remains for non-combat scenes;
  its `PlayerAction` rendering is extracted into the `ActionDeclarationCard`
- `ActionAttachment` — composer chip
- `ActionResult` — ACTION-mode Interaction rendering
- `PersonaContextMenu` — target picker patterns
- `useSceneMessages`, `createActionRequest`, `fetchAvailableActions` — existing
  React Query hooks and API calls

**Frontend (magic app):**
- `PullEffectPreview` — composed into compact rows and the details modal
- `ResonanceBalanceCard` — HoverCard for resonance budget rows
- `ThreadCard` — referenced for visual consistency (the picker row borrows its
  style language)
- `useCharacterResonances`, `useThreadHubSummary`, `useCommitPull` — existing
  React Query hooks

**Backend:**
- `Interaction` model (existing) — used as-is with `mode=ACTION`
- `InteractionFavorite`, `InteractionReaction`, `vote_count` — inherited
  affordances
- `CombatRoundAction`, `ClashContribution`, `CombatPull`, `ComboDefinition` —
  existing models, no schema changes (the bridge is the only new model)
- `PlayerAction` descriptor API — existing
- `detect_available_combos`, `upgrade_action_to_combo`, `revert_combo_upgrade` —
  existing services (the ViewSet actions in `world/combat/views.py` are named
  `upgrade_combo` / `revert_combo`; the underlying service functions carry the
  longer names)
- `previewPull`, `commitPull` — existing APIs

## §8 — New backend pieces

Small surface — most of the backend exists.

1. **`InteractionAction` bridge model** (`world/scenes/models.py`)
   — small migration. See §3 for the open question on the bridge target shape.

2. **Auto-link service** — when a `mode=POSE` Interaction is created, a service
   function attaches the persona's unlinked actions in this scene to it.
   Single-purpose, callable from the POSE submission view.

3. **Applicable-thread-pull API** — extend `previewPull` (or new endpoint, plan
   decides) to return per-thread `applicable: bool` + `inapplicable_reason: enum`
   given `(character, action_context)`. The reason enum is the load-bearing
   part — the frontend renders chips off it.

4. **`PlayerAction` descriptors for clash contributions** — the clash spec
   §4 already calls for these. The cleanup-notes backlog tracks wiring the
   `_find_combat_player_action_for_ref` dispatch path to
   `declare_clash_contribution`. **This dispatch wiring is a hard prerequisite
   for this UI work** — without it, the UI's clash contribution path raises
   `UNKNOWN_ACTION_REF` and cannot be integration-tested. The plan should
   sequence dispatch wiring as Phase 0 (or land it as a separate PR first).
   It is small focused backend work and is the cleanest split between backend
   plumbing and UI implementation.

No `ScenePull` or `ActionPull` envelope is added here — scene-side adoption is
deferred.

## §9 — Scope of this design vs scene-side adoption

This spec covers the **combat UI** and the **shared substrate**
(`<ActionDeclarationCard>`, `<ThreadPullPicker>`, `InteractionAction` bridge,
auto-linking, applicable-pull API). The substrate is authored as reusable from
day one.

What it does **not** cover:

- Scene-side action submission for non-combat thread pulls. There is no
  `ScenePull` envelope in the backend yet, and the scenes `ActionPanel` does
  not currently dispatch through one. The shared `<ActionDeclarationCard>` will
  be importable from scenes when that backend wiring exists — that's a separate
  brainstorm.
- The combat encounter setup, joining flow, GM-side opponent authoring, etc.
- Mobile / responsive layout. Desktop-first for v1.

The implication: the shared components live at the new top-level
`frontend/src/actions/` module (not under `combat/` or `scenes/`) precisely so
neither owns the abstraction and either can adopt.

## §10 — Testing strategy

**Component (Vitest + RTL):**

- `<ActionDeclarationCard>` — render with empty context, populated context,
  intensity-exceeds-control warning state, zero-cost (social-low-effort) state.
  Verify effort selection updates the cost preview live.
- `<ThreadPullPicker>` — render with applicable + inapplicable threads, verify
  toggle reveals inapplicable rows with reason chips. Verify tier selection
  updates the cost line. Verify unaffordable tiers are disabled with tooltips.
  Verify auto-revert when context changes drop a pull's applicability.
- Combined pose-unit rendering — pose+action linked, pose-only, action-only
  states; collapsed (chip-only) and expanded (full effect list) states for
  pose-level and per-chip expand triggers; lazy fetch verification (detail
  data is not fetched until expand).

**Integration:**

- Full declare → pull → pose → submit flow in a combat scene fixture: action
  resolves, pose attaches via auto-link, combined unit renders in pose log,
  reactions work.
- Combat declaration round-trip: pick focused + passive, commit pulls, submit;
  verify `CombatRoundAction` + `CombatPull` rows exist with correct linkages.
- Clash-contribution path: emit clash opportunity, player commits, verify
  contribution writes + UI updates.

**Existing tests inherited:**

- `world/scenes/tests/` (Interaction CRUD, favorites, reactions, vote_count)
- `world/combat/tests/test_combos.py` (combo detection + upgrade)
- `world/combat/tests/test_clash_*` (clash flow integration)
- `world/magic/tests/test_thread_pull_*` (pull preview + commit)
- `frontend/src/magic/__tests__/` (existing thread components)

**Out of scope for v1 tests:**

- Visual regression — would be valuable but not blocking
- E2E (Playwright) — defer until backend wiring is fully exercised by component
  + integration tests

## §11 — Open items for the plan phase

1. **Bridge target shape** (§3) — confirm pattern A (bridge → ACTION-mode
   Interaction) by sketching the query path; fall back to pattern B (per-type
   bridge tables) only if pattern A causes a query to multi-join.

2. **Applicable-pull API surface** (§5) — extend `previewPull` vs new endpoint.
   Plan decides based on existing API shape; widget contract is unchanged.

3. **`inapplicable_reason` enum** (§5) — author the closed set of reasons. From
   the brainstorm: wrong-affinity, anchor-target-not-present,
   anchored-on-other-technique, prerequisite-condition-unmet, location-mismatch.
   Possibly more; plan should enumerate.

4. **Long-pose threshold** (§1) — what triggers "click to expand"? Probably
   character count or rendered-height. Defer to implementation.

5. **Per-effect deep-link enumeration** (§1) — the set of effect kinds that
   carry meaningful deep links (damage → wound detail, condition → source,
   achievement → progress page, discovery → narrative reveal, trigger →
   reactive event explanation). The plan should enumerate the kinds from
   `world/combat/types.py` (`ActionOutcome`, `ParticipantDamageResult`,
   `AppliedConditionResult`, `DamageConsequenceResult`, etc.) and decide
   which targets exist as modals/pages today vs which need new surfaces.

6. **Auto-expand on critical events** (§1) — whether KO / death / dramatic
   condition fires should auto-expand the first time they render. Probably
   yes, behind a player preference (default on). Defer to implementation.

7. **NPC thumbnail source** (§2 Combatants) — `CombatOpponent` doesn't
   currently carry a portrait FK. The plan should decide whether to add one
   (small migration), wire to existing opponent-asset infrastructure if it
   exists, or stick with initial-letter avatar for v1 and add the field
   later. PCs use `Persona.thumbnail` and have no equivalent gap.

8. **Scene-action passive declaration in non-combat scenes** — does the scene
   wrapper allow multiple action cards (one per category) like combat, or is it
   always a single card? Defer to the scene-side spec.

## §12 — Related work

- **Clash design spec** (`docs/superpowers/specs/2026-05-22-clash-design.md`) —
  this UI is the missing frontend for clash.
- **Clash cleanup notes** (`docs/plans/2026-05-23-clash-post-ship-cleanup-notes.md`)
  — lists this UI work + the dispatch handler this UI depends on.
- **Positioning notes** (`docs/plans/2026-05-21-positioning-zones-design-notes.md`)
  — when positioning lands, combatants section will gain spatial indicators.
- **Existing scene components** (`frontend/src/scenes/`) — substantial substrate
  reused; see Reuse map (§7).
- **Existing thread components** (`frontend/src/magic/components/threads/`) —
  `PullEffectPreview` and friends; widget composition described in §5.

## Mockup archive

Iterative mockups produced during the brainstorm live at
`.superpowers/brainstorm/60704-1779582214/` (gitignored). The canonical
combat-side reference is `layout-c-detailed-v7.html`; the shared-core comparison
is `layout-scene-vs-combat-v2.html`.
