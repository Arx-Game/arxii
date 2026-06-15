"""Scene (non-combat) implementation of the RoundContext seam."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.round_context import RoundContext
from world.scenes.constants import (
    ACTIVE_SCENE_ROUND_STATUSES,
    RoundStatus,
    SceneRoundParticipantStatus,
)
from world.scenes.models import SceneRoundParticipant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import SceneRound


class SceneRoundContext(RoundContext):
    """RoundContext backed by a SceneRound the character actively participates in."""

    def __init__(self, scene_round: "SceneRound") -> None:
        self._scene_round = scene_round

    @property
    def scene_round(self) -> "SceneRound":
        return self._scene_round

    @property
    def round_id(self) -> tuple[int, int]:
        return (self._scene_round.pk, self._scene_round.round_number)

    @property
    def is_declaration_open(self) -> bool:
        return self._scene_round.status == RoundStatus.DECLARING

    def record_declaration(
        self,
        character: "CharacterSheet",  # noqa: ARG002
        player_action: Any,  # noqa: ARG002
        kwargs: dict[str, Any],  # noqa: ARG002
    ) -> None:
        # Foundation: non-combat declaration storage/resolution lands in the
        # acute-tier plan. This context gates dispatch (is_declaration_open) but
        # does not yet persist declarations.
        raise NotImplementedError("scene-round declarations land in the acute-tier plan")


def resolve_scene_round_context(character: "CharacterSheet") -> SceneRoundContext | None:
    """Return a SceneRoundContext for the character's active scene round, or None."""
    participant = (
        SceneRoundParticipant.objects.filter(
            character_sheet=character,
            status=SceneRoundParticipantStatus.ACTIVE,
            scene_round__status__in=ACTIVE_SCENE_ROUND_STATUSES,
        )
        .select_related("scene_round")
        .order_by("-scene_round__created_at")
        .first()
    )
    if participant is None:
        return None
    return SceneRoundContext(participant.scene_round)
