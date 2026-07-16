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

from flows.object_states.base_state import unwrap_objectdb

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


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

    raw_character = unwrap_objectdb(character)
    # field_instance may arrive as a BaseState, a RoomFeatureInstance, or a pk.
    raw_field = unwrap_objectdb(field_instance)

    bonus = _pool_difficulty_bonus(raw_field, raw_character)
    return {
        "pool_difficulty_bonus": bonus,
        "difficulty_name": "Normal",  # base; reactive flows can escalate
    }


hooks = {
    "food_collection_difficulty": flow_food_collection_difficulty,
}
