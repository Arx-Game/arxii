"""Battle implementation of the RoundContext seam.

Provides ``BattleRoundContext`` (wrapping a ``BattleParticipant`` and its
``Battle``) and ``resolve_battle_round_context`` (the resolver consulted by
``actions.round_context.get_active_round_context``).

Character → participant resolution:
    CharacterSheet → BattleParticipant (via ``character_sheet`` FK)

Only ACTIVE participants whose battle scene is still active are considered.
If somehow a character is an ACTIVE participant in multiple active battles,
the resolver picks the most recently created battle deterministically.
"""

from __future__ import annotations

from typing import Any

from actions.round_context import RoundContext
from world.battles.constants import BattleActionKind, BattleParticipantStatus
from world.battles.models import BattleActionDeclaration, BattleParticipant
from world.character_sheets.models import CharacterSheet
from world.scenes.constants import RoundStatus

_ACTIVE: frozenset[str] = frozenset(
    {RoundStatus.DECLARING, RoundStatus.RESOLVING, RoundStatus.BETWEEN_ROUNDS}
)


class BattleRoundContext(RoundContext):
    """``RoundContext`` backed by a live ``BattleParticipant`` and its ``Battle``.

    Wraps the participant (which carries the battle FK) so that ``round_id``
    and ``is_declaration_open`` can be read without additional queries when the
    participant is already identity-mapped.
    """

    def __init__(self, participant: BattleParticipant) -> None:
        self._participant = participant
        self._battle = participant.battle

    @property
    def round_id(self) -> tuple[int, int]:
        """Return ``(battle_id, round_number)`` for the active round.

        Returns ``(battle_id, 0)`` when no active round exists yet.
        """
        current = self._battle.current_round
        return (self._battle.pk, current.round_number if current is not None else 0)

    @property
    def is_declaration_open(self) -> bool:
        """True when the battle's current round is in DECLARING status."""
        current = self._battle.current_round
        return current is not None and current.status == RoundStatus.DECLARING

    def is_repeat_blocked(
        self,
        actor: CharacterSheet,  # noqa: ARG002
        action_ref: Any,  # noqa: ARG002
        target_persona: Any,  # noqa: ARG002
    ) -> bool:
        """True when the declaration window is not open (STRICT round gating)."""
        return not self.is_declaration_open

    def record_declaration(
        self,
        character: CharacterSheet,  # noqa: ARG002
        player_action: Any,  # noqa: ARG002
        kwargs: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Minimal inline write of a BattleActionDeclaration.

        Task 6 replaces this with the full ``declare_battle_action`` service.
        """
        from actions.errors import ActionDispatchError  # noqa: PLC0415

        current_round = self._battle.current_round
        if current_round is None or current_round.status != RoundStatus.DECLARING:
            raise ActionDispatchError(ActionDispatchError.ROUND_DECLARATION_CLOSED)
        BattleActionDeclaration.objects.update_or_create(
            battle_round=current_round,
            participant=self._participant,
            defaults={"action_kind": BattleActionKind.STRIKE},
        )


def resolve_battle_round_context(character: CharacterSheet) -> BattleRoundContext | None:
    """Find the character's current active ``BattleParticipant`` and return a context.

    Only ACTIVE participants in battles whose scene is still active are considered.
    If multiple matches exist, the most recently created battle is chosen.

    Args:
        character: The ``CharacterSheet`` for the acting character.

    Returns:
        A ``BattleRoundContext`` wrapping the active participant, or ``None``
        if the character has no active battle participation.
    """
    p = (
        BattleParticipant.objects.filter(
            character_sheet=character,
            status=BattleParticipantStatus.ACTIVE,
            battle__scene__is_active=True,
        )
        .select_related("battle")
        .order_by("-battle__created_at")
        .first()
    )
    return BattleRoundContext(p) if p is not None else None
