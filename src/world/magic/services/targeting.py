"""Technique targeting predicates.

Pure functions that derive targeting relationship and consent requirements from
authored Technique data. Used by validity enforcement, target resolution, and
cast routing downstream.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from actions.constants import ActionTargetType
from world.conditions.services import is_untargetable
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.magic.services.hostility import is_technique_hostile
from world.scenes.models import Persona, Scene


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


def derive_target_relationship(technique: Technique) -> ConditionTargetKind:
    """Derive the targeting relationship encoded in a technique's authored data.

    Resolution order:
    1. ENEMY — if the technique is hostile (deals damage or applies ENEMY conditions).
    2. ALLY — if any condition_application has target_kind=ALLY.
    3. SELF — fallback (no hostile traits, no ALLY conditions).
    """
    if is_technique_hostile(technique):
        return ConditionTargetKind.ENEMY
    if technique.condition_applications.filter(target_kind=ConditionTargetKind.ALLY).exists():
        return ConditionTargetKind.ALLY
    # Cleansing a condition off an ally (dispelling an ally's debuff) resolves ALLY (#1585).
    if technique.removed_conditions.filter(target_kind=ConditionTargetKind.ALLY).exists():
        return ConditionTargetKind.ALLY
    return ConditionTargetKind.SELF


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

    if target_type == ActionTargetType.AREA:
        return eligible

    # FILTERED_GROUP: supplied_personas ∩ eligible (preserve supply order, filter by pk set).
    eligible_ids = {p.pk for p in eligible}
    return [p for p in supplied_personas if p.pk in eligible_ids]
