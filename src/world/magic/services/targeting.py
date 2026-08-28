"""Technique targeting predicates.

Pure functions that derive targeting relationship and consent requirements from
authored Technique data. Used by validity enforcement, target resolution, and
cast routing downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from actions.constants import ActionTargetType
from flows.consts import FlowActionChoices
from flows.models.flows import FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.conditions.models import ConditionTemplate
from world.conditions.services import is_untargetable
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.magic.services.hostility import is_technique_hostile
from world.mechanics.services import prerequisites_met
from world.scenes.models import Persona, Scene

# protective_flavor() return values (#2207) — named constants rather than bare
# strings so callers (e.g. declare_interpose) compare against an identifier,
# not a string literal.
PROTECTIVE_FLAVOR_BARRIER = "barrier"
PROTECTIVE_FLAVOR_BLINK = "blink"
PROTECTIVE_FLAVOR_REDIRECT = "redirect"

# Reactive-trigger handler function name -> guardian-declaration flavor.
# Keyed on the trailing segment of the CALL_SERVICE_FUNCTION step's dotted
# `variable_name` (e.g. "world.magic.services.effect_handlers.absorb_pool"),
# mirroring the handler paths authored in `world/magic/effect_palette_content.py`.
_PROTECTIVE_FLAVOR_BY_HANDLER: dict[str, str] = {
    "absorb_pool": PROTECTIVE_FLAVOR_BARRIER,
    "blink_dodge": PROTECTIVE_FLAVOR_BLINK,
    "reflect_damage": PROTECTIVE_FLAVOR_REDIRECT,
}


class InvalidCastTarget(ValidationError):
    """Raised when a technique's target list violates cardinality or relationship rules."""


def _check_cardinality(
    technique: Technique,
    target_personas: list[Persona],
) -> None:
    """Enforce target_type (cardinality) constraints."""
    target_type = technique.target_type
    target_count = len(target_personas)

    if target_type == ActionTargetType.SELF and target_count > 1:
        msg = "This technique can only target zero or one character."
        raise InvalidCastTarget(msg)

    if target_type == ActionTargetType.SINGLE and target_count > 1:
        msg = f"This technique targets at most one character; {target_count} were provided."
        raise InvalidCastTarget(msg)


def _check_relationship(
    relationship: ConditionTargetKind,
    initiator_sheet_id: int,
    target_personas: list[Persona],
) -> None:
    """Enforce relationship (SELF/ENEMY/ALLY) constraints."""
    if relationship == ConditionTargetKind.SELF:
        for persona in target_personas:
            if persona.character_sheet_id != initiator_sheet_id:
                msg = "This technique's effect can only apply to the caster."
                raise InvalidCastTarget(msg)

    elif relationship == ConditionTargetKind.ENEMY:
        for persona in target_personas:
            if persona.character_sheet_id == initiator_sheet_id:
                msg = "A hostile technique cannot target the caster."
                raise InvalidCastTarget(msg)

    # ALLY: no restriction — self and others are both permitted.


def _target_meets_prerequisites(technique: Technique, caster_od, persona: Persona) -> bool:
    """True if persona's character satisfies every one of technique's target_prerequisites."""
    prereqs = technique.cached_target_prerequisites
    if not prereqs:
        return True
    target_od = persona.character_sheet.character
    return prerequisites_met(prereqs, caster_od, target_od)


def _check_target_prerequisites(
    technique: Technique,
    initiator_persona: Persona,
    target_personas: list[Persona],
) -> None:
    """Enforce target_prerequisites for explicit (SELF/SINGLE) targets — raises on failure.

    For target_type=SELF, the caster IS the target — but the real call site
    (world/scenes/cast_services.py) conventionally omits an explicit target for a SELF
    cast, so target_personas is []. Check initiator_persona directly against the
    prerequisites in that case rather than relying on target_personas being populated.

    AREA/FILTERED_GROUP get NO pre-flight check at all: the one production caller
    (`request_technique_cast`, world/scenes/cast_services.py) conventionally omits
    `target_persona` for an AoE cast, but nothing enforces that — a client could send
    `target_persona` alongside `supplied_personas` on a FILTERED_GROUP request, and
    that one arbitrary persona failing the prerequisite would otherwise hard-block a
    cast where other eligible personas legitimately pass. Defer entirely to
    `resolve_targets`'s existing silent per-persona filter. Mirrors combat's
    `_check_combat_target_prerequisites` (world/combat/services.py, #1793 second-pass
    fix).
    """
    if not technique.cached_target_prerequisites:
        return

    if technique.target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
        return

    caster_od = initiator_persona.character_sheet.character
    msg = "Target does not meet this technique's targeting requirement."

    if technique.target_type == ActionTargetType.SELF:
        if not _target_meets_prerequisites(technique, caster_od, initiator_persona):
            raise InvalidCastTarget(msg)

    for persona in target_personas:
        if not _target_meets_prerequisites(technique, caster_od, persona):
            raise InvalidCastTarget(msg)


def validate_cast_target(
    *,
    technique: Technique,
    initiator_persona: Persona,
    target_personas: list[Persona],
) -> None:
    """Validate that target_personas are legal for the given technique and initiator.

    Raises InvalidCastTarget with a descriptive message when a rule is violated.
    Returns None on success.

    Rules enforced:
    - target_type == SELF: target_personas must be empty or contain only the initiator.
    - target_type == SINGLE: at most one target.
    - relationship SELF: every target must be the initiator (same character_sheet_id).
    - relationship ENEMY: no target may be the initiator.
    - relationship ALLY: any target is allowed (self included).

    Note: reach/range (combat-positional) is NOT enforced here.
    """
    initiator_sheet_id = initiator_persona.character_sheet_id
    relationship = derive_target_relationship(technique)

    _check_cardinality(technique, target_personas)
    _check_relationship(relationship, initiator_sheet_id, target_personas)
    _check_target_prerequisites(technique, initiator_persona, target_personas)


def derive_target_relationship(technique: Technique) -> ConditionTargetKind:
    """Derive the targeting relationship encoded in a technique's authored data.

    Resolution order:
    1. ENEMY — if the technique is hostile (deals damage or applies ENEMY conditions).
    2. ALLY — if any condition_application has target_kind=ALLY.
    3. SELF — fallback (no hostile traits, no ALLY conditions).

    Exactly one relationship comes back, so a technique whose payload rows carry
    more than one distinct ``target_kind`` gets an answer that is a guess — see
    ``technique_relationship_is_ambiguous`` (``services/technique_effects.py``),
    which reports that case rather than guessing again here. This function gates
    live cast targeting; its answers are deliberately unchanged by #2898.

    Reads the technique's ``cached_*`` payload lists rather than its own
    ``.filter().exists()`` queries (#2898), sharing the one query per payload
    table that every other reader on the row already paid.
    """
    if is_technique_hostile(technique):
        return ConditionTargetKind.ENEMY
    if any(
        row.target_kind == ConditionTargetKind.ALLY
        for row in technique.cached_condition_applications
    ):
        return ConditionTargetKind.ALLY
    # Cleansing a condition off an ally (dispelling an ally's debuff) resolves ALLY (#1585).
    if any(
        row.target_kind == ConditionTargetKind.ALLY for row in technique.cached_removed_conditions
    ):
        return ConditionTargetKind.ALLY
    return ConditionTargetKind.SELF


def protective_condition_and_flavor(technique: Technique) -> tuple[ConditionTemplate, str] | None:
    """Classify *technique*'s protective handler AND resolve the matched ConditionTemplate (#2207).

    Guardian declarations (Interpose) need to know whether a technique carries a
    protective reactive-trigger handler and, if so, which family: an absorb-pool
    barrier, a blink-dodge escape, or a reflect-damage redirect. This is derived from
    the technique's existing authored data — `condition_applications ->
    condition.reactive_triggers -> flow_definition.steps` — the same machinery that
    installs Aegis Field / Mirror Ward / Phase Step (see
    `world/magic/effect_palette_content.py`); no new authored field is introduced.

    Traverses one batched query (select_related + nested Prefetch, no N+1 — the
    prefetch-string lint hook requires the Prefetch()+to_attr form, see
    `tools/lint_prefetch_string.py`): for each of the technique's applied conditions,
    walks that condition's reactive triggers, then each trigger's flow's
    CALL_SERVICE_FUNCTION steps, matching the step's `variable_name` (a dotted
    service-function path) against the known handler families.

    Returns the ``(ConditionTemplate, flavor)`` of the FIRST matching step
    encountered — authored techniques carry at most one protective handler in
    practice — or None when no applied condition's reactive triggers resolve to a
    known protective handler.

    Guardian resolution (``world.combat.services._try_technique_interpose``, #2207)
    needs the template itself — its ``reactive_anima_cost`` pays the guardian's
    reaction — not just the flavor string. :func:`protective_flavor` (declaration-time
    validation only needs the flavor) is a thin wrapper over this function so both
    call sites share one traversal.
    """
    applied_conditions = technique.condition_applications.select_related(
        "condition"
    ).prefetch_related(
        Prefetch(
            "condition__reactive_triggers",
            queryset=TriggerDefinition.objects.select_related("flow_definition").prefetch_related(
                Prefetch(
                    "flow_definition__steps",
                    queryset=FlowStepDefinition.objects.filter(
                        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
                    ),
                    to_attr="cached_call_service_steps",
                )
            ),
            to_attr="cached_reactive_triggers",
        )
    )

    for applied in applied_conditions:
        for trigger in applied.condition.cached_reactive_triggers:
            for step in trigger.flow_definition.cached_call_service_steps:
                function_name = step.variable_name.rsplit(".", 1)[-1]
                flavor = _PROTECTIVE_FLAVOR_BY_HANDLER.get(function_name)
                if flavor is not None:
                    return applied.condition, flavor
    return None


def protective_flavor(technique: Technique) -> str | None:
    """Classify *technique*'s reactive-trigger handler family for guardian declarations (#2207).

    Thin wrapper over :func:`protective_condition_and_flavor` — declaration-time
    validation (``declare_interpose``) only needs the flavor, not the resolved
    ``ConditionTemplate``.
    """
    resolved = protective_condition_and_flavor(technique)
    return resolved[1] if resolved is not None else None


#: ProtectiveMagnitude.mode values (#3279) — named constants, not bare strings, so
#: callers (e.g. technique_power_eval's mitigation valuator) compare against an
#: identifier.
PROTECTIVE_MAGNITUDE_MULTIPLY = "multiply"
PROTECTIVE_MAGNITUDE_FLAT = "flat"

#: The MODIFY_PAYLOAD step shape :func:`protective_magnitude` recognizes — the same
#: field/op vocabulary ``world.combat.defend_content.ensure_defend_content`` seeds
#: for the shipped Defend technique and
#: ``flows.models.flows.FlowStepDefinition._execute_modify_payload`` interprets.
_MODIFY_PAYLOAD_AMOUNT_FIELD = "amount"
_MODIFY_PAYLOAD_OP_MULTIPLY = "multiply"
_MODIFY_PAYLOAD_OP_ADD = "add"


@dataclass(frozen=True, slots=True)
class ProtectiveMagnitude:
    """A parsed damage-mitigation magnitude extracted from a protective condition (#3279).

    ``mode=PROTECTIVE_MAGNITUDE_MULTIPLY`` carries ``factor`` (e.g. Defend's 0.5
    halves incoming damage); ``mode=PROTECTIVE_MAGNITUDE_FLAT`` carries ``amount``
    (a flat per-hit reduction). Exactly one of ``factor``/``amount`` is populated
    per mode — the other stays ``None``.
    """

    mode: str
    factor: float | None = None
    amount: int | None = None


def _protective_magnitude_from_step(step: FlowStepDefinition) -> ProtectiveMagnitude | None:
    """Parse one MODIFY_PAYLOAD step into a ProtectiveMagnitude, or None if it doesn't match.

    Recognizes the shape ``world.combat.defend_content.ensure_defend_content`` seeds
    for the shipped Defend technique — ``{"field": "amount", "op": "multiply", "value":
    0.5}`` (or an ``"add"`` of a negative value for a flat reduction). Any other shape
    (wrong field, non-numeric value, unrecognized op) returns ``None``.
    """
    params = step.parameters or {}
    if params.get("field") != _MODIFY_PAYLOAD_AMOUNT_FIELD:
        return None
    op = params.get("op")
    value = params.get("value")
    if not isinstance(value, (int, float)):
        return None
    if op == _MODIFY_PAYLOAD_OP_MULTIPLY:
        return ProtectiveMagnitude(mode=PROTECTIVE_MAGNITUDE_MULTIPLY, factor=float(value))
    if op == _MODIFY_PAYLOAD_OP_ADD and value < 0:
        return ProtectiveMagnitude(mode=PROTECTIVE_MAGNITUDE_FLAT, amount=int(abs(value)))
    return None


def protective_magnitude(condition_template: ConditionTemplate) -> ProtectiveMagnitude | None:
    """Extract a parseable damage-mitigation magnitude from a protective condition (#3279).

    Sibling to :func:`protective_flavor` for the technique combat-power evaluator's
    mitigation valuator (``world.magic.services.technique_power_eval``): walks
    *condition_template*'s ``reactive_triggers -> flow_definition -> steps`` looking
    for a ``MODIFY_PAYLOAD`` step on the ``"amount"`` field — see
    :func:`_protective_magnitude_from_step` for the recognized shapes:

    - ``op == "multiply"`` -> ``ProtectiveMagnitude(mode="multiply", factor=value)``
      (percentage mitigation — Defend's 0.5 halves incoming damage).
    - ``op == "add"`` with a negative ``value`` -> ``ProtectiveMagnitude(mode="flat",
      amount=abs(value))`` (a flat per-hit reduction — ``modify_payload``'s op
      vocabulary has no literal "subtract", so a flat reduction is authored as an
      add of a negative amount, see ``flows.models.flows.FlowStepDefinition
      ._execute_modify_payload``).

    Returns the FIRST matching step across every trigger (authored protective
    conditions carry at most one in practice). Any other shape — a
    ``CALL_SERVICE_FUNCTION`` handler (the barrier/blink/reflect families
    :func:`protective_flavor` classifies), a ``MODIFY_PAYLOAD`` step on a
    different field, or an unrecognized op — returns ``None``: an authoring-gap
    bucket for the evaluator's UNPRICEABLE provenance, not an error.
    """
    triggers = condition_template.reactive_triggers.select_related(
        "flow_definition"
    ).prefetch_related(
        Prefetch(
            "flow_definition__steps",
            queryset=FlowStepDefinition.objects.filter(action=FlowActionChoices.MODIFY_PAYLOAD),
            to_attr="cached_modify_payload_steps",
        )
    )
    for trigger in triggers:
        for step in trigger.flow_definition.cached_modify_payload_steps:
            magnitude = _protective_magnitude_from_step(step)
            if magnitude is not None:
                return magnitude
    return None


#: Reactive-trigger handler families that consume a caster-declared position PAIR
#: (origin + destination), e.g. an obstacle placed between two points.
_PAIR_HANDLERS = ("create_obstacle_on_condition",)

#: Reactive-trigger handler families that consume a single caster-declared position
#: (a destination), e.g. teleport / force-move / zone-hazard placement.
_SINGLE_HANDLERS = (
    "move_position_on_condition",
    "force_move_target_on_condition",
    "create_zone_hazard_on_condition",
)

#: ``position_target_shape`` return values — module-level constants (not bare
#: string literals) so the shape vocabulary has one spelling.
POSITION_SHAPE_PAIR = "pair"
POSITION_SHAPE_SINGLE = "single"
POSITION_SHAPE_NONE = "none"


def position_target_shape(technique: Technique) -> str:
    """Classify which cast-position input (if any) the technique's effects consume.

    Walks the technique's applied conditions to their reactive triggers' flow steps,
    looking for a ``CALL_SERVICE_FUNCTION`` step whose dotted handler path names a
    known position-consuming effect handler:

    - ``POSITION_SHAPE_PAIR`` — an obstacle-family handler is present (origin + destination).
    - ``POSITION_SHAPE_SINGLE`` — a teleport/force-move/zone-hazard-family handler is present.
    - ``POSITION_SHAPE_NONE`` — no position-consuming handler found.
    """
    step_paths: list[str] = []
    applications = technique.condition_applications.select_related("condition").prefetch_related(
        Prefetch(
            "condition__reactive_triggers__flow_definition__steps",
            to_attr="prefetched_shape_steps",
        )
    )
    for applied in applications:
        for trigger in applied.condition.reactive_triggers.all():
            step_paths.extend(
                step.variable_name or "" for step in trigger.flow_definition.prefetched_shape_steps
            )
    joined = " ".join(step_paths)
    if any(handler in joined for handler in _PAIR_HANDLERS):
        return POSITION_SHAPE_PAIR
    if any(handler in joined for handler in _SINGLE_HANDLERS):
        return POSITION_SHAPE_SINGLE
    return POSITION_SHAPE_NONE


def _signature_alters_behavior(caster, technique: Technique) -> bool:
    """Return True if the caster's active signature bonus carries a behavior-altering condition.

    A character may *sign* a technique (#1582, ADR-0072) by attaching a
    ``SignatureMotifBonus`` to its TECHNIQUE-kind Thread. The bonus's
    ``condition_applications`` land on the resolved target at cast time exactly
    like the technique's own conditions — so a behavior-altering condition carried
    by the signature must gate consent just as one authored on the technique does
    (ADR-0024). ``caster`` is the casting game Character (not CharacterSheet).
    """
    from world.magic.services.signature import signature_bonus_for  # noqa: PLC0415

    bonus = signature_bonus_for(caster, technique)
    if bonus is None:
        return False
    return any(
        row.condition.category.alters_behavior for row in bonus.cached_condition_applications
    )


def technique_alters_behavior(technique: Technique, *, caster=None) -> bool:
    """Return True if any applied condition belongs to a behavior-altering category.

    Behavior-altering conditions (compulsion, charm, fear, etc.) require the
    target's consent before being applied to another PC.

    When ``caster`` is supplied (the casting game Character), the caster's active
    ``SignatureMotifBonus`` conditions are folded into the check — a benign
    technique signed with a behavior-altering bonus alters behavior just as if the
    technique itself carried that condition (#1582, ADR-0024/ADR-0072). A
    non-behavior-altering signature condition (e.g. Entangled) does not.
    """
    if technique.condition_applications.filter(condition__category__alters_behavior=True).exists():
        return True
    return caster is not None and _signature_alters_behavior(caster, technique)


def cast_requires_consent(technique: Technique, *, caster=None) -> bool:
    """Return True if casting this technique on another PC requires their consent.

    Hostile techniques are handled separately by routing; this predicate covers
    the behavior-alteration consent path only. Passing ``caster`` includes the
    caster's signed ``SignatureMotifBonus`` conditions in the decision (#1582).
    """
    return technique_alters_behavior(technique, caster=caster)


def _collect_scene_personas(scene: Scene) -> list[Persona]:
    """Return the deduplicated list of personas present in the scene.

    Mirrors SceneListSerializer._collect_personas but called from a service layer
    context where importing a serializer would introduce a circular dependency and
    would be architecturally inappropriate. The logic is simple enough (one query +
    in-Python dedup) that inlining it is cleaner than calling a serializer staticmethod.

    One query is issued (select_related the persona chain); filtering is then
    done in Python to avoid queries-in-loops.
    """
    interactions = list(
        scene.interactions.select_related(
            "persona__character_sheet",
        )
    )
    seen: dict[int, Persona] = {}
    for interaction in interactions:
        persona = interaction.persona
        if persona is None or persona.pk in seen:
            continue
        seen[persona.pk] = persona
    return list(seen.values())


def _eligible_area_personas(
    *,
    relationship: ConditionTargetKind,
    initiator_persona: Persona,
    scene_personas: list[Persona],
) -> list[Persona]:
    """Return the set of scene personas eligible for an AREA or FILTERED_GROUP cast.

    - SELF relationship → only the initiator (unconditionally).
    - ENEMY or ALLY relationship → all scene personas except the initiator.
    """
    if relationship == ConditionTargetKind.SELF:
        # Self-targeting AoE affects only the caster, even if they have no
        # Interaction in the scene yet.
        return [initiator_persona]
    # ALLY and ENEMY both expand to all OTHER personas in the scene.
    return [
        p for p in scene_personas if p.character_sheet_id != initiator_persona.character_sheet_id
    ]


def resolve_targets(
    *,
    technique: Technique,
    initiator_persona: Persona,
    scene: Scene,
    supplied_personas: list[Persona],
) -> list[Persona]:
    """Expand a technique's target_type into a concrete list of Persona targets.

    Resolution rules:
    - SELF       → [initiator_persona]
    - SINGLE     → supplied_personas[:1]  (cardinality validated upstream)
    - AREA       → all scene personas matching the technique's derived relationship
                   (SELF→only caster; ALLY/ENEMY→all others in the scene)
    - FILTERED_GROUP → supplied_personas intersected with the AREA-eligible set

    One query is issued to enumerate scene personas (via _collect_scene_personas);
    all subsequent filtering is done in Python.
    """
    target_type = technique.target_type

    if target_type == ActionTargetType.SELF:
        return [initiator_persona]

    if target_type == ActionTargetType.SINGLE:
        return supplied_personas[:1]

    # AREA and FILTERED_GROUP both need the scene's eligible set.
    relationship = derive_target_relationship(technique)
    scene_personas = _collect_scene_personas(scene)
    eligible = _eligible_area_personas(
        relationship=relationship,
        initiator_persona=initiator_persona,
        scene_personas=scene_personas,
    )
    # Exclude intangible targets — they are untargetable regardless of technique type.
    eligible = [p for p in eligible if not is_untargetable(p.character_sheet.character)]
    if technique.cached_target_prerequisites:
        caster_od = initiator_persona.character_sheet.character
        eligible = [p for p in eligible if _target_meets_prerequisites(technique, caster_od, p)]

    if target_type == ActionTargetType.AREA:
        return eligible

    # FILTERED_GROUP: supplied_personas ∩ eligible (preserve supply order, filter by pk set).
    eligible_ids = {p.pk for p in eligible}
    return [p for p in supplied_personas if p.pk in eligible_ids]
