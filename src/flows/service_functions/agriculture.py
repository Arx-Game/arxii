"""Flow-callable service functions for the agriculture system (#2218).

Thin wrappers that accept string-name lookups so FlowStepDefinition
parameters can reference agriculture concepts by name.  These exist to
bridge the flow parameter-resolution layer (which resolves ``@variable``
references and passes raw values through) with production services.

Registered in ``flows.service_functions.__init__.SERVICE_MODULES`` so the
``hooks`` dict below is auto-discovered by the service function registry.
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
    return getattr(obj, "obj", obj)  # noqa: GETATTR_LITERAL


def flow_food_collection_difficulty(
    *,
    character: ObjectDB,
    field_instance: ObjectDB,
) -> dict[str, int | str]:
    """Compute the pool-size difficulty bonus for a food collection attempt.

    Flow-callable wrapper around the pool-difficulty calculation in
    ``world.agriculture.services.collection``.  Returns a dict with:

    - ``pool_difficulty_bonus``: the computed bonus (capped).
    - ``difficulty_name``: the ``DifficultyChoice`` label for the
      effective difficulty, suitable for display or further flow logic.

    Args:
        character: The collecting character (ObjectDB or BaseState).
        field_instance: The Field RoomFeatureInstance (or its pk).

    Returns:
        Dict with ``pool_difficulty_bonus`` (int) and ``difficulty_name`` (str).
    """
    from world.agriculture.services.collection import (  # noqa: PLC0415
        _pool_difficulty_bonus,
    )

    raw_character = _unwrap_objectdb(character)
    # field_instance may arrive as a BaseState, a RoomFeatureInstance, or a pk.
    raw_field = getattr(field_instance, "obj", field_instance)  # noqa: GETATTR_LITERAL

    bonus = _pool_difficulty_bonus(raw_field, raw_character)
    return {
        "pool_difficulty_bonus": bonus,
        "difficulty_name": "Normal",  # base; reactive flows can escalate
    }


hooks = {
    "food_collection_difficulty": flow_food_collection_difficulty,
}
