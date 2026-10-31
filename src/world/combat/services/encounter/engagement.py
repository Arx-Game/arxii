"""A character's active combat engagement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatParticipant

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.engagement import CharacterEngagement


def _ensure_combat_engagement(participant: CombatParticipant) -> None:
    """Ensure the participant's character holds an engagement (combat-owned, #872).

    Existing non-combat engagements are preserved (begin_engagement contract);
    such participants do not tick or spike this encounter.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import begin_engagement  # noqa: PLC0415

    begin_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def engagement_of_any_type_for(  # noqa: OBJECTDB_PARAM - the reverse accessor lives on ObjectDB
    character: ObjectDB,
) -> CharacterEngagement | None:
    """The character's live ``CharacterEngagement`` whatever its type, or None (#4738).

    Fury lands its trade on whatever engagement she holds (a challenge or mission row
    stays in place when combat starts), so the Pressure surfaces read it here rather
    than through ``active_combat_engagement_for``. Same cached reverse accessor; a
    pk-less engagement is a row deleted through a queryset.
    """
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    try:
        engagement = character.engagement
    except (AttributeError, CharacterEngagement.DoesNotExist):
        return None
    return None if engagement.pk is None else engagement


def active_combat_engagement_for(  # noqa: OBJECTDB_PARAM
    character: ObjectDB,
) -> CharacterEngagement | None:
    """The character's live COMBAT ``CharacterEngagement`` (``source`` is the encounter), or None.

    The reverse OneToOne accessor caches on the identity-mapped instance (no query on
    a warm path); a pk-less engagement is a row deleted through a queryset; a non-COMBAT
    engagement (challenge/mission stakes) is not combat. Extracted from
    ``ParticipantSerializer._combat_engagement`` (#3573) so reactive-cost seams can
    read ``engagement.source.is_lethal``.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    try:
        engagement = character.engagement
    except (AttributeError, CharacterEngagement.DoesNotExist):
        return None
    if engagement.pk is None or engagement.engagement_type != EngagementType.COMBAT:
        return None
    return engagement
