"""Generic checks for verifying access requirements."""

from collections.abc import Iterable, Iterator

from behaviors.models import BehaviorPackageInstance
from commands.exceptions import CommandError
from flows.object_states.base_state import BaseState


def matching_value_refusal(
    pkg: BehaviorPackageInstance, actor_present: bool, values: Iterable[object]
) -> str | None:
    """Return the existing matching-value refusal without loading a state."""
    if not actor_present:
        return "No actor provided."
    attr = pkg.get_from_data("attribute")
    required = pkg.get_from_data("value")
    if attr is None or required is None:
        return "Lock is misconfigured."
    for value in values:
        if value == required:
            return None
    return pkg.get_from_data("error") or "Access denied."


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

    def values() -> Iterator[object]:
        attr = pkg.get_from_data("attribute")
        yield actor.get_attribute(attr)
        for item in actor.contents:
            yield item.get_attribute(attr)

    reason = matching_value_refusal(pkg, actor is not None, values())
    if reason is not None:
        raise CommandError(reason)
