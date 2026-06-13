"""Challenge resolution service functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.consequence_resolution import apply_resolution
from world.checks.models import Consequence
from world.checks.outcome_utils import (
    build_outcome_display,
    filter_character_loss,
    select_weighted,
)
from world.checks.services import perform_check
from world.checks.types import PendingResolution, ResolutionContext
from world.mechanics.constants import ResolutionType
from world.mechanics.models import (
    ApproachConsequence,
    ChallengeTemplateConsequence,
    CharacterChallengeRecord,
    ObjectProperty,
)
from world.mechanics.types import (
    ChallengeResolutionError,
    ChallengeResolutionResult,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.mechanics.models import (
        ChallengeApproach,
        ChallengeInstance,
        ChallengeTemplate,
    )
    from world.mechanics.types import CapabilitySource
    from world.traits.models import CheckOutcome

_ERR_NOT_ACTIVE = "Challenge is not active."
_ERR_NOT_REVEALED = "Challenge has not been revealed."
_ERR_ALREADY_RESOLVED = "Character has already resolved this challenge."
_ERR_WRONG_APPROACH = "Approach does not belong to this challenge's template."


def resolve_challenge(
    character: ObjectDB,
    challenge_instance: ChallengeInstance,
    approach: ChallengeApproach,
    capability_source: CapabilitySource,  # noqa: ARG001
) -> ChallengeResolutionResult:
    """
    Resolve a character's action against a challenge.

    1. Validate state
    2. Perform check
    3. Select consequence
    4. Apply effects
    5. Update challenge state
    6. Create record
    7. Return result
    """
    _validate(character, challenge_instance, approach)

    if approach.action_template is not None:
        return _resolve_via_template(character, challenge_instance, approach)

    template = challenge_instance.template

    # 2. Perform check
    check_result = perform_check(
        character, approach.check_type, target_difficulty=template.severity
    )

    # 3. Select consequence and resolution metadata
    consequence, resolution_type = _select_consequence(
        approach, template, check_result.outcome, character
    )

    # 4. Apply effects
    context = ResolutionContext(character=character, challenge_instance=challenge_instance)
    pending = PendingResolution(
        check_result=check_result,
        selected_consequence=consequence,
    )
    applied_effects = apply_resolution(pending, context)

    for effect in applied_effects:
        if effect.created_instance is not None and isinstance(
            effect.created_instance, ObjectProperty
        ):
            effect.created_instance.source_challenge = challenge_instance
            effect.created_instance.save(update_fields=["source_challenge"])

    # 5. Determine resolution type and update challenge state
    challenge_deactivated = False
    if resolution_type == ResolutionType.DESTROY:
        challenge_instance.is_active = False
        challenge_instance.save()
        challenge_deactivated = True
    # TEMPORARY: For MVP, treated same as PERSONAL (challenge stays active).
    # Future: track bypass duration and re-activate after N rounds.

    # 6. Create record
    record = CharacterChallengeRecord.objects.create(
        character=character,
        challenge_instance=challenge_instance,
        approach=approach,
        outcome=check_result.outcome,
        consequence=consequence if consequence.pk else None,
    )

    _record_challenge_outcome(
        record=record,
        character=character,
        pool=None,
        check_type=approach.check_type,
        consequence=consequence,
    )

    # 7. Build display consequences and return
    all_consequences = list(
        Consequence.objects.filter(
            challenge_template_consequences__challenge_template=template,
        )
    )
    display_consequences = build_outcome_display(all_consequences, consequence)

    return ChallengeResolutionResult(
        challenge_instance_id=challenge_instance.pk,
        challenge_name=template.name,
        approach_name=approach.display_name,
        check_result=check_result,
        consequence=consequence,
        applied_effects=applied_effects,
        resolution_type=resolution_type,
        challenge_deactivated=challenge_deactivated,
        display_consequences=display_consequences,
    )


def _record_challenge_outcome(
    *,
    record: CharacterChallengeRecord,
    character: ObjectDB,
    pool,  # actions.ConsequencePool | None — no import to avoid a cross-app cycle
    check_type,  # checks.CheckType | None
    consequence: Consequence,
) -> None:
    """Persist a ConsequenceOutcome for a challenge resolution (#850).

    Side-effect only — never changes the returned ChallengeResolutionResult.
    Skips silently when the inputs required by the non-nullable ConsequenceOutcome
    columns are absent: a missing check_type (gate-only resolution), or a character
    with no CharacterSheet.

    A null pool is valid — it represents a plain (non-template) challenge resolution
    whose roulette is reconstructed on read from the authored consequence links.

    The ModifierBreakdown is rebuilt from the character's live modifiers via
    collect_check_modifiers — the challenge pipeline does not retain a breakdown
    object, and rebuilding at record time is faithful to resolution-time state.
    """
    from world.checks.services import (  # noqa: PLC0415
        collect_check_modifiers,
        record_consequence_outcome,
    )

    if check_type is None:
        return
    try:
        character_sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return
    if character_sheet is None:
        return

    breakdown = collect_check_modifiers(character_sheet, check_type)
    record_consequence_outcome(
        character_sheet,
        check_type,
        pool,
        consequence if consequence.pk else None,
        breakdown,
        challenge_record=record,
    )


def _validate(
    character: ObjectDB,
    challenge_instance: ChallengeInstance,
    approach: ChallengeApproach,
) -> None:
    """Validate that challenge resolution can proceed."""
    if not challenge_instance.is_active:
        raise ChallengeResolutionError(_ERR_NOT_ACTIVE)
    if not challenge_instance.is_revealed:
        raise ChallengeResolutionError(_ERR_NOT_REVEALED)
    if CharacterChallengeRecord.objects.filter(
        character=character,
        challenge_instance=challenge_instance,
    ).exists():
        raise ChallengeResolutionError(_ERR_ALREADY_RESOLVED)
    if approach.challenge_template_id != challenge_instance.template_id:
        raise ChallengeResolutionError(_ERR_WRONG_APPROACH)


def _select_consequence(
    approach: ChallengeApproach,
    template: ChallengeTemplate,
    outcome: CheckOutcome,
    character: ObjectDB,
) -> tuple[Consequence, str]:
    """
    Select a consequence for the given outcome tier.

    Priority: approach-level consequences override template-level for the same tier.
    Falls back to a synthetic unsaved consequence if no tier matches.

    Returns (consequence, resolution_type) tuple.
    """
    # Check approach-level consequences first
    approach_consequences = list(
        ApproachConsequence.objects.filter(
            approach=approach,
            consequence__outcome_tier=outcome,
        ).select_related("consequence")
    )
    if approach_consequences:
        consequences = [ac.consequence for ac in approach_consequences]
        selected = select_weighted(consequences)
        selected = filter_character_loss(character, selected, consequences)
        # Get resolution_type from ApproachConsequence through model
        ac = next(ac for ac in approach_consequences if ac.consequence_id == selected.pk)
        resolution_type = ac.resolution_type or ResolutionType.PERSONAL
        return selected, resolution_type

    # Fall back to template-level consequences
    template_links = list(
        ChallengeTemplateConsequence.objects.filter(
            challenge_template=template,
            consequence__outcome_tier=outcome,
        ).select_related("consequence")
    )
    if template_links:
        consequences = [link.consequence for link in template_links]
        selected = select_weighted(consequences)
        selected = filter_character_loss(character, selected, consequences)
        # Get resolution_type from through model
        link = next(link for link in template_links if link.consequence_id == selected.pk)
        return selected, link.resolution_type

    # No consequences for this tier — synthetic fallback
    fallback = Consequence(
        outcome_tier=outcome,
        label=str(outcome.name),
        weight=1,
        character_loss=False,
    )
    return fallback, ResolutionType.PERSONAL


def _resolve_via_template(
    character: ObjectDB,
    challenge_instance: ChallengeInstance,
    approach: ChallengeApproach,
) -> ChallengeResolutionResult:
    """Resolve challenge using the approach's ActionTemplate pipeline."""
    from actions.services import start_action_resolution  # noqa: PLC0415

    action_template = approach.action_template
    context = ResolutionContext(character=character, challenge_instance=challenge_instance)

    pending = start_action_resolution(
        character=character,
        template=action_template,
        target_difficulty=challenge_instance.template.severity,
        context=context,
    )

    main = pending.main_result
    check_result: CheckResult | None
    consequence: Consequence
    if main and main.consequence_id:
        consequence = Consequence.objects.get(pk=main.consequence_id)
        check_result = main.check_result
    else:
        check_result = (
            main.check_result
            if main
            else (pending.gate_results[-1].check_result if pending.gate_results else None)
        )
        outcome = check_result.outcome if check_result else None
        consequence = Consequence(
            outcome_tier=outcome,
            label=str(outcome.name) if outcome else "Unknown",
            weight=1,
            character_loss=False,
        )

    # Determine challenge deactivation — check template-level resolution type for this consequence
    challenge_deactivated = False
    resolution_type = ResolutionType.PERSONAL
    if consequence.pk:
        template_links = list(
            ChallengeTemplateConsequence.objects.filter(
                challenge_template=challenge_instance.template,
                consequence=consequence,
            )
        )
        if template_links:
            resolution_type = template_links[0].resolution_type

    if resolution_type == ResolutionType.DESTROY:
        challenge_instance.is_active = False
        challenge_instance.save()
        challenge_deactivated = True

    record = CharacterChallengeRecord.objects.create(
        character=character,
        challenge_instance=challenge_instance,
        approach=approach,
        outcome=check_result.outcome if check_result else None,
        consequence=consequence if consequence.pk else None,
    )

    # Persist the unified ConsequenceOutcome (#850). The action-template path
    # records with its own ConsequencePool; the standard path records with
    # pool=None (#865, roulette reconstructed on read from the authored links).
    # check_result may be None for a gate-only resolution; without a check_type
    # we cannot record.
    _record_challenge_outcome(
        record=record,
        character=character,
        pool=action_template.consequence_pool,
        check_type=action_template.check_type,
        consequence=consequence,
    )

    all_consequences = list(
        Consequence.objects.filter(
            challenge_template_consequences__challenge_template=challenge_instance.template,
        )
    )
    display_consequences = build_outcome_display(all_consequences, consequence)

    return ChallengeResolutionResult(
        challenge_instance_id=challenge_instance.pk,
        challenge_name=challenge_instance.template.name,
        approach_name=approach.display_name,
        check_result=check_result,
        consequence=consequence,
        applied_effects=[],
        resolution_type=resolution_type,
        challenge_deactivated=challenge_deactivated,
        display_consequences=display_consequences,
    )
