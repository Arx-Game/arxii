"""Recording story credit for envoy rescues and breaks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import (
    BreakBarContribution,
    CombatEncounter,
    CombatOpponent,
    CombatRoundAction,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _record_story_envoy_rescue(action: CombatRoundAction, protected: ObjectDB) -> None:
    """Persist a successful PC guardian rescue for an active story contract."""
    encounter = action.participant.encounter
    beat = encounter.story_beat
    if beat is None:
        return
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    activation = get_open_activation(beat)
    if activation is None:
        return
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    protected_sheet = CharacterSheet.objects.filter(character_id=protected.pk).first()
    if protected_sheet is None:
        return
    from world.societies.causal_recognition import record_envoy_rescue  # noqa: PLC0415

    record_envoy_rescue(
        activation,
        action.participant.character_sheet,
        source_id=action.pk,
        source_action_id=action.pk,
        protected_sheet=protected_sheet,
    )


def _record_story_break_recognition(
    encounter: CombatEncounter, boss: CombatOpponent, round_number: int
) -> None:
    """Persist authored opening causes when this boss break reaches zero (#3914)."""
    beat = encounter.story_beat
    if beat is None:
        return
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    activation = get_open_activation(beat)
    if activation is None:
        return
    from world.societies.causal_recognition import record_created_opening  # noqa: PLC0415

    rows = BreakBarContribution.objects.filter(
        opponent=boss,
        round_number=round_number,
        participant__isnull=False,
    ).select_related("participant__character_sheet")
    for row in rows:
        record_created_opening(
            activation,
            row.participant.character_sheet,
            source_id=row.pk,
            contribution_kind=row.kind,
        )
