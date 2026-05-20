"""Flow-callable wrappers for the conditions service.

Thin wrappers that accept string-name lookups so FlowStepDefinition
parameters can reference conditions and check types by name rather than
by PK or model instance.  These are NOT production service functions —
they exist solely to bridge the flow parameter-resolution layer
(which resolves ``@variable`` references and passes raw strings through)
with production services that require model instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _unwrap_objectdb(obj: ObjectDB) -> ObjectDB:
    """Unwrap a BaseState wrapper to its underlying ObjectDB.

    The flow execution layer may pass a ``BaseState`` (e.g., ``CharacterState``)
    rather than a raw ``ObjectDB`` when the parameter is resolved via
    ``_resolve_service_param``.  ``BaseState`` exposes the raw object on its
    ``.obj`` attribute; raw ``ObjectDB`` instances have no such attribute.

    Args:
        obj: A raw ``ObjectDB`` or a ``BaseState`` wrapping one.

    Returns:
        The underlying ``ObjectDB``.
    """
    return getattr(obj, "obj", obj)  # noqa: GETATTR_LITERAL — BaseState.obj holds the raw ObjectDB


def flow_apply_condition(
    *,
    target: ObjectDB,
    condition_name: str,
) -> None:
    """Look up ConditionTemplate by name and apply it to target.

    Flow-callable wrapper.  Use instead of ``world.conditions.services.apply_condition``
    when the flow step parameter carries a string name rather than a model instance.
    Accepts ``target`` as either a raw ``ObjectDB`` or a ``BaseState`` wrapper.

    Args:
        target: The ObjectDB character to apply the condition to (or BaseState wrapping one).
        condition_name: The ConditionTemplate.name to look up and apply.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    raw_target = _unwrap_objectdb(target)
    condition = ConditionTemplate.objects.get(name=condition_name)
    apply_condition(target=raw_target, condition=condition)


def flow_perform_check(
    *,
    character: ObjectDB,
    check_type_name: str,
    target_difficulty: int = 0,
) -> str:
    """Look up CheckType by name, run perform_check, and return the outcome name.

    Flow-callable wrapper.  Use instead of ``world.checks.services.perform_check``
    when the flow step parameter carries a string name and the downstream
    EVALUATE_EQUALS step compares the result against an outcome name string.
    Accepts ``character`` as either a raw ``ObjectDB`` or a ``BaseState`` wrapper.

    Returns:
        The outcome name (e.g. ``"Success"``, ``"Critical Failure"``).
        Returns ``""`` when perform_check returns no outcome.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    raw_character = _unwrap_objectdb(character)
    check_type = CheckType.objects.get(name=check_type_name)
    result = perform_check(
        character=raw_character,
        check_type=check_type,
        target_difficulty=target_difficulty,
    )
    return result.outcome.name if result.outcome is not None else ""
