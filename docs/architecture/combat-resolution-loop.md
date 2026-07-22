# Combat Resolution Loop — Design

**Date:** 2026-05-25
**Status:** Design spec. Implementation in `docs/superpowers/plans/2026-05-25-combat-resolution-loop.md` (gitignored).
**Branch:** `combat-resolution-loop` (forked off `main` after `db6cc0a4 Unified combat UI` merged).
**Builds on:**
- `docs/architecture/unified-combat-ui-design.md` (the C-frame combat UI)
- `docs/architecture/clash-design.md` (the clash mechanic)
- `docs/plans/2026-05-23-clash-post-ship-cleanup-notes.md` §4 (the carry-forward
  list this PR resolves)

## Overview

The unified combat UI PR (#496) shipped the C-frame layout, the
`<ActionDeclarationCard>` primitive, the `<CombatTurnPanel>` wrapper, and the
pose ↔ action bridge model. What it could not yet do, because the underlying
plumbing was missing, is **show the player the outcome of their cast**. The
`/api/combat/action-outcome-details/` endpoint returns empty effect arrays per
action because nothing in production creates an ACTION-mode `Interaction` and
nothing persists the resolved effects.

This PR closes the cast → resolution → pose-log → outcome-detail loop end to
end. After this lands, a player can declare a technique, see it resolve, read
the rendered effects (damage dealt, conditions applied, knockout, death) in
the same pose-log panel that already renders the pose itself. The magic
end-to-end loop becomes visibly real for the first time.

The PR also corrects a clash-participation misdesign that the
unified-combat-UI build did not catch: the existing
`_clash_contribution_actions` surface emits both a FOCUSED and a PASSIVE
descriptor per active clash, implying players choose freely between
"committing" and "lending." That dichotomy is wrong by design. A clash is
**something a PC is bound to by their primary action** — there is no passive
contribution. Some PCs are principals (initiator, lock target); others may be
helpers if the clash flavor and their available techniques allow it. The
correct surface is at most one descriptor per (PC, clash), with eligibility
computed server-side. This PR rebuilds the descriptor surface and the
ActiveState rail accordingly.

### Why this matters now

Everything other than this loop is currently a half-finished story. The mechanical
engine resolves rounds correctly. The frontend renders the encounter, the
combatants, the action list. But a player who casts a Frost Bolt, hits the
resolve button, and looks at the pose log sees a pose chip with no readable
outcome — the panel says "No outcome details available." That gap is the
single biggest blocker to "fully playable magic." Closing it gates everything
downstream: playtest, content authoring iteration loops, the demo path a
designer walks to validate new techniques.

## Design pillars

- **One PR closes one user-visible story arc.** The cast-to-outcome loop, end
  to end. Not "add a join FK" or "expose a serializer field" — the whole
  visible chain.
- **Persisted effects, not transient dataclasses.** The current
  `RoundResolutionResult` is a frozen Python object that disappears when
  `resolve_round` returns. To render outcomes from a request to
  `action-outcome-details`, the effects must live in the database as typed
  rows. No JSONField.
- **One ACTION Interaction per mechanical action.** Both PC focused actions
  (`CombatRoundAction`) and clash contributions (`ClashContribution`)
  represent distinct mechanical events with distinct outcomes. Each gets its
  own ACTION-mode `Interaction` row that the pose log links to. This keeps
  the pose ↔ action bridge polymorphic without contenttypes.
- **Clash participation is role-driven, not menu-driven.** A PC is either
  bound to a clash (their focused action *is* the clash) or eligible to help
  (their focused action *can be* the clash if they pick that path) or
  uninvolved. The descriptor surface and the ActiveState rail reflect that
  shape — at most one action per (PC, clash), labelled by role.
- **The demo path is the integration test setup.** The
  `PlayableCombatScenarioFactory` chain is the single source of truth for
  "what does a playable encounter look like." Used by the new round-trip
  integration test AND by a `just demo-combat` admin recipe that materialises
  the same scenario for a logged-in user.

## Scope

**In scope:**

- New `CombatRoundAction.interaction` FK + `interaction_timestamp`
  denormalized field (composite-FK target onto partitioned `scenes_interaction`).
- New `ClashContribution.interaction` FK + `interaction_timestamp`.
- New service `create_action_interaction(participant, round_number)` —
  builds an ACTION-mode `Interaction` per resolved PC action / clash
  contribution. `Interaction.content` is the action's declaration label
  ("Frost Bolt at Pyromancer"), not pre-rendered outcome text.
- Wire `create_action_interaction` into `_resolve_pc_action` /
  `_resolve_clashes` / `run_clash_round` so every resolved action gets its
  `interaction` FK populated inside the same atomic `resolve_round` block.
- Replace the stub in `ActionOutcomeDetailsView._build_outcome_detail` with
  derivation from existing models — no new audit tables:
  - **Combo triggered:** from `action.combo_upgrade`.
  - **Check outcome (hit/miss/success-level):** from the `CheckOutcome` row
    reachable via the action's resolved technique resolution.
  - **Conditions applied:** from `ConditionInstance` rows correlated by
    `source_character` + `source_technique` + `applied_at` window matching
    the round resolution.
  - **Target status (DEFEATED / KO / DEAD):** from `CombatOpponent.status`
    / `CharacterVitals.status` at request time.
  - Per-row permission check (can the caller see this encounter?).
- Achievement counter increments at damage / KO / death apply-sites:
  `apply_damage_to_opponent`, `apply_damage_to_participant`, the
  survivability pipeline in `world.vitals.services`. Calls into the
  existing achievements app to increment named counters (e.g.
  `damage_dealt`, `killshots`, `times_kod`). No event log.
- `ClashStateSerializer` exposes `contributors` (per-PC ClashContribution
  rows for the active clash) and `side_favored` (computed: PC, NPC, or
  EVEN based on current progress vs thresholds).
- `CombatParticipant.available_strain` (computed property: total anima
  budget minus already-committed strain this round) exposed on
  `ParticipantSerializer`.
- Opposition system (Property-based, see dedicated section below):
  - `ThreatPoolEntry.effect_properties` M2M to `mechanics.Property` (the
    only new schema for opposition).
  - `ClashConfig.clash_min_intensity` global floor (default authored as
    seed content).
  - `can_clash(props_a, props_b) -> bool` predicate (Property-set overlap).
  - `_detect_clash_flavor` consumes property overlap + intensity floor for
    clash *creation*.
- Handlers (new, see dedicated section below):
  - `EncounterCombatHandler` — single cached queryset of encounter clash +
    round-action state; list-comp subsets; explicit invalidation.
  - `CharacterTechniqueHandler` — single cached list of character
    techniques + effect properties; list-comp subsets; explicit invalidation.
  - Service-function bodies in this PR run zero raw queries.
- Clash participation rewrite:
  - `is_pc_principal_in_clash(participant, clash, handler) -> bool` per-flavor.
  - `get_eligible_clash_techniques(participant, clash, ...) -> list[Technique]`
    filtered by `technique.clash_capable` AND `can_clash(technique props,
    clash opposition props)`. Reads from handlers.
  - `_clash_contribution_actions` rewrite: emit FOCUSED-only, narrow by
    role + technique eligibility, reads from handlers.
  - Auto-commit semantics for principals (their focused action is locked to
    the clash; the round-action declaration is the technique selection only).
  - Remove the PASSIVE descriptor emission. Keep the
    `ClashActionSlot.PASSIVE` enum value and the
    `ClashContributionDeclaration.action_slot` field for the data model
    (don't churn the schema in this PR) but they become unreachable from the
    public surface.
- `ActiveState` rewrite: single button per clash card, role-aware:
  - **Principal:** card shows "You are committed" badge + technique-picker
    hint, no button.
  - **Eligible helper:** "Commit" button, opens confirm-with-warn if
    another focused action is already declared, otherwise opens technique
    picker → submits.
  - **Ineligible PC:** status-only card, no button.
- Frontend `PoseUnitDetailPanel` renders the populated effect rows (already
  has the slot; just needs the backend to return non-empty effects).
- `YourTurn` strain slider reads `participant.available_strain` instead of
  hardcoded `max=10`.
- New `PlayableCombatScenarioFactory` chain in `src/world/combat/factories.py`
  (or a sibling) wiring Scene + CombatEncounter (DECLARING) + 2 PC
  CombatParticipants with full character sheets, vitals, techniques, threads
  with positive resonance balance + NPC CombatOpponent + active Clash.
- Full round-trip integration test using the factory as setUp.
- `just demo-combat` recipe that spawns the scenario for a logged-in dev
  user, plus an admin action that does the same.

**Out of scope (intentionally deferred):**

- **Damage numbers in the outcome panel.** Per the roadmap framing ("narrative
  RP game with combat mechanics, not a tactical game"), the panel shows
  narrative outcomes (combo, conditions, hit/miss, target status) without
  per-event damage amounts. The running narrative state is visible via
  `CombatantsList` vitals.
- **Damage / consequence audit tables.** No `ActionDamage`, no
  `ActionConsequence`. Achievement counters capture aggregate damage; server
  logs cover forensics; per-event audit is additive future work if a real
  use case demands it.
- **`Combatant` discriminator model + `CombatParticipant`/`CombatOpponent`
  merge + action-table merge.** The Combatant refactor was motivated by
  needing unified audit-target FKs; with the audit tables dropped, the
  refactor's motivation evaporates. Future PR if and when needed.
- **`ConditionInstance.source_action` FK.** Existing `source_character` +
  `source_technique` + `applied_at` provides adequate attribution for v1.
- Fatigue model exposure on `VitalPools` — its own coherent story arc, next
  beefy PR.
- `CombatOpponent` portrait FK — NPC avatars remain initials-only.
- Conditions data on `CombatantsList` rows.
- `submit_pose` REST endpoint WebSocket broadcast — narrow detach-case path.
- Focused-category resolution on the `PlayerAction` API surface (still
  stubbed `passive-physical`).
- Deep-link routing for outcome-detail effect rows. The `{modal, id}` skeleton
  in `PoseUnitDetailPanel` stays; actual `useNavigate` wiring lands when the
  modal targets exist.
- `Affinity`-based opposition layering on top of Property-opposition. The
  `AffinityInteraction` matrix (Primal > Celestial > Abyssal) stays
  in its existing role — feeding `affinity_tilt` for clash progress
  adjustments. Layering it on top of Property-opposition for finer
  eligibility is a follow-up.
- Removal of `ClashActionSlot.PASSIVE` from the data model and migration of
  existing `ClashContributionDeclaration` rows. The enum value stays but
  becomes unreachable. Schema cleanup in a follow-up.
- Scene-side `ScenePull` envelope; positioning / zones; mobile layout;
  full-state WebSocket push — all unchanged from the unified-combat-UI spec's
  "out of scope."

## Backend design

### Data model

**No new audit tables.** Effects rendered in the outcome panel derive from
data that's already persisted by existing systems:

| Effect | Persisted in | Reverse path from action |
| --- | --- | --- |
| Combo triggered | `CombatRoundAction.combo_upgrade` FK | direct |
| Check outcome (hit / miss / SL) | `CheckOutcome` row | via the action's technique resolution |
| Conditions applied | `ConditionInstance` rows | correlation by `source_character` + `source_technique` + `applied_at` |
| Target defeated / KO / DEAD | `CombatOpponent.status` / `CharacterVitals.status` | direct from target FK |
| Permanent wound | `ConditionInstance` (wound-flagged) | same correlation |

**What the PR adds is just the pose↔action linkage** — `Interaction` FKs on
the two action carriers (PC actions and clash contributions) so the pose
log knows what to link to.

#### `CombatRoundAction.interaction` + `interaction_timestamp`

```python
interaction = models.ForeignKey(
    "scenes.Interaction",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="combat_round_actions",
    db_constraint=False,
    help_text=(
        "The ACTION-mode Interaction created when this round-action "
        "resolved. Null for unresolved declarations and for legacy rows "
        "predating this PR."
    ),
)
interaction_timestamp = models.DateTimeField(
    null=True,
    blank=True,
    db_index=True,
    help_text=(
        "Denormalized from interaction.timestamp. Required because "
        "scenes_interaction is range-partitioned by timestamp — the composite "
        "FK constraint targets (interaction_id, interaction_timestamp). "
        "Populated atomically with interaction_id by create_action_interaction."
    ),
)
```

`db_constraint=False` on the FK because the composite constraint is added
in raw SQL (next subsection). `interaction_timestamp` is denormalized at
create time and treated as immutable thereafter — same invariant the
existing `InteractionAction.timestamp` field already maintains (see
`scenes/models.py` line 621).

#### `ClashContribution.interaction` + `interaction_timestamp`

Same shape. Related-name: `clash_contributions`.

#### Achievement counters at apply-sites

Damage and KO/Death/PermanentWound application sites get achievement
counter-increment calls:

```python
# In apply_damage_to_opponent (services.py):
opponent.health -= damage
# ...
from world.achievements.services import increment_counter  # noqa: PLC0415
increment_counter(source_character_sheet, "damage_dealt", damage)
if opponent.status == OpponentStatus.DEFEATED:
    increment_counter(source_character_sheet, "opponents_defeated", 1)

# In apply_damage_to_participant (services.py):
increment_counter(target_character_sheet, "damage_received", damage)

# In world.vitals.services.process_damage_consequences (or KO/death apply path):
increment_counter(source_character_sheet, "killshots", 1)  # on DEATH
increment_counter(source_character_sheet, "knockouts_dealt", 1)  # on KO
increment_counter(target_character_sheet, "times_kod", 1)  # on KO
```

Counter names are placeholder; final names live in the achievements app's
namespace. The `increment_counter(character_sheet, name, delta)` API is
assumed to exist in the achievements app — if not, the PR adds a thin
stub. **No event log row written.** The achievement system stores
aggregates; the per-event tuple is intentionally not persisted.

If a future feature genuinely needs per-event audit (replay UI, staff
forensics with structured queries, etc.), an additive `ActionDamage`-like
table can be added at that point — no schema blocker.

### Handlers

Service-function bodies in this PR run **zero raw queries**. All read paths
go through handlers; mutations explicitly invalidate the handler's cache.
Pattern: one underlying `cached_property` per handler that prefetches the
scope's full state in a single query plan; regular methods/properties do
list-comp subsets from that cache. Multiple cached querysets per handler is
an anti-pattern — risks stale-data divergence between caches and is
wasteful.

#### `EncounterCombatHandler`

Lives on `CombatEncounter` (or as a thin wrapper accessed via a property
`encounter.combat`). Caches the encounter's clash state, declared round
actions, and NPC actions for the current round. Replaces all the raw
`CombatRoundAction.objects.filter(...)`, `Clash.objects.filter(...)`, and
`CombatOpponentAction.objects.filter(...)` calls currently scattered across
`detect_clash_opportunities`, `_resolve_pc_action`, `_clash_contribution_actions`,
and `resolve_round`.

```python
class EncounterCombatHandler:
    """Encounter-scoped combat state with one prefetched cache."""

    def __init__(self, encounter: CombatEncounter) -> None:
        self.encounter = encounter

    @cached_property
    def _state(self) -> EncounterCombatState:
        """ONE prefetched queryset covering everything we need.

        Loads, for the current round:
          - all CombatRoundAction rows with focused_action, target, combo,
            and participant relations
          - all CombatOpponentAction rows with threat_entry + targets
          - all Clash rows with their ClashRounds and ClashContributions
          - all ClashContributionDeclarations
        """
        # Prefetch + select_related chain — see implementation.
        ...

    # All subset reads are list-comps on _state.

    def active_clashes(self) -> list[Clash]:
        return [c for c in self._state.clashes if c.status == ClashStatus.ACTIVE]

    def pc_actions_for_round(self, round_number: int) -> list[CombatRoundAction]:
        return [a for a in self._state.pc_actions if a.round_number == round_number]

    def npc_actions_for_round(self, round_number: int) -> list[CombatOpponentAction]:
        return [a for a in self._state.npc_actions if a.round_number == round_number]

    def principal_clashes_for(self, participant: CombatParticipant) -> list[Clash]:
        return [
            c for c in self._state.clashes
            if c.status == ClashStatus.ACTIVE
            and c.initiator_id == participant.character_sheet_id
        ]

    def contributions_for_clash(self, clash: Clash) -> list[ClashContribution]:
        return [
            contrib for cr in self._state.clash_rounds
            if cr.clash_id == clash.pk
            for contrib in cr.contributions
        ]

    def invalidate(self) -> None:
        """Drop the cache. Called by services that mutate clash/action state."""
        self.__dict__.pop("_state", None)
```

Invalidation contract: every service function in this PR that creates or
mutates a `Clash`, `ClashRound`, `ClashContribution`, `CombatRoundAction`,
or `CombatOpponentAction` row calls `handler.invalidate()` afterwards. The
caller is responsible for passing the handler around (it's typically built
once at the top of `resolve_round` and threaded through).

#### `CharacterTechniqueHandler`

Lives on the `Character` typeclass (alongside `character.combat_pulls`).
Caches the character's full technique inventory with effect properties
pre-resolved. Replaces the per-call walks of
`mechanics.services._get_technique_effect_property_ids` from inside the
clash-eligibility paths.

```python
class CharacterTechniqueHandler:
    """Character-scoped technique inventory with effect properties."""

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _state(self) -> list[CharacterTechniqueEntry]:
        """ONE prefetched queryset.

        Each entry: (Technique instance, frozenset[Property.pk]).
        Effect property IDs derive from technique.gift.cached_resonances
        × cached_properties via the existing prefetch chain in
        mechanics.services.
        """
        ...

    def all(self) -> list[Technique]:
        return [e.technique for e in self._state]

    def clash_capable(self) -> list[Technique]:
        return [e.technique for e in self._state if e.technique.clash_capable]

    def effect_property_ids_for(self, technique: Technique) -> frozenset[int]:
        for e in self._state:
            if e.technique.pk == technique.pk:
                return e.property_ids
        return frozenset()

    def helper_eligible_for(self, clash_props: frozenset[int]) -> list[Technique]:
        return [
            e.technique for e in self._state
            if e.technique.clash_capable and (e.property_ids & clash_props)
        ]

    def invalidate(self) -> None:
        self.__dict__.pop("_state", None)
```

Invalidation: called when the character is granted or has-revoked a
technique (existing `CharacterTechnique` mutation paths). For this PR the
invalidation surface is narrow — the demo/integration scenarios populate
techniques at setUp and don't change them mid-encounter.

#### Handler usage in service functions

Every service-function signature that previously took raw model instances
plus made queries to discover related state now takes a handler:

```python
# Before:
def _clash_contribution_actions(character: ObjectDB) -> list[PlayerAction]:
    ...
    encounter = participant.encounter
    active_clashes = list(Clash.objects.filter(encounter=encounter, ...))
    ...

# After:
def _clash_contribution_actions(
    character: ObjectDB,
    encounter_handler: EncounterCombatHandler,
    technique_handler: CharacterTechniqueHandler,
) -> list[PlayerAction]:
    ...
    for clash in encounter_handler.active_clashes():
        clash_props = technique_handler.effect_property_ids_for(
            clash.initiator_technique  # or NPC-side equivalent
        )
        eligible_techs = technique_handler.helper_eligible_for(clash_props)
        ...
```

This applies to `_detect_clash_flavor`, `get_eligible_clash_techniques`,
`is_pc_principal_in_clash`, `_clash_contribution_actions`,
`_resolve_pc_action`, `_resolve_clashes`, and the outcome-details
view (where the handler scope is per-Interaction-id lookup, see below).
None of these functions issue a raw `.objects.filter(...)`,
`.get()`, or `.select_related().prefetch_related()` call after this PR
lands. All such reads come from handlers.

### Services

#### `create_action_interaction`

Lives in a new `world/combat/interaction_services.py`:

```python
def create_action_interaction(
    *,
    participant: CombatParticipant,
    round_number: int,
) -> Interaction:
    """Create one ACTION-mode Interaction for a resolved action.

    Resolves the participant's primary persona and the encounter's scene,
    then writes the Interaction row with mode=ACTION and content set to the
    action's declaration label ("Frost Bolt at Pyromancer" — the technique
    name plus optional target name). The caller sets the FK on
    CombatRoundAction or ClashContribution.

    Raises ActionDispatchError(NO_PRIMARY_PERSONA) if the participant's
    character_sheet has no PRIMARY persona. This is a defensive assertion;
    add_participant validates this earlier.
    """
```

`Interaction.content` carries the **declaration**, not the outcome. The
outcome details are rendered live by the outcome-details endpoint from
existing model state. This keeps `Interaction.content` consistent across
ACTION rows — short, structured, declarative — while the outcome panel
remains structured.

Idempotency: not required — each resolved action runs through the
write-the-Interaction path exactly once per round inside the resolve_round
atomic block.

#### Resolve-round wiring

Inside `_resolve_pc_action`:

```python
def _resolve_pc_action(
    participant: CombatParticipant,
    action: CombatRoundAction,
    encounter_handler: EncounterCombatHandler,
    offense_check_fn: PerformCheckFn | None = None,
) -> ActionOutcome:
    outcome = ActionOutcome(...)
    # ... existing resolution logic computes outcome ...

    # NEW: just the Interaction linkage. No effect persistence.
    if action.focused_action is not None:  # skip passives-only rounds
        interaction = create_action_interaction(
            participant=participant,
            round_number=action.round_number,
        )
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp  # denormalize
        action.save(update_fields=["interaction", "interaction_timestamp"])
        encounter_handler.invalidate()

    return outcome
```

The `interaction_timestamp` denormalization is non-optional — the composite
FK constraint to the partitioned `scenes_interaction` requires both columns
populated. Set both fields in the same `save()` call.

For clash contributions, the equivalent wiring lives in `run_clash_round`
/ `aggregate_clash_round`:

```python
for contribution in round_result.contributions:
    interaction = create_action_interaction(
        participant=encounter_handler.participant_for_sheet(contribution.character),
        round_number=clash_round.round_number,
    )
    contribution.interaction = interaction
    contribution.interaction_timestamp = interaction.timestamp
    contribution.save(update_fields=["interaction", "interaction_timestamp"])
```

`ClashContribution` already carries everything the outcome panel needs for
clash side (`progress_delta`, `anima_committed`, `was_audere`,
`soulfray_severity_accrued`) — the panel reads those existing fields.

#### `ActionOutcomeDetailsView._build_outcome_detail` — derive from existing data

```python
def _build_outcome_detail(
    action_interaction_id: int,
    viewer: User,
) -> ActionOutcomeDetail:
    """Read effects from existing models — no audit tables required."""
    # Try CombatRoundAction first, then ClashContribution.
    action = (
        CombatRoundAction.objects.filter(interaction_id=action_interaction_id)
        .select_related(
            "participant__encounter__scene",
            "focused_action",
            "focused_opponent_target",
            "combo_upgrade",
        )
        .first()
    )
    if action is not None:
        if not _viewer_can_see(viewer, action.participant.encounter):
            return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])
        return _build_pc_action_detail(action, action_interaction_id)

    contribution = (
        ClashContribution.objects.filter(interaction_id=action_interaction_id)
        .select_related("clash_round__clash__encounter__scene", "technique", "check_outcome")
        .first()
    )
    if contribution is not None:
        if not _viewer_can_see(viewer, contribution.clash_round.clash.encounter):
            return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])
        return _build_clash_contribution_detail(contribution, action_interaction_id)

    return ActionOutcomeDetail(action_interaction_id=action_interaction_id, effects=[])


def _build_pc_action_detail(action: CombatRoundAction, ii_id: int) -> ActionOutcomeDetail:
    """Derive effect rows from existing models."""
    effects: list[EffectRow] = []

    # 1. Check outcome — reachable via the action's resolution. (CheckOutcome
    #    is created by perform_check; the resolved technique resolution path
    #    threads it back; FK chain depends on existing infrastructure.)
    check = _check_outcome_for_action(action)  # helper to be implemented
    if check is not None:
        effects.append(EffectRow(
            kind="check",
            label=f"{action.focused_action.name}: {check.get_success_level_display()}",
            deep_link=None,
        ))

    # 2. Combo triggered — direct FK.
    if action.combo_upgrade_id:
        effects.append(EffectRow(
            kind="combo",
            label=f"Combo: {action.combo_upgrade.name}",
            deep_link=DeepLinkRef(modal="combo", id=action.combo_upgrade_id),
        ))

    # 3. Conditions applied — correlate ConditionInstance by source_character
    #    + source_technique + applied_at window matching the round resolution.
    applied = _conditions_correlated_to_action(action)  # helper to be implemented
    for ci in applied:
        effects.append(EffectRow(
            kind="condition",
            label=f"Applied {ci.condition.name} to {ci.target.db_key}",
            deep_link=DeepLinkRef(modal="condition", id=ci.pk),
        ))

    # 4. Target status — read live.
    target = action.focused_opponent_target
    if target is not None:
        if target.status == OpponentStatus.DEFEATED:
            effects.append(EffectRow(
                kind="status",
                label=f"{target.name} defeated",
                deep_link=DeepLinkRef(modal="opponent", id=target.pk),
            ))

    return ActionOutcomeDetail(action_interaction_id=ii_id, effects=effects)
```

The `_conditions_correlated_to_action` helper filters `ConditionInstance`
rows by:
- `source_character = action.participant.character_sheet.character`
- `source_technique = action.focused_action`
- `applied_at` within the round's resolve window (e.g.
  `action.encounter.round_started_at <= applied_at <= now()`)

Two casts of the same technique in the same round on the same target can
still collide; for v1 we accept the correlation may over-attribute in that
edge case. If it becomes a problem we'd add the source_action FK on
ConditionInstance later (additive change).

The clash contribution panel reads directly from `ClashContribution`
fields — progress delta, anima committed, audere flag — and emits one
effect row per fact.

Visibility predicate `_viewer_can_see` mirrors the existing
`IsEncounterParticipant` / `IsInEncounterRoom` permission classes.
Returning an empty effect list for unauthorized viewers preserves the
pre-existing carry-forward behavior.

### Opposition system

Clash eligibility is **property-overlap, intensity-gated**. We do not
author a parallel "technique kind" taxonomy — `mechanics.Property` is the
existing abstraction for "what something IS," and it's exactly the right
fit. The change set is small: surface effect properties on threat entries
(currently absent), add a global minimum-intensity floor for clash opening,
and consume both in `_detect_clash_flavor`.

#### Property surface — what already exists

`mechanics.Property` ("neutral descriptive tag on targets or environments")
is the authored taxonomy. Categories already cover the relevant axes —
elemental, physical, social. Per-target attachments exist via
`ChallengeTemplateProperty` (per-challenge-template) and `ObjectProperty`
(per-runtime-object). Techniques already derive effect-property IDs through
`mechanics.services._get_technique_effect_property_ids(technique)`, which
walks `technique.gift.cached_resonances[*].cached_properties` — a
prefetch-chain-friendly path.

So a technique authoring its opposition surface is just authoring the
right `Property` rows on its Gift's Resonance. No new model.

#### What's new — `ThreatPoolEntry.effect_properties`

`ThreatPoolEntry` is the NPC-attack analogue of a Technique cast. Today it
has no Property linkage. We add one M2M:

```python
# On ThreatPoolEntry:
effect_properties = models.ManyToManyField(
    "mechanics.Property",
    blank=True,
    related_name="threat_pool_entries",
    help_text=(
        "Effect Properties this NPC attack carries. Drives clash-opposition "
        "matching against PC techniques' effect properties. Empty = attack "
        "cannot trigger or assist clashes."
    ),
)
```

Existing rows have an empty property set after migration; the opposition
predicate treats empty as "cannot clash."

#### What's new — `ClashConfig.clash_min_intensity`

`ClashConfig` is the existing singleton for clash tuning. Add a global
intensity floor:

```python
# On ClashConfig:
clash_min_intensity = models.PositiveIntegerField(
    default=4,
    help_text=(
        "Minimum effective intensity (technique.intensity + INTENSITY_BUMP "
        "pulls + future combatant ramp) for a clash to open. Prevents "
        "trivial round-1 clashes; clashes become available as players "
        "invest more power. Staff-tunable."
    ),
)
```

The default (placeholder `4`) is a tuning knob — to be calibrated against
seed content's typical round-1 intensity vs round-3+ intensity. Future
work (combatant-intensity-ramp, environmental-intensity mods) flows
through `compute_effective_intensity` and is automatically picked up by
this gate.

#### `can_clash` predicate

```python
def can_clash(
    props_a: set[int],
    props_b: set[int],
) -> bool:
    """Return True iff two effect-property sets share enough to clash.

    Inputs are sets of ``Property.pk``. Symmetric.

    Rule: any overlap = can clash. An empty set on either side returns
    False (unauthored content cannot clash).

    Property authoring is the gate. If "energy_blast" is too broad to use
    as a clash trigger, the authoring fix is "don't put it on techniques
    that shouldn't clash on it." Don't add taxonomy to compensate for
    authoring discipline.
    """
    if not props_a or not props_b:
        return False
    return bool(props_a & props_b)
```

#### `_detect_clash_flavor` update

Today's checks: `technique.clash_capable=True` AND
`threat_entry.clash_capable=True`. With the opposition system, two new
gates:

```python
# Inside _detect_clash_flavor, per (pc_action, npc_action) pair:

# Existing gates...
if not technique.clash_capable: continue
if not npc_action.threat_entry.clash_capable: continue

# NEW: property overlap.
pc_props = character_technique_handler.effect_property_ids_for(technique)
npc_props = npc_threat_handler.effect_property_ids_for(npc_action.threat_entry)
if not can_clash(pc_props, npc_props):
    continue

# NEW: intensity floor.
eff_intensity = compute_effective_intensity(pc_action.participant, pc_action)
if eff_intensity < clash_config.clash_min_intensity:
    continue

# Open the clash.
```

Both lookups go through handlers (next section) — no raw queries in this
detect body. `compute_effective_intensity` already exists and aggregates
the right things; future additions to its source set (combatant ramp,
environmental mods) automatically tighten the clash trigger without code
changes here.

#### What we deliberately don't do

- **No `TechniqueKind` / `TechniqueClashGroup`.** `Property` is the
  taxonomy.
- **No `Technique.effect_properties` direct M2M.** A technique's effect
  properties derive from `Gift → Resonance → Property` (existing). Adding
  a parallel direct M2M creates two sources-of-truth that drift.
- **No `Clash.primary_kind`.** The clash's "primary opposition properties"
  are derived live from the initiator's declared technique via the
  character-technique handler. If perf demands it later, cache by snapshotting
  Property IDs onto the Clash row at creation — but for v1 it's just a
  handler lookup.

### Clash participation rewrite

#### `is_pc_principal_in_clash`

```python
def is_pc_principal_in_clash(
    participant: CombatParticipant,
    clash: Clash,
) -> bool:
    """Return True iff this PC is bound to the clash by their primary action.

    Flavor rules:
    - CLASH: initiator is principal; no other PCs are principals (helpers may
      exist if eligible).
    - LOCK (sustaining): every PC who has a SUSTAINING role on this clash is
      a principal. For v1 with no role assignment, the initiator alone is
      principal.
    - LOCK (escaping): the locked PC is the principal. v1: initiator.
    - WARD: the targeted PC(s) are principals. v1: initiator alone (until
      ward-target-multiplicity is authored).
    - BREAK: initiator is principal.
    """
    if clash.initiator_id == participant.character_sheet_id:
        return True
    # v1: multi-principal logic deferred. Single principal = initiator.
    return False
```

The conservative v1 means: principal = clash.initiator. Multi-PC principal
(e.g. multiple PCs co-sustaining a lock) is data-model-ready but lacks
authored multiplicity; defer to the same future PR that adds positioning.

#### `get_eligible_clash_techniques`

```python
def get_eligible_clash_techniques(
    participant: CombatParticipant,
    clash: Clash,
    technique_handler: CharacterTechniqueHandler,
    encounter_handler: EncounterCombatHandler,
) -> list[Technique]:
    """Return clash-capable techniques this PC can use to help with `clash`.

    Reads through the character technique handler — no raw queries.
    Returns a plain list of Technique instances from the handler's cache.

    Rules:
    1. technique.clash_capable=True.
    2. can_clash(technique.effect_property_ids, clash.opposition_property_ids).

    "clash.opposition_property_ids" is derived live from the clash's
    initiator technique (or the triggering threat entry on NPC-initiated
    clashes) via the handler. v1: empty set → no eligible techniques.
    """
    clash_props = encounter_handler.opposition_property_ids_for(clash)
    return technique_handler.helper_eligible_for(clash_props)
```

#### `_clash_contribution_actions` rewrite

Replaces the existing function in `actions/player_interface.py`. New shape:

```python
def _clash_contribution_actions(character: ObjectDB) -> list[PlayerAction]:
    """Emit one PlayerAction per (PC, active clash) where the PC can contribute.

    Role-aware:
    - Principal: emit one descriptor with prerequisite_met=True, role=PRINCIPAL,
      eligible_technique_ids=[...]. The descriptor encodes that the PC's
      focused action is bound to this clash; the only thing they pick is the
      fueling technique.
    - Eligible helper: emit one descriptor with role=HELPER. The frontend
      shows it in the action list; selecting it makes the clash the PC's
      focused action (with confirm-with-warn if another focused action is
      already declared).
    - Ineligible: no descriptor.

    No PASSIVE descriptors emitted. Ever.
    """
```

The `PlayerAction` shape gets a `clash_role` field (PRINCIPAL / HELPER) on
the ActionRef so the frontend can render appropriately. Adding this field to
the existing `ActionRef` is additive (nullable str); no migration of
existing refs.

#### Auto-commit semantics for principals

When a clash is created (via `detect_clash_opportunities` →
`create_clash`), the principal's focused action for the round is
auto-committed to the clash. Concrete shape:

- The principal's `CombatRoundAction.focused_action` is set to a
  designated "Clash contribution" sentinel — *unless* the principal has
  already declared a focused action this round, in which case the existing
  declaration is **overridden** (with a `ClashCommitOverride` log entry
  written for audit).
- The principal's `_clash_contribution_actions` descriptor surfaces the
  technique picker; submitting picks the fueling technique. If the PC does
  not pick a technique by the resolve deadline, a default technique is
  selected (the first clash-capable one they have); if none exists, the
  contribution is a no-op for the round (defensive — should not happen if
  the principal was correctly classified).

This is a behavior change for principals; called out explicitly in the
migration / rollout section.

#### `ActiveState` rendering

Three card states:

| PC role         | Card content                                                       |
| --------------- | ------------------------------------------------------------------ |
| Principal       | "You are committed to this clash" badge + technique-picker hint    |
| Eligible helper | "Commit" button → opens confirm-with-warn / technique picker modal |
| Ineligible      | Status display only (meter + contributors + side_favored)          |

The card always shows the meter, the contributor list, and the side_favored
chip — those are status, not action.

### Serializer changes

#### `ClashStateSerializer`

Add two fields:

```python
class ClashStateSerializer(serializers.ModelSerializer):
    contributors = serializers.SerializerMethodField()
    side_favored = serializers.SerializerMethodField()

    class Meta:
        model = Clash
        fields = [
            "id", "flavor", "status", "progress",
            "pc_win_threshold", "npc_win_threshold", "npc_opponent",
            "contributors", "side_favored",
        ]

    def get_contributors(self, obj: Clash) -> list[dict]:
        """Per-PC contribution rollup for the active clash round."""
        # Walk obj.cached_contributions (Prefetch in EncounterDetailSerializer)
        # → group by character → render {character_id, character_name,
        # action_slot, progress_delta}.
        ...

    def get_side_favored(self, obj: Clash) -> str:
        """PC, NPC, or EVEN based on current progress vs thresholds."""
        if obj.progress >= obj.pc_win_threshold * 0.75:
            return "PC"
        if obj.npc_win_threshold is not None and obj.progress <= obj.npc_win_threshold * 0.75:
            return "NPC"
        return "EVEN"
```

The 0.75 threshold is an authored tuning knob — for v1, hardcode it; expose
as a `ClashConfig` field in a follow-up if playtest reveals it needs tuning.

#### `ParticipantSerializer`

Add `available_strain`:

```python
available_strain = serializers.SerializerMethodField()

def get_available_strain(self, obj: CombatParticipant) -> int | None:
    """Available strain budget for the round — only visible to viewer's own PC."""
    if not self._can_view_vitals(obj):
        return None
    return obj.available_strain  # computed property on the model
```

`CombatParticipant.available_strain` as a model property:

```python
@property
def available_strain(self) -> int:
    """Anima budget minus strain already committed this round."""
    sheet = self.character_sheet
    total_anima = sheet.vitals.current_anima  # or wherever lives
    # Walk pending ClashContributionDeclarations for the active round and
    # subtract committed strain. v1: just return total_anima; the slider
    # currently does the subtraction client-side from the existing per-clash
    # strain map.
    return total_anima
```

The v1 implementation just exposes `current_anima` as the slider max — the
slider's "strain committed across clashes" tracking is already client-side.
A future iteration may move the subtraction server-side; not in scope here.

## Frontend design

### `PoseUnitDetailPanel`

No structural change — the component already renders the `effects` array.
Just needs the backend to return non-empty rows. One small enhancement: kind
badge colour mapping extends for the new kinds (KNOCKOUT, DEATH,
PERMANENT_WOUND, CLASH_PROGRESS, COMBO_TRIGGERED, PHASE_TRANSITION).

### `ActiveState` rewrite

`ActiveState.tsx` accepts the now-richer clash state including contributors,
side_favored, and (via the encounter detail) the per-PC role on each clash.
Card layout becomes:

```
┌─ Suppress vs Pyromancer ───────────  side: PC ┐
│  Progress  ░░░░▓▓▓▓▓▓▓▓ 12/20 PC                │
│  Contributors:                                  │
│   ▸ Lyssa (focused, +4)                         │
│   ▸ Brand (focused, +2)                         │
│  ▼ You are committed (Frost Bolt selected)      │
└─────────────────────────────────────────────────┘
```

For helpers, the footer slot is a `[Commit]` button. For ineligible PCs,
the footer is empty.

`onCommitClick` is wired to `useDispatchPlayerAction` with the FOCUSED
clash descriptor. The confirm-with-warn modal is a new small component
(`ClashCommitConfirm`) — opens when a focused action is already declared and
asks "Replace your declared X with this clash commitment?"

### `YourTurn` strain slider

`max={participant.available_strain}` replaces `max={10}`. The slider's
existing `strainByClash` map continues to work unchanged.

### `useDispatchPlayerAction` for clash

Already exists in YourTurn for clash declarations. ActiveState re-uses it
via the shared hook — no duplicate dispatch path.

## Migration / rollout

### Schema migrations

Two migrations. The Django ORM migration is thin; the raw SQL lives in
committed `.sql` files (durable artifact that survives migration wipes
pre-prod, mirroring `scenes/sql/partition_interaction_forward.sql`).

| Migration | App | Contents |
| --- | --- | --- |
| `00XX_resolution_loop_models` | combat | ORM-only. Adds `CombatRoundAction.interaction` + `interaction_timestamp`. Adds `ClashContribution.interaction` + `interaction_timestamp`. Adds `ThreatPoolEntry.effect_properties` M2M to `mechanics.Property`. Adds `ClashConfig.clash_min_intensity`. `db_constraint=False` on the `interaction` FKs since the composite constraint is added by the next migration. |
| `00YY_interaction_fk_composites` | combat | Raw SQL via `migrations.RunSQL(_read_sql(...))`. Files: `combat/sql/interaction_fk_composites_forward.sql` + `_reverse.sql`. Adds composite FK constraints `(interaction_id, interaction_timestamp) → scenes_interaction (id, timestamp)` on `combat_combatroundaction` and `combat_clashcontribution`. `ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED`. |

**Raw SQL discipline:** every `migrations.RunSQL(...)` call reads from a
committed `.sql` file. No inline SQL strings in migration files. Same
pattern `scenes/migrations/0003_partition_interaction.py` already follows:

```python
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()

class Migration(migrations.Migration):
    operations = [
        migrations.RunSQL(
            sql=_read_sql("interaction_fk_composites_forward.sql"),
            reverse_sql=_read_sql("interaction_fk_composites_reverse.sql"),
        ),
    ]
```

SQL files committed to `src/world/combat/sql/`:
- `interaction_fk_composites_forward.sql`
- `interaction_fk_composites_reverse.sql`

Pre-prod migration wipes don't lose this work — the SQL files are the
durable artifact; the new post-wipe migrations re-reference them.

No magic-app, conditions-app, or partition migrations needed: the
opposition system uses existing `mechanics.Property`; conditions don't
need a new FK (existing `source_character` + `source_technique` are
sufficient); nothing in this PR has the row volume that justifies
partitioning.

### Seed content

`CombatContent.create_all()` (the staff-runnable content seeder pattern)
gains a small block:

- Sets `ClashConfig.clash_min_intensity` to its tuned default.
- Ensures the `Property` rows the demo path's techniques and threat entries
  reference exist (these are typically already in the mechanics seed
  content — verify and add any gaps).
- The `PlayableCombatScenarioFactory` (Phase 10) authors `effect_properties`
  on its demo techniques and threat entries so the demo path actually
  triggers a clash.

Broader backfill of existing technique Gifts and threat entries with
authored `effect_properties` is staff-driven via the admin — outside this
migration.

### Backwards compatibility

- Existing `CombatRoundAction` rows have `interaction=null` — outcome-details
  endpoint returns empty effects for them. Acceptable; legacy data wasn't
  surfaceable anyway.
- Existing `ClashContributionDeclaration` rows with `action_slot=PASSIVE`
  remain in the DB. They'll never be referenced by a new declaration, but
  they don't break any read paths.
- `_clash_contribution_actions` rewrite is a behavior change for any
  existing PASSIVE descriptor consumers. Search shows the only consumer is
  the unified action endpoint; the frontend ActiveState button wiring is
  also rewritten in this PR, so no orphan code paths.

### Auto-commit behavior change for principals

This PR changes principal behavior: a PC who is the initiator of a clash
no longer has their original focused action survive the clash creation. If
they had declared "Frost Bolt vs Pyromancer" and then a SUPPRESS clash
gets created with them as the initiator, their focused action is overridden
to "Clash contribution (technique tbd)."

The `ClashCommitOverride` audit row records this — staff/GM admin views can
see what was replaced. Player-facing: the YourTurn panel shows a system
message "Your focused action was committed to a clash" the first time it
happens that round.

## Testing strategy

### Backend unit tests

- `test_create_action_interaction.py` — Interaction created with correct
  scene/persona/mode/timestamp/content. Missing primary persona raises.
- `test_resolve_round_interaction_linkage.py` — after `resolve_round`, every
  CombatRoundAction with a focused_action has a populated `interaction` +
  `interaction_timestamp`; every ClashContribution has both populated.
- `test_can_clash.py` — Property-overlap predicate: empty sets, no overlap,
  overlap, symmetric.
- `test_detect_clash_with_properties.py` — property-overlap pairs with
  sufficient intensity open clashes; no-overlap pairs do not; sub-threshold
  intensity pairs do not.
- `test_clash_participation.py` — `is_pc_principal_in_clash` per flavor;
  `get_eligible_clash_techniques` filter chain; `_clash_contribution_actions`
  emits the right descriptors per role.
- `test_action_outcome_details_view.py` — endpoint returns derived effect rows
  (combo, check, conditions, target status); permission gating; unknown ids
  return empty effects (not 404).
- `test_participant_available_strain.py` — strain budget computation.
- `test_clash_state_serializer.py` — contributors + side_favored fields.
- `test_achievement_counter_increments.py` — counter calls fire at
  apply_damage_to_opponent, apply_damage_to_participant, KO transitions,
  death transitions.
- `test_handlers.py` — `EncounterCombatHandler` and `CharacterTechniqueHandler`
  cache the right rows, list-comp subsets return correct subsets, no extra
  queries on subsequent reads (assertNumQueries), invalidation works.

### Backend integration tests

- `test_combat_resolution_loop.py` — single round-trip: build
  PlayableCombatScenarioFactory, declare an action via the dispatch API,
  resolve_round, fetch outcome-details, assert the effects render. This is
  the smoke test that proves the cast → outcome loop is alive.

### Frontend tests

- `PoseUnitDetailPanel.test.tsx` — renders all effect kinds; renders correct
  badge colours; handles empty effects gracefully.
- `ActiveState.test.tsx` — renders principal / helper / ineligible cards;
  Commit button dispatches; confirm-with-warn appears when a focused action
  is declared.
- `YourTurn.test.tsx` — strain slider max reads from `available_strain`.

### Demo path

- `just demo-combat` materialises the scenario for a dev user. Manual smoke:
  log in as the dev user, navigate to the spawned scene, declare an action,
  resolve, verify the pose log + outcome panel render real effects.

## Known limits

- **Multi-principal clashes (e.g. multi-PC LOCK sustainment) are not
  surfaced.** v1 principal = `clash.initiator` only.
- **Outcome-details endpoint does an O(N) lookup over ids.** Acceptable for
  typical request sizes (1-5 ids); batch optimisation deferred.
- **The PASSIVE clash slot stays in the data model but is unreachable from
  the public surface.** Schema cleanup is a follow-up; this PR doesn't
  churn the schema.
- **Per-pose visibility on outcome-details is encounter-scoped, not
  pose-scoped.** Anyone who can see the encounter can see all of its effect
  rows. POV-filtering by pose privacy / persona discovery is a future
  iteration.
- **Legacy techniques and threat entries with empty effect_properties are
  inert in the opposition system.** They cannot trigger clashes
  (`_detect_clash_flavor` skips), and they cannot help clashes (`can_clash`
  returns False for empty sets). Staff backfills via the admin over time.
  The migration does not attempt to guess properties for existing content.
- **Existing `Clash` rows opened before this PR have whatever opposition
  state they had at creation.** Helper eligibility on those clashes derives
  from the initiator's technique properties (live lookup). If the
  initiator's technique has empty effect_properties, no helpers are
  eligible. Principals on legacy clashes are unaffected (bound regardless).
- **No structured damage / KO / death event log.** Achievement counters
  track aggregates; per-event audit is not persisted. The outcome panel
  shows narrative outcomes (combo, conditions, hit/miss, target status)
  without per-event damage amounts. If a future feature wants per-event
  audit (replay UI, structured forensic queries), an `ActionDamage` /
  `ActionConsequence` table can be added additively.
- **Same-technique-same-round-same-target condition attribution is fuzzy.**
  The outcome-details endpoint correlates ConditionInstance rows by
  `source_character` + `source_technique` + `applied_at`. Two casts of
  the same technique by the same character in the same round on the same
  target would collide. Adding `ConditionInstance.source_action` is
  additive when needed.
- **Outcome-details over-attribution edge case.** If a PC casts the same
  technique twice in the same round on different targets, the
  ConditionInstance correlation can attribute conditions to the wrong
  action. Edge case; adding source_action FK on ConditionInstance fixes
  it later.
- **Property authoring is the gate.** No `PropertyCategory`-restricted
  "clash-bearing" subset — any Property overlap counts. If a Property is
  too broad to mean clash-opposition, the authoring fix is to scope it
  more narrowly or to *not* put it on techniques that shouldn't clash
  on it. Don't add taxonomy to compensate for authoring discipline.
- **`compute_effective_intensity` is the single source of truth for
  intensity gating.** v1 inputs are `technique.intensity` +
  `INTENSITY_BUMP` pulls. The "combatant intensity that ramps over rounds"
  the design calls for is a future addition to that function's source set
  — when it lands, this PR's clash gating automatically picks it up.
- **`Affinity` + `AffinityInteraction` stays in its existing role** (clash
  `affinity_tilt` for progress adjustments). Layered onto Property-opposition
  for finer helper eligibility is a follow-up.

## Out of scope (re-statement for clarity)

- Damage / consequence audit tables (`ActionDamage`, `ActionConsequence`).
- `Combatant` / `CombatantAction` unification of CombatParticipant +
  CombatOpponent — deferred until a use case actually demands it.
- Fatigue model end-to-end (VitalPools real values, fatigue accrual per
  dispatch). Its own next-PR.
- CombatOpponent portrait FK.
- Conditions on CombatantsList rows.
- WebSocket broadcast for submit_pose detach-case path.
- Focused-category resolution on PlayerAction API (still stubbed
  `passive-physical`).
- Deep-link routing for outcome-detail effect rows.
- Scene-side ScenePull envelope.
- Positioning / zones integration.
- Mobile responsive layout.
- Full-state WebSocket push for combat.

## Open questions

None blocking — all design decisions either land in this spec or are
explicitly deferred in Known limits. If something turns up during
implementation, surface it before charging ahead.

---

## Implementation addendum — reactive maneuvers (#1273)

**Status: BUILT** (PR #1273 — INTERPOSE maneuver + DEFEND stance)

### resolve_round ordering change

`resolve_round` in `world/combat/services.py` now runs three steps **before** the
focused-action loop:

```
_resolve_passive_actions(encounter, pc_actions)   # 1. apply passive techniques → installs conditions
_refresh_participant_trigger_handlers(encounter)  # 2. sync TriggerHandlers so reactive triggers fire this round
_ensure_interpose_challenges(encounter, pc_actions)  # 3. mint ChallengeInstances for armed INTERPOSE actions
# --- focused-action loop (_resolve_actions) ---
```

Step 2 is new: `_refresh_participant_trigger_handlers` calls `TriggerHandler.refresh()` on
every active participant, ensuring that reactive triggers installed by passive conditions
(e.g. the "Shielded" trigger from the DEFEND stance) are live before NPC attacks resolve.
Without this call, a passive-installed trigger would fire only in the *next* round.

### DAMAGE_PRE_APPLY interpose seam

Inside `apply_damage_to_participant` (the NPC-attack damage write path), before the
payload reaches vitals, `_try_interpose` fires:

```
apply_damage_to_participant(participant, pre_payload)
  → emit_event(DAMAGE_PRE_APPLY, pre_payload)   # DEFEND's Shielded trigger runs here → multiply 0.5
  → _try_interpose(participant, pre_payload)     # find armed INTERPOSE challenge, dispatch if present
     → dispatch_interpose(interposer, protected, pre_payload)
        → dispatch_capability_reaction(...)       # resolve_challenge → CheckOutcome
        → apply_interpose_outcome(pre_payload, result):
            SUCCESS  → pre_payload.amount = 0
            PARTIAL  → pre_payload.amount //= 2
            FAILURE  → no-op
  → vitals.health -= pre_payload.amount          # reduced (possibly 0) amount applied
```

DEFEND and INTERPOSE **compose**: DEFEND's `MODIFY_PAYLOAD multiply 0.5` fires in the
flows layer (step 1), then `_try_interpose` sees the already-halved amount (step 2).
A clean INTERPOSE after DEFEND zeroes the remaining half.

### INTERPOSE maneuver

- Declaration: `declare_interpose(participant, ally)` → `CombatRoundAction.maneuver=INTERPOSE`
  + `focused_ally_target=ally`. Mirrors the COVER maneuver shape.
- Challenge setup: `_ensure_interpose_challenges` mints one `ChallengeInstance` per armed
  INTERPOSE per round (idempotent). Challenge template seeded by `ensure_interpose_content()`.
- Fatigue: charged `INTERPOSE_BASE_FATIGUE_COST` only when the challenge fires, not on declaration.
- Capability gates: telekinesis, shield, barrier, pull_aside (pure data — adding new capabilities
  is a `CapabilityType` + `Application` + `ChallengeApproach` row, no engine change).

### DEFEND stance

- Seeded by `ensure_defend_content()` (`src/world/combat/defend_content.py`).
- Passive `Technique` → `TechniqueAppliedCondition(target_kind=ALLY, condition=Shielded)`.
- "Shielded" `ConditionTemplate` carries a `reactive_triggers` M2M to a `TriggerDefinition`
  on `DAMAGE_PRE_APPLY` with `base_filter_condition=_SELF_TARGET_FILTER` (fires only when
  `payload.target == trigger.obj`, i.e. the shielded ally is the damage target).
- Flow: `FlowDefinition` with a single `MODIFY_PAYLOAD` step
  `{"field": "amount", "op": "multiply", "value": 0.5}`.
- `bulk_apply_conditions` now calls `_install_reactive_side_effects` (was skipped before
  #1273); passive-applied conditions register their reactive triggers in the same batch.

## Implementation addendum — telegraphed wind-ups + reaction economy (#2637, #2639)

**Status: BUILT** (ADR-0156 — extends the pre-armed-declaration shape ADR-0118
established for guardian reactions to a symmetric NPC-side commitment)

### `resolve_round` ordering change

Two new steps bracket the existing per-round pipeline:

```
enc.status != DECLARING? raise
already_selected = CombatOpponentAction OR PendingOpponentAttack exists for this round?
  no  → select_npc_actions(enc)        # 0. wiring-gap fallback — see below (still DECLARING)
enc.status = RESOLVING; enc.save(...)
round_number = enc.round_number
_fire_round_start(enc, round_number)
# ...vulnerability countdown...
_mature_pending_opponent_attacks(enc, round_number)  # NEW — before the query below
# --- Build action lookups (queries CombatOpponentAction for this round) ---
_resolve_passive_actions(...)
_refresh_participant_trigger_handlers(...)
_ensure_reactive_challenges(...)
_resolve_actions(...)  # PC loop calls _apply_windup_interception_rider after each landed hit
```

Maturation runs BEFORE the `CombatOpponentAction` query so a wind-up that matures THIS
round is picked up by the normal NPC-resolution pipeline in the same pass — no second
resolution pass, no special-cased NPC action type downstream of that query.

### Wind-up declare → telegraph → wreck → mature flow

```
_build_opponent_round_actions (NPC declaration, still DECLARING)
  chosen = weighted-random ThreatPoolEntry
  chosen.windup_rounds > 0?
    yes → _declare_windup_attack
            → PendingOpponentAttack.objects.create(declared_round=N, resolves_round=N+windup_rounds)
            → _find_windup_caller (auto-callout, at most 1/round/encounter, #2637 design 6)
            → _broadcast_windup_telegraph → _dual_dispatch_combat_narration (WS + telnet)
          (NO same-round CombatOpponentAction — the round's NPC action budget for this
           attack is spent on the telegraph instead)
    no  → CombatOpponentAction.objects.create(round_number=N, ...)   # unchanged

# ...zero or more rounds pass; the PendingOpponentAttack just sits there...

_resolve_pc_action (any PC's landed hit on the winding-up opponent, PC resolution loop)
  target = action.focused_opponent_target
  damage landed (> 0) on target?
    yes → _apply_windup_interception_rider
            → pending = PendingOpponentAttack.objects.filter(opponent=target,
                          resolves_round__gte=round_number).first()
            → pending.downgrades += (2 if pending.called_out else 1)
            → _broadcast_windup_wreck                       # "X's strike staggers the wind-up!"

# ...round advances until resolves_round == round_number...

_mature_pending_opponent_attacks (top of resolve_round, resolves_round == round_number)
  downgrades >= 3 (WINDUP_FIZZLE_DOWNGRADES)?
    yes → _broadcast_windup_fizzled; pending.delete()         # the perfect chain — cancel, earned
    no  → damage_scale = max(0.25, 1 - 0.25*downgrades)
          CombatOpponentAction.objects.create(round_number=N, threat_entry=..., damage_scale=...)
          (targets re-derived from the pending row's target / re-selected pool)
          pending.delete()
  # resolve_npc_attack / the flat-damage path both read damage_scale, multiplying it
  # in AFTER opponent.damage_multiplier (a Decimal field) to avoid a Decimal*float TypeError
```

### The reaction economy fire seam (#2639, F-10c)

`_dispatch_interpose_action` — the shared tail `_try_interpose` (PC ward) and
`_try_interpose_for_opponent` (ALLY-summon ward) both call — gates on TWO independent
budgets before doing anything else:

```
_dispatch_interpose_action(action, protected, pre_payload)
  action.participant.reactions_used >= REACTIONS_PER_ROUND (1)?      → return (no-op)
  pre_payload.answers_consumed >= ABSORPTION_CAP_PER_MOMENT (2)?     → return (no-op)
  action.participant.reactions_used += 1; save()
  pre_payload.answers_consumed += 1
  # ...existing technique-vs-mundane branch, unchanged...
```

`reactions_used` resets to 0 for every `CombatParticipant` in `begin_declaration_phase`
— via an identity-map-safe `bulk_update` over freshly-queried instances, NOT a raw
queryset `.update()`. A raw `.update()` bypasses `SharedMemoryModel`'s instance cache
entirely: any already-cached `CombatParticipant` Python object (the common case — the
participant was already loaded upstream this request) keeps reading its stale
pre-reset value, and `refresh_from_db()` does NOT fix this for an idmapper model — its
`__call__` override returns the SAME cached instance instead of re-hydrating it from
the row. `bulk_update` mutates the actual cached instances' attributes directly before
persisting, so both the DB row and every live reference agree.

### The `select_npc_actions` wiring gap (#2637 design 8)

Investigated in-PR: `select_npc_actions` had zero production callers outside the
simulation harness (`world/combat/simulation.py`) — `commands/battle.py`,
`actions/definitions/gm_combat.py`, `world/combat/views.py`, and `world/combat/tasks.py`
all call `resolve_round` directly, none of them call `select_npc_actions` first. NPCs
never selected actions in live play. `resolve_round`'s new fallback (see the ordering
change above) closes this conservatively — it only fires when the round has ZERO
selection of either shape yet, so any explicit prior selection (staff, the simulation
harness, tests that call `select_npc_actions` themselves) is left untouched.
