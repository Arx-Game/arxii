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
        CombatParticipant,
        CombatRoundAction,
    )


def create_action_interaction(
    *,
    participant: CombatParticipant,
    round_number: int,
    summary_label: str,
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
