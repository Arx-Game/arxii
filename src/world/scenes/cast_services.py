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
    seat_caster_for_benign_intervention,
    seed_or_feed_encounter_from_cast,
)
from world.combat.services import acknowledge_encounter_risk
from world.magic.models.techniques import CharacterTechnique, ConditionTargetKind
from world.magic.narration import render_cast_outcome_narration
from world.magic.services.condition_application import (
    apply_technique_conditions,
    apply_technique_treatments,
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
from world.scenes.action_models import SceneActionPullDeclaration, SceneActionRequest
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.narrator import get_or_create_narrator_persona
from world.scenes.types import CastResult, EnhancedSceneActionResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import PendingActionResolution
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import FuryTier, Resonance, Technique
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
    apply_variant: bool = True,
    preferred_resonance: Resonance | None = None,
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
    from world.magic.services.anima import resolve_cast_check_type  # noqa: PLC0415
    from world.magic.services.cast_threads import applicable_threads_for_cast  # noqa: PLC0415

    action_template = technique.action_template
    context = ResolutionContext(character=character, target=target)

    # The cast rolls the CASTER'S personal magic check, falling back to the
    # template's own check — the shared rule every cast path uses (ADR-0096).
    cast_check = resolve_cast_check_type(character, action_template)

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
        pull_target=target,
        control_penalty=fury_res.control_penalty if fury_res else 0,
        power_intensity_bonus=(fury_res.intensity_bonus if fury_res else 0) + sig_intensity_delta,
        apply_variant=apply_variant,
        preferred_resonance=preferred_resonance,
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


def create_cast_outcome_pose(  # noqa: PLR0913 - all params describe one pose; cohesive
    *,
    scene: Scene,
    caster_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    result: EnhancedSceneActionResult,
    power_ledger: PowerLedger | None = None,
    fizzle_note: str | None = None,
    technique_name: str | None = None,
) -> Interaction:
    """Author the Narrator OUTCOME pose describing a resolved standalone cast.

    Args:
        fizzle_note: Optional explanatory note appended to the narration when a
            declared pull could not be charged (e.g. resonance drained mid-consent).
        technique_name: Optional display name override. When provided (e.g. a
            gift-technique's unlocked-variant name from #1581), uses this in the
            narration instead of ``technique.name``.
    """
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    outcome_label = check_result.outcome_name if check_result is not None else "Unknown"
    success_level = check_result.success_level if check_result is not None else 0

    # Signature-motif cosmetic (#1582): append the signed bonus's narrative snippet
    # (or primary Motif facet name as fallback) to the cast-outcome narration.
    from world.magic.services.signature_effects import resolve_signature_snippet  # noqa: PLC0415

    signature_snippet = resolve_signature_snippet(
        caster_persona.character_sheet.character, technique
    )

    narration = render_cast_outcome_narration(
        actor_label=caster_persona.name,
        technique_name=technique_name if technique_name is not None else technique.name,
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
    use_base_form: bool = False,
    position_params: dict[str, int] | None = None,
    preferred_resonance: Resonance | None = None,
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

    # #1581: pose and cost reflect the gift-technique's unlocked variant by default.
    # When use_base_form=True, bypass variant resolution and use the raw technique.
    # #2022: when the technique was role-granted, resolve the variant by the
    # COVENANT_ROLE thread level, not the GIFT thread level.
    if use_base_form:
        resolved_name = technique.name
        resolved_intensity = technique.intensity
    else:
        from world.magic.specialization.services import resolve_specialized_variant  # noqa: PLC0415

        # Look up the CharacterTechnique to check for role_source provenance.
        char_technique = CharacterTechnique.objects.filter(
            character_id=caster_persona.character_sheet_id,
            technique=technique,
        ).first()
        resolved = resolve_specialized_variant(
            entity=technique,
            character=character,
            character_technique=char_technique,
            preferred_resonance=preferred_resonance,
        )
        resolved_name = resolved.name
        resolved_intensity = resolved.intensity

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
        apply_variant=not use_base_form,
        preferred_resonance=preferred_resonance,
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
    eff_intensity = power_ledger.total if power_ledger is not None else resolved_intensity
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
        position_params=position_params,
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
    # Technique treatment (#2668): perform bounded-mend treatments on resolved
    # targets. Fires BEFORE remove_technique_conditions so the wound condition
    # is still present when the treatment looks for it. No-op when the technique
    # has no treatment rows.
    apply_technique_treatments(
        technique=technique,
        success_level=success_level,
        targets_by_kind=targets_by_kind,
        source_character=character,
        scene=scene,
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
        technique_name=resolved_name,
    )
    request.result_interaction = pose
    request.save(update_fields=["result_interaction"])

    from world.scenes.interaction_services import create_action_interaction_core  # noqa: PLC0415
    from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

    action_interaction = create_action_interaction_core(
        persona=caster_persona,
        scene=scene,
        summary_label=f"{resolved_name}",
        strain_committed=strain_commitment,
        fury_committed=fury_res.realized_tier if fury_res else None,
    )
    persist_power_ledger(interaction=action_interaction, ledger=power_ledger)
    request.action_interaction = action_interaction
    request.save(update_fields=["action_interaction"])

    # #2646: an out-of-combat PERCEPTION-tagged cast by a ground-preparing role
    # holder rides this resolved cast to record/refresh a PreparedGround. Pure
    # rider — no-op unless every condition holds (see the service docstring).
    from world.covenants.perks.services import (  # noqa: PLC0415
        record_ground_preparation_from_cast,
    )

    record_ground_preparation_from_cast(
        caster_persona.character_sheet, technique, character.location
    )

    return result, power_ledger, pose


def _resolve_hostile_accepted_cast(
    action_request: SceneActionRequest,
    initiator: Persona,
    target: Persona,
    technique: Technique,
) -> None:
    """Resolve a PENDING hostile cast on consent acceptance into combat.

    Seeds (or feeds) the combat encounter, records the target's risk
    acknowledgement, marks the request RESOLVED, and — for entrance-sourced
    casts — fires flourish-only entrance success hooks (the real success level
    becomes known later at combat round resolution, #2183).
    """
    with transaction.atomic():
        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=initiator.character_sheet,
            target_sheet=target.character_sheet,
            technique=technique,
            scene=action_request.scene,
            room=action_request.scene.location,
            from_entrance=action_request.originated_as_entrance,
        )
        acknowledge_encounter_risk(encounter, target.character_sheet)
        action_request.status = ActionRequestStatus.RESOLVED
        action_request.resolved_at = timezone.now()
        action_request.save(update_fields=["status", "resolved_at"])
    if action_request.originated_as_entrance:
        from actions.definitions.social import run_entrance_success_hooks  # noqa: PLC0415

        run_entrance_success_hooks(
            initiator.character_sheet.character,
            action_request.scene,
            success_level=None,
            target_persona_id=target.pk,
            technique=technique,
        )


def _resolve_cast_pull(
    declaration: SceneActionPullDeclaration | None,
    initiator_persona: Persona,
) -> tuple[CastPullDeclaration | None, str | None]:
    """Resolve a committed pull declaration into a payable cast pull.

    Returns ``(cast_pull, fizzle_note)``: when the committed pull's preview is
    still affordable it is charged with the cast; otherwise the cast resolves
    pull-less and the OUTCOME pose carries a fizzle note.
    """
    from world.magic.services.resonance import preview_resonance_pull  # noqa: PLC0415
    from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

    if declaration is None:
        return None, None
    threads = list(declaration.threads.filter(retired_at__isnull=True))
    preview = (
        preview_resonance_pull(
            initiator_persona.character_sheet,
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
        return cast_pull, None
    return None, _PULL_FIZZLE_NOTE


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

    A persisted ``SceneActionPullDeclaration`` is re-checked here on the benign
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

    initiator = action_request.initiator_persona
    target = action_request.target_persona
    technique = action_request.technique
    if (
        target is not None
        and target.character_sheet_id != initiator.character_sheet_id
        and is_technique_hostile(technique)
    ):
        _resolve_hostile_accepted_cast(action_request, initiator, target, technique)
        return None

    declaration = SceneActionPullDeclaration.objects.filter(request=action_request).first()
    cast_pull, fizzle_note = _resolve_cast_pull(declaration, action_request.initiator_persona)

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

    if action_request.originated_as_entrance and result is not None:
        _run_entrance_benign_accept_hooks(action_request, initiator, target, technique, result)

    # #2226: Generalized benign-intervention seating — any benign cast accepted
    # by the target seats the caster if the target is an embattled ally. This
    # supersedes the entrance-only seating that used to live inside
    # _run_entrance_benign_accept_hooks; entrance casts still get their hooks
    # (flourish/disposition/suggestion) from the block above, but seating is
    # now handled here for all benign casts.
    if result is not None and not is_technique_hostile(technique):
        _maybe_seat_after_consent_accept(
            scene=action_request.scene,
            initiator_persona=initiator,
            target_persona=target,
            result=result,
        )

    # #1748: fire any pending decisive-check marker after a benign cast resolves.
    _maybe_fire_decisive_for_cast(action_request, result)

    return result  # result.power_ledger is already set from _resolve_cast


def _maybe_seat_after_consent_accept(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    result: EnhancedSceneActionResult,
) -> None:
    """Seat the caster in combat when a benign consent-accept cast touched an
    embattled ally (#2226).

    The consent-accept benign path is always SINGLE-target (``_route_benign_cast``
    creates requests with a single ``target_persona``; AREA/FILTERED_GROUP
    behavior-altering casts raise ``InvalidCastTarget``), so the target sheet is
    simply ``target_persona.character_sheet``.

    Guarded by ``success_level > 0`` — a resolved-but-fizzled cast does not seat.
    """
    main = result.action_resolution.main_result
    success_level = main.check_result.success_level if main is not None else 0
    if success_level <= 0:
        return
    if target_persona is None:
        return

    seat_caster_for_benign_intervention(
        caster_sheet=initiator_persona.character_sheet,
        target_sheets=[target_persona.character_sheet],
        scene=scene,
    )


def _maybe_fire_decisive_for_cast(
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult | None,
) -> None:
    """Fire any pending DecisiveCheckMarker after a benign cast resolves (#1748)."""
    if result is None:
        return
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


def _run_entrance_benign_accept_hooks(
    action_request: SceneActionRequest,
    initiator: Persona,
    target: Persona | None,
    technique: Technique,
    result: EnhancedSceneActionResult,
) -> None:
    """Fire the #2183 deferred hooks for an accepted benign entrance cast.

    Mirrors ``EntranceAction._resolve_inline_entrance_result`` (the resolved-inline
    branch), but at accept-time resolution instead of request-time: disposition
    (non-hostile + target present, raw resolution), flourish + suggestion when the
    resolved success level clears 0.

    Combat seating (#2226) is no longer handled here — the generalized
    ``_maybe_seat_after_consent_accept`` call in ``resolve_accepted_cast``
    handles it for all benign casts (entrance and non-entrance alike).
    """
    from actions.definitions.social import run_entrance_success_hooks  # noqa: PLC0415
    from world.npc_services.social_disposition import (  # noqa: PLC0415
        apply_social_disposition_delta,
    )

    actor = initiator.character_sheet.character
    main = result.action_resolution.main_result
    success_level = main.check_result.success_level if main is not None else 0

    if target is not None and not is_technique_hostile(technique):
        apply_social_disposition_delta(actor, target.pk, result.action_resolution)

    if success_level <= 0:
        return

    run_entrance_success_hooks(
        actor,
        action_request.scene,
        success_level=success_level,
        target_persona_id=target.pk if target is not None else None,
        technique=technique,
    )


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
    use_base_form: bool = False,
    position_params: dict[str, int] | None = None,
    preferred_resonance: Resonance | None = None,
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
        use_base_form=use_base_form,
        position_params=position_params,
        preferred_resonance=preferred_resonance,
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
    use_base_form: bool = False,
    position_params: dict[str, int] | None = None,
    originated_as_entrance: bool = False,
    preferred_resonance: Resonance | None = None,
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
            originated_as_entrance=originated_as_entrance,
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
            originated_as_entrance=originated_as_entrance,
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
        use_base_form=use_base_form,
        position_params=position_params,
        preferred_resonance=preferred_resonance,
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
    use_base_form: bool = False,
    position_params: dict[str, int] | None = None,
    originated_as_entrance: bool = False,
    preferred_resonance: Resonance | None = None,
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
            immediate path; persisted as a ``SceneActionPullDeclaration`` on the
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
        originated_as_entrance: Marks the cast as dispatched by a technique-driven
            combat entrance (#2183). Threaded onto the PENDING ``SceneActionRequest``
            row on the other-PC (benign consent / hostile risk-gated) paths only —
            the self/room/no-target immediate path resolves in this same call and
            has no later resolution step to gate. Defaults ``False`` so all existing
            callers are unaffected.

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
            use_base_form=use_base_form,
            position_params=position_params,
            preferred_resonance=preferred_resonance,
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
            use_base_form=use_base_form,
            position_params=position_params,
            originated_as_entrance=originated_as_entrance,
            preferred_resonance=preferred_resonance,
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
        use_base_form=use_base_form,
        position_params=position_params,
        preferred_resonance=preferred_resonance,
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
    originated_as_entrance: bool = False,
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
        originated_as_entrance=originated_as_entrance,
    )


def _route_hostile_cast(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona,
    technique: Technique,
    originated_as_entrance: bool = False,
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
            originated_as_entrance=originated_as_entrance,
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
            originated_as_entrance=originated_as_entrance,
        )
        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=initiator_persona.character_sheet,
            target_sheet=target_persona.character_sheet,
            technique=technique,
            scene=scene,
            room=scene.location,
            from_entrance=originated_as_entrance,
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
    originated_as_entrance: bool = False,
) -> CastResult:
    """Benign cast at another PC → PENDING request awaiting consent (resolved on accept).

    A declared pull is persisted (not charged) as a ``SceneActionPullDeclaration``
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
            originated_as_entrance=originated_as_entrance,
        )
        if cast_pull is not None:
            declaration = SceneActionPullDeclaration.objects.create(
                request=request,
                resonance=cast_pull.resonance,
                tier=cast_pull.tier,
            )
            declaration.threads.set(cast_pull.threads)
    return CastResult(request=request)


def _maybe_seat_caster_after_benign_cast(  # noqa: PLR0913 - cohesive seating params
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    technique: Technique,
    supplied_personas: list[Persona] | None,
    result: EnhancedSceneActionResult | None,
) -> bool:
    """Seat the caster in combat when a benign cast touched an embattled ally (#2226).

    Returns True if the caster was seated (newly or already). The cast must
    have succeeded (success_level > 0) and the technique must be non-hostile
    (hostile casts seed encounters via ``_route_hostile_cast``).

    Enumerates the target sheets by targeting mode:
    - SINGLE: the single ``target_persona``.
    - FILTERED_GROUP: the ``supplied_personas`` list.
    - AREA: ``resolve_targets`` (a pure query) to enumerate affected scene personas.
    """
    if result is None:
        return False
    main = result.action_resolution.main_result
    success_level = main.check_result.success_level if main is not None else 0
    if success_level <= 0:
        return False
    if is_technique_hostile(technique):
        return False

    caster_sheet = initiator_persona.character_sheet
    target_sheets: list[CharacterSheet] = []

    if supplied_personas is not None:
        target_sheets = [p.character_sheet for p in supplied_personas]
    elif target_persona is not None:
        target_sheets = [target_persona.character_sheet]
    else:
        # AREA cast: enumerate affected personas via the pure query.
        from actions.constants import ActionTargetType  # noqa: PLC0415

        if technique.target_type == ActionTargetType.AREA:
            resolved = resolve_targets(
                technique=technique,
                initiator_persona=initiator_persona,
                scene=scene,
                supplied_personas=[],
            )
            target_sheets = [p.character_sheet for p in resolved]

    if not target_sheets:
        return False

    participant = seat_caster_for_benign_intervention(
        caster_sheet=caster_sheet,
        target_sheets=target_sheets,
        scene=scene,
    )
    return participant is not None


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
    use_base_form: bool = False,
    position_params: dict[str, int] | None = None,
    preferred_resonance: Resonance | None = None,
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
            use_base_form=use_base_form,
            position_params=position_params,
            preferred_resonance=preferred_resonance,
        )

    return CastResult(
        request=request,
        result=result,
        outcome_interaction=pose,
        power_ledger=power_ledger,
        combat_seated=_maybe_seat_caster_after_benign_cast(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            technique=technique,
            supplied_personas=supplied_personas,
            result=result,
        ),
    )
