"""Generic checks for verifying access requirements."""

from behaviors.models import BehaviorPackageInstance
from commands.exceptions import CommandError
from flows.object_states.base_state import BaseState


def require_matching_value(
    state: BaseState,
    pkg: BehaviorPackageInstance,
    actor: BaseState | None,
) -> None:
    """Require a matching attribute on ``actor`` or its inventory.

    The package ``data`` should define:
        ``attribute``: Name of the attribute to look up on states.
        ``value``: Required value for that attribute.
        ``error``: Optional message to raise when the check fails.

    Example:
        ````python
        lock_def = BehaviorPackageDefinition.objects.create(
            name="locked_exit",
            service_function_path="behaviors.matching_value_package.require_matching_value",
        )
        BehaviorPackageInstance.objects.create(
            definition=lock_def,
            obj=exit_obj,
            hook="can_traverse",
            data={"attribute": "key_id", "value": "silver"},
        )
        ````
    """

    if actor is None:
        msg = "No actor provided."
        raise CommandError(msg)

    attr = pkg.data.get("attribute")
    required = pkg.data.get("value")
    if attr is None or required is None:
        msg = "Lock is misconfigured."
        raise CommandError(msg)

    # Check the actor and any carried objects for the required value.
    if actor.get_attribute(attr) == required:
        return
    for item in actor.contents:
        if item.get_attribute(attr) == required:
            return

    raise CommandError(pkg.data.get("error", "Access denied."))
