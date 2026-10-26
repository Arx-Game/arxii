"""Challenge resolution service functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.consequence_resolution import apply_resolution
from world.checks.constants import ModifierSourceKind
from world.checks.models import Consequence
from world.checks.outcome_utils import (
    build_outcome_display,
    filter_character_loss,
    select_weighted,
)
from world.checks.services import collect_check_modifiers, perform_check
from world.checks.types import (
    ModifierBreakdown,
    ModifierContribution,
    PendingResolution,
    ResolutionContext,
)
from world.mechanics.constants import CapabilitySourceType, DiscoveryType, ResolutionType
from world.mechanics.models import (
    ApproachConsequence,
    ChallengeInstance,
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

    from actions.types import PendingActionResolution
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ExtraTraitTerm
    from world.mechanics.models import (
        ChallengeApproach,
        ChallengeTemplate,
    )
    from world.mechanics.types import CapabilitySource
    from world.traits.models import CheckOutcome

_ERR_NOT_ACTIVE = "Challenge is not active."
_ERR_NOT_REVEALED = "Challenge has not been revealed."
_ERR_ALREADY_RESOLVED = "Character has already resolved this challenge."
_ERR_WRONG_APPROACH = "Approach does not belong to this challenge's template."


def instantiate_challenge(
    template: ChallengeTemplate,
    *,
    location: ObjectDB,
    target_object: ObjectDB,
) -> ChallengeInstance:
    """Mint a bare, active ChallengeInstance from a template.

    No SituationInstance involved — mirrors the direct-mint pattern
    ``positioning/plummet.py`` uses for the "Catch the Faller" challenge.

    ``is_revealed`` follows the template's authored ``discovery_type`` (#2865).
    It used to be hardcoded ``True``, which silently defeated
    ``DiscoveryType.DISCOVERABLE`` on every authored template this function
    minted — a GM staging a hidden beat got it revealed anyway. Every reactive
    combat challenge minted through here (Interpose, Succor, Catch the Faller)
    is authored OBVIOUS, so their behavior is unchanged.
    """
    return ChallengeInstance.objects.create(
        template=template,
        location=location,
        target_object=target_object,
        is_active=True,
        is_revealed=template.discovery_type == DiscoveryType.OBVIOUS,
    )


def resolve_challenge(
    character: ObjectDB,
    challenge_instance: ChallengeInstance,
    approach: ChallengeApproach,
    capability_source: CapabilitySource,
    *,
    extra_modifiers: int = 0,
) -> ChallengeResolutionResult:
    """
    Resolve a character's action against a challenge.

    1. Validate state
    2. Gather the character's modifiers for the check (#4629)
    3. Perform check with them, the capability source's value and ``extra_modifiers``
    4. Select consequence
    5. Apply effects
    6. Update challenge state
    7. Create record, storing the breakdown the roll used
    8. Return result

    The roll counts what any other check counts: worn items, buffs, conditions,
    distinctions and the active scene's modifiers, gathered by
    ``collect_check_modifiers`` (see :func:`_gather_challenge_modifiers`). The
    capability source's ``value`` (the one capability instance that opened this
    approach, ADR-0145) is added once, as before; authored ``CheckTypeCapabilityModifier``
    points are added once, by ``perform_check`` itself. ``extra_modifiers`` is the
    caller's own bonus (the bond bonus on Interpose and Succor).
    """
    _validate(character, challenge_instance, approach)
    extra_traits = capability_skill_terms(character, capability_source)

    if approach.action_template is not None:
        return _resolve_via_template(
            character,
            challenge_instance,
            approach,
            capability_source,
            extra_modifiers=extra_modifiers,
            extra_traits=extra_traits,
        )

    template = challenge_instance.template

    # 2-3. Gather modifiers, then perform check.
    # effective_severity, not template.severity: a GM who placed this instance may
    # have shifted it one band with a stated reason (#2865).
    breakdown = _gather_challenge_modifiers(
        character,
        approach.check_type,
        challenge_instance,
        capability_source,
        extra_traits=extra_traits,
    )
    check_result = perform_check(
        character,
        approach.check_type,
        target_difficulty=challenge_instance.effective_severity,
        extra_modifiers=_roll_modifiers(capability_source, breakdown, extra_modifiers),
        extra_traits=extra_traits,
    )
    if breakdown is not None:
        # Lazy import: world.conditions.services imports world.checks at load time.
        from world.conditions.services import spend_contributing_conditions  # noqa: PLC0415

        spend_contributing_conditions(breakdown)

    # 4. Select consequence and resolution metadata
    consequence, resolution_type = _select_consequence(
        approach, template, check_result.outcome, character
    )

    # 5. Apply effects
    # target=challenge_instance.target_object (#2503): ChallengeInstance.target_object
    # is a required field naming "the object embodying this challenge" — for a
    # bare-object affordance that's the actual torch/door/etc a consequence effect
    # with EffectTarget.TARGET must land on, not the acting character (the previous
    # unconditional None left every such effect falling back to context.character).
    context = ResolutionContext(
        character=character,
        challenge_instance=challenge_instance,
        target=challenge_instance.target_object,
    )
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

    # 6. Determine resolution type and update challenge state
    challenge_deactivated = False
    if resolution_type == ResolutionType.DESTROY:
        challenge_instance.is_active = False
        challenge_instance.save()
        challenge_deactivated = True
    # TEMPORARY: For MVP, treated same as PERSONAL (challenge stays active).
    # Future: track bypass duration and re-activate after N rounds.

    # 7. Create record
    record = CharacterChallengeRecord.objects.create(
        character=character.sheet_data,
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
        breakdown=breakdown,
    )

    # 8. Build display consequences and return
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


def capability_skill_terms(
    character: ObjectDB,
    capability_source: CapabilitySource,
) -> tuple[ExtraTraitTerm, ...]:
    """The skill term a challenge roll adds for ``capability_source`` (#4450).

    A capability that comes from a technique makes the roll magical, so it adds that
    technique's skill. Any other source adds nothing. The difficulty indicator shown
    before the player commits previews with the same terms, so the label matches the roll.
    """
    if capability_source.source_type != CapabilitySourceType.TECHNIQUE:
        return ()
    from world.magic.models import Technique  # noqa: PLC0415
    from world.magic.services.magic_skills import technique_skill_term  # noqa: PLC0415

    term = technique_skill_term(character, Technique.objects.get(pk=capability_source.source_id))
    return (term,) if term is not None else ()


def _sheet_or_none(character: ObjectDB) -> CharacterSheet | None:
    """The character's sheet, or None for a sheet-less actor (a GM puppet, a prop)."""
    try:
        return character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _capability_source_contribution(
    capability_source: CapabilitySource,
) -> list[ModifierContribution]:
    """The approach's capability as a labelled CAPABILITY row, for the stored record.

    CAPABILITY rows stay out of ``ModifierBreakdown.extra_modifiers_total`` because the
    roll adds those points by its own route (#4453); this one's route is
    :func:`_roll_modifiers`, which adds ``capability_source.value`` once. Labelled
    "<capability>: <source>" so it never reads like an authored check link
    ("Capability: <capability>"). A zero value moved nothing and is not recorded.
    """
    if capability_source.value == 0:
        return []
    names = [n for n in (capability_source.capability_name, capability_source.source_name) if n]
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.CAPABILITY,
            source_label=": ".join(names) or "Capability",
            value=capability_source.value,
        )
    ]


def _gather_challenge_modifiers(
    character: ObjectDB,
    check_type: CheckType,
    challenge_instance: ChallengeInstance,
    capability_source: CapabilitySource,
    *,
    extra_traits: tuple[ExtraTraitTerm, ...] = (),
) -> ModifierBreakdown | None:
    """The character's modifiers for a challenge roll, gathered once, before it (#4629).

    Through ``collect_check_modifiers`` with the active scene at the challenge's
    location, so worn items, buffs, conditions, distinctions, fashion and the scene's
    own modifiers count as on any other check. The approach's capability rides along
    as a CAPABILITY row (:func:`_capability_source_contribution`) so the stored record
    shows it. This one breakdown feeds the roll and is the one stored on the
    ``ConsequenceOutcome``; nothing rebuilds it afterwards. None for a sheet-less
    actor, which rolls without gathered modifiers.
    """
    sheet = _sheet_or_none(character)
    if sheet is None:
        return None
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    return collect_check_modifiers(
        sheet,
        check_type,
        scene=get_active_scene(challenge_instance.location),
        extra_contributions=_capability_source_contribution(capability_source),
        extra_traits=extra_traits,
    )


def _roll_modifiers(
    capability_source: CapabilitySource,
    breakdown: ModifierBreakdown | None,
    extra_modifiers: int,
) -> int:
    """What a challenge roll adds as ``extra_modifiers``: each term exactly once.

    The caller's bonus, the capability source's value (ADR-0145), and the gathered
    breakdown's ``extra_modifiers_total``, which leaves out every CAPABILITY row:
    authored capability links are added by ``perform_check`` itself and the source's
    row is the value added here (#4453).
    """
    gathered = breakdown.extra_modifiers_total if breakdown is not None else 0
    return extra_modifiers + capability_source.value + gathered


def _record_challenge_outcome(  # noqa: PLR0913 - keyword-only record context
    *,
    record: CharacterChallengeRecord,
    character: ObjectDB,
    pool,  # actions.ConsequencePool | None — no import to avoid a cross-app cycle
    check_type,  # checks.CheckType | None
    consequence: Consequence,
    breakdown: ModifierBreakdown | None,
) -> None:
    """Persist a ConsequenceOutcome for a challenge resolution (#850).

    Side-effect only — never changes the returned ChallengeResolutionResult.
    Skips silently when the inputs required by the non-nullable ConsequenceOutcome
    columns are absent: a missing check_type (gate-only resolution), or a character
    with no CharacterSheet.

    A null pool is valid — it represents a plain (non-template) challenge resolution
    whose roulette is reconstructed on read from the authored consequence links.

    ``breakdown`` is the one the roll used, gathered before it by
    :func:`_gather_challenge_modifiers` and passed through (#4629). It is never
    rebuilt here: a rebuild after the roll would see conditions the consequence just
    applied or a once-only condition the roll just spent, and before #4629 it stored
    modifiers the roll had never counted. An empty breakdown means the roll used
    none (a gate-only template resolution).
    """
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415

    if check_type is None or breakdown is None:
        return
    character_sheet = _sheet_or_none(character)
    if character_sheet is None:
        return

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
        character_id=character.pk,
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


def _outcome_of_pending(
    pending: PendingActionResolution,
) -> tuple[Consequence, CheckResult | None]:
    """The consequence a finished pipeline landed on, and the check behind it.

    A pipeline that selected a real consequence hands back the saved row. One
    that did not — a gate-only resolution, or a main step with no consequence —
    gets an unsaved stand-in labelled from the outcome tier, falling back to the
    last gate's check result and finally to "Unknown" when nothing rolled at all.
    """
    main = pending.main_result
    if main and main.consequence_id:
        return Consequence.objects.get(pk=main.consequence_id), main.check_result
    if main:
        check_result = main.check_result
    elif pending.gate_results:
        check_result = pending.gate_results[-1].check_result
    else:
        check_result = None
    outcome = check_result.outcome if check_result else None
    consequence = Consequence(
        outcome_tier=outcome,
        label=str(outcome.name) if outcome else "Unknown",
        weight=1,
        character_loss=False,
    )
    return consequence, check_result


def _resolution_type_for(
    challenge_instance: ChallengeInstance, consequence: Consequence
) -> ResolutionType:
    """What this consequence does to the challenge, per the template's own links.

    PERSONAL unless the template says otherwise — which is also the answer for an
    unsaved stand-in consequence, since nothing can be linked to it.
    """
    if not consequence.pk:
        return ResolutionType.PERSONAL
    link = ChallengeTemplateConsequence.objects.filter(
        challenge_template=challenge_instance.template,
        consequence=consequence,
    ).first()
    return link.resolution_type if link else ResolutionType.PERSONAL


def _resolve_via_template(  # noqa: PLR0913 - mirrors resolve_challenge's inputs
    character: ObjectDB,
    challenge_instance: ChallengeInstance,
    approach: ChallengeApproach,
    capability_source: CapabilitySource,
    *,
    extra_modifiers: int = 0,
    extra_traits: tuple[ExtraTraitTerm, ...] = (),
) -> ChallengeResolutionResult:
    """Resolve challenge using the approach's ActionTemplate pipeline.

    The template's main check gets the same roll inputs as the plain path (#4629):
    the gathered modifiers, the capability source's value and the caller's
    ``extra_modifiers``. Gates roll without them, as ``start_action_resolution``
    documents for every caller.
    """
    from actions.services import (  # noqa: PLC0415
        spend_or_defer_condition_uses,
        start_action_resolution,
    )

    action_template = approach.action_template
    # target=challenge_instance.target_object (#2503) — see the direct-path comment above.
    context = ResolutionContext(
        character=character,
        challenge_instance=challenge_instance,
        target=challenge_instance.target_object,
    )

    breakdown = _gather_challenge_modifiers(
        character,
        action_template.check_type,
        challenge_instance,
        capability_source,
        extra_traits=extra_traits,
    )
    pending = start_action_resolution(
        character=character,
        template=action_template,
        target_difficulty=challenge_instance.effective_severity,
        context=context,
        extra_modifiers=_roll_modifiers(capability_source, breakdown, extra_modifiers),
        extra_traits=extra_traits,
    )
    if breakdown is not None:
        spend_or_defer_condition_uses(pending, breakdown)
        if pending.main_result is None:
            # The main check never rolled (a gate stopped or paused it): nothing the
            # breakdown holds moved a roll, so the record stores no modifiers.
            breakdown = ModifierBreakdown()

    consequence, check_result = _outcome_of_pending(pending)
    resolution_type = _resolution_type_for(challenge_instance, consequence)

    challenge_deactivated = False
    if resolution_type == ResolutionType.DESTROY:
        challenge_instance.is_active = False
        challenge_instance.save()
        challenge_deactivated = True

    record = CharacterChallengeRecord.objects.create(
        character=character.sheet_data,
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
        breakdown=breakdown,
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
