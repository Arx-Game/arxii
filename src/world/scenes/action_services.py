"""Service functions for scene action requests and consent flow."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.progression.models import KudosSourceCategory
from world.progression.models.kudos import KudosDifficultyWeight
from world.progression.services.engagement import accrue
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    RESIST_FATIGUE_BASE,
    ActionDelivery,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import (
    SceneActionPullDeclaration,
    SceneActionRequest,
    SceneActionTarget,
)
from world.scenes.action_resolvers import get_resolver
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, Persona, Scene
from world.scenes.types import EnhancedSceneActionResult

CustomActionResolver = Callable[["SceneActionRequest"], "EnhancedSceneActionResult | None"]
CUSTOM_ACTION_RESOLVERS: dict[str, CustomActionResolver] = {}


def _maybe_fire_decisive(
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
) -> None:
    """Fire any pending DecisiveCheckMarker after a social check resolves (#1748)."""
    from world.scenes.decisive_check_services import maybe_fire_decisive_check  # noqa: PLC0415

    main = result.action_resolution.main_result
    if main is None:
        return
    maybe_fire_decisive_check(
        scene=action_request.scene,
        check_outcome=main.check_result.outcome,
        initiator_sheet=action_request.initiator_persona.character_sheet,
        target_persona=action_request.target_persona,
    )


def register_custom_action_resolver(action_key: str, resolver: CustomActionResolver) -> None:
    """Register a function that resolves a consent request bypassing the ActionTemplate path."""
    CUSTOM_ACTION_RESOLVERS[action_key] = resolver


def _describe_treatment_outcome(
    helper_persona: Persona,
    target_persona: Persona,
    treatment: TreatmentTemplate,
    target_effect: ConditionInstance | PendingAlteration,
    outcome: TreatmentOutcome,
) -> str:
    """Render a short IC description of what treatment produced."""
    # Names are sourced from the participating personas; target_effect is kept
    # in the signature for caller symmetry with perform_treatment.
    _ = target_effect
    helper_name = helper_persona.name
    target_name = target_persona.name
    lines = [f"{helper_name} applies {treatment.name} to {target_name}."]
    if outcome.target_resolved:
        lines.append("The condition is lifted.")
    elif outcome.effect_applied:
        lines.append("The treatment takes hold.")
    elif outcome.helper_backlash_applied:
        lines.append("The treatment backfires.")
    else:
        lines.append("The treatment has no effect.")
    return " ".join(lines)


def _resolve_treatment_request(
    action_request: SceneActionRequest,
) -> EnhancedSceneActionResult | None:
    """Resolve a treat_condition request by calling perform_treatment.

    Treatment carries its own check/cost/reduction logic, so it bypasses the
    ActionTemplate resolution chain entirely. The result is recorded as a regular
    scene interaction on the request and the function returns None because there
    is no PendingActionResolution to hand back to the SCENE_ADAPTIVE pipeline.
    """
    from world.conditions.services import perform_treatment  # noqa: PLC0415

    treatment = action_request.treatment
    target_effect = action_request.target_condition_instance
    if target_effect is None:
        target_effect = action_request.target_pending_alteration
        if target_effect is None:
            msg = "Treatment request has no target effect."
            raise ValueError(msg)

    outcome = perform_treatment(
        helper_sheet=action_request.initiator_persona.character_sheet,
        target_sheet=action_request.target_persona.character_sheet,
        scene=action_request.scene,
        treatment=treatment,
        target_effect=target_effect,
        bond_thread=action_request.thread_used,
    )

    content = _describe_treatment_outcome(
        action_request.initiator_persona,
        action_request.target_persona,
        treatment,
        target_effect,
        outcome,
    )
    interaction = create_interaction(
        persona=action_request.initiator_persona,
        content=content,
        mode=InteractionMode.POSE,
        scene=action_request.scene,
        target_personas=[action_request.target_persona],
    )

    action_request.status = ActionRequestStatus.RESOLVED
    action_request.resolved_at = timezone.now()
    action_request.resolved_difficulty = 0
    action_request.result_interaction = interaction
    action_request.save(
        update_fields=[
            "status",
            "resolved_at",
            "resolved_difficulty",
            "result_interaction",
        ]
    )
    return None


if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ActionTemplate
    from actions.types import PendingActionResolution
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.conditions.models import ConditionInstance, TreatmentTemplate
    from world.conditions.types import TreatmentOutcome
    from world.magic.models import FuryTier, PendingAlteration, Technique, Thread
    from world.magic.types.pull import CastPullDeclaration
    from world.roster.models import RosterTenure
    from world.scenes.boon_services import BoonAsk
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


def _action_template_for_key(action_key: str) -> ActionTemplate | None:
    """Resolve the ActionTemplate a registry social action resolves through.

    The consent path runs the template's check chain, so a targeted social request
    needs its ``action_template`` set at creation. Registry social singletons carry
    the template's ``name`` via ``Action.template_name``; action_keys without one
    (standalone casts, rituals) yield None and leave the request template-less —
    unchanged behaviour (#1172).
    """
    from actions.models import ActionTemplate  # noqa: PLC0415
    from actions.registry import get_action  # noqa: PLC0415

    action_obj = get_action(action_key)
    if action_obj is None or not action_obj.template_name:
        return None
    return ActionTemplate.objects.filter(name=action_obj.template_name).first()


def _dispatch_action_effects(
    action_request: SceneActionRequest,
    actor: ObjectDB,
    target: ObjectDB,
) -> None:
    """Fire the request's registry action's inherent target effects (#1172).

    The consent path resolves the template's check chain via ``start_action_resolution``
    but never reaches the ``Action``'s ``execute()``; social actions with built-in
    effects (RestoreSense's ``RemoveConditionOnCheckConfig``) dispatch them here so
    the effect fires on the live player path. No-op for actions without inherent
    effects and for non-registry action_keys (standalone casts, rituals).
    """
    from actions.registry import get_action  # noqa: PLC0415

    action_obj = get_action(action_request.action_key)
    if action_obj is None:
        return
    action_obj.dispatch_effects(actor, target)


def create_action_request(  # noqa: PLR0913, C901 - the one dispatch orchestrator
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    action_key: str,
    effort_level: str = "medium",
    technique: Technique | None = None,
    ritual_id: int | None = None,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    delivery: str = "",
    delivery_receivers: list[Persona] | None = None,
    additional_target_personas: list[Persona] | None = None,
    pull: CastPullDeclaration | None = None,
    treatment: TreatmentTemplate | None = None,
    target_condition_instance: ConditionInstance | None = None,
    target_pending_alteration: PendingAlteration | None = None,
    thread_used: Thread | None = None,
    boon: BoonAsk | None = None,
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
        effort_level: EffortLevel value declared by the initiator at dispatch.
            Modifies the check and scales social fatigue. Defaults to "medium".
            Difficulty is left at NORMAL (model default); the defender sets it later.
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
        fury_commitment: Optional FuryTier the initiator declares for this action.
        fury_anchor: CharacterSheet of the anchor character whose bond caps the tier.
        delivery: Explicit audience-routing override (#903). Blank defers to
            the template's default_delivery at resolution time.
        delivery_receivers: Explicit WHISPER audience. Empty/None = the
            action target alone.
        additional_target_personas: Optional additional targets beyond the
            primary (``target_persona``). Each persona gets a ``SceneActionTarget``
            row. NPC additional targets are auto-resolved immediately (#572);
            PC additional targets stay PENDING until they respond.
        pull: Optional declared thread pull (#1919). Persisted as a
            ``SceneActionPullDeclaration`` on the request so it survives the
            consent gap. Charged exactly once at accept-time via
            ``_charge_social_pull``. ``None`` for actions without a pull.
        treatment: Optional TreatmentTemplate being attempted (treat_condition only).
            Set at creation — not after, via a post-hoc save — so it's already on the
            row before auto-resolve may fire for an NPC target (#2214).
        target_condition_instance: Optional ConditionInstance being treated.
        target_pending_alteration: Optional PendingAlteration being treated.
        thread_used: Optional bond Thread paying a treatment's cost.
        boon: Optional structured-ask payload (#2540, boon action only). Validated
            up front (ask-time eligibility, dial 1) and persisted as the request's
            ``Boon`` row BEFORE NPC auto-resolve fires, so the payload exists for
            the pending-consent UI and the NPC-side cost band alike.

    Returns:
        The created SceneActionRequest. Status is PENDING when the primary
        target is a PC, or when the primary target is an NPC but the request
        isn't yet resolvable (see ``_request_is_resolvable`` — e.g. no
        ``action_template`` attached). Status is RESOLVED when the primary
        (and/or additional) NPC target(s) auto-resolve at creation time
        (#2214, #572). When auto-resolution fires, its result is NOT carried
        by this return value — it's stashed on the transient
        ``request._auto_resolve_result`` attribute for callers that need it
        (e.g. the REST view surfaces it in the create response's ``result``
        key).

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

    # #2540: validate the boon ask BEFORE creating any rows — an ineligible ask
    # (uncoverable amount, item not held, vault stub) must not leave an orphan request.
    if boon is not None:
        from world.scenes.boon_services import validate_boon_ask  # noqa: PLC0415

        validate_boon_ask(ask=boon, target_persona=target_persona)

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
        action_template=_action_template_for_key(action_key),
        effort_level=effort_level,
        status=ActionRequestStatus.PENDING,
        technique=technique,
        strain_commitment=strain_commitment,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        delivery=delivery,
        treatment=treatment,
        target_condition_instance=target_condition_instance,
        target_pending_alteration=target_pending_alteration,
        thread_used=thread_used,
        **snapshot_kwargs,
    )
    if delivery_receivers:
        request.delivery_receivers.set(delivery_receivers)
    additional = additional_target_personas or []
    for persona in additional:
        SceneActionTarget.objects.create(action_request=request, target_persona=persona)
    # #1919: Persist the pull declaration BEFORE auto-resolving NPC targets so
    # the declaration exists when _charge_social_pull fires during auto-resolve.
    if pull is not None:
        decl = SceneActionPullDeclaration.objects.create(
            request=request,
            resonance=pull.resonance,
            tier=pull.tier,
        )
        decl.threads.set(pull.threads)
    # #2540: persist the boon payload BEFORE auto-resolving NPC targets so the ask
    # exists when the NPC-side cost band and the boon resolver fire during auto-resolve.
    if boon is not None:
        from world.scenes.boon_services import create_boon_for_request  # noqa: PLC0415

        create_boon_for_request(request, boon)
    # #2214: always attempt auto-resolve — a lone NPC primary target (no additional
    # rows) must resolve too, not just the multi-target case. The result is stashed as
    # a transient attribute (mirrors interaction_services.py's _active_scene_cache
    # idiom) rather than changed into create_action_request's return type, which 30+
    # existing callers across the test suite expect to stay a bare SceneActionRequest.
    request._auto_resolve_result = _auto_resolve_npc_targets(request)  # noqa: SLF001

    # #1278 — if the initiator is a blocked player reaching the blocker (via any identity), flag
    # the attempt for staff. The coded block stops the exact pair; circumvention is not code-
    # prevented (that would leak the alt), so staff review it instead.
    from world.scenes.block_services import flag_blocked_contact_attempt  # noqa: PLC0415

    for persona in [target_persona, *additional]:
        if persona is not None:
            flag_blocked_contact_attempt(
                initiator_persona=initiator_persona, target_persona=persona, scene=scene
            )
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


def _compute_difficulty_override_for_primary(
    action_request: SceneActionRequest,
    resist_effort: str,
) -> int | None:
    """Compute the difficulty override for the primary target, applying resist fatigue if needed.

    Returns None when there is no primary target (area/standalone-cast requests).
    """
    if action_request.target_persona is None:
        return None
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.checks.services import compute_resist_increment  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue  # noqa: PLC0415
    from world.scenes.boon_services import npc_boon_tier_shift  # noqa: PLC0415
    from world.scenes.social_difficulty import resolved_base_difficulty  # noqa: PLC0415

    base = resolved_base_difficulty(
        action_request=action_request,
        difficulty_choice=action_request.difficulty_choice,
        target_sheet=action_request.target_persona.character_sheet,
        # #2540 dial 2: the mandatory NPC-side relative-cost band for boon asks —
        # 0 for every other request and for piloted targets (their choice rules).
        extra_tier_modifier=npc_boon_tier_shift(action_request),
    )
    if resist_effort:
        increment = compute_resist_increment(
            action_request.target_persona.character_sheet.character,
            resist_effort,
        )
        apply_fatigue(
            action_request.target_persona.character_sheet,
            ActionCategory.SOCIAL,
            RESIST_FATIGUE_BASE,
            resist_effort,
        )
    else:
        increment = 0
    return base + increment


def _persona_current_tenure(persona: Persona | None) -> RosterTenure | None:
    """Resolve a persona to its character's active RosterTenure, or None.

    Walks ``persona → character_sheet → roster_entry → current_tenure``; any broken
    link (or a persona with no rostered character) yields ``None``.
    """
    if persona is None:
        return None
    try:
        entry = persona.character_sheet.roster_entry
    except (AttributeError, ObjectDoesNotExist):
        return None
    return entry.current_tenure if entry is not None else None


def _blacklist_initiator_for_denier(
    action_request: SceneActionRequest, denier_persona: Persona | None
) -> None:
    """Best-effort: add the request's initiator to *denier_persona*'s antagonism blacklist.

    Invoked on the DENY-and-blacklist path (#1698) so a defender can, in one motion,
    both refuse the action AND bar that actor from the action's category in future. No-op
    when the action has no consent category, or when either tenure can't be resolved (the
    blacklist is tenure-scoped). The blocked party is never told.
    """
    template = action_request.action_template
    category = template.consent_category if template is not None else None
    if category is None:
        return
    owner_tenure = _persona_current_tenure(denier_persona)
    blocked_tenure = _persona_current_tenure(action_request.initiator_persona)
    if owner_tenure is None or blocked_tenure is None:
        return
    from world.consent.services import add_social_consent_blacklist  # noqa: PLC0415

    add_social_consent_blacklist(owner_tenure, blocked_tenure, category)


def _deny_action_request(action_request: SceneActionRequest, blacklist_actor: bool) -> None:
    """Mark an action request as denied and clean up its pull declaration.

    #1919: The pull declaration is removed so it doesn't linger as an orphan
    row (the charge never fires on DENY). Optionally blacklists the initiator
    for the denier's antagonism category (#1698).
    """
    action_request.status = ActionRequestStatus.DENIED
    action_request.resolved_at = timezone.now()
    action_request.save(update_fields=["status", "resolved_at"])
    SceneActionPullDeclaration.objects.filter(request=action_request).delete()
    if blacklist_actor:
        _blacklist_initiator_for_denier(action_request, action_request.target_persona)


def _charge_primary_pull_flat_bonus(
    action_request: SceneActionRequest,
) -> tuple[int, str | None]:
    """Charge the primary target's social pull, returning (flat_bonus, fizzle_note).

    #1919: Charges a persisted social pull declaration exactly once before
    per-target resolution. The resolved FLAT_BONUS is threaded into
    _resolve_action_against_persona as pull_flat_bonus. On failure (balance
    drained, anchor no longer in action, lock acquired, …), the pull fizzles —
    the action resolves pull-less with a fizzle note.
    """
    pull_flat_bonus = 0
    fizzle_note: str | None = None
    action_template = action_request.action_template
    if action_template is not None and action_template.check_type_id is not None:
        from world.magic.exceptions import (  # noqa: PLC0415
            MagicError,
            ProtagonismLockedError,
        )

        try:
            pull_flat_bonus = _charge_social_pull(
                action_request=action_request,
                check_type=action_template.check_type,
            )
        except (MagicError, ProtagonismLockedError) as exc:
            fizzle_note = str(exc) or "The thread pull fizzled."
    return pull_flat_bonus, fizzle_note


def _resolve_accepted_action_request(
    action_request: SceneActionRequest, resist_effort: str
) -> EnhancedSceneActionResult | None:
    """Resolve an accepted action request via the appropriate pipeline.

    Dispatches to a custom resolver, the standalone-cast pipeline, or the
    standard action pipeline (charging the social pull first).
    """
    custom_resolver = CUSTOM_ACTION_RESOLVERS.get(action_request.action_key)
    if custom_resolver is not None:
        return custom_resolver(action_request)
    if action_request.is_standalone_cast:
        from world.scenes.cast_services import resolve_accepted_cast  # noqa: PLC0415

        return resolve_accepted_cast(action_request)
    pull_flat_bonus, fizzle_note = _charge_primary_pull_flat_bonus(action_request)
    difficulty_override = _compute_difficulty_override_for_primary(action_request, resist_effort)
    return _resolve_standard_action(
        action_request,
        difficulty_override=difficulty_override,
        pull_flat_bonus=pull_flat_bonus,
        fizzle_note=fizzle_note,
    )


def _invoke_action_resolver(
    action_request: SceneActionRequest, result: EnhancedSceneActionResult | None
) -> None:
    """Fire the registered resolver for an action request's result, if any."""
    if result is None:
        return
    resolver = get_resolver(action_request.action_key)
    if resolver is not None:
        resolver(action_request, result)


def respond_to_action_request(
    *,
    action_request: SceneActionRequest,
    decision: str,
    difficulty: str | None = None,
    resist_effort: str = "",
    blacklist_actor: bool = False,
) -> EnhancedSceneActionResult | None:
    """Process a consent decision on an action request.

    If accepted, resolves the action via the full pipeline and creates a result
    interaction. If denied, marks the request as denied and returns None.

    Args:
        action_request: The pending action request.
        decision: ConsentDecision value (ACCEPT or DENY).
        difficulty: Optional DifficultyChoice value supplied by the defender at
            consent. When present, overrides the initiator's authored band for
            this target only (Task 4 — per-target plausibility).
        resist_effort: Optional EffortLevel value for the defender's active
            resistance. Stored on the request; increment applied in a later task.
        blacklist_actor: On DENY, also add the initiator to the denier's antagonism
            blacklist for the action's category (#1698). Ignored on ACCEPT and when the
            action has no consent category.

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
        _deny_action_request(action_request, blacklist_actor)
        return None

    if decision == ConsentDecision.ACCEPT:
        with transaction.atomic():
            if difficulty is not None:
                action_request.difficulty_choice = difficulty
            action_request.resist_effort_level = resist_effort
            action_request.save(update_fields=["difficulty_choice", "resist_effort_level"])

            result = _resolve_accepted_action_request(action_request, resist_effort)

            _accrue_engagement_for_primary(action_request)
            _invoke_action_resolver(action_request, result)

        return result

    return None


def _scene_is_high_stakes(action_request: SceneActionRequest) -> bool:
    """True when an active combat encounter or DANGER round is on the scene (#1919).

    Anima cost is waived (zeroed) for social pulls in low-stakes scenes — pure
    social RP with no combat encounter (status ≠ COMPLETED) and no DANGER round
    (``SceneRound.start_reason=DANGER``, non-COMPLETED). This reuses existing
    state; no new schema field.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.scenes.constants import RoundStatus, SceneRoundStartReason  # noqa: PLC0415

    scene = action_request.scene
    if scene is None:
        return False
    room = scene.location
    has_active_combat = CombatEncounter.objects.filter(
        scene=scene,
        status__in=[
            RoundStatus.DECLARING,
            RoundStatus.RESOLVING,
            RoundStatus.BETWEEN_ROUNDS,
        ],
    ).exists()
    if has_active_combat:
        return True
    if room is None:
        return False
    return scene.scene_rounds.filter(
        start_reason=SceneRoundStartReason.DANGER,
        status__in=[
            RoundStatus.DECLARING,
            RoundStatus.RESOLVING,
            RoundStatus.BETWEEN_ROUNDS,
        ],
    ).exists()


def _charge_social_pull(
    *,
    action_request: SceneActionRequest,
    check_type: CheckType,
) -> int:
    """Charge a persisted social pull declaration and return the FLAT_BONUS total.

    Returns ``0`` when no declaration exists on the request.

    Resolves ``involved_traits`` from the check type's trait weights so TRAIT
    threads can be validated as anchor-in-action. Waives anima cost when the
    scene is not high-stakes (no active combat encounter or DANGER round).

    **Idempotent (#1919):** on first call, charges via
    ``spend_resonance_for_pull``, stamps ``charged_at`` + ``charged_flat_bonus``,
    and returns the bonus. On subsequent calls (when ``charged_at`` is already
    set — e.g. multi-target resolutions or the NPC auto-resolve path), returns
    the cached bonus without re-charging.

    Raises:
        MagicError / ProtagonismLockedError: when the pull cannot be charged
            (balance drained, anchor not in action, lock acquired, …). The caller
            (``respond_to_action_request``) catches these to degrade to a fizzle.
    """
    from world.magic.constants import EffectKind, TargetKind  # noqa: PLC0415
    from world.magic.services.resonance import spend_resonance_for_pull  # noqa: PLC0415
    from world.magic.types.pull import PullActionContext  # noqa: PLC0415

    declaration = SceneActionPullDeclaration.objects.filter(request=action_request).first()
    if declaration is None:
        return 0

    # Idempotent guard: if already charged, return the cached bonus.
    if declaration.charged_at is not None:
        return declaration.charged_flat_bonus or 0

    sheet = action_request.initiator_persona.character_sheet
    threads = list(declaration.threads.filter(retired_at__isnull=True))
    if not threads:
        return 0

    target = None
    if action_request.target_persona is not None:
        target = action_request.target_persona.character_sheet.character

    involved_traits = tuple(check_type.traits.values_list("trait_id", flat=True))

    # Anima waiver: waived (zeroed) when no active combat or DANGER round.
    anima_cost_override = 0 if not _scene_is_high_stakes(action_request) else None

    pull_result = spend_resonance_for_pull(
        sheet,
        declaration.resonance,
        declaration.tier,
        threads,
        PullActionContext(
            combat_encounter=None,
            involved_traits=involved_traits,
            target=target,
            excluded_kinds=frozenset({TargetKind.GIFT}),
        ),
        # Defense-in-depth: beseech_bonus=0 ensures no emergency draw fires
        # even if the declaration somehow carried a bonus.
        beseech_bonus=0,
        anima_cost_override=anima_cost_override,
    )

    pull_flat_bonus = 0
    for eff in pull_result.resolved_effects:
        if eff.inactive:
            continue
        if eff.kind == EffectKind.FLAT_BONUS:
            pull_flat_bonus += eff.scaled_value or 0

    # Stamp the charge guard + cached bonus so subsequent calls (multi-target)
    # return the same bonus without re-charging.
    declaration.charged_at = timezone.now()
    declaration.charged_flat_bonus = pull_flat_bonus
    declaration.save(update_fields=["charged_at", "charged_flat_bonus"])
    return pull_flat_bonus


def _resolve_action_against_persona(
    action_request: SceneActionRequest,
    target_persona: Persona,
    *,
    difficulty_override: int | None = None,
    pull_flat_bonus: int = 0,
) -> tuple[EnhancedSceneActionResult, Interaction | None, int]:
    """Resolve ``action_request`` against ONE persona.

    Status bookkeeping is the caller's job (request.status for the primary,
    SceneActionTarget.status for additional targets), so this helper never
    writes a status field.

    Args:
        action_request: The action request being resolved.
        target_persona: The persona being targeted.
        difficulty_override: When provided, overrides the difficulty computed
            from ``action_request.difficulty_choice``. Task 4 (plausibility
            defender) supplies per-target values via this seam.
        pull_flat_bonus: FLAT_BONUS from a charged social pull (#1919), folded
            into the plain-action check's ``extra_modifiers``. 0 when no pull
            was declared or the pull fizzled.

    Returns:
        (result, result_interaction, difficulty) — difficulty is returned so
        callers can persist ``resolved_difficulty`` without recomputing.

    Raises:
        ValueError: If the request has no action_template set.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.checks.services import collect_check_modifiers  # noqa: PLC0415
    from world.fatigue.constants import EFFORT_CHECK_MODIFIER  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue, get_fatigue_penalty  # noqa: PLC0415
    from world.npc_services.social_disposition import (  # noqa: PLC0415
        apply_social_disposition_delta,
    )
    from world.relationships.services import relationship_gated_contributions  # noqa: PLC0415

    if difficulty_override is not None:
        difficulty = difficulty_override
    else:
        difficulty = DIFFICULTY_VALUES.get(
            action_request.difficulty_choice, DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        )
    action_template = action_request.action_template
    if action_template is None:
        msg = f"Cannot resolve action '{action_request.action_key}': no ActionTemplate set."
        raise ValueError(msg)

    character = action_request.initiator_persona.character_sheet.character
    target_character = target_persona.character_sheet.character
    context = ResolutionContext(character=character, target=target_character)

    # Effort is a check-roll modifier (not a difficulty delta) applied on BOTH the
    # technique-enhanced and plain branches (#1293). It is orthogonal to the
    # technique's anima/intensity/fury levers, which scale cast power; the effort
    # cost axis is charged separately by apply_fatigue below.
    check_modifiers = EFFORT_CHECK_MODIFIER.get(action_request.effort_level, 0)
    # Read the initiator's accumulated social fatigue penalty back into the check
    # roll (#2241). Combat already does this (combat/services.py:323-329); social
    # actions charged fatigue but never read it back, so repeated flirting had no
    # diminishing-returns teeth. The penalty is 0 when FRESH, −1 through −4 as
    # fatigue accumulates — the "getting tired of this" effect.
    fatigue_penalty = get_fatigue_penalty(
        action_request.initiator_persona.character_sheet,
        ActionCategory.SOCIAL,
    )
    check_modifiers += fatigue_penalty
    if action_request.technique is not None:
        result = _resolve_enhanced_action(
            character=character,
            technique=action_request.technique,
            action_template=action_template,
            action_key=action_request.action_key,
            difficulty=difficulty,
            context=context,
            effort_modifier=check_modifiers,
            strain_commitment=action_request.strain_commitment,
            fury_commitment=action_request.fury_commitment,
            fury_anchor=action_request.fury_anchor,
        )
    else:
        # Plain (non-technique) actions do not use the fury lever; fury is a
        # technique-cast-only mechanic (spec: intensity rides power_intensity_bonus
        # inside use_technique). The serializer rejects fury_commitment_id on
        # plain actions, so fury_commitment is always None here.
        #
        # Social/scene actions are always plain, and this is the ONE place they
        # enter the modifier seam: combat/challenge/vitals already funnel their
        # checks through collect_check_modifiers, but the social path did not, so
        # no condition / rollmod / scene / equipment / CHARACTER / fashion (and,
        # once scoped, allure — #1696) modifier reached a social check. Fold the
        # initiator's breakdown into extra_modifiers here, scene-scoped so the
        # perception-relative fashion bonus resolves (#512). The technique branch
        # collects its own modifiers downstream, so it is left untouched.
        # ActionTemplate.check_type is NOT NULL, so the action always has a check to
        # gather modifiers for.
        #
        # Directed relationship-gated modifiers (allure — #1696): when the TARGET holds a
        # gating relationship-condition toward the initiator (e.g. "Attracted To"), fold the
        # initiator's gated modifier (allure) in as a directed contribution — once per gating
        # condition, so "Very Attracted" stacks the double. Empty until #1697 seeds the
        # conditions + Flirt/Seduction wiring.
        gated = relationship_gated_contributions(
            perceiver=target_persona.character_sheet,
            perceived=action_request.initiator_persona.character_sheet,
        )
        breakdown = collect_check_modifiers(
            action_request.initiator_persona.character_sheet,
            action_template.check_type,
            scene=action_request.scene,
            extra_contributions=gated,
        )
        action_resolution = start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
            extra_modifiers=check_modifiers + breakdown.total + pull_flat_bonus,
        )
        result = EnhancedSceneActionResult(
            action_resolution=action_resolution,
            action_key=action_request.action_key,
            fury_committed=None,
        )

    # #1748: fire any pending decisive-check marker after a social check resolves.
    _maybe_fire_decisive(action_request, result)

    # Charge social fatigue once per target resolved. Multi-target casts charge
    # the initiator per-target — this is the intended per-target-independent model.
    apply_fatigue(
        action_request.initiator_persona.character_sheet,
        ActionCategory.SOCIAL,
        action_template.social_fatigue_cost,
        action_request.effort_level,
    )

    # Dispatch the action's inherent target effects (e.g. RestoreSense removing a
    # Berserk condition). The check chain above resolves the action; this is where
    # data-driven condition effects reach the live player path (#1172).
    _dispatch_action_effects(action_request, character, target_character)

    result.disposition_message = apply_social_disposition_delta(
        character, target_persona.pk, result.action_resolution
    )

    result_interaction = _create_result_interaction(
        action_request=action_request,
        result=result,
        strain_committed=action_request.strain_commitment,
        target_persona=target_persona,
        fury_committed=result.fury_committed,
    )
    return result, result_interaction, difficulty


def _resolve_standard_action(
    action_request: SceneActionRequest,
    *,
    difficulty_override: int | None = None,
    pull_flat_bonus: int = 0,
    fizzle_note: str | None = None,
) -> EnhancedSceneActionResult:
    """Resolve the request against its primary target inside a transaction."""
    with transaction.atomic():
        result, result_interaction, difficulty = _resolve_action_against_persona(
            action_request,
            action_request.target_persona,
            difficulty_override=difficulty_override,
            pull_flat_bonus=pull_flat_bonus,
        )
        action_request.status = ActionRequestStatus.RESOLVED
        action_request.resolved_at = timezone.now()
        action_request.resolved_difficulty = difficulty
        action_request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])
        if result_interaction is not None:
            action_request.result_interaction = result_interaction
            action_request.save(update_fields=["result_interaction"])
    if fizzle_note is not None:
        result.fizzle_note = fizzle_note
    return result


def _accrue_engagement_for_persona(
    action_request: SceneActionRequest,
    persona: Persona,
    band: str,
) -> None:
    """Accrue graded good-sport credit for ``persona`` accepting an action request.

    Skips when:
    - The persona's character has no linked account (NPC defender — no accrual).
    - The initiator has no account (NPC initiator — no accrual).
    - The initiator and target share the same account (self-target — no farming).
    """
    target_character = persona.character_sheet.character
    target_account = target_character.db_account
    if target_account is None:
        return
    initiator_character = action_request.initiator_persona.character_sheet.character
    initiator_account = initiator_character.db_account
    if initiator_account is None or initiator_account == target_account:
        return
    category = _get_social_engagement_category()
    pts = Decimal(category.default_amount) * KudosDifficultyWeight.weight_for(band)
    accrue(target_account, initiator_account, pts)


def _accrue_engagement_for_primary(action_request: SceneActionRequest) -> None:
    """Accrue graded good-sport credit for the primary target of an action request.

    Skips when the target persona is absent (standalone casts allow no-target).
    Delegates the per-persona accrual rule to ``_accrue_engagement_for_persona``.
    """
    if action_request.target_persona is None:
        return
    _accrue_engagement_for_persona(
        action_request, action_request.target_persona, band=action_request.difficulty_choice
    )


def _persona_is_npc(persona: Persona) -> bool:
    """True when the persona has no controlling player account (NPC)."""
    return persona.character_sheet.character.db_account is None


def _deny_action_target(action_target: SceneActionTarget, blacklist_actor: bool) -> None:
    """Mark an action target row as denied, optionally blacklisting the initiator."""
    action_target.status = ActionRequestStatus.DENIED
    action_target.resolved_at = timezone.now()
    action_target.save(update_fields=["status", "resolved_at"])
    if blacklist_actor:
        _blacklist_initiator_for_denier(action_target.action_request, action_target.target_persona)


def _compute_target_difficulty_override(
    action_request: SceneActionRequest,
    action_target: SceneActionTarget,
    resist_effort: str,
) -> int:
    """Compute the difficulty override for an accepted target row.

    Persists the defender's plausibility band on the target row, then passes it
    as difficulty_override so the per-target band is used for resolution (the
    target's band lives on SceneActionTarget, not the request). Applies resist
    fatigue when a resist effort is supplied.
    """
    from world.scenes.social_difficulty import resolved_base_difficulty  # noqa: PLC0415

    base = resolved_base_difficulty(
        action_request=action_request,
        difficulty_choice=action_target.difficulty_choice,
        target_sheet=action_target.target_persona.character_sheet,
    )
    if resist_effort:
        from actions.constants import ActionCategory  # noqa: PLC0415
        from world.checks.services import compute_resist_increment  # noqa: PLC0415
        from world.fatigue.services import apply_fatigue  # noqa: PLC0415

        increment = compute_resist_increment(
            action_target.target_persona.character_sheet.character,
            resist_effort,
        )
        apply_fatigue(
            action_target.target_persona.character_sheet,
            ActionCategory.SOCIAL,
            RESIST_FATIGUE_BASE,
            resist_effort,
        )
    else:
        increment = 0
    return base + increment


def _charge_target_pull_flat_bonus(action_request: SceneActionRequest) -> int:
    """Retrieve the pull flat bonus for an additional target (idempotent).

    #1919: The primary resolution or an earlier NPC auto-resolve may have
    already charged it. Returns 0 when no declaration exists or it already
    fizzled (the primary charge's fizzle note already covers the request).
    """
    pull_flat_bonus = 0
    action_template = action_request.action_template
    if action_template is not None and action_template.check_type_id is not None:
        from world.magic.exceptions import (  # noqa: PLC0415
            MagicError,
            ProtagonismLockedError,
        )

        try:
            pull_flat_bonus = _charge_social_pull(
                action_request=action_request,
                check_type=action_template.check_type,
            )
        except (MagicError, ProtagonismLockedError):
            # Already fizzled on the primary charge; no bonus for this target.
            pull_flat_bonus = 0
    return pull_flat_bonus


def respond_to_action_target(
    *,
    action_target: SceneActionTarget,
    decision: str,
    difficulty: str | None = None,
    resist_effort: str = "",
    blacklist_actor: bool = False,
) -> EnhancedSceneActionResult | None:
    """Consent + resolution for ONE additional target row. Never touches siblings.

    Args:
        action_target: The SceneActionTarget row to resolve.
        decision: ConsentDecision value (ACCEPT or DENY).
        difficulty: Optional DifficultyChoice value supplied by the defender at
            consent. When present, stored on the target row and used as the
            difficulty_override for resolution (Task 4 — per-target plausibility).
        resist_effort: Optional EffortLevel value for the defender's active
            resistance. Stored on the target row; increment applied in a later task.
        blacklist_actor: On DENY, also add the initiator to this target's antagonism
            blacklist for the action's category (#1698). Ignored on ACCEPT.

    Returns:
        EnhancedSceneActionResult if accepted and resolved. None if denied, already
        resolved, or any other non-PENDING/non-ACCEPT state.
    """
    if action_target.status != ActionRequestStatus.PENDING:
        return None
    if decision == ConsentDecision.DENY:
        _deny_action_target(action_target, blacklist_actor)
        return None
    if decision == ConsentDecision.ACCEPT:
        action_request = action_target.action_request
        with transaction.atomic():
            if difficulty is not None:
                action_target.difficulty_choice = difficulty
            action_target.resist_effort_level = resist_effort
            difficulty_override = _compute_target_difficulty_override(
                action_request, action_target, resist_effort
            )
            pull_flat_bonus = _charge_target_pull_flat_bonus(action_request)
            result, result_interaction, resolved_difficulty = _resolve_action_against_persona(
                action_request,
                action_target.target_persona,
                difficulty_override=difficulty_override,
                pull_flat_bonus=pull_flat_bonus,
            )
            action_target.status = ActionRequestStatus.RESOLVED
            action_target.resolved_at = timezone.now()
            action_target.resolved_difficulty = resolved_difficulty
            action_target.result_interaction = result_interaction
            _accrue_engagement_for_persona(
                action_request, action_target.target_persona, band=action_target.difficulty_choice
            )
            action_target.save(
                update_fields=[
                    "status",
                    "resolved_at",
                    "resolved_difficulty",
                    "result_interaction",
                    "difficulty_choice",
                    "resist_effort_level",
                ]
            )
            # Per-target resolver invocation (#1178): fire the registered resolver for
            # THIS target's result, symmetric with respond_to_action_request (:340).
            # Runs once per accepted target; resolvers registered for multi-target
            # actions must keep cast-level side-effects idempotent. result is None only
            # for hostile consent-accepts (empty action_key → no resolver).
            _invoke_action_resolver(action_request, result)
        return result
    return None


def _request_is_resolvable(action_request: SceneActionRequest) -> bool:
    """True when accepting this request has a real resolution path.

    Mirrors ``_resolve_accepted_action_request``'s own dispatch (custom resolver,
    standalone cast, or a real ``ActionTemplate``). Guards auto-resolve-at-dispatch
    from raising ``ValueError`` on a data/fixture gap (a request whose action_key has
    no matching template) — that ValueError is a real validation signal for the
    ``respond()`` endpoint (a human explicitly consenting to a broken request), but
    auto-resolve-at-creation has no human in the loop to show it to, so it should
    silently leave the request PENDING instead, exactly as it did before #2214.
    """
    return (
        action_request.action_key in CUSTOM_ACTION_RESOLVERS
        or action_request.is_standalone_cast
        or action_request.action_template is not None
    )


def _auto_resolve_npc_targets(
    action_request: SceneActionRequest,
) -> EnhancedSceneActionResult | None:
    """Resolve NPC targets immediately at dispatch; PC targets stay PENDING.

    The primary target (if present, NPC, and resolvable) is resolved via
    ``respond_to_action_request``, whose result is returned to the caller (#2214 — the
    primary's disposition/check result needs to reach ``create_action_request``'s caller).
    Each NPC additional-target row is resolved via ``respond_to_action_target`` as before;
    those per-row results are intentionally not collected here (#2214 non-goal — surfacing
    them needs a list-shaped response, a separate concern). PC targets, and any target whose
    request isn't resolvable yet (see ``_request_is_resolvable``), are left PENDING.
    """
    primary = action_request.target_persona
    result: EnhancedSceneActionResult | None = None
    if primary is not None and _persona_is_npc(primary) and _request_is_resolvable(action_request):
        result = respond_to_action_request(
            action_request=action_request, decision=ConsentDecision.ACCEPT
        )
    for row in action_request.additional_targets.filter(status=ActionRequestStatus.PENDING):
        if _persona_is_npc(row.target_persona) and _request_is_resolvable(action_request):
            respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)
    return result


def _resolve_enhanced_action(  # noqa: PLR0913
    *,
    character: ObjectDB,
    technique: Technique,
    action_template: ActionTemplate,
    action_key: str,
    difficulty: int,
    context: ResolutionContext,
    effort_modifier: int = 0,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
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
        effort_modifier: The EFFORT_CHECK_MODIFIER for the action's effort level,
            applied as a check-roll modifier (extra_modifiers) on the inner
            start_action_resolution — parity with the plain/area branches (#1293).
        strain_commitment: Optional extra anima the caster commits beyond the
            technique's baseline cost. Forwarded to use_technique so the cost
            calculation accounts for the strain.
        fury_commitment: Optional FuryTier the player declared.
        fury_anchor: CharacterSheet of the anchor character (bond caps the tier).

    Returns:
        EnhancedSceneActionResult with both action_resolution and technique_result.
    """
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.cast_threads import applicable_threads_for_cast  # noqa: PLC0415
    from world.magic.services.fury import run_fury_for_action  # noqa: PLC0415

    applicable_threads = applicable_threads_for_cast(character, technique, cast_pull=cast_pull)

    fury_res = run_fury_for_action(
        character=character,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        source_technique=technique,
    )

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=lambda *, power, ledger, extra_modifiers=0: start_action_resolution(  # noqa: ARG005
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
            extra_modifiers=effort_modifier + extra_modifiers,
        ),
        confirm_soulfray_risk=True,
        strain_commitment=strain_commitment,
        applicable_threads=applicable_threads,
        cast_pull=cast_pull,
        pull_target=context.target,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=fury_res.intensity_bonus if fury_res else 0,
    )

    resolution_result: PendingActionResolution = technique_result.resolution_result  # type: ignore[assignment]
    return EnhancedSceneActionResult(
        action_resolution=resolution_result,
        action_key=action_key,
        technique_result=technique_result,
        fury_committed=fury_res.realized_tier if fury_res else None,
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


def _area_outcome_content(
    *,
    action_request: SceneActionRequest,
    status_word: str,
    outcome_name: str,
) -> str:
    """Build the content line for an area action (no target persona).

    A telling always names its tale (#902) — listeners can't learn a deed the
    echo never identifies.
    """
    initiator_name = action_request.initiator_persona.name
    action_key = action_request.action_key
    if action_request.spread_deed_target is not None:
        outcome_line = (
            f"{initiator_name} spreads the tale of "
            f"«{action_request.spread_deed_target.title}»: "
            f"{status_word} ({outcome_name})"
        )
    else:
        outcome_line = f"{initiator_name} ({action_key}): {status_word} ({outcome_name})"
    return (
        f"{action_request.pose_text}\n{outcome_line}" if action_request.pose_text else outcome_line
    )


def _targeted_outcome_content(
    *,
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
    target_name: str,
    status_word: str,
    outcome_name: str,
) -> str:
    """Build the content line for a targeted action (technique-aware)."""
    initiator_name = action_request.initiator_persona.name
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
    # #1919: Append a fizzle note when the thread pull failed at charge time.
    if result.fizzle_note:
        content += f" — {result.fizzle_note}"
    return content


def _create_result_interaction(
    *,
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
    strain_committed: int = 0,
    target_persona: Persona | None = None,
    fury_committed: FuryTier | None = None,
) -> Interaction | None:
    """Create an interaction recording the result of a scene action.

    Args:
        action_request: The resolved SceneActionRequest.
        result: The resolution outcome (including optional technique result).
        strain_committed: Strain the initiator actually committed; recorded on
            the resulting Interaction for canonical audit.
        target_persona: Override the target persona for the interaction. When
            None, falls back to ``action_request.target_persona`` (the primary
            target). Pass explicitly when resolving an additional target so the
            interaction names the correct persona rather than the primary one.
        fury_committed: Realized FuryTier post-resolution; recorded for audit.
    """
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    success = (check_result.success_level > 0) if check_result is not None else False
    status_word = "Success" if success else "Failure"
    outcome_name = check_result.outcome_name if check_result is not None else "Unknown"

    effective_target = target_persona or action_request.target_persona

    if effective_target is None:
        # Area action (e.g. a telling to the room): no target, optional pose
        # text echoed above the outcome.
        content = _area_outcome_content(
            action_request=action_request,
            status_word=status_word,
            outcome_name=outcome_name,
        )
        receivers: list[Persona] = []
        target_personas: list[Persona] = []
    else:
        content = _targeted_outcome_content(
            action_request=action_request,
            result=result,
            target_name=effective_target.name,
            status_word=status_word,
            outcome_name=outcome_name,
        )
        receivers = [effective_target]
        target_personas = [effective_target]

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
        fury_committed=fury_committed,
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


register_custom_action_resolver("treat_condition", _resolve_treatment_request)
