"""Scene-round Succor challenge-binding (#1744).

No scene-round-side "bind a reactive ChallengeInstance to a target" plumbing
existed before this — combat's _ensure_interpose_challenges/
_bind_interpose_challenges_any_ally are combat-only (CombatRoundAction/
CombatParticipant-keyed). This module is the scene-round equivalent, keyed off
SceneActionDeclaration.succor_target instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.mechanics.models import ChallengeInstance, ChallengeTemplate
from world.mechanics.succor_shared import SUCCOR_CHALLENGE_NAME

if TYPE_CHECKING:
    from world.scenes.models import SceneRound


def ensure_succor_challenges_for_round(scene_round: SceneRound) -> None:
    """Bind a Succor ChallengeInstance to each protected ally declared this round.

    Called from resolve_scene_round BEFORE _resolve_scene_declarations, so the
    challenge exists in time for get_available_actions to surface it when the
    declared Succor action itself resolves in initiative order.
    """
    declarations = list(
        scene_round.action_declarations.filter(
            round_number=scene_round.round_number,
            succor_target__isnull=False,
        ).select_related("succor_target__character_sheet__character")
    )
    if not declarations:
        return
    try:
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
    except ChallengeTemplate.DoesNotExist:
        return

    room = scene_round.room
    for decl in declarations:
        ally_char = decl.succor_target.character_sheet.character
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally_char,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )
