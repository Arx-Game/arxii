"""Encounter aftermath digest (#3551): what the fight changed for each participant,
assembled from the rows the completion seam writes and delivered as a private
Narrator line plus a telnet message.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from world.combat.constants import AFTERMATH_ATTRIBUTION_WINDOW, EncounterOutcome, ParticipantStatus
from world.combat.types import AftermathDigest

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatParticipant


def aftermath_window(encounter: CombatEncounter) -> tuple[datetime, datetime]:
    """[completed_at, completed_at + AFTERMATH_ATTRIBUTION_WINDOW).

    Raises ValueError when completed_at is None.
    """
    if encounter.completed_at is None:
        msg = f"Encounter {encounter.pk} has no completed_at; cannot compute aftermath window."
        raise ValueError(msg)
    start = encounter.completed_at
    return start, start + AFTERMATH_ATTRIBUTION_WINDOW


def has_acute_peril(character_sheet: CharacterSheet) -> bool:
    """True when the character still holds Bleeding Out or Plummeting (the conditions
    _hand_off_acute_peril_to_scene_round hands to a scene round).
    """
    from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character_sheet.character,
        condition__name__in=[BLEED_OUT_CONDITION_NAME, PLUMMETING_CONDITION_NAME],
    ).exists()


def build_aftermath_digest(
    encounter: CombatEncounter, participant: CombatParticipant
) -> AftermathDigest:
    """Assemble what this encounter changed for this participant.

    Everything below is read from rows complete_encounter already wrote earlier
    in its own transaction (aftermath ConsequenceOutcome, LegendEntry, BeatCompletion);
    this function never writes anything itself. Consequence, legend and beat rows
    are bounded by aftermath_window's [completed_at, completed_at +
    AFTERMATH_ATTRIBUTION_WINDOW). Conditions are bounded by
    [encounter.created_at, completed_at + AFTERMATH_ATTRIBUTION_WINDOW) so the
    window's upper edge also excludes a later fight's condition in the same scene,
    not just a later fight's consequence/legend/beat rows.
    """
    from world.checks.outcome_models import ConsequenceOutcome  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.societies.models import LegendEntry  # noqa: PLC0415
    from world.stories.constants import BeatVisibility  # noqa: PLC0415
    from world.stories.models import BeatCompletion  # noqa: PLC0415

    sheet = participant.character_sheet
    character = sheet.character
    start, end = aftermath_window(encounter)

    consequence = (
        ConsequenceOutcome.objects.filter(
            character=sheet,
            combat_interaction__scene_id=encounter.scene_id,
            combat_interaction__mode=InteractionMode.OUTCOME,
            created_at__gte=start,
            created_at__lt=end,
        )
        .select_related("selected_consequence__outcome_tier", "pool", "check_type")
        .order_by("-created_at")
        .first()
    )

    conditions = list(
        get_active_conditions(character)
        .filter(applied_at__gte=encounter.created_at, applied_at__lt=end)
        .order_by("-condition__display_priority", "pk")
    )

    legend_entries = list(
        LegendEntry.objects.filter(
            persona__character_sheet=sheet,
            created_at__gte=start,
            created_at__lt=end,
        ).order_by("created_at")
    )

    beat_completion = None
    if encounter.scenario_deed_id is None:
        candidates = [
            beat
            for beat in (encounter.story_beat, encounter.scene.running_beat)
            if beat is not None
        ]
        if candidates:
            beat_completion = (
                BeatCompletion.objects.filter(
                    beat__in=candidates,
                    recorded_at__gte=start,
                    recorded_at__lt=end,
                )
                .select_related("beat", "outcome_tier")
                .order_by("recorded_at")
                .first()
            )

    beat_visible_to_player = (
        beat_completion is not None and beat_completion.beat.visibility != BeatVisibility.SECRET
    )

    return AftermathDigest(
        outcome=encounter.outcome,
        consequence=consequence,
        conditions=conditions,
        legend_entries=legend_entries,
        beat_completion=beat_completion,
        beat_visible_to_player=beat_visible_to_player,
        peril_round_active=has_acute_peril(sheet),
    )


def render_aftermath_digest(digest: AftermathDigest, *, include_secret_beat: bool) -> str:
    """Render a digest to player-facing text, omitting sections with nothing to say."""
    from world.combat.interaction_services import join_labels  # noqa: PLC0415
    from world.stories.constants import BeatOutcome  # noqa: PLC0415

    lines: list[str] = [f"Aftermath: {EncounterOutcome(digest.outcome).label}."]

    if digest.consequence is not None and digest.consequence.selected_consequence is not None:
        selected = digest.consequence.selected_consequence
        lines.append(f"Consequence: {selected.label} ({selected.outcome_tier.name}).")

    if digest.conditions:
        condition_labels = [c.condition.name for c in digest.conditions]
        lines.append(f"You carry out of the fight: {join_labels(condition_labels)}.")

    lines.extend(
        f"Deed remembered: {entry.title} (+{entry.base_value} legend)."
        for entry in digest.legend_entries
    )

    if digest.beat_completion is not None and (
        include_secret_beat or digest.beat_visible_to_player
    ):
        completion = digest.beat_completion
        beat = completion.beat
        text = beat.player_resolution_text or "the beat is resolved"
        tier = completion.outcome_tier.name if completion.outcome_tier_id else "ungraded"
        outcome_label = BeatOutcome(completion.outcome).label
        lines.append(f"Story: {text} ({tier}, {outcome_label}).")

    if digest.peril_round_active:
        lines.append("Your peril is not over: a scene round now tracks it.")

    return "\n".join(lines)


def deliver_aftermath_digests(encounter: CombatEncounter) -> None:
    """One private Narrator OUTCOME interaction per ACTIVE or FLED participant, pushed
    to that character only, plus ``character.msg(text)`` for telnet. REMOVED rows
    get nothing.
    """
    from world.combat.models import CombatParticipant  # noqa: PLC0415
    from world.combat.narrator import get_or_create_narrator_persona  # noqa: PLC0415
    from world.scenes.constants import InteractionMode, InteractionVisibility  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _build_interaction_payload,
        _send_to_objects,
        create_interaction,
    )
    from world.scenes.models import Persona  # noqa: PLC0415

    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status__in=[ParticipantStatus.ACTIVE, ParticipantStatus.FLED],
    ).select_related("character_sheet__character")

    for participant in participants:
        sheet = participant.character_sheet
        character = sheet.character
        if character is None:
            continue

        digest = build_aftermath_digest(encounter, participant)
        text = render_aftermath_digest(digest, include_secret_beat=False)

        try:
            persona = sheet.primary_persona
        except Persona.DoesNotExist:
            persona = None

        if persona is not None:
            narrator = get_or_create_narrator_persona()
            interaction = create_interaction(
                persona=narrator,
                content=text,
                mode=InteractionMode.OUTCOME,
                scene=encounter.scene,
                receivers=[persona],
                visibility=InteractionVisibility.PERCEIVED_ONLY,
            )
            payload = _build_interaction_payload(
                interaction_id=interaction.pk,
                persona=narrator,
                content=text,
                mode=interaction.mode,
                timestamp=interaction.timestamp.isoformat(),
                scene_id=interaction.scene_id,
                receiver_persona_ids=[persona.pk],
            )
            _send_to_objects([character], payload)

        character.msg(text)
