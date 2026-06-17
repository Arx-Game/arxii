"""Party profile aggregation for encounter scaling (#566).

This module provides the level-only party snapshot consumed by Task 3's
scaling formula.  The invariant: difficulty scales on party size + average
primary character level ONLY — never on "threads" (relationships, covenants,
facets, fashion, magical loadout).
"""

from dataclasses import dataclass

from world.classes.models import CharacterClassLevel
from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant


@dataclass(frozen=True)
class PartyProfile:
    """Immutable snapshot of the active party used by the scaling formula.

    Attributes:
        party_size: Number of ACTIVE participants in the encounter.
        avg_level: Mean primary class level across ACTIVE participants;
            0.0 when the party is empty.
    """

    party_size: int
    avg_level: float


def compute_party_profile(encounter: CombatEncounter) -> PartyProfile:
    """Return a level-only snapshot of the ACTIVE party for *encounter*.

    Two queries only — no traversal of magic/thread/covenant/relationship
    models:

    1. Collect the character-sheet PKs of every ACTIVE participant.
    2. Fetch the primary class level for each of those characters.

    Because ``CharacterSheet`` uses a OneToOneField to ``ObjectDB`` as its
    primary key, ``character_sheet_id == character_id`` on that FK, so the
    second query's ``character_id__in`` filter directly matches
    ``CharacterClassLevel.character_id``.

    Returns:
        PartyProfile with ``party_size=0`` and ``avg_level=0.0`` for an
        empty encounter.
    """
    sheet_ids = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )

    levels = list(
        CharacterClassLevel.objects.filter(
            character_id__in=sheet_ids,
            is_primary=True,
        ).values_list("level", flat=True)
    )

    party_size = len(sheet_ids)
    avg_level = (sum(levels) / len(levels)) if levels else 0.0

    return PartyProfile(party_size=party_size, avg_level=avg_level)
