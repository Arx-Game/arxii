"""Combat implementation of the RoundContext seam.

Provides ``CombatRoundContext`` (wrapping a ``CombatParticipant`` and its
``CombatEncounter``) and ``resolve_combat_round_context`` (the resolver
consulted by ``actions.round_context.get_active_round_context``).

Character → participant resolution mirrors the canonical path already used
in ``world.combat.views.CombatEncounterViewSet._get_participant``:

    participant.character_sheet  →  CharacterSheet (the FK on CombatParticipant)

The resolver goes the reverse direction:

    CharacterSheet  →  CombatParticipant.objects.filter(
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
        encounter__status__in=<non-completed statuses>,
    )

The ``encounter__status`` exclusion of COMPLETED matches the project intent
that a COMPLETED encounter is no longer "active" — participants in it should
not be declaration-gated.

If somehow a character is an ACTIVE participant in multiple non-completed
encounters (should not happen with current service logic but is possible if
two encounters are created manually), the resolver picks the most recently
created encounter (``encounter__created_at`` descending) to be deterministic
rather than silently picking the first arbitrary DB row.
"""

from __future__ import annotations

from typing import Any

from actions.round_context import RoundContext
from world.character_sheets.models import CharacterSheet
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.models import CombatParticipant

# Encounter statuses that represent an ongoing (non-completed) combat.
_ACTIVE_ENCOUNTER_STATUSES: frozenset[str] = frozenset(
    {
        EncounterStatus.DECLARING,
        EncounterStatus.RESOLVING,
        EncounterStatus.BETWEEN_ROUNDS,
    }
)


class CombatRoundContext(RoundContext):
    """``RoundContext`` backed by a live ``CombatParticipant`` + ``CombatEncounter``.

    Wraps the participant (which carries the encounter FK) so that
    ``round_id`` and ``is_declaration_open`` can be read without additional
    queries when the participant is already identity-mapped.
    """

    def __init__(self, participant: CombatParticipant) -> None:
        self._participant = participant
        # Cache the encounter on first access via the SharedMemoryModel
        # identity map — no second query if the encounter is already loaded.
        self._encounter = participant.encounter

    @property
    def round_id(self) -> tuple[int, int]:
        """Return ``(encounter_id, round_number)`` for this active round."""
        return (self._encounter.pk, self._encounter.round_number)

    @property
    def is_declaration_open(self) -> bool:
        """True when the encounter is in the DECLARING phase."""
        return self._encounter.status == EncounterStatus.DECLARING

    def record_declaration(
        self,
        character: CharacterSheet,
        # player_action: typed as PlayerAction once actions.types defines it (later task)
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Stub — real mutual-exclusion logic lands in P2T8.

        Raises:
            NotImplementedError: Always, until the bridge model is added.
        """
        _msg = "record_declaration is not implemented until P2T8 (RoundChallengeDeclaration)."
        raise NotImplementedError(_msg)


def resolve_combat_round_context(character: CharacterSheet) -> CombatRoundContext | None:
    """Find the character's current active ``CombatParticipant`` and return a context.

    Resolution path (canonical — mirrors ``views._get_participant`` in reverse):
        ``CharacterSheet`` → ``CombatParticipant`` (via ``character_sheet`` FK)

    Only ACTIVE participants in non-COMPLETED encounters are considered.  If
    multiple matches exist (edge case), the most recently started encounter is
    chosen deterministically.

    Args:
        character: The ``CharacterSheet`` for the acting character.

    Returns:
        A ``CombatRoundContext`` wrapping the active participant, or ``None``
        if the character has no active combat participation.
    """
    participant = (
        CombatParticipant.objects.filter(
            character_sheet=character,
            status=ParticipantStatus.ACTIVE,
            encounter__status__in=_ACTIVE_ENCOUNTER_STATUSES,
        )
        .select_related("encounter")
        .order_by("-encounter__created_at")
        .first()
    )
    if participant is None:
        return None
    return CombatRoundContext(participant)
