"""Service functions for standalone technique casts.

``request_technique_cast`` is the central routing service for a cast made
outside an enhanced base action. It dispatches three ways per the feature
matrix:

- Self / room / no-target (or the caster's own persona) → resolve immediately
  through the technique pipeline, persist a RESOLVED ``SceneActionRequest``, and
  author a Narrator OUTCOME pose.
- Benign technique at another PC → create a PENDING ``SceneActionRequest`` for
  consent; resolution happens later on accept.
- Hostile technique at another PC → seed (or feed) a combat encounter and return
  it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.combat.cast_seed import seed_or_feed_encounter_from_cast
from world.combat.narrator import get_or_create_narrator_persona
from world.magic.models.techniques import CharacterTechnique
from world.magic.narration import render_cast_outcome_narration
from world.magic.services.hostility import is_technique_hostile
from world.scenes.action_constants import (
    CAST_ACTION_KEY,
    CAST_DIFFICULTY_BANDS,
    ActionRequestStatus,
)
from world.scenes.action_models import SceneActionRequest
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.types import CastResult, EnhancedSceneActionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import PendingActionResolution
    from world.magic.models import Technique
    from world.magic.types.power_ledger import PowerLedger
    from world.scenes.models import Interaction, Persona, Scene


def derive_cast_difficulty(technique: Technique) -> int:
    """Difficulty for a standalone cast, sourced from the technique's authored intensity."""
    intensity = technique.intensity or 1
    for ceiling, difficulty in CAST_DIFFICULTY_BANDS:
        if intensity <= ceiling:
            return difficulty
    return CAST_DIFFICULTY_BANDS[-1][1]


def _resolve_cast(
    *,
    technique: Technique,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — mirrors _resolve_enhanced_action
    target: ObjectDB | None,  # noqa: OBJECTDB_PARAM
    difficulty: int,
    strain_commitment: int = 0,
) -> tuple[EnhancedSceneActionResult, PowerLedger | None]:
    """Resolve a standalone cast through use_technique + start_action_resolution.

    Mirrors ``action_services._resolve_enhanced_action`` so anima deduction,
    Soulfray accumulation, and control-mishap evaluation all wrap the standard
    action pipeline. Differs only in sourcing the template from the technique
    itself (``technique.action_template``) and the difficulty from
    ``derive_cast_difficulty`` rather than a base-action difficulty choice.

    Args:
        difficulty: Pre-computed cast difficulty (from ``derive_cast_difficulty``);
            passed in so the caller only computes it once and reuses it for
            ``resolved_difficulty`` on the ``SceneActionRequest``.
        strain_commitment: Extra anima committed beyond the technique baseline,
            forwarded to ``use_technique`` so anima costs are tallied correctly.

    Returns the ``EnhancedSceneActionResult`` plus the cast-level ``PowerLedger``
    (BASE + ENVIRONMENT stages) captured from ``use_technique``'s ``resolve_fn``
    so the caller can surface ward/environment clauses in the OUTCOME pose.
    """
    from world.magic.services import use_technique  # noqa: PLC0415

    action_template = technique.action_template
    context = ResolutionContext(character=character, target=target)

    captured: dict[str, PowerLedger] = {}

    def _resolve_fn(*, power: int, ledger: PowerLedger):  # noqa: ARG001 — power is the pipeline's
        captured["ledger"] = ledger
        return start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
        )

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=_resolve_fn,
        confirm_soulfray_risk=True,
        strain_commitment=strain_commitment,
    )

    resolution_result: PendingActionResolution = technique_result.resolution_result  # type: ignore[assignment]
    power_ledger = captured.get("ledger")
    result = EnhancedSceneActionResult(
        action_resolution=resolution_result,
        action_key=CAST_ACTION_KEY,
        technique_result=technique_result,
        power_ledger=power_ledger,
    )
    return result, power_ledger


def create_cast_outcome_pose(  # noqa: PLR0913 - all params describe one pose; cohesive
    *,
    scene: Scene,
    caster_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    result: EnhancedSceneActionResult,
    power_ledger: PowerLedger | None = None,
) -> Interaction:
    """Author the Narrator OUTCOME pose describing a resolved standalone cast."""
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    outcome_label = check_result.outcome_name if check_result is not None else "Unknown"
    success_level = check_result.success_level if check_result is not None else 0

    narration = render_cast_outcome_narration(
        actor_label=caster_persona.name,
        technique_name=technique.name,
        target_label=target_persona.name if target_persona is not None else None,
        outcome_label=outcome_label,
        success_level=success_level,
        power_ledger=power_ledger,
    )

    return create_interaction(
        persona=get_or_create_narrator_persona(),
        content=narration,
        mode=InteractionMode.OUTCOME,
        scene=scene,
        target_personas=[target_persona] if target_persona is not None else None,
    )


def _resolve_and_pose_cast(  # noqa: PLR0913 - all params describe one cast resolution; cohesive
    *,
    request: SceneActionRequest,
    scene: Scene,
    caster_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    strain_commitment: int,
) -> tuple[EnhancedSceneActionResult, PowerLedger | None, Interaction]:
    """Resolve a persisted standalone-cast request, mark it RESOLVED, author the OUTCOME pose.

    Shared by the immediate path (request just created) and the consent-accept path
    (an existing PENDING request). The caller MUST wrap this in ``transaction.atomic()``.
    """
    character = caster_persona.character_sheet.character
    target = target_persona.character_sheet.character if target_persona is not None else None
    difficulty = derive_cast_difficulty(technique)

    result, power_ledger = _resolve_cast(
        technique=technique,
        character=character,
        target=target,
        difficulty=difficulty,
        strain_commitment=strain_commitment,
    )

    request.status = ActionRequestStatus.RESOLVED
    request.resolved_at = timezone.now()
    request.resolved_difficulty = difficulty
    request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])

    pose = create_cast_outcome_pose(
        scene=scene,
        caster_persona=caster_persona,
        target_persona=target_persona,
        technique=technique,
        result=result,
        power_ledger=power_ledger,
    )
    request.result_interaction = pose
    request.save(update_fields=["result_interaction"])

    from world.scenes.interaction_services import create_action_interaction_core  # noqa: PLC0415
    from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

    action_interaction = create_action_interaction_core(
        persona=caster_persona,
        scene=scene,
        summary_label=f"{technique.name}",
        strain_committed=strain_commitment,
    )
    persist_power_ledger(interaction=action_interaction, ledger=power_ledger)
    request.action_interaction = action_interaction
    request.save(update_fields=["action_interaction"])

    return result, power_ledger, pose


def resolve_accepted_cast(action_request: SceneActionRequest) -> EnhancedSceneActionResult:
    """Resolve a PENDING standalone cast on consent acceptance.

    Resolves via the cast pipeline, marks the request RESOLVED, and authors a
    Narrator OUTCOME pose (with the cast-level power ledger). Returns the result.

    Args:
        action_request: A PENDING SceneActionRequest with ``is_standalone_cast`` True.

    Returns:
        The resolved EnhancedSceneActionResult from the cast pipeline.
    """
    with transaction.atomic():
        result, _power_ledger, _pose = _resolve_and_pose_cast(
            request=action_request,
            scene=action_request.scene,
            caster_persona=action_request.initiator_persona,
            target_persona=action_request.target_persona,
            technique=action_request.technique,
            strain_commitment=action_request.strain_commitment,
        )
    return result  # result.power_ledger is already set from _resolve_cast


def request_technique_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None = None,
    technique: Technique,
    strain_commitment: int = 0,
) -> CastResult:
    """Route a standalone technique cast per the consent/combat/immediate matrix.

    Args:
        scene: The scene the cast happens in.
        initiator_persona: The casting persona (FK to a CharacterSheet).
        target_persona: The targeted persona, or None for self/room/no-target.
        technique: The technique being cast (must be castable standalone).
        strain_commitment: Extra anima committed beyond the technique baseline.

    Returns:
        A CastResult whose populated payload depends on the routing branch taken.

    Raises:
        ValidationError: If the caster does not know the technique, or the
            technique has no action template (not castable standalone).
    """
    knows_technique = CharacterTechnique.objects.filter(
        character_id=initiator_persona.character_sheet_id,
        technique=technique,
    ).exists()
    if not knows_technique:
        msg = f"Character does not know technique '{technique}'."
        raise ValidationError(msg)

    if not technique.action_template_id:
        msg = "Technique is not castable standalone (no action template)."
        raise ValidationError(msg)

    # Inline the other-PC check (rather than a bool var) so the type checker can
    # narrow ``target_persona`` to non-None inside the block.
    if (
        target_persona is not None
        and target_persona.character_sheet_id != initiator_persona.character_sheet_id
    ):
        if is_technique_hostile(technique):
            return _route_hostile_cast(
                scene=scene,
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                technique=technique,
            )
        return _route_benign_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            strain_commitment=strain_commitment,
        )

    return _route_immediate_cast(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        technique=technique,
        strain_commitment=strain_commitment,
    )


def _create_cast_request(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    status: str,
    strain_commitment: int = 0,
    resolved_at=None,
) -> SceneActionRequest:
    """Create a SceneActionRequest for a standalone cast.

    Shared by all three routing branches so the identical create() call is not
    copy-pasted across ``_route_benign_cast``, ``_route_hostile_cast``, and
    ``_route_immediate_cast``. The hostile branch passes ``resolved_at`` so the
    audit timestamp is written in a single INSERT rather than a follow-up UPDATE.
    """
    return SceneActionRequest.objects.create(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        technique=technique,
        status=status,
        strain_commitment=strain_commitment,
        resolved_at=resolved_at,
    )


def _route_hostile_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
) -> CastResult:
    """Hostile cast at another PC → audit request + seed/feed a combat encounter."""
    with transaction.atomic():
        request = _create_cast_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            status=ActionRequestStatus.RESOLVED,
            resolved_at=timezone.now(),
        )
        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=initiator_persona.character_sheet,
            target_sheet=target_persona.character_sheet,
            technique=technique,
            scene=scene,
            room=scene.location,
        )
    return CastResult(request=request, encounter=encounter)


def _route_benign_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
    strain_commitment: int,
) -> CastResult:
    """Benign cast at another PC → PENDING request awaiting consent (resolved on accept)."""
    request = _create_cast_request(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        technique=technique,
        status=ActionRequestStatus.PENDING,
        strain_commitment=strain_commitment,
    )
    return CastResult(request=request)


def _route_immediate_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    strain_commitment: int = 0,
) -> CastResult:
    """Self/room/no-target cast → resolve now, persist RESOLVED, author OUTCOME pose."""
    with transaction.atomic():
        request = _create_cast_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            status=ActionRequestStatus.PENDING,
            strain_commitment=strain_commitment,
        )
        result, power_ledger, pose = _resolve_and_pose_cast(
            request=request,
            scene=scene,
            caster_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            strain_commitment=strain_commitment,
        )

    return CastResult(
        request=request,
        result=result,
        outcome_interaction=pose,
        power_ledger=power_ledger,
    )
