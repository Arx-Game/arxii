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

from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction

if TYPE_CHECKING:
    from world.combat.models import (
        ClashContribution,
        CombatEncounter,
        CombatParticipant,
        CombatRoundAction,
    )
    from world.combat.types import ActionOutcome


def create_action_interaction(
    *,
    participant: CombatParticipant,
    round_number: int,
    summary_label: str,
    strain_committed: int = 0,
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
    scene = encounter.scene  # nullable on Interaction; pass through as-is

    # The round_number parameter is currently informational — it's encoded in
    # the action row that calls this, and Interaction.timestamp gives temporal
    # ordering. Kept in the signature so callers can pass it without having to
    # walk back through the action.
    del round_number

    return Interaction.objects.create(
        persona=persona,
        scene=scene,
        content=summary_label,
        mode=InteractionMode.ACTION,
        strain_committed=strain_committed,
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


def render_action_outcome_narration(
    *,
    actor_label: str,
    technique_name: str,
    target_label: str | None,
    outcome: ActionOutcome,
) -> str:
    """Render a one-line, deterministic outcome narration from resolved data.

    Pure function — no DB access, no randomness. Composes clauses from the
    ActionOutcome’s damage results and consequences. Absent data → omitted
    clause. Used as the content of an OUTCOME-mode Interaction authored by the
    Narrator persona.

    Examples:
        "Kira’s Frost Bolt strikes the Pyromancer for 24 damage."
        "Kira’s Frost Bolt strikes the Pyromancer for 40 damage, defeating them."
        "Kira’s Frost Bolt misses the Pyromancer."
        "Garruk uses Guard Stance."
    """
    total_damage = sum(dr.damage_dealt for dr in outcome.damage_results)
    defeated = any(getattr(dr, "defeated", False) for dr in outcome.damage_results)  # noqa: GETATTR_LITERAL
    knocked_out = any(c.knocked_out for c in outcome.damage_consequences)
    dying = any(c.dying for c in outcome.damage_consequences)
    wounds = [ct.name for c in outcome.damage_consequences for ct in c.wounds_applied]

    # No target → self/utility action.
    if target_label is None:
        if outcome.combo_used is not None:
            return f"{actor_label} unleashes {outcome.combo_used.name}."
        return f"{actor_label} uses {technique_name}."

    # Targeted action with no damage and no wounds → miss.
    if total_damage <= 0 and not wounds:
        return f"{actor_label}’s {technique_name} misses {target_label}."

    head = f"{actor_label}’s {technique_name} strikes {target_label} for {total_damage} damage"
    tail_clauses: list[str] = []
    if wounds:
        tail_clauses.append("leaving them " + ", ".join(wounds))
    if defeated:
        tail_clauses.append("defeating them")
    elif dying:
        tail_clauses.append("leaving them dying")
    elif knocked_out:
        tail_clauses.append("knocking them out")

    if tail_clauses:
        return head + ", " + ", ".join(tail_clauses) + "."
    return head + "."


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
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
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
