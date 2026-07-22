"""
Condition Service Layer

Provides the interface for applying, removing, and querying conditions on targets.
Handles all interaction processing, modifier calculations, and round-based updates.

Design principles:
- Everything is math (no binary immunity)
- Intensity - Resistance = Net Value
- Bidirectional modifiers (conditions can be good or bad depending on context)
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    ConditionAppliedPayload,
    ConditionPreApplyPayload,
    ConditionRemovedPayload,
    ConditionStageChangedPayload,
)
from flows.models.triggers import Trigger
from world.achievements.constants import ConditionEventType
from world.checks.constants import ModifierSourceKind
from world.checks.models import CheckType
from world.checks.services import perform_check
from world.checks.types import ModifierContribution
from world.conditions.constants import (
    POISON_CATEGORY_NAME,
    POISON_DAMAGE_TYPE_NAME,
    POISONED_CONDITION_NAME,
    SLOW_POISON_CONDITION_NAME,
    TARGET_EFFECT_ALTERATION,
    TARGET_EFFECT_CONDITION,
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DamageTickTiming,
    DurationType,
    StackBehavior,
    TreatmentTargetKind,
)
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionModifierEffect,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageSuccessLevelMultiplier,
    DamageType,
    PenetrationOutcomeFactor,
    TreatmentAttempt,
    TreatmentTemplate,
)
from world.conditions.types import (
    AdvancementOutcome,
    AdvancementResistFailureKind,
    ApplyConditionResult,
    BulkConditionApplication,
    CapabilityStatus,
    CheckModifierResult,
    ChronicTickSummary,
    ConditionStageAdvanceCheckPayload,
    DamageInteractionResult,
    DecayTickSummary,
    InteractionResult,
    ResistanceModifierResult,
    RoundTickResult,
    SeverityAdvanceResult,
    SeverityDecayResult,
    TreatmentOutcome,
)
from world.game_clock.services import get_ic_now
from world.mechanics.models import CharacterModifier

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole
    from world.magic.models import PendingAlteration, Technique, Thread
    from world.mechanics.models import ModifierTarget
    from world.scenes.models import Scene

# Timing constants
SECONDS_PER_ROUND = 6


def _invalidate_condition_handler(target: "ObjectDB") -> None:  # noqa: OBJECTDB_PARAM
    """Invalidate the target's cached conditions handler.

    ``conditions`` is installed as a ``cached_property`` on ``ObjectParent``
    so every typeclassed object (Character, Room, Exit, Object) exposes the
    handler.  However, a ``ConditionInstance.target`` FK accessor resolved on
    an identity-map MISS returns a bare ``ObjectDB`` instance — Django skips
    the typeclass lookup and returns the base model, which does not go through
    ``ObjectParent``'s MRO and therefore does NOT have ``.conditions``.
    In that case there is no cached handler to invalidate, so silently skipping
    is correct (not a swallowed bug).  ``hasattr`` is the right guard here —
    it is NOT a getattr-literal and carries no linter suppression.
    """
    if hasattr(target, "conditions"):
        target.conditions.invalidate()


# =============================================================================
# Core Service Functions
# =============================================================================


def resolve_damage_type_resistance(
    character: "ObjectDB",  # noqa: OBJECTDB_PARAM
    damage_amount: int,
    damage_type: "DamageType | None",
) -> int:
    """Net damage-type resistance (condition + gift-thread) and return reduced damage (>=0).

    The single source of truth for damage-type resistance across every damage seam
    (#1588). Mirrors the netting that previously lived inlined in
    ``combat.services.apply_damage_to_participant``. When ``damage_type`` is None
    (untyped damage) resistance does not apply — the amount is returned unchanged.

    A negative resistance total (a vulnerability, e.g. a species drawback) *increases*
    damage above the base; a large positive total (high resistance, functioning as
    "immunity") reduces it toward zero but overwhelming damage still exceeds it.

    Args:
        character: the ObjectDB character taking damage (must expose ``.conditions``
            and be passable to ``gift_thread_resistance``).
        damage_amount: the incoming damage before resistance.
        damage_type: a ``DamageType`` instance, or None for untyped damage.

    Returns:
        The damage after subtracting total resistance, clamped to >= 0.
    """
    if damage_type is None:
        return damage_amount
    from world.magic.services import gift_thread_resistance  # noqa: PLC0415

    resistance = character.conditions.resistance_modifier(damage_type)
    resistance += gift_thread_resistance(character, damage_type)
    return max(0, damage_amount - resistance)


def get_active_conditions(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    *,
    category: "ConditionCategory | None" = None,
    condition: ConditionTemplate | None = None,
    include_suppressed: bool = False,
) -> QuerySet[ConditionInstance]:
    """
    Get active condition instances on a target.

    Args:
        target: The ObjectDB instance to query
        category: Filter to specific category instance
        condition: Filter to specific condition template instance
        include_suppressed: Include suppressed conditions

    Returns:
        QuerySet of active ConditionInstance objects
    """
    qs = ConditionInstance.objects.filter(target=target).select_related(
        "condition",
        "condition__category",
        "current_stage",
    )

    if not include_suppressed:
        # Keep in sync with ConditionHandler._canonical_active_qs in handlers.py
        qs = qs.filter(
            Q(is_suppressed=False)
            | Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
        )

    if category:
        qs = qs.filter(condition__category=category)

    if condition:
        qs = qs.filter(condition=condition)

    # #2537: lazy IC-time expiry. Remove any instances whose expires_at has
    # passed before returning them as "active." Removal is always safe
    # (CONDITION_REMOVED event + deferred-death resolution fire via the
    # teardown helper). Uses _teardown_removed_condition_instance directly
    # (not remove_condition) to avoid re-entrancy: remove_condition calls
    # get_condition_instance → get_active_conditions, which would re-enter
    # this function. The instance is already in hand, so the direct teardown
    # (the same path remove_conditions_by_category and clear_all_conditions
    # use) is correct and avoids the loop.
    #
    # Only sweep conditions whose template duration_type is INGAME_TIME.
    # The ``expires_at`` field is also used by the wake-arc system
    # (``_stamp_unconscious_wake_deadline``) as a force-wake backstop on
    # conditions with OTHER duration types (e.g. Unconscious, which is
    # UNTIL_CURED). Sweeping those would remove them before the wake system
    # can process the guaranteed-wake deadline (#2287).
    instances = list(qs)
    if instances:
        now = timezone.now()
        expired = [
            inst
            for inst in instances
            if inst.expires_at is not None
            and now >= inst.expires_at
            and inst.condition.default_duration_type == DurationType.INGAME_TIME
        ]
        if expired:
            for inst in expired:
                _teardown_removed_condition_instance(inst.target, inst)
            # Re-query to exclude removed instances. pk__in is already filtered
            # (derived from the post-filter instances list above), so the
            # category/condition/suppressed filters don't need re-applying.
            surviving_pks = [inst.pk for inst in instances if inst not in expired]
            qs = ConditionInstance.objects.filter(pk__in=surviving_pks).select_related(
                "condition", "condition__category", "current_stage"
            )

    return qs


def has_condition(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    *,
    include_suppressed: bool = False,
) -> bool:
    """
    Check if target has a specific condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        include_suppressed: Count suppressed conditions

    Returns:
        True if condition is present
    """
    return get_active_conditions(
        target, condition=condition, include_suppressed=include_suppressed
    ).exists()


def get_condition_instance(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    *,
    include_suppressed: bool = False,
) -> ConditionInstance | None:
    """
    Get a specific condition instance on a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        include_suppressed: Include suppressed conditions in search

    Returns:
        ConditionInstance or None
    """
    return get_active_conditions(
        target, condition=condition, include_suppressed=include_suppressed
    ).first()


def is_untargetable(target: "ObjectDB") -> bool:  # noqa: OBJECTDB_PARAM
    """True if *target* holds any active intangibility condition.

    Mirrors the derive-on-read pattern: aggregate over the bearer's active,
    non-suppressed, unresolved ConditionInstances whose category grants
    intangibility. Gates target resolution in cast + combat.
    """
    return target.condition_instances.filter(
        condition__category__grants_intangibility=True,
        is_suppressed=False,
        resolved_at__isnull=True,
    ).exists()


def is_concealed(target: "ObjectDB") -> bool:  # noqa: OBJECTDB_PARAM
    """True if *target* holds any active perception-concealing condition.

    Mirrors is_untargetable's derive-on-read pattern (#1225).
    """
    return active_concealments(target).exists()


def can_perceive(actor: "ObjectDB", target: "ObjectDB") -> bool:  # noqa: OBJECTDB_PARAM
    """Whether *actor* can perceive *target*.

    Co-located (the pre-#1225 MVP baseline, unchanged), and either target carries no
    active concealing condition or actor's sheet has detected every concealing
    instance currently active on target (per-observer, not blanket — #1225).
    """
    if target.location not in (actor.location, actor):
        return False
    concealments = active_concealments(target)
    if not concealments.exists():
        return True
    actor_sheet = actor.character_sheet
    if actor_sheet is None:
        return False
    return not concealments.exclude(detected_by=actor_sheet).exists()


def register_detection(
    observer_sheet: "CharacterSheet",
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
) -> None:
    """Record that observer_sheet has pierced target's active concealment(s) (#1225)."""
    for instance in active_concealments(target):
        instance.detected_by.add(observer_sheet)


def _register_unseen_observer_if_concealing(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
) -> None:
    """OOC-notice hook (#1225): any conceals_from_perception condition, on apply,
    registers an unseen-observer grant for the scene at target's location — generic
    across every current and future concealing condition, no per-mechanism plumbing."""
    if not condition.category.conceals_from_perception:
        return
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import register_unseen_observer  # noqa: PLC0415

    scene = get_active_scene(target.location)
    if scene is None:
        return
    try:
        sheet = target.sheet_data
    except CharacterSheet.DoesNotExist:
        return
    register_unseen_observer(scene, sheet, "concealment")


def _clear_unseen_observer_if_concealing(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
) -> None:
    """Inverse of _register_unseen_observer_if_concealing (#1225)."""
    if not condition.category.conceals_from_perception:
        return
    if is_concealed(target):
        # Another independently-applied concealing condition is still active on
        # target — the OOC banner must stay up until the LAST concealment clears,
        # not the first (#1225 review fix).
        return
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import clear_unseen_observer  # noqa: PLC0415

    scene = get_active_scene(target.location)
    if scene is None:
        return
    try:
        sheet = target.sheet_data
    except CharacterSheet.DoesNotExist:
        return
    clear_unseen_observer(scene, sheet)


def active_concealments(target: "ObjectDB") -> QuerySet[ConditionInstance]:  # noqa: OBJECTDB_PARAM
    return target.condition_instances.filter(
        condition__category__conceals_from_perception=True,
        is_suppressed=False,
        resolved_at__isnull=True,
    )


def _resolve_source_vow_anchor(
    source_character: "ObjectDB | None",  # noqa: OBJECTDB_PARAM
) -> "CovenantRole | None":
    """Resolve the applier's engaged-vow anchor for ``ConditionInstance.source_vow`` (#2643).

    The FIRST of ``character.covenant_roles.currently_engaged_roles()`` determines the
    vow key (list order today; a deliberately-chosen "primary vow" concept is a
    #2536-family follow-up, not built here). Its ANCHOR — ``parent_role`` when the
    engaged role resolved to a sub-role, else the role itself — is stamped, never the
    resolved sub-role, matching Thread's ``target_covenant_role_id`` anchor convention
    (a resonance-specialized sub-role is a read-time view, not a distinct vow key).

    Returns ``None`` when there is no source character, the character has no
    ``covenant_roles`` handler (not a real Character typeclass instance — e.g. some
    test doubles), the character has no ``CharacterSheet`` at all (NPCs, unfinalized
    characters — the handler's row-fetch requires one), or the character has no
    currently-engaged role.
    """
    if source_character is None:
        return None
    try:
        roles = source_character.covenant_roles.currently_engaged_roles()
    except AttributeError:
        # Not a real Character typeclass instance (no covenant_roles handler) —
        # some test doubles.
        return None
    except ObjectDoesNotExist:
        # No CharacterSheet (e.g. an NPC-backed or not-yet-finalized caster) — no
        # engaged role is derivable, mirroring every other "no sheet -> no vow" path.
        return None
    if not roles:
        return None
    first = roles[0]
    return first.parent_role or first


@dataclass
class _ApplyConditionParams:
    """Parameters for applying a condition (reduces argument count)."""

    target: "ObjectDB"  # noqa: OBJECTDB_PARAM
    severity: int = 1
    duration_rounds: int | None = None
    stack_count: int = 1
    source_character: "ObjectDB | None" = None
    source_technique: "Technique | None" = None
    source_description: str = ""
    source_vow: "CovenantRole | None" = None


@dataclass
class _BulkConditionContext:
    """Pre-fetched data for bulk condition application.

    Holds all DB-fetched state needed by _apply_single, avoiding per-call queries.
    """

    # target_id -> list of active ConditionInstance
    active_instances_by_target: dict[int, list[ConditionInstance]] = field(default_factory=dict)
    # (target_id, condition_id) -> ConditionInstance or None
    existing_pairs: dict[tuple[int, int], ConditionInstance] = field(default_factory=dict)
    # All prevention interactions for the template set
    prevention_interactions: list[ConditionConditionInteraction] = field(default_factory=list)
    # All application interactions for the template set
    application_interactions: list[ConditionConditionInteraction] = field(default_factory=list)
    # condition_id -> first ConditionStage (for progressive templates)
    first_stages: dict[int, ConditionStage] = field(default_factory=dict)

    def get_existing_instance(
        self,
        target_id: int,
        condition_id: int,
    ) -> ConditionInstance | None:
        return self.existing_pairs.get((target_id, condition_id))

    def get_active_condition_ids(self, target_id: int) -> set[int]:
        return {i.condition_id for i in self.active_instances_by_target.get(target_id, [])}


def _build_bulk_context(
    targets: list["ObjectDB"],  # noqa: OBJECTDB_PARAM
    templates: list[ConditionTemplate],
) -> _BulkConditionContext:
    """Batch-fetch all data needed for applying conditions to multiple targets.

    One query per data type instead of per (target, condition) pair.
    """
    target_ids = [t.pk for t in targets]
    template_ids = [t.pk for t in templates]

    # Suppression filter matching get_active_conditions() default behavior
    not_suppressed = Q(is_suppressed=False) | Q(
        suppressed_until__isnull=False,
        suppressed_until__lt=timezone.now(),
    )

    # 1. All active (non-suppressed) condition instances for all targets (1 query)
    all_instances = list(
        ConditionInstance.objects.filter(
            not_suppressed,
            target_id__in=target_ids,
        ).select_related("condition", "condition__category", "current_stage")
    )

    active_by_target: dict[int, list[ConditionInstance]] = {}
    for inst in all_instances:
        active_by_target.setdefault(inst.target_id, []).append(inst)

    # 2. Build existing pairs from all_instances (no extra query — m3 fix)
    existing_pairs: dict[tuple[int, int], ConditionInstance] = {
        (inst.target_id, inst.condition_id): inst
        for inst in all_instances
        if inst.condition_id in template_ids
    }

    # 3. All prevention interactions involving these templates (1 query with Q OR)
    # Include template_ids so intra-batch template interactions are detected
    all_condition_ids = {i.condition_id for i in all_instances} | set(template_ids)
    prevention_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_OTHER,
            )
            | Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
                outcome=ConditionInteractionOutcome.PREVENT_SELF,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 4. All application interactions involving these templates (1 query)
    application_interactions = list(
        ConditionConditionInteraction.objects.filter(
            Q(
                condition_id__in=template_ids,
                other_condition_id__in=all_condition_ids,
                trigger=ConditionInteractionTrigger.ON_SELF_APPLIED,
            )
            | Q(
                condition_id__in=all_condition_ids,
                other_condition_id__in=template_ids,
                trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            )
        )
        .select_related("condition", "other_condition")
        .order_by("-priority")
    )

    # 5. First stages for progressive templates (1 query, PG DISTINCT ON)
    progressive_ids = [t.pk for t in templates if t.has_progression]
    first_stages: dict[int, ConditionStage] = {}
    if progressive_ids:
        for stage in (
            ConditionStage.objects.filter(condition_id__in=progressive_ids)
            .order_by("condition_id", "stage_order")
            .distinct("condition_id")
        ):
            first_stages[stage.condition_id] = stage

    return _BulkConditionContext(
        active_instances_by_target=active_by_target,
        existing_pairs=existing_pairs,
        prevention_interactions=prevention_interactions,
        application_interactions=application_interactions,
        first_stages=first_stages,
    )


def _check_prevention_from_context(
    target_id: int,
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> ConditionTemplate | None:
    """Check prevention using pre-fetched interactions."""
    active_condition_ids = ctx.get_active_condition_ids(target_id)
    for interaction in ctx.prevention_interactions:
        # Check "existing prevents incoming"
        if (
            interaction.other_condition_id == incoming_condition.pk
            and interaction.condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_OTHER_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_OTHER
        ):
            return interaction.condition
        # Check "incoming self-prevents"
        if (
            interaction.condition_id == incoming_condition.pk
            and interaction.other_condition_id in active_condition_ids
            and interaction.trigger == ConditionInteractionTrigger.ON_SELF_APPLIED
            and interaction.outcome == ConditionInteractionOutcome.PREVENT_SELF
        ):
            return interaction.other_condition
    return None


def _check_application_resist(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    template: ConditionTemplate,
) -> bool:
    """Return True if *target* resists having *template* applied.

    Rolls the target's own resist_check_type against resist_difficulty.
    success_level > 0 means the target's roll beat the difficulty — resisted.
    resist_check_type=None (the default) means unconditional application;
    this always returns False in that case, matching every existing
    ConditionTemplate's current behavior unchanged.
    """
    if template.resist_check_type is None:
        return False
    result = perform_check(
        character=target,
        check_type=template.resist_check_type,
        target_difficulty=template.resist_difficulty,
    )
    return int(result.success_level) > 0


def _process_interactions_from_context(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    incoming_condition: ConditionTemplate,
    ctx: _BulkConditionContext,
) -> InteractionResult:
    """Process application interactions using pre-fetched data.

    Mutates ctx.active_instances_by_target in-place so subsequent
    iterations in bulk_apply_conditions see removals from earlier iterations.
    """
    result = InteractionResult()
    active_instances = ctx.active_instances_by_target.get(target.pk, [])
    active_condition_ids = {i.condition_id for i in active_instances}

    for interaction in ctx.application_interactions:
        # Filter to interactions relevant to this target's active conditions
        if interaction.condition_id == incoming_condition.pk:
            if interaction.other_condition_id not in active_condition_ids:
                continue
            match_id = interaction.other_condition_id
        elif interaction.other_condition_id == incoming_condition.pk:
            if interaction.condition_id not in active_condition_ids:
                continue
            match_id = interaction.condition_id
        else:
            continue

        existing_instance = next(
            (i for i in active_instances if i.condition_id == match_id),
            None,
        )
        if not existing_instance:
            continue

        if _should_remove_existing(interaction, incoming_condition):
            result.removed.append(existing_instance.condition)
            removed_condition = existing_instance.condition
            removed_target_id = existing_instance.target_id
            existing_instance.delete()
            _clear_unseen_observer_if_concealing(target, removed_condition)
            active_instances.remove(existing_instance)
            active_condition_ids.discard(match_id)
            # Clean existing_pairs so later batch entries don't resurrect it
            ctx.existing_pairs.pop(
                (removed_target_id, match_id),
                None,
            )

    return result


def _compute_ingame_time_expires(template: ConditionTemplate) -> datetime | None:
    """Compute the real-time ``expires_at`` for an INGAME_TIME condition.

    For ``DurationType.INGAME_TIME``, ``default_duration_value`` is interpreted
    as IC hours. The real-time expiration is ``ic_duration / time_ratio`` from
    now, where ``time_ratio`` is IC seconds per real second (default 3.0).

    Returns ``None`` if no game clock exists or the duration value is falsy —
    the condition simply won't expire by IC time (degrades to PERMANENT-like).

    Args:
        template: The condition template (must have ``default_duration_type ==
            INGAME_TIME``).

    Returns:
        A real-time datetime for expiration, or ``None``.
    """
    ic_hours = template.default_duration_value or 0
    if ic_hours <= 0:
        return None

    from world.game_clock.models import GameClock  # noqa: PLC0415

    clock = GameClock.get_active()
    if clock is None:
        return None

    # time_ratio = IC seconds per real second (default 3.0).
    # real_duration = ic_duration / time_ratio.
    real_seconds = (ic_hours * 3600) / clock.time_ratio
    return timezone.now() + timedelta(seconds=real_seconds)


def _create_instance_from_context(
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Create a new condition instance using pre-fetched stage data."""
    rounds = params.duration_rounds or template.default_duration_value
    rounds_remaining = rounds if template.default_duration_type == DurationType.ROUNDS else None

    expires_at = (
        _compute_ingame_time_expires(template)
        if template.default_duration_type == DurationType.INGAME_TIME
        else None
    )

    first_stage = ctx.first_stages.get(template.pk) if template.has_progression else None
    stage_rounds = (
        first_stage.rounds_to_next
        if first_stage and first_stage.rounds_to_next is not None
        else None
    )

    instance = ConditionInstance.objects.create(
        target=params.target,
        condition=template,
        severity=params.severity,
        stacks=1,
        rounds_remaining=rounds_remaining,
        expires_at=expires_at,
        current_stage=first_stage,
        stage_rounds_remaining=stage_rounds,
        source_character=params.source_character,
        source_technique=params.source_technique,
        source_description=params.source_description,
        source_vow=params.source_vow,
    )

    return ApplyConditionResult(
        success=True,
        instance=instance,
        stacks_added=1,
        message=f"{template.name} applied",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


def _apply_single(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    ctx: _BulkConditionContext,
) -> ApplyConditionResult:
    """Apply a single condition using pre-fetched context data.

    Core logic extracted from apply_condition. All DB reads come from ctx;
    only writes (create/save/delete) hit the database.
    """
    prevention = _check_prevention_from_context(target.pk, template, ctx)
    if prevention:
        return ApplyConditionResult(
            success=False,
            was_prevented=True,
            prevented_by=prevention,
            message=f"{template.name} was prevented by {prevention.name}",
        )

    interaction_results = _process_interactions_from_context(target, template, ctx)

    existing = ctx.get_existing_instance(target.pk, template.pk)

    if existing:
        if template.is_stackable and existing.stacks < template.max_stacks:
            return _handle_stacking(existing, template, params, interaction_results)
        return _handle_refresh(existing, template, params, interaction_results)

    apply_result = _create_instance_from_context(
        template,
        params,
        interaction_results,
        ctx,
    )

    # Update context so subsequent bulk iterations see this new instance
    if apply_result.instance:
        new_inst = apply_result.instance
        ctx.existing_pairs[(target.pk, template.pk)] = new_inst
        ctx.active_instances_by_target.setdefault(target.pk, []).append(
            new_inst,
        )

    return apply_result


def _handle_stacking(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
) -> ApplyConditionResult:
    """Handle stacking for an existing condition instance."""
    existing.stacks += params.stack_count

    if template.stack_behavior in (
        StackBehavior.INTENSITY,
        StackBehavior.BOTH,
    ):
        existing.severity = max(existing.severity, params.severity)

    if template.stack_behavior in (
        StackBehavior.DURATION,
        StackBehavior.BOTH,
    ):
        rounds = params.duration_rounds or template.default_duration_value
        if existing.rounds_remaining is not None:
            existing.rounds_remaining += rounds

    existing.save()

    return ApplyConditionResult(
        success=True,
        instance=existing,
        stacks_added=params.stack_count,
        message=f"{template.name} stacked to {existing.stacks}",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


def _handle_refresh(
    existing: ConditionInstance,
    template: ConditionTemplate,
    params: _ApplyConditionParams,
    interaction_results: InteractionResult,
) -> ApplyConditionResult:
    """Handle refresh for a non-stackable existing condition."""
    if params.severity < existing.severity:
        return ApplyConditionResult(
            success=True,
            instance=existing,
            message=f"{template.name} already active at higher severity",
            removed_conditions=interaction_results.removed,
            applied_conditions=interaction_results.applied,
        )

    existing.severity = params.severity
    rounds = params.duration_rounds or template.default_duration_value
    if template.default_duration_type == DurationType.ROUNDS:
        existing.rounds_remaining = rounds
    elif template.default_duration_type == DurationType.INGAME_TIME:
        existing.expires_at = _compute_ingame_time_expires(template)
    existing.save()

    return ApplyConditionResult(
        success=True,
        instance=existing,
        message=f"{template.name} refreshed",
        removed_conditions=interaction_results.removed,
        applied_conditions=interaction_results.applied,
    )


@transaction.atomic
def apply_condition(  # noqa: PLR0913
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    *,
    severity: int = 1,
    duration_rounds: int | None = None,
    source_character: "ObjectDB | None" = None,  # noqa: OBJECTDB_PARAM
    source_technique: "Technique | None" = None,
    source_description: str = "",
) -> ApplyConditionResult:
    """Apply a condition to a target, handling stacking and interactions.

    Thin wrapper around _apply_single — builds a single-item context
    and delegates. For applying multiple conditions, use bulk_apply_conditions.

    Emits reactive events:
    - CONDITION_PRE_APPLY (cancellable)
    - CONDITION_APPLIED (post-save, frozen)
    """
    source = source_character or source_technique
    target_location = target.location
    pre_payload = ConditionPreApplyPayload(
        target=target,
        template=condition,
        source=source,
        stage=None,
    )
    if target_location is not None:
        stack = emit_event(
            EventName.CONDITION_PRE_APPLY,
            pre_payload,
            location=target_location,
        )
        if stack.was_cancelled():
            return ApplyConditionResult(
                success=False,
                instance=None,
                message="cancelled by trigger",
                removed_conditions=[],
                applied_conditions=[],
            )

    if _check_application_resist(target, condition):
        return ApplyConditionResult(
            success=False,
            instance=None,
            message="resisted",
            removed_conditions=[],
            applied_conditions=[],
        )

    ctx = _build_bulk_context([target], [condition])
    params = _ApplyConditionParams(
        target=target,
        severity=severity,
        duration_rounds=duration_rounds,
        source_character=source_character,
        source_technique=source_technique,
        source_description=source_description,
        source_vow=_resolve_source_vow_anchor(source_character),
    )
    result = _apply_single(target, condition, params, ctx)

    _invalidate_condition_handler(target)

    if result.success and result.instance is not None:
        _notify_stories_condition_applied(target, result.instance)
        _install_reactive_side_effects(target, condition, result.instance)
        _make_just_installed_triggers_live(target)
        _register_unseen_observer_if_concealing(target, condition)

    if result.instance is not None and target_location is not None:
        emit_event(
            EventName.CONDITION_APPLIED,
            ConditionAppliedPayload(
                target=target,
                instance=result.instance,
                stage=result.instance.current_stage,
            ),
            location=target_location,
        )

    return result


def apply_condition_by_name(*, payload: object, condition_name: str) -> None:
    """Apply a named condition to the character carried by the event payload.

    General-purpose ``CALL_SERVICE_FUNCTION`` target for flow steps that need to
    apply a condition by name. ``payload`` must have a ``character`` attribute
    (e.g. ``MovedPayload``). Silently no-ops if the condition name does not
    exist — allows authored content to reference conditions not yet seeded
    in a given environment without raising.

    Usage in a FlowStepDefinition::

        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name="world.conditions.services.apply_condition_by_name",
        parameters={"payload": "@payload", "condition_name": "<name>"},
    """
    try:
        template = ConditionTemplate.get_by_name(condition_name)
    except ConditionTemplate.DoesNotExist:
        return
    target = payload.character  # type: ignore[union-attr]
    apply_condition(target=target, condition=template)


@transaction.atomic
def bulk_apply_conditions(
    applications: list[BulkConditionApplication],
    *,
    source_character: "ObjectDB | None" = None,  # noqa: OBJECTDB_PARAM
    source_technique: "Technique | None" = None,
    source_description: str = "",
) -> list[ApplyConditionResult]:
    """Apply multiple conditions in a single transaction with batched queries.

    Each BulkConditionApplication carries its own severity, duration_rounds,
    and stack_count. Source attribution (caster, technique, description) is
    shared across the batch — a single cast is the source of all entries.

    Fetches all needed data (active instances, interactions, stages) in ~5
    queries regardless of how many (target, condition) pairs are passed, PLUS
    one perform_check call (and its own query cost) per item whose template
    sets resist_check_type (#1738) — mirrors the same caveat already accepted
    for _attempt_removal's bulk removal loop.
    Each application still respects prevention, interaction, and stacking rules.
    """
    if not applications:
        return []

    targets = list({app.target for app in applications})
    templates = list({app.template for app in applications})

    ctx = _build_bulk_context(targets, templates)
    # Resolved once per batch (#2643) — a single cast is the source of every entry
    # (see the docstring above), so the vow anchor is shared across the whole batch
    # exactly like source_character/source_technique/source_description already are.
    source_vow = _resolve_source_vow_anchor(source_character)

    results: list[ApplyConditionResult] = []
    for app in applications:
        source = source_character or source_technique
        target_location = app.target.location
        pre_payload = ConditionPreApplyPayload(
            target=app.target,
            template=app.template,
            source=source,
            stage=None,
        )
        if target_location is not None:
            stack = emit_event(
                EventName.CONDITION_PRE_APPLY,
                pre_payload,
                location=target_location,
            )
            if stack.was_cancelled():
                results.append(
                    ApplyConditionResult(
                        success=False,
                        instance=None,
                        message="cancelled by trigger",
                        removed_conditions=[],
                        applied_conditions=[],
                    )
                )
                continue

        if _check_application_resist(app.target, app.template):
            results.append(
                ApplyConditionResult(
                    success=False,
                    instance=None,
                    message="resisted",
                    removed_conditions=[],
                    applied_conditions=[],
                )
            )
            continue

        params = _ApplyConditionParams(
            target=app.target,
            severity=app.severity,
            duration_rounds=app.duration_rounds,
            stack_count=app.stack_count,
            source_character=source_character,
            source_technique=source_technique,
            source_description=source_description,
            source_vow=source_vow,
        )
        result = _apply_single(app.target, app.template, params, ctx)

        # Invalidate immediately after the mutation and BEFORE emitting
        # CONDITION_APPLIED, mirroring the single-target apply_condition ordering.
        # A reactive handler that fires during CONDITION_APPLIED must see a fresh
        # cache — if we deferred invalidation to a second pass after all emits,
        # any reactive subscriber would read the stale pre-bulk cache instead.
        _invalidate_condition_handler(app.target)

        if result.success and result.instance is not None:
            _notify_stories_condition_applied(app.target, result.instance)
            _install_reactive_side_effects(app.target, app.template, result.instance)
            _make_just_installed_triggers_live(app.target)
            _register_unseen_observer_if_concealing(app.target, app.template)
            _stamp_cast_positions(result.instance, app)

        if result.instance is not None and target_location is not None:
            emit_event(
                EventName.CONDITION_APPLIED,
                ConditionAppliedPayload(
                    target=app.target,
                    instance=result.instance,
                    stage=result.instance.current_stage,
                ),
                location=target_location,
            )

        results.append(result)

    return results


def _stamp_cast_positions(instance: "ConditionInstance", app: BulkConditionApplication) -> None:
    """Set ``app``'s optional cast-time position FKs on ``instance`` (#2206).

    Must run BEFORE ``CONDITION_APPLIED`` is emitted (caller-enforced ordering,
    see ``BulkConditionApplication`` docstring) — same-event reactive handlers
    (``create_obstacle_on_condition`` and siblings, #2019) read these fields off
    ``payload.instance`` synchronously.
    """
    update_fields: list[str] = []
    if app.cast_destination_id:
        instance.cast_destination_id = app.cast_destination_id
        update_fields.append("cast_destination_id")
    if app.cast_position_a_id:
        instance.cast_position_a_id = app.cast_position_a_id
        update_fields.append("cast_position_a_id")
    if app.cast_position_b_id:
        instance.cast_position_b_id = app.cast_position_b_id
        update_fields.append("cast_position_b_id")
    if update_fields:
        instance.save(update_fields=update_fields)


def _make_just_installed_triggers_live(target: "ObjectDB") -> None:  # noqa: OBJECTDB_PARAM
    """Synchronously refresh ``target``'s trigger handler after install (#1584).

    ``_install_reactive_side_effects`` installs Trigger rows via ``on_trigger_added``,
    whose cache reset is ``transaction.on_commit``-deferred for cross-transaction
    rollback safety — so the new triggers are NOT visible within the current
    transaction. An active cast-time effect (e.g. summon) wired as a
    ``CONDITION_APPLIED`` trigger on its OWN condition must catch its own application,
    and ``apply_condition``/``bulk_apply_conditions`` emit ``CONDITION_APPLIED``
    immediately after installing. Refresh synchronously here so that emit sees the
    just-installed trigger (mirrors combat ``resolve_round``'s pre-attack refresh).
    """
    handler = target.trigger_handler
    if handler is not None:
        handler.refresh()


def _install_reactive_side_effects(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    instance: ConditionInstance,
) -> None:
    """Auto-install reactive triggers and increment bridged stats after apply.

    Both lookups go through the cached handler — never touches
    template.reactive_triggers.all() or ConditionStatRule.objects.filter() directly.

    Trigger.obj FK accepts ObjectDB directly; source_condition ensures
    CASCADE cleanup when the ConditionInstance is removed.

    Stat increments are guarded: non-character targets (rooms, items)
    lack sheet_data and raise DoesNotExist — the increment loop is skipped.
    """
    handler = condition.reactive_handler

    # Auto-install reactive triggers via the cached handler.
    trigger_defs = handler.reactive_trigger_definitions
    if trigger_defs:
        created_triggers = Trigger.objects.bulk_create(
            [
                Trigger(
                    trigger_definition=td,
                    obj=target,
                    source_condition=instance,
                )
                for td in trigger_defs
            ]
        )
        # Notify the target's in-memory TriggerHandler so the new rows are
        # visible to the NEXT emit_event dispatch (bulk_create bypasses
        # save(), so on_trigger_added is not called automatically).
        trigger_handler = target.trigger_handler
        if trigger_handler is not None:
            for new_trigger in created_triggers:
                trigger_handler.on_trigger_added(new_trigger)

    # Auto-increment bridged stats via the cached handler.
    try:
        sheet_data = target.sheet_data
    except ObjectDoesNotExist:
        sheet_data = None
    if sheet_data is not None:
        for rule in handler.stat_rules_for_event(ConditionEventType.GAINED):
            sheet_data.stats.increment(rule.stat, amount=rule.increment_amount)


def _notify_stories_condition_applied(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    instance: ConditionInstance,
) -> None:
    """Route condition-applied events to the stories reactivity module.

    Only fires when the target is a playable character with a sheet; if
    the target has no CharacterSheet (e.g., an NPC ObjectDB that isn't on
    the roster), silently skip — nothing to re-evaluate.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.stories.services.reactivity import on_condition_applied  # noqa: PLC0415

    try:
        sheet = target.sheet_data
    except CharacterSheet.DoesNotExist:
        return
    on_condition_applied(sheet, instance)


def _notify_stories_condition_expired(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
) -> None:
    """Route condition-removed events to the stories reactivity module.

    Covers Task 3.4 — the hook exists so future inverse/blocker-lifted
    predicates can flip on condition removal. Current CONDITION_HELD
    predicates don't un-flip on removal (SUCCESS is sticky).
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.stories.services.reactivity import on_condition_expired  # noqa: PLC0415

    try:
        sheet = target.sheet_data
    except CharacterSheet.DoesNotExist:
        return
    on_condition_expired(sheet, condition)


def _teardown_removed_condition_instance(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    instance: ConditionInstance,
) -> ConditionTemplate:
    """Fully delete ``instance`` and run every side effect a removal must trigger.

    Shared by ``remove_condition`` (full-stack removal branch), ``remove_conditions_by_category``,
    and ``clear_all_conditions`` so bulk-clear paths never bypass the CONDITION_REMOVED event,
    stories re-evaluation, the OOC unseen-observer clear hook (#1225), or deferred-death
    resolution the way a raw queryset ``.delete()`` would. Always removes the instance outright —
    callers needing partial-stack reduction (``remove_condition``'s ``remove_all_stacks=False``
    branch) do not go through this helper.
    """
    instance_pk = instance.pk
    condition = instance.condition
    source = instance.source_character or instance.source_technique
    target_location = target.location

    instance.delete()
    _invalidate_condition_handler(target)
    if target_location is not None:
        emit_event(
            EventName.CONDITION_REMOVED,
            ConditionRemovedPayload(
                target=target,
                instance_id=instance_pk,
                template=condition,
                source=source,
            ),
            location=target_location,
        )
    _notify_stories_condition_expired(target, condition)
    _clear_unseen_observer_if_concealing(target, condition)
    _resolve_deferred_death_on_expiry(target, condition)
    return condition


@transaction.atomic
def remove_condition(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    *,
    remove_all_stacks: bool = True,
    include_suppressed: bool = False,
) -> bool:
    """
    Remove a condition from a target.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        remove_all_stacks: If False, only remove one stack
        include_suppressed: Also remove the condition if it is currently
            suppressed (default skips suppressed instances)

    Returns:
        True if condition was removed

    Emits reactive events:
    - CONDITION_REMOVED (post-delete, frozen)
    """
    instance = get_condition_instance(target, condition, include_suppressed=include_suppressed)
    if not instance:
        return False

    instance_pk = instance.pk
    source = instance.source_character or instance.source_technique
    target_location = target.location

    if not remove_all_stacks and instance.stacks > 1:
        instance.stacks -= 1
        instance.save()
        _invalidate_condition_handler(target)
        if target_location is not None:
            emit_event(
                EventName.CONDITION_REMOVED,
                ConditionRemovedPayload(
                    target=target,
                    instance_id=instance_pk,
                    template=condition,
                    source=source,
                ),
                location=target_location,
            )
        # Single-stack reduction does not fully lift the condition; no
        # stories re-evaluation needed until the condition is gone.
        return True

    _teardown_removed_condition_instance(target, instance)
    return True


def _resolve_deferred_death_on_expiry(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: "ConditionTemplate",
) -> None:
    """Emit CHARACTER_KILLED if the expiring condition was deferring a pending death.

    Checks two gates: the removed condition must have carried the 'death_deferred'
    property, and the target's CharacterVitals.death_deferred_pending must be True
    (set when CHARACTER_KILLED was suppressed during damage resolution). Both gates
    must hold to avoid spurious kills on unrelated condition removal.
    """
    if not condition.properties.filter(name="death_deferred").exists():
        return

    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    try:
        sheet = target.sheet_data
        vitals = CharacterVitals.objects.get(character_sheet=sheet)
    except (CharacterVitals.DoesNotExist, CharacterSheet.DoesNotExist):
        return

    if not vitals.death_deferred_pending:
        return

    vitals.death_deferred_pending = False
    vitals.save(update_fields=["death_deferred_pending"])

    target_location = target.location
    if target_location is not None:
        from flows.constants import EventName  # noqa: PLC0415
        from flows.events.payloads import CharacterKilledPayload  # noqa: PLC0415

        emit_event(
            EventName.CHARACTER_KILLED,
            CharacterKilledPayload(character=target, source_event=None),
            location=target_location,
        )


@transaction.atomic
def remove_conditions_by_category(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    category: "ConditionCategory",
) -> list[ConditionTemplate]:
    """
    Remove all conditions in a category from a target.

    Args:
        target: The ObjectDB instance
        category: ConditionCategory instance to remove

    Returns:
        List of removed ConditionTemplates

    Reuses ``_teardown_removed_condition_instance`` per instance (the same helper
    ``remove_condition`` uses) rather than a raw queryset ``.delete()``, so the OOC
    unseen-observer clear hook (#1225) and every other per-instance teardown side
    effect fires for a bulk category clear too.
    """
    instances = list(get_active_conditions(target, category=category))
    return [_teardown_removed_condition_instance(target, instance) for instance in instances]


@transaction.atomic
def expire_end_of_combat_conditions(
    targets: Iterable["ObjectDB"],  # noqa: OBJECTDB_PARAM
) -> list[ConditionTemplate]:
    """Remove all UNTIL_END_OF_COMBAT conditions from the given targets.

    Called when a combat encounter completes (see
    ``world.combat.services.cleanup_completed_encounter``). The duration
    countdown in ``_process_duration_and_progression`` only decrements ROUNDS
    instances, so nothing else expires end-of-combat conditions — without this
    sweep they would persist indefinitely after combat ends.

    Reuses ``remove_condition`` per instance so the full teardown fires
    (CONDITION_REMOVED reactive event, stories notification, deferred-death
    resolution). Suppressed instances are included. Idempotent: targets with
    no such conditions are no-ops, so it composes safely with system-specific
    sweeps that already removed their own buffs (e.g. covenant rites).

    Args:
        targets: ObjectDB instances to sweep (encounter participants and
            opponents). ``None`` entries are ignored.

    Returns:
        The list of removed ConditionTemplates.
    """
    target_list = [t for t in targets if t is not None]
    if not target_list:
        return []

    instances = ConditionInstance.objects.filter(
        target_id__in=[t.pk for t in target_list],
        condition__default_duration_type=DurationType.UNTIL_END_OF_COMBAT,
    ).select_related("condition", "target")

    removed: list[ConditionTemplate] = []
    for instance in instances:
        was_removed = remove_condition(instance.target, instance.condition, include_suppressed=True)
        if was_removed:
            removed.append(instance.condition)
    return removed


@transaction.atomic
def expire_scene_scoped_conditions(
    targets: Iterable["ObjectDB"],  # noqa: OBJECTDB_PARAM
) -> list[ConditionTemplate]:
    """Remove all SCENE-duration conditions from the given targets.

    Called when a scene finishes (see ``finish_scene_full`` in
    ``world.scenes.scene_admin_services``). Mirrors
    ``expire_end_of_combat_conditions``: queries by
    ``condition__default_duration_type=DurationType.SCENE`` and calls
    ``remove_condition`` per instance so the full teardown fires
    (CONDITION_REMOVED reactive event, stories notification, deferred-death
    resolution). Suppressed instances are included.

    Idempotent: targets with no SCENE-duration conditions are no-ops, so it
    composes safely with system-specific sweeps that already removed their own
    scene-scoped state.

    Args:
        targets: ObjectDB instances to sweep (scene participants). ``None``
            entries are ignored.

    Returns:
        The list of removed ConditionTemplates.
    """
    target_list = [t for t in targets if t is not None]
    if not target_list:
        return []

    instances = ConditionInstance.objects.filter(
        target_id__in=[t.pk for t in target_list],
        condition__default_duration_type=DurationType.SCENE,
    ).select_related("condition", "target")

    removed: list[ConditionTemplate] = []
    for instance in instances:
        was_removed = remove_condition(instance.target, instance.condition, include_suppressed=True)
        if was_removed:
            removed.append(instance.condition)
    return removed


# =============================================================================
# Interaction Processing
# =============================================================================


def _should_remove_existing(
    interaction: ConditionConditionInteraction,
    incoming_condition: ConditionTemplate,
) -> bool:
    """Determine if an interaction should remove the existing condition."""
    outcome = interaction.outcome
    is_existing_owner = interaction.condition != incoming_condition

    if outcome == ConditionInteractionOutcome.REMOVE_SELF:
        # Remove self = existing condition removes itself when it reacts
        return is_existing_owner

    if outcome == ConditionInteractionOutcome.REMOVE_OTHER:
        # Remove other = incoming's interaction removes the existing
        return not is_existing_owner

    if outcome in (
        ConditionInteractionOutcome.REMOVE_BOTH,
        ConditionInteractionOutcome.MERGE,
    ):
        # These always remove the existing condition
        return True

    return False


@transaction.atomic
def process_damage_interactions(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    damage_type: DamageType,
) -> DamageInteractionResult:
    """
    Process condition interactions when target takes damage.

    Args:
        target: The ObjectDB taking damage
        damage_type: DamageType instance

    Returns:
        DamageInteractionResult with modifier percent and condition changes.
        Caller applies the modifier to their damage calculation.
    """
    dtype = damage_type

    result = DamageInteractionResult(
        damage_modifier_percent=0,
        removed_conditions=[],
        applied_conditions=[],
    )

    # Get all damage interactions for active conditions
    active_instances = list(get_active_conditions(target))
    condition_ids = [i.condition_id for i in active_instances]

    interactions = ConditionDamageInteraction.objects.filter(
        condition_id__in=condition_ids,
        damage_type=dtype,
    ).select_related("condition", "applies_condition")

    instance_map = {i.condition_id: i for i in active_instances}

    for interaction in interactions:
        instance = instance_map.get(interaction.condition_id)
        if not instance:
            continue

        # Track interactions with a non-trivial effect for narration (#2018).
        is_non_trivial = (
            interaction.damage_modifier_percent != 0
            or interaction.removes_condition
            or interaction.applies_condition is not None
        )
        if is_non_trivial:
            result.fired_interactions.append(interaction)

        # Accumulate damage modifier
        result.damage_modifier_percent += interaction.damage_modifier_percent

        # Handle condition removal
        if interaction.removes_condition:
            result.removed_conditions.append(instance)
            removed_condition = instance.condition
            instance.delete()
            _clear_unseen_observer_if_concealing(target, removed_condition)
            del instance_map[interaction.condition_id]

        # Handle applying new condition
        if interaction.applies_condition:
            apply_result = apply_condition(
                target,
                interaction.applies_condition,
                severity=interaction.applied_condition_severity,
                source_description=f"Triggered by {dtype.name} damage",
            )
            if apply_result.success and apply_result.instance:
                result.applied_conditions.append(apply_result.instance)

    # Invalidate once after all interactions — covers removed conditions.
    # apply_condition (above) also invalidates, but if only removals occurred
    # (no applies), the cache must still be cleared.
    _invalidate_condition_handler(target)

    return result


# =============================================================================
# Modifier Queries
# =============================================================================


def _passive_capability_grants(character_sheet: "CharacterSheet") -> set[int]:
    """Thread-passive CapabilityType PKs granted to ``character_sheet`` (#751 B2).

    Single source of thread-passive grants — delegates to the B1 handler
    (``CharacterThreadHandler.passive_capability_grants``), the canonical,
    engagement-gated authority. Prefers the character's memoized ``.threads``
    handler (a typeclass ``cached_property`` returning the same instance across
    calls in a request), so a sweep over many techniques reuses one cached grant
    set instead of re-querying per requirement (no N+1). Falls back to a fresh
    ``CharacterThreadHandler`` only when ``.threads`` is unavailable — e.g. when
    ``character_sheet.character`` is a bare ObjectDB (the test setup in
    test_services.py), where that lazy property is absent. The handler only needs
    ``character.sheet_data``, which a sheet-bearing ObjectDB always exposes.
    Magic is imported locally to avoid a circular import at module load.
    """
    character = character_sheet.character
    try:
        handler = character.threads
    except AttributeError:
        from world.magic.handlers import CharacterThreadHandler  # noqa: PLC0415

        handler = CharacterThreadHandler(character)
    return handler.passive_capability_grants()


def _technique_capability_values(character_sheet: "CharacterSheet") -> dict[int, int]:
    """Best (max) technique-granted value per CapabilityType, for the agency oracle (#2504).

    One query over ``TechniqueCapabilityGrant`` restricted to the character's KNOWN
    techniques (``technique__character_grants__character=character_sheet``), and further
    restricted to ``prerequisite__isnull=True`` — a source-level prerequisite is
    contextual to a target and stays availability-only (see
    ``get_capability_sources_for_character`` in world.mechanics.services, which reads
    ALL grants including prerequisite-gated ones for that purpose). Reuses
    ``TechniqueCapabilityGrant.calculate_value()`` — never re-derives the
    base + intensity formula. Grants with ``calculate_value() <= 0`` are skipped.
    When multiple known techniques grant the same capability, the fold is MAX, not
    sum (ADR-0034 individuation) — stacking many techniques must not inflate an
    unrelated capability. Magic is imported locally to avoid a circular import at
    module load, mirroring ``_passive_capability_grants`` above.

    Args:
        character_sheet: The character's CharacterSheet.

    Returns:
        Dict mapping CapabilityType PK to the best positive technique-granted value.
    """
    from world.magic.models.techniques import TechniqueCapabilityGrant  # noqa: PLC0415

    grants = TechniqueCapabilityGrant.objects.filter(
        technique__character_grants__character=character_sheet,
        prerequisite__isnull=True,
    ).select_related("technique")

    totals: dict[int, int] = {}
    for grant in grants:
        value = grant.calculate_value()
        if value <= 0:
            continue
        cap_id = grant.capability_id
        totals[cap_id] = max(totals.get(cap_id, 0), value)
    return totals


def get_capability_status(
    character_sheet: "CharacterSheet",
    capability: CapabilityType,
) -> CapabilityStatus:
    """
    Get the status of a capability for a target based on active conditions.

    Collects additive values from all active ConditionCapabilityEffect rows
    that target this capability. Floor at 0.

    Args:
        target: The ObjectDB instance
        capability: CapabilityType instance

    Returns:
        CapabilityStatus with total value and per-condition breakdown
    """
    target = character_sheet.character
    result = CapabilityStatus()

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        effects = ConditionCapabilityEffect.objects.filter(query, capability=capability)

        for effect in effects:
            modifier = effect.value
            if instance.current_stage:
                modifier = int(modifier * instance.current_stage.severity_multiplier)
            result.value += modifier
            result.condition_contributions.append((instance, modifier))

    # Floor at 0
    result.value = max(0, result.value)

    return result


def get_condition_modifier_total(
    character_sheet: "CharacterSheet",
    modifier_target: "ModifierTarget",
) -> int:
    """Sum active-condition contributions to a mechanics ModifierTarget (#636).

    Walks every active condition on the character and sums the ``value`` of each
    ConditionModifierEffect that points at ``modifier_target``. Staged conditions
    scale by their current stage's severity_multiplier, mirroring
    get_capability_status. No floor here — the consumer (e.g. _derive_power) owns
    any clamping, since deltas may legitimately be negative.

    Args:
        character_sheet: The character whose conditions are read.
        modifier_target: The mechanics.ModifierTarget to total contributions for.

    Returns:
        Integer sum of matching condition-effect contributions (0 when none).
    """
    target = character_sheet.character
    total = 0

    for instance in get_active_conditions(target):
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        effects = ConditionModifierEffect.objects.filter(query, modifier_target=modifier_target)

        for effect in effects:
            value = effect.value
            if effect.scales_with_severity:
                value = int(value * instance.effective_severity)
            elif instance.current_stage:
                value = int(value * instance.current_stage.severity_multiplier)
            total += value

    return total


def get_condition_modifier_breakdown(
    character_sheet: "CharacterSheet",
    modifier_target: "ModifierTarget",
) -> list[tuple[str, int]]:
    """Per-source sibling of get_condition_modifier_total (#639 power ledger).

    Returns one (source_label, value) row per active-condition ConditionModifierEffect
    that targets ``modifier_target`` — same walk/scaling as get_condition_modifier_total,
    but attributed per condition instead of summed. ``source_label`` is the condition's
    name. Staged conditions scale by current_stage.severity_multiplier (mirrors the total).
    The sum of returned values MUST equal get_condition_modifier_total for the same inputs.
    Empty list when no contributions.
    """
    target = character_sheet.character
    rows: list[tuple[str, int]] = []

    for instance in get_active_conditions(target):
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        effects = ConditionModifierEffect.objects.filter(query, modifier_target=modifier_target)

        for effect in effects:
            value = effect.value
            if effect.scales_with_severity:
                value = int(value * instance.effective_severity)
            elif instance.current_stage:
                value = int(value * instance.current_stage.severity_multiplier)
            rows.append((instance.condition.name, value))

    return rows


@dataclass(frozen=True)
class ConditionModifierVowContribution:
    """One per-instance contribution to a ModifierTarget, carrying its source_vow (#2643).

    Vow-keyed sibling of the ``(source_label, value)`` tuples
    ``get_condition_modifier_breakdown`` returns — used where the caller needs to
    GROUP contributions by the applying condition instance's ``source_vow_id`` (the
    bounded team-damage-percent lane's diminishing-returns read) rather than just sum
    or label them.
    """

    source_vow_id: int | None
    source_name: str
    value: int


def get_condition_modifier_vow_contributions(
    character_sheet: "CharacterSheet",
    modifier_target: "ModifierTarget",
) -> list["ConditionModifierVowContribution"]:
    """Vow-keyed sibling of get_condition_modifier_breakdown (#2643).

    Identical walk/scaling to ``get_condition_modifier_breakdown``, but each row also
    carries the applying ``ConditionInstance.source_vow_id`` — the bounded
    team-damage-percent lane's read groups contributions by this before running vow-keyed
    diminishing returns (``world.magic.services.techniques.vow_keyed_diminished_total``)
    and clamping. A row with ``source_vow_id=None`` (no engaged role at apply time) is
    its own DR group, same as any named vow. The sum of returned values MUST equal
    ``get_condition_modifier_total`` for the same inputs. Empty list when no
    contributions.
    """
    target = character_sheet.character
    rows: list[ConditionModifierVowContribution] = []

    for instance in get_active_conditions(target):
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        effects = ConditionModifierEffect.objects.filter(query, modifier_target=modifier_target)

        for effect in effects:
            value = effect.value
            if effect.scales_with_severity:
                value = int(value * instance.effective_severity)
            elif instance.current_stage:
                value = int(value * instance.current_stage.severity_multiplier)
            rows.append(
                ConditionModifierVowContribution(
                    source_vow_id=instance.source_vow_id,
                    source_name=instance.condition.name,
                    value=value,
                )
            )

    return rows


def priced_percent_severity(*, eff_intensity: int, target: "ObjectDB") -> int:  # noqa: OBJECTDB_PARAM
    """Apply-time percent severity for the bounded team-damage-percent lane (#2643).

    Power buys the percentage; the price scales inversely with the buffed target's
    level — the same cast power buys a smaller percentage on a higher-level target::

        severity = clamp(round(eff_intensity * PCT_PER_POWER_TENTHS / 10
                                / max(1, target_level)),
                          1, TEAM_BUFF_LANE_CAP_PERCENT)

    ``target_level`` resolves generically for whoever the condition landed on (a
    team_damage_percent-carrying condition can target an ally OR an enemy — see
    ``world.magic.services.condition_application.apply_technique_conditions``):
    a PC target reads ``CharacterSheet.current_level``; a ``CombatOpponent`` target
    reads its pseudo-level from ``OPPONENT_TIER_LEVEL`` (tier -> level,
    ``world.combat.constants``); an unresolvable target defaults to level 1 (no
    dampening). Floor 1 (a landed buff always grants something); ceiling is the
    bounded lane's own cap — the read side clamps again after vow-keyed DR, but a
    single write should never itself exceed what the lane could legally display.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.combat.constants import OPPONENT_TIER_LEVEL  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.magic.constants import (  # noqa: PLC0415
        PCT_PER_POWER_TENTHS,
        TEAM_BUFF_LANE_CAP_PERCENT,
    )

    target_level = 1
    sheet = CharacterSheet.objects.filter(character=target).first()
    if sheet is not None:
        target_level = sheet.current_level
    else:
        opponent = CombatOpponent.objects.filter(objectdb=target).first()
        if opponent is not None:
            target_level = OPPONENT_TIER_LEVEL.get(opponent.tier, 1)

    raw = eff_intensity * PCT_PER_POWER_TENTHS / 10 / max(1, target_level)
    return max(1, min(TEAM_BUFF_LANE_CAP_PERCENT, round(raw)))


def get_capability_value(
    character_sheet: "CharacterSheet",
    capability: CapabilityType,
) -> int:
    """
    Get the total value of a capability for a character.

    Convenience wrapper around get_capability_status that returns just the value.
    Floor at 0.

    Args:
        target: The ObjectDB instance
        capability: CapabilityType instance

    Returns:
        Integer capability value (0 = effectively blocked / not possessed)
    """
    return get_capability_status(character_sheet, capability).value


def get_effective_capability_value(
    character_sheet: "CharacterSheet", capability: CapabilityType
) -> int:
    """Effective capability value = innate baseline + CharacterModifier contributions
    (distinctions/species/equipment via ModifierTarget.target_capability) + raw
    condition contributions + the best (max) known-technique grant, floored at 0.

    Distinct from get_capability_value (condition-only): this is the agency/requirement
    value — intrinsic capacity (identity) impaired by transient state.

    **One-oracle merge (#2504):** this is the single "what can this character do"
    answer — technique-granted capabilities (via ``TechniqueCapabilityGrant``,
    prerequisite-null grants only) now satisfy requirement/gate checks the same
    way an innate baseline or condition would, not just the availability oracle
    (``get_capability_sources_for_character``, world.mechanics.services). Multiple
    known techniques granting the same capability contribute their MAX, not a sum
    (ADR-0034 individuation) — see ``_technique_capability_values``.
    ``TraitCapabilityDerivation`` deliberately does NOT fold in here (ruled
    availability-only) — that asymmetry is intentional, not an oversight.

    Args:
        character_sheet: The character's CharacterSheet.
        capability: CapabilityType instance

    Returns:
        Integer effective capability value (0 = effectively blocked / not possessed)
    """
    baseline = capability.innate_baseline
    modifier_total = sum(
        m.value
        for m in CharacterModifier.objects.filter(
            character=character_sheet, target__target_capability=capability
        )
    )
    # get_capability_status still operates on ObjectDB; walk back at the
    # boundary. Refactoring its signature is Phase 2 follow-up.
    status = get_capability_status(character_sheet, capability)
    condition_total = sum(modifier for _instance, modifier in status.condition_contributions)
    # Thread-passive grants (#751 B2): an engaged tier-0 role CAPABILITY_GRANT
    # means the capability is POSSESSED → contribute an additive floor of 1
    # (intrinsic capacity, not a condition). Folded here rather than in
    # get_capability_status because that chokepoint is shared with
    # get_capability_value, whose condition-only semantics must stay intact.
    # The handler caches threads and runs ~2 queries; this is a per-capability
    # read, not a loop, so the cost is acceptable.
    granted = _passive_capability_grants(character_sheet)
    grant_floor = 1 if capability.pk in granted else 0
    technique_value = _technique_capability_values(character_sheet).get(capability.pk, 0)
    return max(0, baseline + modifier_total + condition_total + grant_floor + technique_value)


def get_all_capability_values(character_sheet: "CharacterSheet") -> dict[int, int]:
    """
    Get all capability values for a character.

    Batch-queries all ConditionCapabilityEffect rows for active conditions
    and aggregates per capability. This is condition/baseline aggregation for
    *source enumeration* — its sole real consumer is the availability oracle
    (``world.mechanics.services._get_condition_sources``), which enumerates
    per-source ``CapabilitySource`` rows for action discovery.

    **One-oracle merge (#2504) boundary:** technique grants are deliberately
    NOT folded in here. They already enter the availability oracle via its own
    dedicated channel — ``world.mechanics.services._get_technique_sources``,
    which emits one properly-attributed TECHNIQUE-type ``CapabilitySource`` per
    grant (source_name, prerequisite, effect_property_ids intact). Folding
    technique values into this bulk dict as well would double-count them as a
    second, poorly-specified CONDITION-type source and duplicate actions in
    ``get_available_actions`` (regression caught in
    ``test_pipeline_integration.ChallengePathTests``). The agency oracle
    (``get_effective_capability_value``, single-capability gate/requirement
    checks) is where technique grants fold in — see ``_technique_capability_values``.

    Args:
        target: The ObjectDB instance

    Returns:
        Dict mapping capability PK to total values (floor 0)
    """
    target = character_sheet.character
    active_instances = list(get_active_conditions(target))

    # Aggregate condition-derived values (may be empty with no active conditions).
    totals: dict[int, int] = {}
    if active_instances:
        # Build batch filter
        condition_ids = [i.condition_id for i in active_instances]
        query = Q(condition_id__in=condition_ids)
        stage_ids = [i.current_stage_id for i in active_instances if i.current_stage_id]
        if stage_ids:
            query |= Q(stage_id__in=stage_ids)

        effects = ConditionCapabilityEffect.objects.filter(query).select_related("capability")

        # Build instance lookup maps
        instance_by_condition: dict[int, ConditionInstance] = {
            i.condition_id: i for i in active_instances
        }
        instance_by_stage: dict[int, ConditionInstance] = {
            i.current_stage_id: i for i in active_instances if i.current_stage_id
        }

        for effect in effects:
            instance = instance_by_condition.get(effect.condition_id) or instance_by_stage.get(
                effect.stage_id
            )
            if not instance:
                continue

            modifier = effect.value
            if instance.current_stage:
                modifier = int(modifier * instance.current_stage.severity_multiplier)

            cap_id = effect.capability_id
            totals[cap_id] = totals.get(cap_id, 0) + modifier

    # Thread-passive grants (#751 B2): fold engaged tier-0 role CAPABILITY_GRANT
    # PKs in with an additive floor of 1 so the obstacle/action-generation
    # consumer (mechanics._get_condition_sources) sees them. Called ONCE; the
    # handler caches threads. The early-return for the no-active-conditions case
    # was removed above so grants surface even when the character has no
    # conditions at all.
    granted = _passive_capability_grants(character_sheet)
    for cap_id in granted:
        totals[cap_id] = totals.get(cap_id, 0) + 1

    # Floor at 0
    return {cap_id: max(0, val) for cap_id, val in totals.items()}


def get_check_modifier(
    character_sheet: "CharacterSheet",
    check_type: CheckType,
) -> CheckModifierResult:
    """
    Get the total modifier for a check type from active conditions.

    Args:
        target: The ObjectDB instance
        check_type: CheckType instance

    Returns:
        CheckModifierResult with total and breakdown
    """
    target = character_sheet.character
    ctype = check_type

    result = CheckModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        modifiers = ConditionCheckModifier.objects.filter(query, check_type=ctype)

        for mod in modifiers:
            modifier_value = mod.modifier_value

            # effective_severity already folds in the stage multiplier, so scaling
            # by severity and by the stage are mutually exclusive — if/elif, not two
            # ifs, mirroring get_condition_modifier_total. (Two ifs double-applied
            # the stage multiplier for a staged, severity-scaled modifier.)
            if mod.scales_with_severity:
                modifier_value = int(modifier_value * instance.effective_severity)
            elif instance.current_stage:
                modifier_value = int(modifier_value * instance.current_stage.severity_multiplier)

            result.total_modifier += modifier_value
            result.breakdown.append((instance, modifier_value))

    return result


def condition_contributions(
    character_sheet: "CharacterSheet",
    check_type: CheckType,
) -> list[ModifierContribution]:
    """
    Adapt get_check_modifier's breakdown into a list of ModifierContribution.

    Each active condition that modifies the given check_type produces one
    ModifierContribution with source_kind=CONDITION.  The label is the
    condition's template name, plus the current stage name in parentheses
    when the instance is at a stage (e.g. "Paralytic Poison (Numbness)").

    This function does NOT reimplement get_check_modifier's logic — it
    delegates entirely to that function and maps the result.
    """
    result = get_check_modifier(character_sheet, check_type)
    contributions: list[ModifierContribution] = []
    for instance, modifier_value in result.breakdown:
        label = instance.condition.name
        if instance.current_stage is not None:
            label = f"{label} ({instance.current_stage.name})"
        contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.CONDITION,
                source_label=label,
                value=modifier_value,
            )
        )
    return contributions


def get_resistance_modifier(
    character_sheet: "CharacterSheet",
    damage_type: DamageType | None = None,
) -> ResistanceModifierResult:
    """
    Get the total resistance modifier for a damage type from active conditions.

    Args:
        target: The ObjectDB instance
        damage_type: DamageType instance, or None for "all damage" modifiers only

    Returns:
        ResistanceModifierResult with total and breakdown
    """
    target = character_sheet.character
    dtype = damage_type

    result = ResistanceModifierResult(total_modifier=0, breakdown=[])

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get modifiers: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        modifiers = ConditionResistanceModifier.objects.filter(query)

        if dtype:
            modifiers = modifiers.filter(Q(damage_type=dtype) | Q(damage_type__isnull=True))
        else:
            modifiers = modifiers.filter(damage_type__isnull=True)

        for mod in modifiers:
            modifier_value = mod.modifier_value

            # Honor scales_with_severity, consistent with the other numeric readers
            # (get_condition_modifier_total / get_check_modifier). effective_severity
            # already folds in the stage multiplier, so it's if/elif.
            if mod.scales_with_severity:
                modifier_value = int(modifier_value * instance.effective_severity)
            elif instance.current_stage:
                modifier_value = int(modifier_value * instance.current_stage.severity_multiplier)

            result.total_modifier += modifier_value
            result.breakdown.append((instance, modifier_value))

    return result


# =============================================================================
# Round Processing
# =============================================================================


@transaction.atomic
def process_round_start(target: "ObjectDB") -> RoundTickResult:  # noqa: OBJECTDB_PARAM
    """
    Process start-of-round effects for all conditions on a target.

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage, progressions, and expirations
    """
    result = _process_round_tick(target, DamageTickTiming.START_OF_ROUND)
    _invalidate_condition_handler(target)
    return result


@transaction.atomic
def process_round_end(target: "ObjectDB") -> RoundTickResult:  # noqa: OBJECTDB_PARAM
    """
    Process end-of-round effects for all conditions on a target.

    This also handles duration countdown and progression.

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage, progressions, and expirations
    """
    result = _process_round_tick(target, DamageTickTiming.END_OF_ROUND)

    # Process duration countdown and progression
    _process_duration_and_progression(target, result)

    _invalidate_condition_handler(target)

    return result


@transaction.atomic
def process_action_tick(target: "ObjectDB") -> RoundTickResult:  # noqa: OBJECTDB_PARAM
    """
    Process on-action damage for conditions (when target takes an action).

    Args:
        target: The ObjectDB instance

    Returns:
        RoundTickResult with damage dealt
    """
    result = _process_round_tick(target, DamageTickTiming.ON_ACTION)
    _invalidate_condition_handler(target)
    return result


def _process_round_tick(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    timing: DamageTickTiming,
) -> RoundTickResult:
    """
    Process damage-over-time for a specific tick timing.
    """
    result = RoundTickResult(
        damage_dealt=[],
        progressed_conditions=[],
        expired_conditions=[],
        removed_conditions=[],
    )

    active_instances = get_active_conditions(target)

    for instance in active_instances:
        # Get DoT effects: condition-level OR stage-specific (if at a stage)
        query = Q(condition=instance.condition)
        if instance.current_stage:
            query |= Q(stage=instance.current_stage)
        dot_effects = ConditionDamageOverTime.objects.filter(
            query, tick_timing=timing, is_long_term=False
        )

        for dot in dot_effects:
            damage = dot.base_damage

            # effective_severity already folds in the stage multiplier, so scaling
            # by severity and by the stage are mutually exclusive — if/elif, not two
            # ifs, mirroring get_check_modifier / get_condition_modifier_total. (Two
            # ifs double-applied the stage multiplier for a staged severity-scaled DoT.)
            if dot.scales_with_severity:
                damage = damage * instance.effective_severity
            elif instance.current_stage:
                damage = damage * instance.current_stage.severity_multiplier

            # Scale by stacks
            if dot.scales_with_stacks:
                damage = damage * instance.stacks

            damage = int(damage)

            if damage > 0:
                result.damage_dealt.append((dot.damage_type, damage))

    return result


def _process_duration_and_progression(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    result: RoundTickResult,
) -> None:
    """
    Process duration countdown and stage progression at end of round.
    """
    active_instances = list(get_active_conditions(target))

    for instance in active_instances:
        # Duration countdown
        if instance.rounds_remaining is not None:
            instance.rounds_remaining -= 1
            if instance.rounds_remaining <= 0:
                result.expired_conditions.append(instance)
                expired_condition = instance.condition
                instance.delete()
                _clear_unseen_observer_if_concealing(target, expired_condition)
                continue

        # Stage progression
        if instance.stage_rounds_remaining is not None:
            instance.stage_rounds_remaining -= 1
            if instance.stage_rounds_remaining <= 0:
                # Progress to next stage
                next_stage = _get_next_stage(instance)
                if next_stage:
                    instance.current_stage = next_stage
                    instance.stage_rounds_remaining = next_stage.rounds_to_next
                    result.progressed_conditions.append(instance)
                else:
                    # No next stage - condition may end or stay at final stage
                    instance.stage_rounds_remaining = None

        instance.save()


def _get_next_stage(instance: ConditionInstance) -> ConditionStage | None:
    """Get the next stage for a progressive condition."""
    if not instance.current_stage:
        return None

    return (
        ConditionStage.objects.filter(
            condition=instance.condition,
            stage_order__gt=instance.current_stage.stage_order,
        )
        .order_by("stage_order")
        .first()
    )


# =============================================================================
# Utility Functions
# =============================================================================


def suppress_condition(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
    *,
    duration_rounds: int | None = None,
) -> bool:
    """
    Temporarily suppress a condition's effects.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance
        duration_rounds: Rounds to suppress (None = indefinite)

    Returns:
        True if condition was suppressed
    """
    instance = get_condition_instance(target, condition, include_suppressed=True)
    if not instance:
        return False

    instance.is_suppressed = True
    if duration_rounds:
        instance.suppressed_until = timezone.now() + timedelta(
            seconds=duration_rounds * SECONDS_PER_ROUND
        )
    instance.save()
    _invalidate_condition_handler(target)
    _clear_unseen_observer_if_concealing(target, condition)
    return True


def unsuppress_condition(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    condition: ConditionTemplate,
) -> bool:
    """
    Remove suppression from a condition.

    Args:
        target: The ObjectDB instance
        condition: ConditionTemplate instance

    Returns:
        True if condition was unsuppressed
    """
    instance = get_condition_instance(target, condition, include_suppressed=True)
    if not instance:
        return False

    instance.is_suppressed = False
    instance.suppressed_until = None
    instance.save()
    _invalidate_condition_handler(target)
    _register_unseen_observer_if_concealing(target, condition)
    return True


@transaction.atomic
def clear_all_conditions(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
    *,
    only_negative: bool = False,
    only_category: "ConditionCategory | None" = None,
) -> int:
    """
    Remove all conditions from a target.

    Args:
        target: The ObjectDB instance
        only_negative: Only clear negative conditions
        only_category: Only clear conditions in this category instance

    Returns:
        Number of conditions removed

    Reuses ``_teardown_removed_condition_instance`` per instance (the same helper
    ``remove_condition`` uses) rather than a raw queryset ``.delete()``, so the OOC
    unseen-observer clear hook (#1225) and every other per-instance teardown side
    effect fires for a full clear too. Includes suppressed instances, matching the
    original unfiltered queryset.
    """
    qs = ConditionInstance.objects.filter(target=target)

    if only_negative:
        qs = qs.filter(condition__category__is_negative=True)

    if only_category:
        qs = qs.filter(condition__category=only_category)

    instances = list(qs)
    for instance in instances:
        _teardown_removed_condition_instance(target, instance)
    return len(instances)


def get_turn_order_modifier(character_sheet: "CharacterSheet") -> int:
    """
    Get the total turn order modifier from all conditions.

    Args:
        target: The ObjectDB instance

    Returns:
        Integer modifier to turn order (positive = act earlier)
    """
    target = character_sheet.character
    result = (
        get_active_conditions(target)
        .filter(condition__affects_turn_order=True)
        .aggregate(total=Coalesce(Sum("condition__turn_order_modifier"), 0))
    )
    return result["total"]


def get_aggro_priority(character_sheet: "CharacterSheet") -> int:
    """
    Get the total aggro priority from all conditions.

    Args:
        target: The ObjectDB instance

    Returns:
        Integer priority (higher = more likely to be targeted)
    """
    target = character_sheet.character
    result = (
        get_active_conditions(target)
        .filter(condition__draws_aggro=True)
        .aggregate(total=Coalesce(Sum("condition__aggro_priority"), 0))
    )
    return result["total"]


def has_death_deferred(character: "ObjectDB") -> bool:  # noqa: OBJECTDB_PARAM
    """Return True if the character has any active condition granting death_deferred.

    Single source of truth for the death-deferred query, shared by combat
    services and the vitals peril-resolution gate (world.vitals.peril_resolution).
    Supersedes the private ``_character_has_death_deferred`` in
    ``world.combat.services``, which now delegates here.
    """
    return ConditionInstance.objects.filter(
        target=character,
        is_suppressed=False,
        resolved_at__isnull=True,
        condition__properties__name="death_deferred",
    ).exists()


# =============================================================================
# Percentage Modifier Queries (from Distinctions)
# =============================================================================


def _get_condition_percent_modifier(
    character_sheet: "CharacterSheet",
    category_name: str,
    condition_name: str,
) -> int:
    """
    Get total percentage modifier for a condition effect category.

    Queries CharacterModifier for modifiers targeting the specified
    condition percentage category and condition name.

    Args:
        target: The ObjectDB instance (character)
        category_name: Modifier category (e.g., "condition_control_percent")
        condition_name: Condition name to match (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 100 means +100%)
    """
    target = character_sheet.character
    try:
        sheet = target.sheet_data
    except AttributeError:
        return 0

    modifiers = CharacterModifier.objects.filter(
        character=sheet,
        target__category__name=category_name,
        target__name__iexact=condition_name,
    )

    return sum(m.value for m in modifiers)


def get_condition_control_percent_modifier(
    character_sheet: "CharacterSheet",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to control loss rate for a condition.

    Used by emotional conditions like anger to determine how quickly
    a character loses control. A +100% modifier doubles the control loss rate.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 100 for Wrathful)
    """
    return _get_condition_percent_modifier(
        character_sheet, "condition_control_percent", condition_name
    )


def get_condition_intensity_percent_modifier(
    character_sheet: "CharacterSheet",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to intensity gain for a condition.

    Used by emotional conditions like anger to determine how much
    intensity is gained when the condition intensifies. A +50% modifier
    means 1.5x normal intensity gain.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "anger")

    Returns:
        Total percentage modifier (e.g., 50 for Wrathful)
    """
    return _get_condition_percent_modifier(
        character_sheet, "condition_intensity_percent", condition_name
    )


def get_condition_penalty_percent_modifier(
    character_sheet: "CharacterSheet",
    condition_name: str,
) -> int:
    """
    Get percentage modifier to check penalties for a condition.

    Used by conditions like humbled to determine how severe the check
    penalties are. A +100% modifier doubles all check penalties.

    Args:
        target: The character ObjectDB instance
        condition_name: Condition name (e.g., "humbled")

    Returns:
        Total percentage modifier (e.g., 100 for Hubris)
    """
    return _get_condition_percent_modifier(
        character_sheet, "condition_penalty_percent", condition_name
    )


# =============================================================================
# Severity-Driven Advancement
# =============================================================================


def advance_condition_severity(
    instance: ConditionInstance,
    amount: int,
) -> SeverityAdvanceResult:
    """Increment a condition's severity and advance stage if threshold crossed.

    Used for conditions like Soulfray where severity accumulates from
    external events rather than being set once at creation.

    Stages with severity_threshold=None are ignored (time-based only).
    Can skip multiple stages if the severity jump is large enough.

    If the next stage opts into HOLD_OVERFLOW with a resist_check_type,
    a resist check fires before advancement. Pass = stage holds (severity
    persists over threshold). Fail = stage advances normally.
    """
    previous_stage = instance.current_stage
    # Captured before any mutation below — used to detect the resolved→active
    # transition (severity re-advancing from zero) so the OOC unseen-observer
    # hook fires exactly once, on the edge, not on every call (#1225 — ADR-0083
    # promises this for any future duration/decay-based concealment producer).
    was_resolved = instance.resolved_at is not None
    instance.severity += amount

    # Find the highest severity-threshold stage that's been reached
    new_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=instance.severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    stage_changed = False
    outcome = AdvancementOutcome.NO_CHANGE

    if new_stage and new_stage != previous_stage:
        if (
            new_stage.advancement_resist_failure_kind == AdvancementResistFailureKind.HOLD_OVERFLOW
            and new_stage.resist_check_type is not None
        ):
            check_passed = _perform_advancement_resist_check(instance, new_stage)
            if check_passed:
                # Severity persists over threshold; stage does not advance.
                update_fields: list[str] = ["severity", "current_stage"]
                if instance.severity > 0 and instance.resolved_at is not None:
                    instance.resolved_at = None
                    update_fields.append("resolved_at")
                instance.save(update_fields=update_fields)
                _invalidate_condition_handler(instance.target)
                if was_resolved and instance.resolved_at is None:
                    _register_unseen_observer_if_concealing(instance.target, instance.condition)
                return SeverityAdvanceResult(
                    previous_stage=previous_stage,
                    new_stage=previous_stage,
                    stage_changed=False,
                    total_severity=instance.severity,
                    outcome=AdvancementOutcome.HELD,
                )
        # ADVANCE_AT_THRESHOLD or HOLD_OVERFLOW resist failed — advance.
        instance.current_stage = new_stage
        stage_changed = True
        outcome = AdvancementOutcome.ADVANCED

    update_fields = ["severity", "current_stage"]
    if instance.severity > 0 and instance.resolved_at is not None:
        instance.resolved_at = None
        update_fields.append("resolved_at")

    instance.save(update_fields=update_fields)
    _invalidate_condition_handler(instance.target)

    if was_resolved and instance.resolved_at is None:
        _register_unseen_observer_if_concealing(instance.target, instance.condition)

    if stage_changed:
        stage_change_payload = ConditionStageChangedPayload(
            target=instance.target,
            instance=instance,
            old_stage=previous_stage,
            new_stage=instance.current_stage,
        )
        target_location = instance.target.location
        if target_location is not None:
            emit_event(
                EventName.CONDITION_STAGE_CHANGED,
                stage_change_payload,
                location=target_location,
            )

        # Inline dispatch of the stage-entry aftermath hook. The reactive layer
        # dispatches only to DB Trigger rows; Python subscribers use the inline
        # pattern (see apply_damage_reduction_from_threads in magic/services.py).
        # Only ascending transitions apply aftermath — apply_stage_entry_aftermath
        # gates internally on stage_order comparison.
        apply_stage_entry_aftermath(stage_change_payload)

    return SeverityAdvanceResult(
        previous_stage=previous_stage,
        new_stage=instance.current_stage,
        stage_changed=stage_changed,
        total_severity=instance.severity,
        outcome=outcome,
    )


def _perform_advancement_resist_check(
    instance: ConditionInstance,
    next_stage: ConditionStage,
) -> bool:
    """Fire the reactive event, run the resist check, return True if the resist succeeded.

    Emits CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE so triggers can modify the
    difficulty before resolution (MODIFY_PAYLOAD pattern). The payload is mutable,
    so triggers adjust base_difficulty in-place.

    Returns True if the resist check passed (success_level >= 0), False otherwise.
    """
    payload = ConditionStageAdvanceCheckPayload(
        instance=instance,
        target_stage=next_stage,
        base_difficulty=next_stage.resist_difficulty,
    )
    location = instance.target.location
    if location is not None:
        emit_event(
            EventName.CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE,
            payload,
            location=location,
        )

    result = perform_check(
        character=instance.target,
        check_type=next_stage.resist_check_type,
        target_difficulty=payload.base_difficulty,
    )
    # success_level >= 0 means partial success or better — resist holds.
    return int(result.success_level) >= 0


def apply_stage_entry_aftermath(payload: ConditionStageChangedPayload) -> None:
    """On ascending stage changes, apply the stage's on_entry_conditions.

    Per spec §5.6. Callers pass a ConditionStageChangedPayload frozen
    dataclass (the same payload emitted by advance_condition_severity).
    Gates:
    - new_stage is None → no-op (fully decayed).
    - old_stage.stage_order >= new_stage.stage_order → descending or
      sideways; no-op.
    Idempotency: existing aftermath instance with severity >= assoc.severity
    is left alone; lower severity is advanced to assoc.severity.
    """
    # Aftermath conditions must not themselves have on_entry_conditions; unbounded
    # recursion otherwise. Authoring/validation enforces this invariant.
    old = payload.old_stage
    new = payload.new_stage
    if new is None:
        return
    if old is not None and new.stage_order <= old.stage_order:
        return
    target = payload.target

    for assoc in new.on_entry_assocs.select_related("condition").all():
        existing = ConditionInstance.objects.filter(
            target=target,
            condition=assoc.condition,
            resolved_at__isnull=True,
        ).first()
        if existing is None:
            apply_condition(
                target,
                assoc.condition,
                severity=assoc.severity,
                source_description=f"on_entry of {new.name}",
            )
        elif existing.severity < assoc.severity:
            advance_condition_severity(existing, assoc.severity - existing.severity)
        # else: existing severity >= assoc.severity — leave alone.


def _resolve_character_sheet_for_target(
    target: "ObjectDB",  # noqa: OBJECTDB_PARAM
) -> "CharacterSheet | None":
    """Walk an ObjectDB target back to its CharacterSheet, or None.

    CharacterSheet uses OneToOneField(ObjectDB, primary_key=True), so
    CharacterSheet.pk == ObjectDB.pk for all character objects. Non-character
    ObjectDB rows (rooms, items, exits) have no CharacterSheet row; the
    DoesNotExist exception is caught and returns None.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        return CharacterSheet.objects.get(pk=target.pk)
    except CharacterSheet.DoesNotExist:
        return None


def decay_condition_severity(
    instance: ConditionInstance,
    amount: int,
    *,
    _skip_corruption_sync: bool = False,
) -> SeverityDecayResult:
    """Inverse of advance_condition_severity. Walks stage down if threshold crossed.

    Per spec Scope 6 §5.3. Emits CONDITION_STAGE_CHANGED only when the stage
    actually changes; consumers derive descending-vs-ascending from
    stage_order comparison. Sets resolved_at when severity reaches 0.

    Per spec §3.4 (passive decay integration): if the condition's template is
    Corruption-kind (corruption_resonance is not None), calls reduce_corruption
    with _from_decay=True to keep CharacterResonance.corruption_current in sync.
    The _from_decay flag prevents re-entrant calls back into this function.

    ``_skip_corruption_sync``: internal flag set by reduce_corruption when it
    calls this function directly (having already decremented corruption_current),
    preventing double-decrement.
    """
    previous_stage = instance.current_stage
    # Captured before any mutation below — used to detect the active→resolved
    # transition (severity decaying to zero) so the OOC unseen-observer hook
    # fires exactly once, on the edge, not on every call (#1225 — ADR-0083
    # promises this for any future duration/decay-based concealment producer).
    previously_resolved = instance.resolved_at is not None
    new_severity = max(0, instance.severity - amount)

    new_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=new_severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    instance.severity = new_severity
    instance.current_stage = new_stage
    update_fields = ["severity", "current_stage"]

    resolved = new_severity == 0
    if resolved:
        instance.resolved_at = get_ic_now() or timezone.now()
        update_fields.append("resolved_at")

    instance.save(update_fields=update_fields)
    _invalidate_condition_handler(instance.target)

    if resolved and not previously_resolved:
        _clear_unseen_observer_if_concealing(instance.target, instance.condition)

    if new_stage != previous_stage:
        target_location = instance.target.location
        if target_location is not None:
            emit_event(
                EventName.CONDITION_STAGE_CHANGED,
                ConditionStageChangedPayload(
                    target=instance.target,
                    instance=instance,
                    old_stage=previous_stage,
                    new_stage=new_stage,
                ),
                location=target_location,
            )

    # Field sync for Corruption-kind conditions (spec §3.4).
    # _skip_corruption_sync is set by reduce_corruption when it calls this function
    # directly (having already decremented corruption_current), preventing double-decrement.
    # _from_decay=True on the reduce_corruption call prevents recursion back into
    # decay_condition_severity from the reduce_corruption side.
    if not _skip_corruption_sync and instance.condition.corruption_resonance is not None:
        from world.magic.services.corruption import reduce_corruption  # noqa: PLC0415
        from world.magic.types.corruption import CorruptionRecoverySource  # noqa: PLC0415

        sheet = _resolve_character_sheet_for_target(instance.target)
        if sheet is not None:
            reduce_corruption(
                character_sheet=sheet,
                resonance=instance.condition.corruption_resonance,
                amount=amount,
                source=CorruptionRecoverySource.PASSIVE_DECAY,
                _from_decay=True,
            )

    return SeverityDecayResult(
        previous_stage=previous_stage,
        new_stage=new_stage,
        new_severity=new_severity,
        resolved=resolved,
    )


def decay_all_conditions_tick() -> DecayTickSummary:
    """Scheduler entry point. Decays all opt-in conditions by one tick.

    Per spec Scope 6 §5.4. Skips:
    - instances whose template sets passive_decay_blocked_in_engagement=True
      and whose target is an engaged character
    - instances where severity exceeds passive_decay_max_severity
    """
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    examined = 0
    ticked = 0
    engagement_blocked = 0
    severity_gated = 0

    qs = ConditionInstance.objects.filter(
        resolved_at__isnull=True,
        condition__passive_decay_per_day__gt=0,
    ).select_related("condition", "current_stage", "target")

    for instance in qs:
        examined += 1
        cond = instance.condition
        if (
            cond.passive_decay_blocked_in_engagement
            and CharacterEngagement.objects.filter(
                character=instance.target,
            ).exists()
        ):
            engagement_blocked += 1
            continue
        if (
            cond.passive_decay_max_severity is not None
            and instance.severity > cond.passive_decay_max_severity
        ):
            severity_gated += 1
            continue
        decay_condition_severity(instance, cond.passive_decay_per_day)
        ticked += 1

    return DecayTickSummary(
        examined=examined,
        ticked=ticked,
        engagement_blocked=engagement_blocked,
        severity_gated=severity_gated,
    )


def _compute_chronic_damage(instance: "ConditionInstance") -> int:
    """Sum long-term DoT damage for one condition instance.

    Applies per-row severity and stacks scaling; rows that resolve to ≤0 are ignored.
    """
    total = 0
    long_term_rows = ConditionDamageOverTime.objects.filter(
        condition=instance.condition,
        is_long_term=True,
    )
    for dot in long_term_rows:
        damage = dot.base_damage
        if dot.scales_with_severity:
            damage = int(damage * instance.effective_severity)
        if dot.scales_with_stacks:
            damage = damage * instance.stacks
        if damage > 0:
            total += damage
    return total


def _chronic_tick_sheet(instance: "ConditionInstance") -> "object | None":
    """Return the character sheet for the instance's target, or None if absent."""
    try:
        return instance.target.sheet_data
    except ObjectDoesNotExist:
        return None


def batch_chronic_effect_tick() -> ChronicTickSummary:
    """Scheduler entry point. Advance long-term (chronic) DoT by one tick.

    The capped long-term tier (#520 §5.3 + §6): for each active condition
    instance whose template carries at least one ``is_long_term=True`` DoT row,
    reduce the target's health DIRECTLY via apply_clamped_chronic_damage — a
    non-lethal clamp that keeps health strictly above the knockout floor and
    NEVER routes through process_damage_consequences (so it can never wound,
    knock out, or kill).

    Targets currently owned by an active (non-completed) combat or scene round
    are skipped: the acute round tick advances their poison in that window (§6).

    Long-term DoT has no stages, so the per-stage multiplier is intentionally
    NOT applied here (mirroring the spec; avoids the known double-severity
    scaling). base_damage is scaled only by effective_severity / stacks when the
    row opts in.
    """
    from actions.round_context import get_active_round_context  # noqa: PLC0415
    from world.vitals.services import apply_clamped_chronic_damage  # noqa: PLC0415

    summary = ChronicTickSummary()

    instances = (
        ConditionInstance.objects.filter(
            resolved_at__isnull=True,
            condition__conditiondamageovertime_set__is_long_term=True,
        )
        .filter(
            Q(is_suppressed=False)
            | Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now())
        )
        .select_related("condition", "current_stage", "target")
        .distinct()
    )

    for instance in instances:
        summary.examined += 1

        sheet = _chronic_tick_sheet(instance)
        if sheet is not None and get_active_round_context(sheet) is not None:
            summary.active_round_skipped += 1
            continue

        total = _compute_chronic_damage(instance)
        if total > 0 and sheet is not None:
            removed = apply_clamped_chronic_damage(sheet, total)
            if removed > 0:
                summary.ticked += 1

    return summary


# =============================================================================
# Treatment service (Scope 6 §5.2)
# =============================================================================


_CRIT_SUCCESS_LEVEL = 2
_SUCCESS_LEVEL = 1
_PARTIAL_LEVEL = 0


def _map_outcome_to_reduction(outcome: "object", treatment: TreatmentTemplate) -> int:
    """Map a CheckOutcome instance to a severity-reduction integer via success_level.

    Correction #2 from Phase 6 plan: outcome.name is human-readable, not a slug.
    The canonical discriminator is the integer success_level field on CheckOutcome.
      >= 2  → critical success
      == 1  → success
      == 0  → partial
      <  0  → failure
    """
    level = int(outcome.success_level)  # type: ignore[union-attr]
    if level >= _CRIT_SUCCESS_LEVEL:
        return treatment.reduction_on_crit
    if level >= _SUCCESS_LEVEL:
        return treatment.reduction_on_success
    if level == _PARTIAL_LEVEL:
        return treatment.reduction_on_partial
    return treatment.reduction_on_failure


def _is_failure_outcome(outcome: "object") -> bool:
    """Return True when the outcome represents a failure (success_level < 0)."""
    return int(outcome.success_level) < _PARTIAL_LEVEL  # type: ignore[union-attr]


def _thread_anchors_to_character(thread: "Thread", target_sheet: "CharacterSheet") -> bool:
    """Return True if a Thread's anchor resolves to target_sheet.

    Anchor access path (Correction #3 from Phase 6 plan):
    - RELATIONSHIP_TRACK anchor: thread.target_relationship_track is a
      RelationshipTrackProgress, whose .relationship FK is a CharacterRelationship
      with .source and .target FKs to CharacterSheet. The thread owner (helper)
      holds a relationship *toward* the target, so we check relationship.target.
    - RELATIONSHIP_CAPSTONE anchor: thread.target_capstone is a RelationshipCapstone,
      whose .relationship FK similarly has .target pointing at the other party.
    Returns False if neither anchor kind is set.
    """
    track = thread.target_relationship_track
    if track is not None:
        # RelationshipTrackProgress → CharacterRelationship → target CharacterSheet
        return int(track.relationship.target_id) == int(target_sheet.pk)
    capstone = thread.target_capstone
    if capstone is not None:
        # RelationshipCapstone → CharacterRelationship → target CharacterSheet
        return int(capstone.relationship.target_id) == int(target_sheet.pk)
    return False


def _scene_participant(scene: "Scene", character_sheet: "CharacterSheet") -> bool:
    """Return True when *character* has a SceneParticipation row in *scene*.

    SceneParticipation links accounts, not characters directly. The character's
    account is reached via the roster tenure path (same as
    interaction_services._get_account_for_character). This helper must be cheap
    enough to call twice per perform_treatment invocation.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_sheet_id=character_sheet.pk)
        tenure = entry.tenures.filter(end_date__isnull=True).first()
        if tenure is None:
            return False
        account_id = tenure.player_data.account_id
    except RosterEntry.DoesNotExist:
        return False

    return SceneParticipation.objects.filter(scene=scene, account_id=account_id).exists()


def _treatment_scene_ok(
    treatment: TreatmentTemplate,
    scene: "Scene",
    helper_sheet: "CharacterSheet",
    target_sheet: "CharacterSheet",
) -> bool:
    """Return True when *treatment*'s scene gate is satisfied for both parties."""
    if not treatment.scene_required:
        return True
    return (
        scene.is_active
        and _scene_participant(scene, helper_sheet)
        and _scene_participant(scene, target_sheet)
    )


def _find_bond_thread(
    candidate_threads: list["Thread"],
    target_sheet: "CharacterSheet",
) -> "Thread | None":
    """Return the first helper thread anchored to *target_sheet*, or None."""
    for thread in candidate_threads:
        if _thread_anchors_to_character(thread, target_sheet):
            return thread
    return None


def _condition_matches_treatment(treatment: TreatmentTemplate, instance: ConditionInstance) -> bool:
    """Return True when a condition instance is a valid target for *treatment*."""
    if treatment.target_kind == TreatmentTargetKind.PRIMARY:
        return instance.condition_id == treatment.target_condition_id
    if treatment.target_kind == TreatmentTargetKind.AFTERMATH:
        return instance.condition.parent_condition_id == treatment.target_condition_id
    return True


def _build_treatment_candidates(
    treatment: TreatmentTemplate,
    bond_thread: "Thread | None",
    alteration_qs: Iterable["PendingAlteration"],
    condition_qs: Iterable[ConditionInstance],
) -> list[dict[str, Any]]:
    """Build candidate dicts for a single *treatment* over the target's effects."""
    if treatment.target_kind == TreatmentTargetKind.PENDING_ALTERATION:
        return [
            {
                "treatment": treatment,
                "target_effect": alteration,
                "target_effect_type": TARGET_EFFECT_ALTERATION,
                "bond_thread": bond_thread,
            }
            for alteration in alteration_qs
        ]
    return [
        {
            "treatment": treatment,
            "target_effect": instance,
            "target_effect_type": TARGET_EFFECT_CONDITION,
            "bond_thread": bond_thread,
        }
        for instance in condition_qs
        if _condition_matches_treatment(treatment, instance)
    ]


def get_treatment_candidates(
    helper_sheet: "CharacterSheet",
    target_sheet: "CharacterSheet",
    scene: "Scene",
) -> list[dict[str, Any]]:
    """Return valid (treatment, target_effect) pairs for helper to attempt on target.

    Discovery query for the treat-condition consent flow: enumerates every
    TreatmentTemplate against the target's open conditions and pending
    alterations, applying the same scene / engagement / bond gates as
    perform_treatment. Each returned dict carries: treatment, target_effect,
    target_effect_type (TARGET_EFFECT_CONDITION | TARGET_EFFECT_ALTERATION),
    and bond_thread (the helper's thread anchored to the target, or None when
    the treatment does not require a bond).
    """
    from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
    from world.magic.models import PendingAlteration, Thread  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    target_character = target_sheet.character
    helper_character = helper_sheet.character

    # Engagement gate: neither helper nor target may be engaged.
    if CharacterEngagement.objects.filter(
        character__in=[helper_character, target_character]
    ).exists():
        return []

    candidate_threads = list(Thread.objects.filter(owner=helper_sheet, retired_at__isnull=True))

    condition_qs = ConditionInstance.objects.filter(
        target=target_character,
        resolved_at__isnull=True,
    ).select_related("condition")

    alteration_qs = PendingAlteration.objects.filter(
        character=target_sheet,
        status=PendingAlterationStatus.OPEN,
    )

    candidates: list[dict[str, Any]] = []

    for treatment in TreatmentTemplate.objects.all():
        if not _treatment_scene_ok(treatment, scene, helper_sheet, target_sheet):
            continue

        if treatment.requires_bond:
            bond_thread = _find_bond_thread(candidate_threads, target_sheet)
            if bond_thread is None:
                continue
        else:
            bond_thread = None

        candidates.extend(
            _build_treatment_candidates(treatment, bond_thread, alteration_qs, condition_qs)
        )

    return candidates


@transaction.atomic
def perform_treatment(  # noqa: PLR0912, PLR0913, PLR0915, C901
    helper_sheet: "CharacterSheet",
    target_sheet: "CharacterSheet",
    scene: "Scene",
    treatment: TreatmentTemplate,
    target_effect: "ConditionInstance | PendingAlteration",
    bond_thread: "Thread | None" = None,
) -> TreatmentOutcome:
    """Resolve a TreatmentTemplate against an effect instance.

    Full preflight gate suite per spec Scope 6 §5.2:
      1. Type match (TreatmentTargetKind vs instance type)
      2. Parent/primary match (condition ancestry)
      3. Bond gate (thread anchored to target when requires_bond)
      4. Scene gate (active scene + both participants present)
      5. Engagement gate (neither helper nor target engaged)
      6. Duplicate pre-check (racy; INSERT-time UniqueConstraint is authoritative)
      7. Resonance cost debit
      8. Anima cost debit

    The PENDING_ALTERATION branch calls reduce_pending_alteration_tier (lazy
    import) to reduce the alteration's tier. The import is lazy so an ImportError
    only fires at runtime if this code path is actually invoked.
    """
    from django.db import IntegrityError  # noqa: PLC0415
    from django.utils import timezone as tz  # noqa: PLC0415

    from world.checks.services import perform_check  # noqa: PLC0415
    from world.conditions.exceptions import (  # noqa: PLC0415
        HelperEngagedForTreatment,
        NoSupportingBondThread,
        TreatmentAlreadyAttempted,
        TreatmentAnimaInsufficient,
        TreatmentParentMismatch,
        TreatmentResonanceInsufficient,
        TreatmentScenePrerequisiteFailed,
        TreatmentTargetMismatch,
    )
    from world.magic.models import (  # noqa: PLC0415
        CharacterAnima,
        CharacterResonance,
        PendingAlteration,
    )
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    helper = helper_sheet.character
    target = target_sheet.character

    # ------------------------------------------------------------------
    # Gate 1: type match
    # ------------------------------------------------------------------
    if treatment.target_kind == TreatmentTargetKind.PENDING_ALTERATION:
        if not isinstance(target_effect, PendingAlteration):
            raise TreatmentTargetMismatch
    elif not isinstance(target_effect, ConditionInstance):
        raise TreatmentTargetMismatch

    # ------------------------------------------------------------------
    # Gate 2: parent/primary match
    # ------------------------------------------------------------------
    if treatment.target_kind == TreatmentTargetKind.PRIMARY:
        if target_effect.condition_id != treatment.target_condition_id:
            raise TreatmentParentMismatch
    elif treatment.target_kind == TreatmentTargetKind.AFTERMATH:
        if target_effect.condition.parent_condition_id != treatment.target_condition_id:
            raise TreatmentParentMismatch
    # PENDING_ALTERATION: no parent-match check per spec §5.2 step 2.

    # ------------------------------------------------------------------
    # Gate 3: bond gate
    # ------------------------------------------------------------------
    if treatment.requires_bond:
        if bond_thread is None or int(bond_thread.owner_id) != int(helper_sheet.pk):
            raise NoSupportingBondThread
        if bond_thread.retired_at is not None:
            raise NoSupportingBondThread
        if not _thread_anchors_to_character(bond_thread, target_sheet):
            raise NoSupportingBondThread

    # ------------------------------------------------------------------
    # Gate 4: scene gate
    # ------------------------------------------------------------------
    if treatment.scene_required:
        if (
            not scene.is_active
            or not _scene_participant(scene, helper)
            or not _scene_participant(scene, target)
        ):
            raise TreatmentScenePrerequisiteFailed

    # ------------------------------------------------------------------
    # Gate 5: engagement gate (both helper and target)
    # ------------------------------------------------------------------
    if CharacterEngagement.objects.filter(character__in=[helper, target]).exists():
        raise HelperEngagedForTreatment

    # ------------------------------------------------------------------
    # Gate 6: duplicate pre-check (racy; INSERT-time constraint is authoritative)
    # ------------------------------------------------------------------
    if (
        treatment.once_per_scene_per_helper
        and TreatmentAttempt.objects.filter(
            helper=helper,
            target=target,
            scene=scene,
            treatment=treatment,
        ).exists()
    ):
        raise TreatmentAlreadyAttempted

    # ------------------------------------------------------------------
    # Gate 7: resonance cost
    # ------------------------------------------------------------------
    resonance_spent = 0
    if treatment.resonance_cost > 0:
        # bond_thread guaranteed non-None here: clean() enforces requires_bond
        # when resonance_cost > 0, and Gate 3 validated bond_thread above.
        res_row = CharacterResonance.objects.select_for_update().get(
            character_sheet=helper_sheet,
            resonance=bond_thread.resonance,  # type: ignore[union-attr]
        )
        if res_row.balance < treatment.resonance_cost:
            raise TreatmentResonanceInsufficient
        res_row.balance -= treatment.resonance_cost
        res_row.save(update_fields=["balance"])
        resonance_spent = treatment.resonance_cost

    # ------------------------------------------------------------------
    # Gate 8: anima cost — mirror resonance gate: lock, check, debit in-place.
    # Treatment has no overburn; insufficient anima fails cleanly at the gate.
    # ------------------------------------------------------------------
    anima_spent = 0
    if treatment.anima_cost > 0:
        anima_row = CharacterAnima.objects.select_for_update().get(character=helper)
        if anima_row.current < treatment.anima_cost:
            raise TreatmentAnimaInsufficient
        anima_row.current -= treatment.anima_cost
        anima_row.save(update_fields=["current"])
        anima_spent = treatment.anima_cost

    # ------------------------------------------------------------------
    # Execute: perform check
    # ------------------------------------------------------------------
    check_result = perform_check(
        helper,
        check_type=treatment.check_type,
        target_difficulty=treatment.target_difficulty,
    )

    # ------------------------------------------------------------------
    # Map outcome → reduction (Correction #2: use success_level, not .name)
    # ------------------------------------------------------------------
    reduction = _map_outcome_to_reduction(check_result.outcome, treatment)
    is_failure = _is_failure_outcome(check_result.outcome)

    # ------------------------------------------------------------------
    # Apply reduction
    # ------------------------------------------------------------------
    severity_reduced = 0
    tiers_reduced = 0
    target_resolved = False

    if not is_failure and reduction > 0:
        if treatment.target_kind in (
            TreatmentTargetKind.PRIMARY,
            TreatmentTargetKind.AFTERMATH,
        ):
            decay_result = decay_condition_severity(target_effect, amount=reduction)  # type: ignore[arg-type]
            severity_reduced = reduction
            target_resolved = decay_result.resolved
        else:
            # PENDING_ALTERATION — deferred to Phase 7.  Import is lazy so an
            # ImportError only surfaces if this branch is actually reached.
            from world.magic.services.alterations import (  # noqa: PLC0415
                reduce_pending_alteration_tier,
            )

            tier_result = reduce_pending_alteration_tier(
                pending=target_effect,
                amount=reduction,
                reason="treatment",
            )
            tiers_reduced = tier_result.previous_tier - tier_result.new_tier
            target_resolved = tier_result.resolved

    # ------------------------------------------------------------------
    # Failure backlash
    # ------------------------------------------------------------------
    helper_backlash = 0
    if is_failure and treatment.backlash_severity_on_failure > 0:
        backlash_target = treatment.backlash_target_condition or treatment.target_condition
        helper_backlash = treatment.backlash_severity_on_failure
        existing = ConditionInstance.objects.filter(
            target=helper,
            condition=backlash_target,
            resolved_at__isnull=True,
        ).first()
        if existing is None:
            apply_condition(
                helper,
                backlash_target,
                severity=helper_backlash,
                source_description="stabilization backlash",
            )
        else:
            advance_condition_severity(existing, helper_backlash)

    # ------------------------------------------------------------------
    # Persist attempt; authoritative duplicate check via UniqueConstraint
    # ------------------------------------------------------------------
    from typing import Any  # noqa: PLC0415

    from psycopg.errors import UniqueViolation  # noqa: PLC0415

    attempt_kwargs: dict[str, Any] = {
        "helper": helper,
        "target": target,
        "scene": scene,
        "treatment": treatment,
        "thread_used": bond_thread,
        "outcome": check_result.outcome,
        "severity_reduced": severity_reduced,
        "tiers_reduced": tiers_reduced,
        "helper_backlash_applied": helper_backlash,
        "resonance_spent": resonance_spent,
        "anima_spent": anima_spent,
        "created_at": get_ic_now() or tz.now(),
        "once_per_scene_guard": treatment.once_per_scene_per_helper,
    }
    if treatment.target_kind == TreatmentTargetKind.PENDING_ALTERATION:
        attempt_kwargs["target_pending_alteration"] = target_effect
    else:
        attempt_kwargs["target_condition_instance"] = target_effect

    try:
        attempt = TreatmentAttempt.objects.create(**attempt_kwargs)
    except IntegrityError as exc:
        if isinstance(exc.__cause__, UniqueViolation):
            raise TreatmentAlreadyAttempted from exc
        raise

    return TreatmentOutcome(
        attempt=attempt,
        outcome=check_result.outcome,
        effect_applied=(severity_reduced + tiers_reduced) > 0,
        severity_reduced=severity_reduced,
        tiers_reduced=tiers_reduced,
        helper_backlash_applied=helper_backlash,
        target_resolved=target_resolved,
    )


# =============================================================================
# Damage Scaling Helpers
# =============================================================================


def get_damage_multiplier(success_level: int) -> Decimal:
    """Look up the damage multiplier for a given success level.

    Returns the multiplier of the highest-threshold row whose
    `min_success_level` is <= `success_level`. Returns Decimal("0")
    when no row matches (table empty or SL below lowest threshold).
    """
    rows = DamageSuccessLevelMultiplier.objects.filter(
        min_success_level__lte=success_level,
    ).order_by("-min_success_level")
    first = rows.first()
    return first.multiplier if first else Decimal(0)


def get_penetration_factor(success_level: int) -> Decimal:
    """Look up the penetration power factor for a given success level (#639).

    Returns the ``factor`` of the highest authored row whose
    ``min_success_level`` is <= ``success_level``. Returns ``Decimal("1.00")``
    (full power, unchanged) when no row matches — an unauthored ladder must
    never accidentally zero out a working. A ``factor`` of ``0`` means the
    working bounced off the ward.
    """
    rows = PenetrationOutcomeFactor.objects.filter(
        min_success_level__lte=success_level,
    ).order_by("-min_success_level")
    first = rows.first()
    return first.factor if first else Decimal("1.00")


# =============================================================================
# Poison content seed (#1050)
# =============================================================================


def _ensure_poison_category() -> ConditionCategory:
    """Idempotently seed the Poison ConditionCategory.

    ConditionTemplate.category is a non-null PROTECT FK, so the poison templates
    need a stable category row to point at.
    """
    obj, _ = ConditionCategory.objects.get_or_create(
        name=POISON_CATEGORY_NAME,
        defaults={
            "description": "Toxins and venoms that linger and harm over time.",
            "is_negative": True,
        },
    )
    return obj


def _ensure_poison_damage_type() -> DamageType:
    """Idempotently seed the engine-required Poison DamageType.

    Leaves the consequence pools null so the config-default fallback applies.
    """
    obj, _ = DamageType.objects.get_or_create(
        name=POISON_DAMAGE_TYPE_NAME,
        defaults={"description": "Toxin damage that lingers as a poisoning condition."},
    )
    return obj


def ensure_poison_content() -> None:
    """Idempotently seed poison content (#1050).

    Seeds the Poison DamageType, the staged acute Poisoned ConditionTemplate
    (an acute DoT row plus two severity-ramping progression stages), and the
    Slow Poison long-term variant (a single long-term DoT row advanced by the
    daily chronic tick rather than the acute round tick). Safe to call
    repeatedly — every write goes through get_or_create.
    """
    category = _ensure_poison_category()
    dtype = _ensure_poison_damage_type()

    poisoned, _ = ConditionTemplate.objects.get_or_create(
        name=POISONED_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "A virulent toxin courses through the body, worsening with each round."
            ),
            "has_progression": True,
            "is_stackable": True,
            "max_stacks": 5,
            "stack_behavior": StackBehavior.INTENSITY,
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 5,
        },
    )
    ConditionDamageOverTime.objects.get_or_create(
        condition=poisoned,
        damage_type=dtype,
        defaults={
            "base_damage": 4,
            "scales_with_severity": True,
            "scales_with_stacks": True,
            "tick_timing": DamageTickTiming.END_OF_ROUND,
            "is_long_term": False,
        },
    )
    ConditionStage.objects.get_or_create(
        condition=poisoned,
        stage_order=1,
        defaults={
            "name": "Queasy",
            "description": "The first churning of the toxin; mild but mounting.",
            "rounds_to_next": 2,
            "severity_multiplier": Decimal("1.00"),
        },
    )
    ConditionStage.objects.get_or_create(
        condition=poisoned,
        stage_order=2,
        defaults={
            "name": "Wracked",
            "description": "The poison takes full hold, racking the body with pain.",
            "rounds_to_next": None,
            "severity_multiplier": Decimal("2.00"),
        },
    )

    slow, _ = ConditionTemplate.objects.get_or_create(
        name=SLOW_POISON_CONDITION_NAME,
        defaults={
            "category": category,
            "description": ("A slow-acting toxin that gnaws at the body over days until cured."),
            "has_progression": False,
            "default_duration_type": DurationType.UNTIL_CURED,
        },
    )
    ConditionDamageOverTime.objects.get_or_create(
        condition=slow,
        damage_type=dtype,
        defaults={
            "base_damage": 2,
            "scales_with_severity": False,
            "scales_with_stacks": False,
            "tick_timing": DamageTickTiming.END_OF_ROUND,
            "is_long_term": True,
        },
    )


def ensure_conditions_content() -> None:
    """Idempotently seed all core conditions content.

    Aggregates the existing poison seed with the charm/calm seed so callers have
    a single entry point for the condition content required by multiple systems.
    """
    from world.conditions.capability_content import (  # noqa: PLC0415
        ensure_at_will_shifting_capability,
    )
    from world.conditions.charm_content import ensure_charm_content  # noqa: PLC0415

    ensure_poison_content()
    ensure_charm_content()
    ensure_at_will_shifting_capability()
