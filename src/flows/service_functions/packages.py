"""Service functions for managing behavior packages."""

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from commands.types import Kwargs
from flows.flow_execution import FlowExecution


def register_behavior_package(
    flow_execution: FlowExecution,
    obj: str,
    package_name: str,
    hook: str,
    data: dict | None = None,
    **kwargs: Kwargs,
) -> None:
    """Attach a behavior package to an object."""
    state = flow_execution.get_object_state(obj)
    if state is None:
        msg = "Invalid target for package registration."
        raise RuntimeError(msg)
    target = state.obj
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist as exc:
        msg = "Unknown behavior package."
        raise RuntimeError(msg) from exc
    BehaviorPackageInstance.objects.create(
        definition=definition,
        obj=target,
        hook=hook,
        data=data or {},
    )


def remove_behavior_package(
    flow_execution: FlowExecution,
    obj: str,
    package_name: str,
    **kwargs: Kwargs,
) -> None:
    """Remove a behavior package from an object."""
    state = flow_execution.get_object_state(obj)
    if state is None:
        msg = "Invalid target for package removal."
        raise RuntimeError(msg)
    target = state.obj
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist:
        return
    BehaviorPackageInstance.objects.filter(definition=definition, obj=target).delete()


hooks = {
    "register_behavior_package": register_behavior_package,
    "remove_behavior_package": remove_behavior_package,
}
