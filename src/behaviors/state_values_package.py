"""Service helpers for setting state values from package data."""

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def initialize_state(state: BaseState, pkg: BehaviorPackageInstance) -> None:
    """Apply values from ``pkg.data`` to ``state``.

    The package's ``data`` should contain a mapping named ``values``. Each key
    in that mapping is assigned to the corresponding attribute on ``state``. If
    ``values`` is omitted, all top-level keys of ``pkg.data`` are applied
    directly.

    Example:
        ````python
        key_def = BehaviorPackageDefinition.objects.create(
            name="key",
            service_function_path="behaviors.state_values_package.initialize_state",
        )
        BehaviorPackageInstance.objects.create(
            definition=key_def,
            obj=key_obj,
            hook="initialize_state",
            data={"values": {"key_id": "silver"}},
        )
        ````
    """

    values = pkg.get_from_data("values")
    if values is None:
        values = pkg.data or {}
    for attr, value in values.items():
        state.set_attribute(attr, value)
