"""Service functions for scene action requests and consent flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionRequest
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, Persona, Scene
from world.scenes.types import EnhancedSceneActionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ActionTemplate
    from actions.types import PendingActionResolution
    from world.magic.models import Technique


def _validate_technique_enhancement(
    *,
    technique: Technique,
    action_key: str,
    character_id: int,
) -> None:
    """Validate that a technique may be used with an action request.

    Raises ValidationError if:
    - No ActionEnhancement links this technique to the given action_key.
    - The character does not know this technique.

    Args:
        technique: The technique being applied.
        action_key: The action key to check for an enhancement record.
        character_id: The ObjectDB PK of the initiating character.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from actions.models import ActionEnhancement  # noqa: PLC0415
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    if not ActionEnhancement.objects.filter(
        base_action_key=action_key,
        technique=technique,
    ).exists():
        msg = f"Technique '{technique}' has no ActionEnhancement for action '{action_key}'."
        raise ValidationError(msg)

    if not CharacterTechnique.objects.filter(
        character_id=character_id,
        technique=technique,
    ).exists():
        msg = f"Character does not know technique '{technique}'."
        raise ValidationError(msg)


def create_action_request(  # noqa: PLR0913 — keyword-only API, technique is optional
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    action_key: str,
    difficulty_choice: str = DifficultyChoice.NORMAL,
    technique: Technique | None = None,
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
        technique: Optional technique to enhance this action. Must have an
            ActionEnhancement record for the given action_key and the
            initiator's character must know it.

    Returns:
        The created SceneActionRequest in PENDING status.

    Raises:
        ValidationError: If technique is provided but fails validation.
    """
    if technique is not None:
        _validate_technique_enhancement(
            technique=technique,
            action_key=action_key,
            character_id=initiator_persona.character_id,
        )

    return SceneActionRequest.objects.create(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=action_key,
        difficulty_choice=difficulty_choice,
        status=ActionRequestStatus.PENDING,
        technique=technique,
    )


def respond_to_action_request(
    *,
    action_request: SceneActionRequest,
    decision: str,
) -> EnhancedSceneActionResult | None:
    """Process a consent decision on an action request.

    If accepted, resolves the action via the full pipeline and creates a result
    interaction. If denied, marks the request as denied and returns None.

    Args:
        action_request: The pending action request.
        decision: ConsentDecision value (ACCEPT or DENY).

    Returns:
        EnhancedSceneActionResult if accepted and resolved, None if denied.

    Raises:
        ValueError: If the request has no action_template set.
    """
    if action_request.status != ActionRequestStatus.PENDING:
        return None

    if decision == ConsentDecision.DENY:
        action_request.status = ActionRequestStatus.DENIED
        action_request.resolved_at = timezone.now()
        action_request.save(update_fields=["status", "resolved_at"])
        return None

    if decision == ConsentDecision.ACCEPT:
        difficulty = DIFFICULTY_VALUES.get(
            action_request.difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        )

        with transaction.atomic():
            action_template = action_request.action_template
            if action_template is None:
                msg = f"Cannot resolve action '{action_request.action_key}': no ActionTemplate set."
                raise ValueError(msg)

            character = action_request.initiator_persona.character
            target_character = action_request.target_persona.character
            context = ResolutionContext(character=character, target=target_character)

            if action_request.technique is not None:
                result = _resolve_enhanced_action(
                    character=character,
                    technique=action_request.technique,
                    action_template=action_template,
                    action_key=action_request.action_key,
                    difficulty=difficulty,
                    context=context,
                )
            else:
                action_resolution = start_action_resolution(
                    character=character,
                    template=action_template,
                    target_difficulty=difficulty,
                    context=context,
                )
                result = EnhancedSceneActionResult(
                    action_resolution=action_resolution,
                    action_key=action_request.action_key,
                )

            action_request.status = ActionRequestStatus.RESOLVED
            action_request.resolved_at = timezone.now()
            action_request.resolved_difficulty = difficulty
            action_request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])

            result_interaction = _create_result_interaction(
                action_request=action_request,
                result=result,
            )
            if result_interaction is not None:
                action_request.result_interaction = result_interaction
                action_request.save(update_fields=["result_interaction"])

        return result

    return None


def _resolve_enhanced_action(  # noqa: PLR0913 — keyword-only API, all params are required
    *,
    character: ObjectDB,
    technique: Technique,
    action_template: ActionTemplate,
    action_key: str,
    difficulty: int,
    context: ResolutionContext,
) -> EnhancedSceneActionResult:
    """Resolve a technique-enhanced social action via use_technique().

    Wraps start_action_resolution in use_technique() so that anima deduction,
    Soulfray accumulation, and control mishap evaluation all run around the
    standard action pipeline.

    Args:
        character: The character performing the action.
        technique: The technique being applied.
        action_template: The ActionTemplate defining the action steps.
        action_key: The action key (e.g. "flirt").
        difficulty: The resolved numeric difficulty.
        context: Resolution context carrying character data.

    Returns:
        EnhancedSceneActionResult with both action_resolution and technique_result.
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=lambda: start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
        ),
        confirm_soulfray_risk=True,
    )

    resolution_result: PendingActionResolution = technique_result.resolution_result  # type: ignore[assignment]
    return EnhancedSceneActionResult(
        action_resolution=resolution_result,
        action_key=action_key,
        technique_result=technique_result,
    )


def _create_result_interaction(
    *,
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
) -> Interaction | None:
    """Create an interaction recording the result of a scene action."""
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    success = (check_result.success_level > 0) if check_result is not None else False
    status_word = "Success" if success else "Failure"
    outcome_name = check_result.outcome_name if check_result is not None else "Unknown"

    initiator_name = action_request.initiator_persona.name
    target_name = action_request.target_persona.name
    action_key = action_request.action_key

    if result.technique_result is not None and action_request.technique is not None:
        technique_name = action_request.technique.name
        anima_spent = result.technique_result.anima_cost.effective_cost
        content = (
            f"{initiator_name} uses {technique_name} to {action_key} {target_name}: "
            f"{status_word} ({outcome_name}) [Anima: {anima_spent}]"
        )
    else:
        content = (
            f"{initiator_name} attempts to {action_key} {target_name}: "
            f"{status_word} ({outcome_name})"
        )

    return create_interaction(
        persona=action_request.initiator_persona,
        content=content,
        mode="action",
        scene=action_request.scene,
        receivers=[action_request.target_persona],
        target_personas=[action_request.target_persona],
    )
