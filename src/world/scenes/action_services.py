"""Service functions for scene action requests and consent flow."""

from __future__ import annotations

from django.utils import timezone

from actions.services import resolve_scene_action
from actions.types import SceneActionResult
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionRequest
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, Persona, Scene


def create_action_request(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    action_key: str,
    difficulty_choice: str = DifficultyChoice.NORMAL,
) -> SceneActionRequest:
    """Create a pending action request for consent.

    The request starts in PENDING status. The target must accept or deny
    before resolution can proceed.

    Args:
        scene: The scene where this action takes place.
        initiator_persona: The persona attempting the action.
        target_persona: The persona being targeted.
        action_key: Key identifying the action type.
        difficulty_choice: Difficulty level for this action.

    Returns:
        The created SceneActionRequest in PENDING status.
    """
    return SceneActionRequest.objects.create(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=action_key,
        difficulty_choice=difficulty_choice,
        status=ActionRequestStatus.PENDING,
    )


def respond_to_action_request(
    *,
    action_request: SceneActionRequest,
    decision: str,
) -> SceneActionResult | None:
    """Process a consent decision on an action request.

    If accepted, resolves the action and creates a result interaction.
    If denied, marks the request as denied and returns None.

    Args:
        action_request: The pending action request.
        decision: ConsentDecision value (ACCEPT or DENY).

    Returns:
        SceneActionResult if accepted and resolved, None if denied.
    """
    if action_request.status != ActionRequestStatus.PENDING:
        return None

    if decision == ConsentDecision.DENY:
        action_request.status = ActionRequestStatus.DENIED
        action_request.resolved_at = timezone.now()
        action_request.save(update_fields=["status", "resolved_at"])
        return None

    if decision == ConsentDecision.ACCEPT:
        action_request.status = ActionRequestStatus.ACCEPTED
        action_request.save(update_fields=["status"])

        # Resolve the action
        difficulty = DIFFICULTY_VALUES.get(
            action_request.difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        )
        action_request.resolved_difficulty = difficulty

        result = resolve_scene_action(
            character=action_request.initiator_persona.character,
            action_template=action_request.action_template,
            action_key=action_request.action_key,
            difficulty=difficulty,
        )

        # Create result interaction
        result_interaction = _create_result_interaction(
            action_request=action_request,
            result=result,
        )

        action_request.status = ActionRequestStatus.RESOLVED
        action_request.resolved_at = timezone.now()
        if result_interaction is not None:
            action_request.result_interaction = result_interaction
            result.interaction_id = result_interaction.pk
        result.action_request_id = action_request.pk

        action_request.save(
            update_fields=[
                "status",
                "resolved_at",
                "resolved_difficulty",
                "result_interaction",
            ]
        )

        return result

    return None


def _create_result_interaction(
    *,
    action_request: SceneActionRequest,
    result: SceneActionResult,
) -> Interaction | None:
    """Create an interaction recording the result of a scene action."""
    content = (
        f"{action_request.initiator_persona.name} attempts to "
        f"{action_request.action_key} {action_request.target_persona.name}: "
        f"{'Success' if result.success else 'Failure'}"
    )

    return create_interaction(
        persona=action_request.initiator_persona,
        content=content,
        mode="action",
        scene=action_request.scene,
        receivers=[action_request.target_persona],
        target_personas=[action_request.target_persona],
    )
