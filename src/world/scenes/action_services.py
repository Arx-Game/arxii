"""Service functions for scene action requests and consent flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.progression.models import KudosSourceCategory
from world.progression.services.kudos import award_kudos
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionDelivery,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_resolvers import get_resolver
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, Persona, Scene
from world.scenes.types import EnhancedSceneActionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ActionTemplate
    from actions.types import PendingActionResolution
    from world.magic.models import Technique
    from world.magic.types.pull import CastPullDeclaration
    from world.scenes.place_models import Place


def resolve_delivery(*, requested: str, template: ActionTemplate | None) -> str:
    """Resolve the audience routing for an action: override > template > POSE (#903)."""
    if requested:
        return requested
    if template is not None and template.default_delivery:
        return template.default_delivery
    return ActionDelivery.POSE


def _current_place_for(persona: Persona) -> Place | None:
    """The place the persona is presently at, or None."""
    from world.scenes.place_models import PlacePresence  # noqa: PLC0415

    presence = PlacePresence.objects.filter(persona=persona).select_related("place").first()
    return presence.place if presence is not None else None


# Cache for social_engagement category - initialized on first access.
_SOCIAL_ENGAGEMENT_CATEGORY: KudosSourceCategory | None = None


def _get_social_engagement_category() -> KudosSourceCategory:
    """Lazy-load the social_engagement KudosSourceCategory from DB.

    Uses module-level caching to avoid repeated DB lookups.
    """
    global _SOCIAL_ENGAGEMENT_CATEGORY  # noqa: PLW0603
    if _SOCIAL_ENGAGEMENT_CATEGORY is None:
        _SOCIAL_ENGAGEMENT_CATEGORY = KudosSourceCategory.objects.get(name="social_engagement")
    return _SOCIAL_ENGAGEMENT_CATEGORY


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


def create_action_request(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    action_key: str,
    difficulty_choice: str = DifficultyChoice.NORMAL,
    technique: Technique | None = None,
    ritual_id: int | None = None,
    strain_commitment: int = 0,
    delivery: str = "",
    delivery_receivers: list[Persona] | None = None,
) -> SceneActionRequest:
    """Create a pending action request for consent.

    The request starts in PENDING status. The target must accept or deny
    before resolution can proceed.

    When ritual_id is provided (a Ritual.id with execution_kind=SCENE_ACTION),
    the snapshot fields are populated from the ritual's check specification so
    the accepted request carries a full audit trail of the ritual config at
    fire time.

    Args:
        scene: The scene where this action takes place.
        initiator_persona: The persona attempting the action.
        target_persona: The persona being targeted.
        action_key: Key identifying the action type.
        difficulty_choice: Difficulty level for this action.
        technique: Optional technique to enhance this action. Must have an
            ActionEnhancement record for the given action_key and the
            initiator's character must know it.
        ritual_id: Optional Ritual PK (execution_kind=SCENE_ACTION). When provided,
            snapshot fields (stat, skill, specialization, resonance, check_type,
            target_difficulty) are populated from the ritual's sidecar config.
        strain_commitment: Optional non-negative scalar of self-strain the
            initiator commits to this action. Persisted via the
            CommittingDeclaration mixin and consumed downstream when the
            interaction is recorded.
        delivery: Explicit audience-routing override (#903). Blank defers to
            the template's default_delivery at resolution time.
        delivery_receivers: Explicit WHISPER audience. Empty/None = the
            action target alone.

    Returns:
        The created SceneActionRequest in PENDING status.

    Raises:
        ValidationError: If technique is provided but fails validation, or if
            TABLE_TALK delivery is requested while the initiator is not at a
            place.
    """
    if technique is not None:
        _validate_technique_enhancement(
            technique=technique,
            action_key=action_key,
            character_id=initiator_persona.character_sheet_id,
        )

    # Validate only the EXPLICIT override here — the template default is
    # resolved at resolution time (the template FK is attached later in the
    # pipeline), where a placeless TABLE_TALK default falls back to POSE.
    if delivery == ActionDelivery.TABLE_TALK and _current_place_for(initiator_persona) is None:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        msg = "Table-talk delivery requires you to be at a place."
        raise ValidationError(msg)

    snapshot_kwargs: dict[str, object] = {}
    if ritual_id is not None:
        snapshot_kwargs = _snapshot_kwargs_from_ritual(ritual_id)

    request = SceneActionRequest.objects.create(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=action_key,
        difficulty_choice=difficulty_choice,
        status=ActionRequestStatus.PENDING,
        technique=technique,
        strain_commitment=strain_commitment,
        delivery=delivery,
        **snapshot_kwargs,
    )
    if delivery_receivers:
        request.delivery_receivers.set(delivery_receivers)
    return request


def _snapshot_kwargs_from_ritual(ritual_id: int) -> dict[str, object]:
    """Build snapshot field kwargs from a Ritual + RitualCheckConfig row.

    Args:
        ritual_id: PK of the Ritual (execution_kind=SCENE_ACTION) to snapshot.

    Returns:
        Dict of snapshot_* kwargs ready to spread into SceneActionRequest.objects.create().

    Raises:
        Ritual.DoesNotExist: If no matching row is found.
    """
    from world.magic.models.rituals import Ritual  # noqa: PLC0415

    ritual = Ritual.objects.select_related(
        "check_config__stat",
        "check_config__skill",
        "check_config__specialization",
        "check_config__resonance",
        "check_config__check_type",
    ).get(id=ritual_id)

    config = ritual.check_config

    return {
        "snapshot_ritual": ritual,
        "snapshot_stat": config.stat,
        "snapshot_skill": config.skill,
        "snapshot_specialization": config.specialization,
        "snapshot_resonance": config.resonance,
        "snapshot_check_type": config.check_type,
        "snapshot_target_difficulty": config.target_difficulty,
    }


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
        EnhancedSceneActionResult if accepted and resolved via the cast/action
        pipeline. None if denied — or if the accepted cast resolved into combat
        instead of a check result (the #777 hostile consent-accept path).

    Raises:
        ValueError: If the request is a non-standalone-cast with no action_template
            set (standalone cast requests resolve via the cast pipeline and do not
            require an action_template).
    """
    if action_request.status != ActionRequestStatus.PENDING:
        return None

    if decision == ConsentDecision.DENY:
        action_request.status = ActionRequestStatus.DENIED
        action_request.resolved_at = timezone.now()
        action_request.save(update_fields=["status", "resolved_at"])
        return None

    if decision == ConsentDecision.ACCEPT:
        with transaction.atomic():
            # Standalone cast (no action_template, no action_key) — resolve via the cast
            # pipeline; enhanced/plain actions go through the standard resolution path.
            # The inner transaction.atomic() blocks in resolve_accepted_cast and
            # _resolve_standard_action become savepoints inside this outer atomic — harmless
            # and idiomatic Django. This outer block restores the pre-refactor guarantee:
            # if the resolver or kudos award raises, the whole resolution rolls back.
            if action_request.is_standalone_cast:
                from world.scenes.cast_services import resolve_accepted_cast  # noqa: PLC0415

                result = resolve_accepted_cast(action_request)
            else:
                result = _resolve_standard_action(action_request)

            _award_acceptance_kudos(action_request)

            # result is None only for hostile consent-accepts (#777), which have
            # an empty action_key and therefore never a resolver.
            resolver = get_resolver(action_request.action_key)
            if resolver is not None and result is not None:
                resolver(action_request, result)

        return result

    return None


def _resolve_standard_action(
    action_request: SceneActionRequest,
) -> EnhancedSceneActionResult:
    """Resolve an enhanced or plain action request inside a transaction.

    Covers the two non-cast branches of ``respond_to_action_request``:
    - Plain action (no technique): ``start_action_resolution`` directly.
    - Technique-enhanced action: ``_resolve_enhanced_action`` wrapping use_technique.

    Sets status=RESOLVED, resolved_at, resolved_difficulty, and result_interaction
    on the request before returning.

    Raises:
        ValueError: If the request has no action_template set.
    """
    difficulty = DIFFICULTY_VALUES.get(
        action_request.difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
    )

    with transaction.atomic():
        action_template = action_request.action_template
        if action_template is None:
            msg = f"Cannot resolve action '{action_request.action_key}': no ActionTemplate set."
            raise ValueError(msg)

        character = action_request.initiator_persona.character_sheet.character
        target_character = action_request.target_persona.character_sheet.character
        context = ResolutionContext(character=character, target=target_character)

        if action_request.technique is not None:
            result = _resolve_enhanced_action(
                character=character,
                technique=action_request.technique,
                action_template=action_template,
                action_key=action_request.action_key,
                difficulty=difficulty,
                context=context,
                strain_commitment=action_request.strain_commitment,
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
            strain_committed=action_request.strain_commitment,
        )
        if result_interaction is not None:
            action_request.result_interaction = result_interaction
            action_request.save(update_fields=["result_interaction"])

    return result


def _award_acceptance_kudos(action_request: SceneActionRequest) -> None:
    """Award kudos to the target for accepting an action request.

    Skips the award when the target persona is absent (standalone casts allow
    no-target) or when the target's character has no linked account (NPC personas
    and established/temporary personas without an account are valid; the kudos
    award only applies to real player accounts).
    """
    if action_request.target_persona is None:
        return
    target_character = action_request.target_persona.character_sheet.character
    target_account = target_character.db_account
    if target_account is None:
        return
    category = _get_social_engagement_category()
    initiator_character = action_request.initiator_persona.character_sheet.character
    initiator_account = initiator_character.db_account
    initiator_name = action_request.initiator_persona.name
    award_kudos(
        account=target_account,
        amount=category.default_amount,
        source_category=category,
        description=f"Engaged with action request from {initiator_name}",
        awarded_by=initiator_account,
    )


def _resolve_enhanced_action(  # noqa: PLR0913
    *,
    character: ObjectDB,
    technique: Technique,
    action_template: ActionTemplate,
    action_key: str,
    difficulty: int,
    context: ResolutionContext,
    strain_commitment: int = 0,
    cast_pull: CastPullDeclaration | None = None,
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
        strain_commitment: Optional extra anima the caster commits beyond the
            technique's baseline cost. Forwarded to use_technique so the cost
            calculation accounts for the strain.

    Returns:
        EnhancedSceneActionResult with both action_resolution and technique_result.
    """
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.cast_threads import applicable_threads_for_cast  # noqa: PLC0415

    applicable_threads = applicable_threads_for_cast(character, technique, cast_pull=cast_pull)

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=lambda *, power, ledger: start_action_resolution(  # noqa: ARG005
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
        ),
        confirm_soulfray_risk=True,
        strain_commitment=strain_commitment,
        applicable_threads=applicable_threads,
        cast_pull=cast_pull,
    )

    resolution_result: PendingActionResolution = technique_result.resolution_result  # type: ignore[assignment]
    return EnhancedSceneActionResult(
        action_resolution=resolution_result,
        action_key=action_key,
        technique_result=technique_result,
    )


def _route_delivery(
    action_request: SceneActionRequest,
    receivers: list[Persona],
) -> tuple[str, Place | None, list[Persona] | None]:
    """Map the resolved delivery onto (mode, place, receivers) (#903).

    Invariant (from #900): the persisted log never shows more than the room
    heard — WHISPER mode and place scoping are receiver-scoped in feed +
    detail, so routing here is the whole privacy story.
    """
    delivery = resolve_delivery(
        requested=action_request.delivery,
        template=action_request.action_template,
    )
    if delivery == ActionDelivery.WHISPER:
        explicit = list(action_request.delivery_receivers.all())
        return InteractionMode.WHISPER, None, explicit or receivers
    if delivery == ActionDelivery.MUTTER:
        # #905: the full result is receiver-scoped like a whisper; the
        # public fragment is emitted by _create_result_interaction.
        explicit = list(action_request.delivery_receivers.all())
        return InteractionMode.MUTTER, None, explicit or receivers
    if delivery == ActionDelivery.TABLE_TALK:
        place = _current_place_for(action_request.initiator_persona)
        if place is not None:
            # receivers=None (not []) → create_interaction auto-populates the
            # audience from PlacePresence. The distinction is load-bearing.
            return InteractionMode.ACTION, place, None
        # Place gone between create and resolution → stay a public pose.
        # Never silently narrows a whisper; only widens a missing table.
    return InteractionMode.ACTION, None, receivers


def _create_result_interaction(
    *,
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
    strain_committed: int = 0,
) -> Interaction | None:
    """Create an interaction recording the result of a scene action.

    Args:
        action_request: The resolved SceneActionRequest.
        result: The resolution outcome (including optional technique result).
        strain_committed: Strain the initiator actually committed; recorded on
            the resulting Interaction for canonical audit.
    """
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    success = (check_result.success_level > 0) if check_result is not None else False
    status_word = "Success" if success else "Failure"
    outcome_name = check_result.outcome_name if check_result is not None else "Unknown"

    initiator_name = action_request.initiator_persona.name
    action_key = action_request.action_key
    target_persona = action_request.target_persona

    if target_persona is None:
        # Area action (e.g. a telling to the room): no target, optional pose
        # text echoed above the outcome. A telling always names its tale
        # (#902) — listeners can't learn a deed the echo never identifies.
        if action_request.spread_deed_target is not None:
            outcome_line = (
                f"{initiator_name} spreads the tale of "
                f"«{action_request.spread_deed_target.title}»: "
                f"{status_word} ({outcome_name})"
            )
        else:
            outcome_line = f"{initiator_name} ({action_key}): {status_word} ({outcome_name})"
        content = (
            f"{action_request.pose_text}\n{outcome_line}"
            if action_request.pose_text
            else outcome_line
        )
        receivers: list[Persona] = []
        target_personas: list[Persona] = []
    else:
        target_name = target_persona.name
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
        receivers = [target_persona]
        target_personas = [target_persona]

    mode, place, interaction_receivers = _route_delivery(action_request, receivers)

    interaction = create_interaction(
        persona=action_request.initiator_persona,
        content=content,
        mode=mode,
        scene=action_request.scene,
        place=place,
        receivers=interaction_receivers,
        target_personas=target_personas,
        strain_committed=strain_committed,
    )
    if mode == InteractionMode.MUTTER:
        # #905: the room heard a fragment — and the fragment is public
        # BECAUSE it is what the room heard (#900 invariant).
        from world.scenes.interaction_services import mutter_fragment  # noqa: PLC0415

        create_interaction(
            persona=action_request.initiator_persona,
            content=mutter_fragment(content),
            mode=InteractionMode.MUTTER,
            scene=action_request.scene,
        )
    return interaction


def create_and_resolve_area_action(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    action_template: ActionTemplate,
    action_key: str,
    pose_text: str = "",
    effort_level: str = "medium",
    difficulty_choice: str = DifficultyChoice.NORMAL,
    spread_deed_target: object | None = None,
    extra_modifiers: int = 0,
) -> EnhancedSceneActionResult:
    """Create and immediately resolve an area (to-the-room) scene action.

    Area actions have no target and no consent round-trip — the telling resolves
    on the spot. Charges the template's action points + social fatigue (scaled by
    effort), resolves the check, echoes the pose + the outcome, and runs any
    registered resolver (e.g. spread_a_tale).

    Effort and ``extra_modifiers`` (a caller-supplied roller bonus, e.g. a chosen
    specialization) are applied as check modifiers, not difficulty deltas.

    Raises:
        ValidationError: if the initiator lacks the template's action-point cost.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.fatigue.constants import EFFORT_CHECK_MODIFIER  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue  # noqa: PLC0415

    character = initiator_persona.character_sheet.character

    difficulty = DIFFICULTY_VALUES.get(
        difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
    )
    check_modifiers = EFFORT_CHECK_MODIFIER.get(effort_level, 0) + extra_modifiers

    with transaction.atomic():
        # AP spend lives INSIDE the atomic (as a savepoint) so a failed
        # resolution rolls the debit back — never charge for a spread that
        # didn't happen.
        ap_pool = ActionPointPool.get_or_create_for_character(character)
        if action_template.ap_cost and not ap_pool.spend(action_template.ap_cost):
            msg = f"Not enough action points (need {action_template.ap_cost})."
            raise ValidationError(msg)

        request = SceneActionRequest.objects.create(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=None,
            action_template=action_template,
            action_key=action_key,
            pose_text=pose_text,
            effort_level=effort_level,
            difficulty_choice=difficulty_choice,
            spread_deed_target=spread_deed_target,
            status=ActionRequestStatus.PENDING,
        )
        context = ResolutionContext(character=character, target=None)
        action_resolution = start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
            extra_modifiers=check_modifiers,
        )
        result = EnhancedSceneActionResult(
            action_resolution=action_resolution, action_key=action_key
        )

        request.status = ActionRequestStatus.RESOLVED
        request.resolved_at = timezone.now()
        request.resolved_difficulty = difficulty
        request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])

        apply_fatigue(
            initiator_persona.character_sheet,
            ActionCategory.SOCIAL,
            action_template.social_fatigue_cost,
            effort_level,
        )

        result_interaction = _create_result_interaction(action_request=request, result=result)
        if result_interaction is not None:
            request.result_interaction = result_interaction
            request.save(update_fields=["result_interaction"])

        resolver = get_resolver(action_key)
        if resolver is not None:
            resolver(request, result)

    return result
