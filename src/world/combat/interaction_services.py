"""Interaction-creation service for resolved combat actions.

When the resolve_round pipeline finishes a PC action or a clash contribution,
it creates an ACTION-mode ``Interaction`` row so the pose log can link to it.
The ``Interaction.content`` carries the **declaration label** of the action
(e.g. "Frost Bolt at Pyromancer") — not pre-rendered outcome text. Outcome
details are derived live by ``views_outcome_details`` from existing model
state (combo, conditions, vitals).

Phase 3 — combat-resolution-loop PR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ClashResolution, EncounterOutcome
from world.magic.narration import power_outcome_clause, signature_clause
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction

if TYPE_CHECKING:
    from world.combat.models import (
        ClashContribution,
        CombatEncounter,
        CombatOpponentAction,
        CombatParticipant,
        CombatRoundAction,
    )
    from world.combat.types import ActionOutcome
    from world.conditions.types import DamageInteractionResult
    from world.magic.models import FuryTier
    from world.magic.types.power_ledger import PowerLedger


def create_action_interaction(
    *,
    participant: CombatParticipant,
    round_number: int,
    summary_label: str,
    strain_committed: int = 0,
    fury_committed: FuryTier | None = None,
) -> Interaction | None:
    """Create one ACTION-mode Interaction for a resolved action.

    Args:
        participant: The PC participant whose action resolved.
        round_number: The encounter round this resolution happened in. Currently
            informational; the Interaction itself carries timestamp via
            auto_now_add.
        summary_label: Short label for ``Interaction.content`` — the action's
            declaration text. Examples: "Frost Bolt at Pyromancer",
            "Strain commitment to Suppress vs Pyromancer".
        strain_committed: Strain the participant actually committed for this
            action. Recorded on the resulting Interaction's canonical
            ``strain_committed`` audit column. Defaults to 0 for non-clash
            actions that do not commit strain.

    Returns:
        The newly-created Interaction row, or ``None`` if the participant's
        character sheet has no PRIMARY persona (legacy fixture content predating
        the create_character_with_sheet invariant — skipped silently to allow
        the resolve loop to continue without writing a pose-log link).
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    sheet = participant.character_sheet
    try:
        persona = sheet.primary_persona
    except Persona.DoesNotExist:
        # Legacy fixture content; skip Interaction creation. The action still
        # resolves; it just won't have a pose-log link.
        return None

    encounter = participant.encounter
    scene = encounter.scene  # always set since #1236; passed through to Interaction.scene

    # The round_number parameter is currently informational — it's encoded in
    # the action row that calls this, and Interaction.timestamp gives temporal
    # ordering. Kept in the signature so callers can pass it without having to
    # walk back through the action.
    del round_number

    from world.scenes.interaction_services import create_action_interaction_core  # noqa: PLC0415

    return create_action_interaction_core(
        persona=persona,
        scene=scene,
        summary_label=summary_label,
        strain_committed=strain_committed,
        fury_committed=fury_committed,
    )


def create_npc_action_interaction(
    *,
    opponent_action: CombatOpponentAction,
    target_label: str | None = None,
) -> Interaction:
    """Create one ACTION-mode Interaction for a resolving NPC action.

    NPC opponents have no PRIMARY persona, so the interaction is authored by the
    Narrator persona (same persona used for OUTCOME narration). It anchors the
    survivability ConsequenceOutcome records (#850) created when the NPC's hit
    drives a PC toward knockout/death/wound, so those outcomes link back to a
    real pose-log row.

    The encounter's scene is always set since #1236; it is passed through to
    Interaction.scene (which remains nullable for non-combat interactions).
    """
    from world.combat.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    threat = opponent_action.threat_entry
    content = f"{threat.name} at {target_label}" if target_label else threat.name
    narrator = get_or_create_narrator_persona()
    scene = opponent_action.opponent.encounter.scene
    return Interaction.objects.create(
        persona=narrator,
        scene=scene,
        content=content,
        mode=InteractionMode.ACTION,
    )


def render_action_declaration_label(action: CombatRoundAction) -> str:
    """Render a one-line declaration label for an ACTION Interaction's content.

    Format: ``<TechniqueName> at <TargetName>`` for targeted attacks;
    ``<TechniqueName>`` alone when no target. Falls back to ``"passives only"``
    when ``focused_action`` is null (which the resolver normally skips, but
    surfacing a non-empty string is safer than empty content).
    """
    technique = action.focused_action
    if technique is None:
        return "passives only"

    if action.focused_opponent_target_id is not None:
        target_name = action.focused_opponent_target.name
        return f"{technique.name} at {target_name}"
    if action.focused_ally_target_id is not None:
        ally = action.focused_ally_target
        target_name = ally.character_sheet.character.db_key
        return f"{technique.name} at {target_name}"
    return technique.name


def render_clash_contribution_label(contribution: ClashContribution) -> str:
    """Render a one-line declaration label for a clash contribution.

    Format: ``<TechniqueName> → <ClashFlavor> vs <OpponentName>``.
    """
    technique = contribution.technique
    clash = contribution.clash_round.clash
    flavor = clash.get_flavor_display()
    opponent_name = clash.npc_opponent.name if clash.npc_opponent_id else "?"
    return f"{technique.name} → {flavor} vs {opponent_name}"


def _build_tail_clauses(
    *, wounds: list[str], defeated: bool, dying: bool, knocked_out: bool
) -> list[str]:
    """Collect the consequence tail clauses for a damage hit."""
    tail: list[str] = []
    if wounds:
        tail.append("leaving them " + ", ".join(wounds))
    if defeated:
        tail.append("defeating them")
    elif dying:
        tail.append("leaving them dying")
    elif knocked_out:
        tail.append("knocking them out")
    return tail


def _assemble_hit_line(head: str, tail_clauses: list[str], power_clause: str) -> str:
    """Compose the damage-hit narration line from its constituent parts."""
    body = head + (", " + ", ".join(tail_clauses) if tail_clauses else "")
    return f"{body} {power_clause}." if power_clause else f"{body}."


def synergy_clause(interaction_result: DamageInteractionResult | None) -> str | None:
    """Compose a suffix clause for condition-damage interactions that fired.

    Returns None (no clause) when:
    - No interaction result (None).
    - Only a silent modifier applied (no condition removed or applied).

    Returns a clause when an interaction caused a condition transition
    (removal or application). If the interaction has an authored
    ``narration_snippet``, it is used; otherwise a deterministic fallback is
    composed from the condition name + interaction kind.

    When the modifier is non-zero and a transition occurred, the modifier
    percentage is appended (e.g. " (+50%)").
    """
    if interaction_result is None:
        return None

    # Only narrate transitions — a pure modifier with no removal/apply is
    # silent math (anti-spam rule, spec decision #1).
    transition_interactions = [
        i
        for i in interaction_result.fired_interactions
        if i.removes_condition or i.applies_condition is not None
    ]
    if not transition_interactions:
        return None

    parts: list[str] = []
    for interaction in transition_interactions:
        if interaction.narration_snippet:
            parts.append(interaction.narration_snippet)
        elif interaction.removes_condition:
            parts.append(f"{interaction.condition.name} shatters")
        elif interaction.applies_condition is not None:
            parts.append(
                f"{interaction.condition.name} transforms into {interaction.applies_condition.name}"
            )

    clause = " — ".join(parts)

    # Append the modifier if non-zero.
    if interaction_result.damage_modifier_percent != 0:
        sign = "+" if interaction_result.damage_modifier_percent > 0 else ""
        clause += f" ({sign}{interaction_result.damage_modifier_percent}%)"

    return f"— {clause}" if clause else None


def render_action_outcome_narration(  # noqa: PLR0913 - all params describe one narration; cohesive
    *,
    actor_label: str,
    technique_name: str,
    target_label: str | None,
    outcome: ActionOutcome,
    power_ledger: PowerLedger | None = None,
    signature_snippet: str | None = None,
    interaction_result: DamageInteractionResult | None = None,
) -> str:
    """Render a one-line, deterministic outcome narration from resolved data.

    Pure function — no DB access, no randomness. Composes clauses from the
    ActionOutcome’s damage results and consequences. Absent data → omitted
    clause. Used as the content of an OUTCOME-mode Interaction authored by the
    Narrator persona.

    When ``power_ledger`` is supplied (magic-pipeline actions only), a concise
    ward/environment clause is appended to the OUTCOME line: e.g.
    "— the ward turns it aside" for a full bounce, "— it tears through the ward"
    for clean penetration, or "— the place’s resonance swells the working" for
    an environment amplification. Combo and non-magic paths pass ``None`` and
    get no clause, preserving backward compatibility.

    When ``signature_snippet`` is supplied (the caster's technique is signed with
    a ``SignatureMotifBonus``, #1728), its cosmetic "— <snippet>" clause is
    appended alongside the power clause — the combat-narration sibling of
    ``render_cast_outcome_narration``'s signature handling.

    Examples:
        "Kira’s Frost Bolt strikes the Pyromancer for 24 damage."
        "Kira’s Frost Bolt strikes the Pyromancer for 40 damage, defeating them."
        "Kira’s Frost Bolt misses the Pyromancer — the ward turns it aside."
        "Garruk uses Guard Stance."
    """
    from world.combat.types import OpponentDamageResult  # noqa: PLC0415

    total_damage = sum(dr.damage_dealt for dr in outcome.damage_results)
    # Only opponent results carry `defeated`; participant results never do.
    defeated = any(
        isinstance(dr, OpponentDamageResult) and dr.defeated for dr in outcome.damage_results
    )
    knocked_out = any(c.knocked_out for c in outcome.damage_consequences)
    dying = any(c.dying for c in outcome.damage_consequences)
    wounds = [ct.name for c in outcome.damage_consequences for ct in c.wounds_applied]

    # No target → self/utility action.
    if target_label is None:
        if outcome.combo_used is not None:
            return f"{actor_label} unleashes {outcome.combo_used.name}."
        return f"{actor_label} uses {technique_name}."

    power_clause = power_outcome_clause(power_ledger)
    sig_clause = signature_clause(signature_snippet)
    synergy = synergy_clause(interaction_result)
    suffix_parts = [c for c in (power_clause, sig_clause, synergy) if c]
    suffix = " ".join(suffix_parts)

    # Targeted action with no damage and no wounds → miss (or warded bounce).
    if total_damage <= 0 and not wounds:
        base = f"{actor_label}’s {technique_name} misses {target_label}"
        return f"{base} {suffix}." if suffix else f"{base}."

    head = f"{actor_label}’s {technique_name} strikes {target_label} for {total_damage} damage"
    tail = _build_tail_clauses(
        wounds=wounds, defeated=defeated, dying=dying, knocked_out=knocked_out
    )
    return _assemble_hit_line(head, tail, suffix)


def render_combo_finisher_narration(
    *,
    combo_name: str,
    contributor_labels: list[str],
    target_label: str | None,
    total_damage: int,
    signature_clause: str | None = None,
) -> str:
    """Render a joint finisher narration for a multi-PC combo.

    Pure function — no DB access, no randomness. Names all contributors and
    the combo, sums total damage across all contributors' outcomes, and
    appends an optional signature flourish clause.

    Examples:
        "Kira and Garruk unleash Firestorm Fusion on the Pyromancer for 85 damage."
        "Kira, Garruk and Vex unleash Storm Call on the Ogre for 120 damage — their signature move."
    """
    actors = join_labels(contributor_labels)
    if target_label is None:
        base = f"{actors} unleash {combo_name}"
    else:
        base = f"{actors} unleash {combo_name} on {target_label} for {total_damage} damage"
    if signature_clause:
        return f"{base} — {signature_clause}."
    return f"{base}."


def render_flee_outcome_narration(
    *,
    actor_label: str,
    escaped: bool,
    at_cost: bool,
) -> str:
    """Render a one-line, deterministic outcome narration for a flee attempt.

    Pure function — no DB access, no randomness. Sibling of
    ``render_action_outcome_narration`` for the flee-maneuver path (#878).
    Three cases: clean escape, escape at a cost (PARTIAL — the selected pool
    consequence landed on the way out), and failed escape.

    Examples:
        "Kira breaks away and escapes the fight."
        "Kira escapes the fight, but not unscathed."
        "Kira tries to break away but cannot escape."
    """
    if escaped and at_cost:
        return f"{actor_label} escapes the fight, but not unscathed."
    if escaped:
        return f"{actor_label} breaks away and escapes the fight."
    return f"{actor_label} tries to break away but cannot escape."


# Per-tier resolution clause for clash-outcome narration. Keys are
# ``ClashResolution`` members (str-valued TextChoices, so a raw value string
# from a resolved clash matches the same key). ``{opponent}`` is interpolated
# at render time for NPC-favored tiers.
_CLASH_TIER_CLAUSES: dict[str, str] = {
    ClashResolution.PC_DECISIVE: "resolves decisively in the casters' favor",
    ClashResolution.PC_MARGINAL: "resolves narrowly in the casters' favor",
    ClashResolution.MUTUAL: "ends in a mutual stalemate",
    ClashResolution.NPC_MARGINAL: "resolves narrowly in {opponent}'s favor",
    ClashResolution.NPC_DECISIVE: "resolves decisively in {opponent}'s favor",
    ClashResolution.ABANDONED: "is abandoned",
}


def render_clash_outcome_narration(
    *,
    flavor_label: str,
    opponent_label: str,
    resolution_tier: str,
    consequence_label: str | None = None,
) -> str:
    """Render a one-line, deterministic outcome narration for a resolved clash.

    Pure function — no DB access, no randomness. Primitives in (the caller
    extracts them from the ``ClashResolutionResult`` + its ``Clash``) so this
    stays DB-free and unit-testable like ``render_action_outcome_narration``.

    Examples:
        "The Break with the Pyromancer resolves decisively in the casters' favor."
        "The Ward with the Pyromancer resolves decisively in the Pyromancer's "
        "favor, leaving Stagger."
    """
    clause = _CLASH_TIER_CLAUSES.get(resolution_tier, "resolves").format(opponent=opponent_label)
    head = f"The {flavor_label} with {opponent_label} {clause}"
    if consequence_label:
        return f"{head}, leaving {consequence_label}."
    return f"{head}."


_ENCOUNTER_OUTCOME_HEADLINES: dict[str, str] = {
    "victory": "The field falls silent — victory.",
    "defeat": "The field falls silent — the defenders lie broken.",
    "fled": "The field falls silent — the survivors have scattered.",
    "abandoned": "The encounter disperses, its ending unwritten.",
}


def join_labels(labels: list[str]) -> str:
    """Format labels as a natural-language series: "A", "A and B", "A, B and C".

    Public (not module-private) since #2642's break-celebration narration
    reuses this from services.py — the shared contributor-naming primitive.
    """
    if len(labels) <= 1:
        return labels[0] if labels else ""
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def render_encounter_outcome_narration(
    *,
    outcome: str,
    active_labels: list[str],
    fled_labels: list[str],
    defeated_opponent_labels: list[str],
) -> str:
    """Ceremonial encounter-level OUTCOME line (#876)."""
    # Fail-loud on unknown outcomes: values are the closed EncounterOutcome enum.
    clauses: list[str] = [_ENCOUNTER_OUTCOME_HEADLINES[outcome]]
    if outcome == EncounterOutcome.VICTORY:
        if defeated_opponent_labels:
            clauses.append(f"{join_labels(defeated_opponent_labels)} will trouble no one further.")
        if active_labels:
            clauses.append(f"{join_labels(active_labels)} stand victorious.")
    elif outcome == EncounterOutcome.DEFEAT and active_labels:
        clauses.append(f"{join_labels(active_labels)} can fight no longer.")
    if fled_labels:
        clauses.append(f"{join_labels(fled_labels)} fled the field.")
    return " ".join(clauses)


def broadcast_action_outcome(
    *,
    encounter: CombatEncounter,
    narration: str,
) -> Interaction | None:
    """Persist a Narrator-authored OUTCOME interaction and broadcast it.

    Returns the created Interaction, or None when there is no narration
    text (empty string -> nothing to say). The OUTCOME is persisted in
    the encounter's scene so it appears in the scene log on re-read;
    broadcast goes to every object in the encounter room via the existing
    interaction WebSocket payload. When the encounter has no room, the
    interaction is still persisted (durable) but not broadcast.
    """
    if not narration:
        return None

    from world.combat.narrator import get_or_create_narrator_persona  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _broadcast_to_location,
        _build_interaction_payload,
        create_interaction,
    )

    narrator = get_or_create_narrator_persona()
    interaction = create_interaction(
        persona=narrator,
        content=narration,
        mode=InteractionMode.OUTCOME,
        scene=encounter.scene,
    )

    room = encounter.room
    if room is None:
        return interaction

    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=narrator,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        scene_id=interaction.scene_id,
    )
    _broadcast_to_location(room, payload)
    return interaction
