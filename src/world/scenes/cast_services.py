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
  it — unless the target has not acknowledged a high-risk encounter (#777), in
  which case a PENDING ``SceneActionRequest`` is created and the encounter feed
  is deferred to acceptance.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from actions.services import start_action_resolution
from world.checks.types import ResolutionContext
from world.combat.cast_seed import (
    encounter_requiring_risk_acknowledgement,
    seed_or_feed_encounter_from_cast,
)
from world.combat.services import acknowledge_encounter_risk
from world.magic.models.techniques import CharacterTechnique, ConditionTargetKind
from world.magic.narration import render_cast_outcome_narration
from world.magic.services.condition_application import (
    apply_technique_conditions,
    remove_technique_conditions,
)
from world.magic.services.hostility import is_technique_hostile
from world.magic.services.signature_effects import apply_signature_bonus_conditions
from world.magic.services.targeting import (
    InvalidCastTarget,
    cast_requires_consent,
    derive_target_relationship,
    resolve_targets,
    validate_cast_target,
)
from world.scenes.action_constants import (
    CAST_ACTION_KEY,
    CAST_DIFFICULTY_BANDS,
    ActionRequestStatus,
)
from world.scenes.action_models import SceneActionRequest, SceneCastPullDeclaration
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.narrator import get_or_create_narrator_persona
from world.scenes.types import CastResult, EnhancedSceneActionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import PendingActionResolution
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import FuryTier, Technique
    from world.magic.models.signature import SignatureMotifBonus
    from world.magic.services.fury import FuryResolution
    from world.magic.types.power_ledger import PowerLedger
    from world.magic.types.pull import CastPullDeclaration
    from world.scenes.models import Interaction, Persona, Scene

_PULL_FIZZLE_NOTE = "The declared thread pull fizzles — its committed resonance is spent."


def derive_cast_difficulty(technique: Technique) -> int:
    """Difficulty for a standalone cast, sourced from the technique's authored intensity."""
    intensity = technique.intensity or 1
    for ceiling, difficulty in CAST_DIFFICULTY_BANDS:
        if intensity <= ceiling:
            return difficulty
    return CAST_DIFFICULTY_BANDS[-1][1]


def _resolve_cast(  # noqa: PLR0913 - cohesive cast-resolution params
    *,
    technique: Technique,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — mirrors _resolve_enhanced_action
    target: ObjectDB | None,  # noqa: OBJECTDB_PARAM
    difficulty: int,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_pull: CastPullDeclaration | None = None,
    confirm_soulfray_risk: bool = True,
) -> tuple[EnhancedSceneActionResult | None, PowerLedger | None, FuryResolution | None]:
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
        fury_commitment: Optional FuryTier the player declared.
        fury_anchor: CharacterSheet of the anchor character (bond caps the tier).

    Returns the ``EnhancedSceneActionResult`` (``None`` when ``use_technique``
    returns ``confirmed=False`` — soulfray gate not confirmed), the cast-level
    ``PowerLedger`` (BASE + ENVIRONMENT stages), and the ``FuryResolution`` (None
    if no fury).
    """
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.anima import get_character_cast_check  # noqa: PLC0415
    from world.magic.services.cast_threads import applicable_threads_for_cast  # noqa: PLC0415

    action_template = technique.action_template
    context = ResolutionContext(character=character, target=target)

    # The cast rolls the CASTER'S personal magic check (their anima-ritual check);
    # falls back to the template's own check (None) when no ritual is provisioned.
    cast_check = get_character_cast_check(character)

    from world.magic.services.fury import run_fury_for_action  # noqa: PLC0415

    applicable_threads = applicable_threads_for_cast(character, technique, cast_pull=cast_pull)

    # Signature-motif bonus (#1582): a flat intensity delta on the signed technique's
    # thread folds into the cast's power derivation (no-op / 0 when unsigned).
    from world.magic.services.signature_effects import signature_intensity_delta  # noqa: PLC0415

    sig_intensity_delta = signature_intensity_delta(character, technique)

    fury_res = run_fury_for_action(
        character=character,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        source_technique=technique,
    )

    captured: dict[str, PowerLedger] = {}

    def _resolve_fn(
        *,
        power: int,  # noqa: ARG001 — power unused; ledger is what the cast pipeline captures
        ledger: PowerLedger,
        extra_modifiers: int = 0,
    ) -> PendingActionResolution:
        captured["ledger"] = ledger
        return start_action_resolution(
            character=character,
            template=action_template,
            target_difficulty=difficulty,
            context=context,
            check_type=cast_check,
            extra_modifiers=extra_modifiers,
        )

    technique_result = use_technique(
        character=character,
        technique=technique,
        resolve_fn=_resolve_fn,
        confirm_soulfray_risk=confirm_soulfray_risk,
        strain_commitment=strain_commitment,
        applicable_threads=applicable_threads,
        cast_pull=cast_pull,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=(fury_res.intensity_bonus if fury_res else 0) + sig_intensity_delta,
    )

    # Soulfray gate: use_technique returned without resolving — propagate None result.
    if not technique_result.confirmed:
        return None, None, fury_res

    resolution_result: PendingActionResolution = technique_result.resolution_result  # type: ignore[assignment]
    power_ledger = captured.get("ledger")
    result = EnhancedSceneActionResult(
        action_resolution=resolution_result,
        action_key=CAST_ACTION_KEY,
        technique_result=technique_result,
        power_ledger=power_ledger,
        fury_committed=fury_res.realized_tier if fury_res else None,
    )
    return result, power_ledger, fury_res


def _resolve_signature_snippet(
    bonus: SignatureMotifBonus | None, character_sheet: CharacterSheet
) -> str | None:
    """Resolve the cosmetic narration snippet for a signed technique's bonus.

    Prefers ``bonus.narrative_snippet`` (staff-authored prose). When blank, falls
    back to the first facet name found in the character's Motif
    (``MotifResonanceAssociation.facet.name``).  Returns ``None`` when no bonus is
    set or no fallback facet is available.

    Args:
        bonus: The active ``SignatureMotifBonus`` (or ``None`` — early-return).
        character_sheet: The caster's ``CharacterSheet`` (used for the Motif lookup).
    """
    if bonus is None:
        return None
    if bonus.narrative_snippet:
        return bonus.narrative_snippet
    # Fallback: primary Motif facet name (first MotifResonanceAssociation on record).
    from world.magic.models.motifs import MotifResonanceAssociation  # noqa: PLC0415

    first_assoc = (
        MotifResonanceAssociation.objects.filter(motif_resonance__motif__character=character_sheet)
        .select_related("facet")
        .first()
    )
    return first_assoc.facet.name if first_assoc is not None else None


def create_cast_outcome_pose(  # noqa: PLR0913 - all params describe one pose; cohesive
    *,
    scene: Scene,
    caster_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    result: EnhancedSceneActionResult,
    power_ledger: PowerLedger | None = None,
    fizzle_note: str | None = None,
) -> Interaction:
    """Author the Narrator OUTCOME pose describing a resolved standalone cast.

    Args:
        fizzle_note: Optional explanatory note appended to the narration when a
            declared pull could not be charged (e.g. resonance drained mid-consent).
    """
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    outcome_label = check_result.outcome_name if check_result is not None else "Unknown"
    success_level = check_result.success_level if check_result is not None else 0

    # Signature-motif cosmetic (#1582): append the signed bonus's narrative snippet
    # (or primary Motif facet name as fallback) to the cast-outcome narration.
    from world.magic.services.signature import signature_bonus_for  # noqa: PLC0415

    sig_bonus = signature_bonus_for(caster_persona.character_sheet.character, technique)
    signature_snippet = _resolve_signature_snippet(sig_bonus, caster_persona.character_sheet)

    narration = render_cast_outcome_narration(
        actor_label=caster_persona.name,
        technique_name=technique.name,
        target_label=target_persona.name if target_persona is not None else None,
        outcome_label=outcome_label,
        success_level=success_level,
        power_ledger=power_ledger,
        fizzle_note=fizzle_note,
        signature_snippet=signature_snippet,
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
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_pull: CastPullDeclaration | None = None,
    fizzle_note: str | None = None,
    supplied_personas: list[Persona] | None = None,
    confirm_soulfray_risk: bool = True,
) -> tuple[EnhancedSceneActionResult | None, PowerLedger | None, Interaction | None]:
    """Resolve a persisted standalone-cast request, mark it RESOLVED, author the OUTCOME pose.

    Shared by the immediate path (request just created) and the consent-accept path
    (an existing PENDING request). The caller MUST wrap this in ``transaction.atomic()``.

    Args:
        fizzle_note: Optional note forwarded to ``create_cast_outcome_pose`` when a
            declared pull could not be charged and fizzled instead.
        supplied_personas: For FILTERED_GROUP techniques, the player-picked subset of
            targets already resolved from ``target_persona_ids``. Passed directly to
            ``resolve_targets`` as ``supplied_personas``. If ``None``, falls back to
            ``[target_persona]`` (the pre-existing single-target path).
    """
    character = caster_persona.character_sheet.character
    target = target_persona.character_sheet.character if target_persona is not None else None
    difficulty = derive_cast_difficulty(technique)

    result, power_ledger, fury_res = _resolve_cast(
        technique=technique,
        character=character,
        target=target,
        difficulty=difficulty,
        strain_commitment=strain_commitment,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        cast_pull=cast_pull,
        confirm_soulfray_risk=confirm_soulfray_risk,
    )

    # Soulfray gate: use_technique returned unconfirmed — propagate without resolving.
    if result is None:
        return None, None, None

    # Apply technique-authored conditions to resolved targets.
    success_level = (
        result.action_resolution.main_result.check_result.success_level
        if result.action_resolution.main_result is not None
        else 0
    )
    eff_intensity = power_ledger.total if power_ledger is not None else technique.intensity
    relationship = derive_target_relationship(technique)
    if relationship == ConditionTargetKind.SELF:
        # A SELF technique's effect always lands on the caster, independent of the
        # technique's target_type cardinality — mirrors combat's _resolve_condition_target,
        # where SELF resolves to caster_od unconditionally. resolve_targets is
        # cardinality-driven (SINGLE + no supplied target → []), so a self-cast with
        # the default SINGLE cardinality would otherwise resolve to no targets and
        # silently drop the condition.
        targets_by_kind: dict[str, list] = {relationship: [character]}
    else:
        # Use the caller-supplied list when provided (FILTERED_GROUP picks a subset);
        # fall back to the single-target form for SELF/SINGLE/AREA paths.
        _supplied = (
            supplied_personas
            if supplied_personas is not None
            else ([target_persona] if target_persona is not None else [])
        )
        resolved_personas = resolve_targets(
            technique=technique,
            initiator_persona=caster_persona,
            scene=scene,
            supplied_personas=_supplied,
        )
        targets_by_kind = {relationship: [p.character_sheet.character for p in resolved_personas]}
    apply_technique_conditions(
        technique=technique,
        success_level=success_level,
        eff_intensity=eff_intensity,
        targets_by_kind=targets_by_kind,
        source_character=character,
    )
    # Signature-motif bonus (#1582): apply the signed technique's bonus conditions
    # through the SAME shared seam, over the same resolved targets. No-op when the
    # technique is not signed or the bonus carries no condition rows.
    apply_signature_bonus_conditions(
        character=character,
        technique=technique,
        success_level=success_level,
        eff_intensity=eff_intensity,
        targets_by_kind=targets_by_kind,
        source_character=character,
    )
    # Dispel/cleanse sibling (#1585): strip technique-authored conditions from the
    # same resolved targets. Independent of the apply call — a technique may apply
    # some conditions and remove others. No-op when the technique has no
    # removed_conditions rows.
    remove_technique_conditions(
        technique=technique,
        success_level=success_level,
        targets_by_kind=targets_by_kind,
        source_character=character,
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
        fizzle_note=fizzle_note,
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
        fury_committed=fury_res.realized_tier if fury_res else None,
    )
    persist_power_ledger(interaction=action_interaction, ledger=power_ledger)
    request.action_interaction = action_interaction
    request.save(update_fields=["action_interaction"])

    return result, power_ledger, pose


def resolve_accepted_cast(
    action_request: SceneActionRequest,
) -> EnhancedSceneActionResult | None:
    """Resolve a PENDING standalone cast on consent acceptance.

    Benign casts resolve via the cast pipeline (check result + OUTCOME pose).
    Hostile casts — PENDING only when the #777 risk gate fired — resolve by
    seeding/feeding the combat encounter and recording the target's risk
    acknowledgement; they return None (combat state carries the outcome; the
    only caller's view guards ``result is not None``).

    Args:
        action_request: A PENDING SceneActionRequest with ``is_standalone_cast`` True.

    Returns:
        The resolved EnhancedSceneActionResult for benign casts; None for hostile
        casts resolved into combat.

    A persisted ``SceneCastPullDeclaration`` is re-checked here on the benign
    path: if the committed pull is still payable it is charged with the cast;
    otherwise the cast resolves pull-less and the OUTCOME pose carries a fizzle
    note. (Hostile casts never carry a declaration — pulls are rejected on the
    hostile route at request time.)

    Note:
        The affordability preview is unlocked and does not cover every charge-time
        gate (anchor-in-action, worn facets, engagement, protagonism locks, or a
        balance drained by a concurrent spend). Any ``MagicError`` raised while
        charging the pull is caught and the cast degrades to the fizzle path
        rather than surfacing as an error to the consent accepter.
    """
    from world.magic.services.resonance import preview_resonance_pull  # noqa: PLC0415
    from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

    initiator = action_request.initiator_persona
    target = action_request.target_persona
    technique = action_request.technique
    if (
        target is not None
        and target.character_sheet_id != initiator.character_sheet_id
        and is_technique_hostile(technique)
    ):
        with transaction.atomic():
            encounter = seed_or_feed_encounter_from_cast(
                caster_sheet=initiator.character_sheet,
                target_sheet=target.character_sheet,
                technique=technique,
                scene=action_request.scene,
                room=action_request.scene.location,
            )
            acknowledge_encounter_risk(encounter, target.character_sheet)
            action_request.status = ActionRequestStatus.RESOLVED
            action_request.resolved_at = timezone.now()
            action_request.save(update_fields=["status", "resolved_at"])
        return None

    declaration = SceneCastPullDeclaration.objects.filter(request=action_request).first()
    cast_pull = None
    fizzle_note = None
    if declaration is not None:
        threads = list(declaration.threads.filter(retired_at__isnull=True))
        preview = (
            preview_resonance_pull(
                action_request.initiator_persona.character_sheet,
                declaration.resonance,
                declaration.tier,
                threads,
            )
            if threads
            else None
        )
        if preview is not None and preview.affordable:
            cast_pull = CastPullDeclaration(
                resonance=declaration.resonance,
                tier=declaration.tier,
                threads=tuple(threads),
            )
        else:
            fizzle_note = _PULL_FIZZLE_NOTE

    from world.magic.exceptions import MagicError  # noqa: PLC0415

    def _resolve(
        pull: CastPullDeclaration | None, note: str | None
    ) -> tuple[EnhancedSceneActionResult | None, PowerLedger | None, Interaction | None]:
        with transaction.atomic():
            return _resolve_and_pose_cast(
                request=action_request,
                scene=action_request.scene,
                caster_persona=action_request.initiator_persona,
                target_persona=action_request.target_persona,
                technique=action_request.technique,
                strain_commitment=action_request.strain_commitment,
                fury_commitment=action_request.fury_commitment,
                fury_anchor=action_request.fury_anchor,
                cast_pull=pull,
                fizzle_note=note,
                confirm_soulfray_risk=True,  # consent-accept always confirms soulfray
            )

    try:
        result, _power_ledger, _pose = _resolve(cast_pull, fizzle_note)
    except MagicError:
        if cast_pull is None:
            raise
        # Charge-time pull failure after an affordable preview (drained balance,
        # anchor no longer in action, lock acquired, …) — degrade to the fizzle
        # path instead of failing the consent accept.
        result, _power_ledger, _pose = _resolve(None, _PULL_FIZZLE_NOTE)
    return result  # result.power_ledger is already set from _resolve_cast


def _guard_area_consent(technique: Technique, *, caster: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Raise InvalidCastTarget when a behavior-altering AREA cast would expand without consent.

    ``caster`` is the casting game Character so the caster's signed
    ``SignatureMotifBonus`` conditions are included in the consent decision (#1582).
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415

    if technique.target_type != ActionTargetType.AREA or not cast_requires_consent(
        technique, caster=caster
    ):
        return
    if derive_target_relationship(technique) == ConditionTargetKind.ALLY:
        # TODO(#1321 follow-up): mass-consent state machine for AREA behavior-altering
        # techniques; per-target consent is not yet supported for multi-target casts.
        msg = (
            "Multi-target behavior-altering AREA casts are not yet supported; "
            "obtain individual consent before casting."
        )
        raise InvalidCastTarget(msg)


def _route_filtered_group_cast(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    technique: Technique,
    strain_commitment: int,
    fury_commitment: FuryTier | None,
    fury_anchor: CharacterSheet | None,
    cast_pull: CastPullDeclaration | None,
    supplied_personas: list[Persona],
    confirm_soulfray_risk: bool = True,
) -> CastResult:
    """Route a FILTERED_GROUP cast that has a player-supplied persona list.

    Raises InvalidCastTarget for hostile or behavior-altering cases (deferred paths).
    """
    if is_technique_hostile(technique):
        # TODO(#1321 follow-up): multi-target hostile FILTERED_GROUP needs
        # per-target combat seeds; not yet supported.
        msg = (
            "Multi-target hostile FILTERED_GROUP casts are not yet supported standalone; "
            "use combat targeting instead."
        )
        raise InvalidCastTarget(msg)
    if cast_requires_consent(technique, caster=initiator_persona.character_sheet.character):
        # TODO(#1321 follow-up): behavior-altering FILTERED_GROUP requires a
        # per-target consent state machine; not yet supported.
        msg = (
            "Multi-target behavior-altering FILTERED_GROUP casts are not yet supported; "
            "obtain individual consent before casting."
        )
        raise InvalidCastTarget(msg)
    return _route_immediate_cast(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=None,  # no single primary target; resolve_targets uses supplied_personas
        technique=technique,
        strain_commitment=strain_commitment,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        cast_pull=cast_pull,
        supplied_personas=supplied_personas,
        confirm_soulfray_risk=confirm_soulfray_risk,
    )


def _route_other_pc_cast(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
    strain_commitment: int,
    fury_commitment: FuryTier | None,
    fury_anchor: CharacterSheet | None,
    cast_pull: CastPullDeclaration | None,
    confirm_soulfray_risk: bool = True,
) -> CastResult:
    """Route a cast directed at another PC (not the caster's own sheet)."""
    if is_technique_hostile(technique):
        if cast_pull is not None:
            msg = "Pulls cannot be declared on hostile casts."
            raise ValidationError(msg)
        return _route_hostile_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
        )
    if cast_requires_consent(technique, caster=initiator_persona.character_sheet.character):
        return _route_benign_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
            cast_pull=cast_pull,
            confirm_soulfray_risk=confirm_soulfray_risk,
        )
    return _route_immediate_cast(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        technique=technique,
        strain_commitment=strain_commitment,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        cast_pull=cast_pull,
        confirm_soulfray_risk=confirm_soulfray_risk,
    )


def request_technique_cast(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None = None,
    technique: Technique,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_pull: CastPullDeclaration | None = None,
    supplied_personas: list[Persona] | None = None,
    confirm_soulfray_risk: bool = True,
) -> CastResult:
    """Route a standalone technique cast per the consent/combat/immediate matrix.

    Args:
        scene: The scene the cast happens in.
        initiator_persona: The casting persona (FK to a CharacterSheet).
        target_persona: The targeted persona, or None for self/room/no-target.
        technique: The technique being cast (must be castable standalone).
        strain_commitment: Extra anima committed beyond the technique baseline.
        fury_commitment: Optional FuryTier the player declared.
        fury_anchor: CharacterSheet of the anchor character (bond caps the tier).
        cast_pull: Optional declared thread pull. Charged in-line on the
            immediate path; persisted as a ``SceneCastPullDeclaration`` on the
            benign consent path; rejected on hostile casts (combat pulls go
            through ``CombatPull``).
        supplied_personas: For FILTERED_GROUP techniques, the player-picked subset of
            targets. When provided alongside a FILTERED_GROUP technique, they are
            forwarded to ``resolve_targets`` for intersection with the eligible set.
            Only the immediate (benign, consent-free) path is supported; hostile or
            behavior-altering FILTERED_GROUP raises ``InvalidCastTarget``.
        confirm_soulfray_risk: When ``False`` and the caster has an active Soulfray
            stage, the cast is halted before resolving and a ``CastResult`` with
            ``soulfray_warning`` populated (and no request row) is returned. Defaults
            ``True`` so all existing callers are unaffected.

    Returns:
        A CastResult whose populated payload depends on the routing branch taken.

    Raises:
        ValidationError: If the caster does not know the technique, the
            technique has no action template (not castable standalone), or a
            pull is declared on a hostile cast.
        InvalidCastTarget: If ``supplied_personas`` is provided for a FILTERED_GROUP
            technique that requires consent or is hostile (deferred paths).
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415

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

    validate_cast_target(
        technique=technique,
        initiator_persona=initiator_persona,
        target_personas=[target_persona] if target_persona is not None else [],
    )

    _guard_area_consent(technique, caster=initiator_persona.character_sheet.character)

    if supplied_personas is not None and technique.target_type == ActionTargetType.FILTERED_GROUP:
        return _route_filtered_group_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            technique=technique,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
            cast_pull=cast_pull,
            supplied_personas=supplied_personas,
            confirm_soulfray_risk=confirm_soulfray_risk,
        )

    # Inline the other-PC check (rather than a bool var) so the type checker can
    # narrow ``target_persona`` to non-None inside the block.
    if (
        target_persona is not None
        and target_persona.character_sheet_id != initiator_persona.character_sheet_id
    ):
        return _route_other_pc_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
            cast_pull=cast_pull,
            confirm_soulfray_risk=confirm_soulfray_risk,
        )

    return _route_immediate_cast(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        technique=technique,
        strain_commitment=strain_commitment,
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        cast_pull=cast_pull,
        confirm_soulfray_risk=confirm_soulfray_risk,
    )


def _create_cast_request(  # noqa: PLR0913
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    status: str,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    resolved_at: datetime | None = None,
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
        fury_commitment=fury_commitment,
        fury_anchor=fury_anchor,
        resolved_at=resolved_at,
    )


def _route_hostile_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
) -> CastResult:
    """Hostile cast at another PC → audit request + seed/feed a combat encounter.

    When the cast would pull an unacknowledged target into a high-risk encounter
    (#777), it becomes a PENDING consent request instead; acceptance resolves it
    via the hostile branch of resolve_accepted_cast.
    """
    gating_encounter = encounter_requiring_risk_acknowledgement(
        scene, target_persona.character_sheet
    )
    if gating_encounter is not None:
        request = _create_cast_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            status=ActionRequestStatus.PENDING,
        )
        return CastResult(request=request)
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


def _route_benign_cast(  # noqa: PLR0913 - cohesive benign-cast routing params
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
    strain_commitment: int,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_pull: CastPullDeclaration | None = None,
    confirm_soulfray_risk: bool = True,  # noqa: ARG001 — resolution deferred to accept; kept for signature symmetry
) -> CastResult:
    """Benign cast at another PC → PENDING request awaiting consent (resolved on accept).

    A declared pull is persisted (not charged) as a ``SceneCastPullDeclaration``
    so it survives until consent-resolution re-checks affordability.
    """
    with transaction.atomic():
        request = _create_cast_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            status=ActionRequestStatus.PENDING,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
        )
        if cast_pull is not None:
            declaration = SceneCastPullDeclaration.objects.create(
                request=request,
                resonance=cast_pull.resonance,
                tier=cast_pull.tier,
            )
            declaration.threads.set(cast_pull.threads)
    return CastResult(request=request)


def _route_immediate_cast(  # noqa: PLR0913 - cohesive immediate-cast routing params
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    strain_commitment: int = 0,
    fury_commitment: FuryTier | None = None,
    fury_anchor: CharacterSheet | None = None,
    cast_pull: CastPullDeclaration | None = None,
    supplied_personas: list[Persona] | None = None,
    confirm_soulfray_risk: bool = True,
) -> CastResult:
    """Self/room/no-target cast → resolve now, persist RESOLVED, author OUTCOME pose.

    When ``confirm_soulfray_risk=False`` and the caster has an active Soulfray stage,
    ``use_technique`` will return without resolving. In that case no request row is
    persisted and a ``CastResult`` with only ``soulfray_warning`` populated is returned.
    """
    from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

    # Pre-flight soulfray check: avoid creating a SceneActionRequest when the cast
    # will be halted by the soulfray gate (use_technique returns confirmed=False).
    if not confirm_soulfray_risk:
        character = initiator_persona.character_sheet.character
        warning = get_soulfray_warning(character)
        if warning is not None:
            return CastResult(soulfray_warning=warning)

    with transaction.atomic():
        request = _create_cast_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            status=ActionRequestStatus.PENDING,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
        )
        result, power_ledger, pose = _resolve_and_pose_cast(
            request=request,
            scene=scene,
            caster_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            strain_commitment=strain_commitment,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
            cast_pull=cast_pull,
            supplied_personas=supplied_personas,
            confirm_soulfray_risk=confirm_soulfray_risk,
        )

    return CastResult(
        request=request,
        result=result,
        outcome_interaction=pose,
        power_ledger=power_ledger,
    )
