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

from django.db import transaction

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.round_context import RoundContext
from world.character_sheets.models import CharacterSheet
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.models import CombatParticipant, CombatRoundAction, RoundChallengeDeclaration

# Encounter statuses that represent an ongoing (non-completed) combat.
_ACTIVE_ENCOUNTER_STATUSES: frozenset[str] = frozenset(
    {
        EncounterStatus.DECLARING,
        EncounterStatus.RESOLVING,
        EncounterStatus.BETWEEN_ROUNDS,
    }
)

# kwargs key for effort level — used as a guard and a lookup in _record_combat_declaration.
_EFFORT_LEVEL_KEY: str = "effort_level"


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
        character: CharacterSheet,  # noqa: ARG002 — ABC contract; participant resolved from self
        # player_action: PlayerAction from actions.types
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Record a participant's declared action for the current round.

        Enforces mutual exclusion: COMBAT declarations delete any existing
        RoundChallengeDeclaration; CHALLENGE declarations delete any existing
        CombatRoundAction. Only one declared action type is permitted per
        (encounter, round, participant).

        Args:
            character: The CharacterSheet of the acting character (unused for
                lookup — ``self._participant`` is already resolved).
            player_action: A ``PlayerAction`` carrying backend + ref.
            kwargs: Extra dispatch kwargs forwarded to the backend handler
                (e.g. ``effort_level`` for COMBAT).

        Raises:
            ActionDispatchError: With ``ROUND_DECLARATION_CLOSED`` if the
                encounter is not in DECLARING status.
            ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if backend is
                REGISTRY (registry actions are not round-declared).
        """
        if not self.is_declaration_open:
            raise ActionDispatchError(ActionDispatchError.ROUND_DECLARATION_CLOSED)

        participant = self._participant
        backend: str = player_action.backend

        if backend == ActionBackend.COMBAT:
            self._record_combat_declaration(participant, player_action, kwargs)
        elif backend == ActionBackend.CHALLENGE:
            self._record_challenge_declaration(participant, player_action)
        else:
            # REGISTRY actions are immediate utility; they are never round-declared.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    @transaction.atomic
    def _record_combat_declaration(
        self,
        participant: CombatParticipant,
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Upsert a CombatRoundAction and clear any competing challenge declaration."""
        from world.magic.models import Technique  # noqa: PLC0415

        if _EFFORT_LEVEL_KEY not in kwargs:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

        # Clear any prior challenge declaration for this (encounter, round, participant).
        RoundChallengeDeclaration.objects.filter(
            encounter=self._encounter,
            round_number=self._encounter.round_number,
            participant=participant,
        ).delete()

        try:
            technique = Technique.objects.get(pk=player_action.ref.technique_id)
        except Technique.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        from world.combat.services import declare_action  # noqa: PLC0415

        declare_action(
            participant,
            focused_action=technique,
            focused_category=kwargs.get("focused_category"),
            effort_level=kwargs[_EFFORT_LEVEL_KEY],
            focused_opponent_target=kwargs.get("focused_opponent_target"),
            focused_ally_target=kwargs.get("focused_ally_target"),
            physical_passive=kwargs.get("physical_passive"),
            social_passive=kwargs.get("social_passive"),
            mental_passive=kwargs.get("mental_passive"),
        )

    @transaction.atomic
    def _record_challenge_declaration(
        self,
        participant: CombatParticipant,
        player_action: Any,
    ) -> None:
        """Upsert a RoundChallengeDeclaration and clear any competing round action."""
        from world.mechanics.models import ChallengeApproach, ChallengeInstance  # noqa: PLC0415

        # Clear any prior combat round action for this (participant, round).
        CombatRoundAction.objects.filter(
            participant=participant,
            round_number=self._encounter.round_number,
        ).delete()

        try:
            challenge_instance = ChallengeInstance.objects.get(
                pk=player_action.ref.challenge_instance_id
            )
        except ChallengeInstance.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        try:
            challenge_approach = ChallengeApproach.objects.get(pk=player_action.ref.approach_id)
        except ChallengeApproach.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        RoundChallengeDeclaration.objects.update_or_create(
            encounter=self._encounter,
            round_number=self._encounter.round_number,
            participant=participant,
            defaults={
                "challenge_instance": challenge_instance,
                "challenge_approach": challenge_approach,
            },
        )


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
