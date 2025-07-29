"""Service functions for managing behavior packages."""

from typing import Any

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from flows.flow_execution import FlowExecution


def register_behavior_package(
    flow_execution: FlowExecution,
    obj: str,
    package_name: str,
    hook: str,
    data: dict | None = None,
    **kwargs: Any,
) -> None:
    """Attach a behavior package to an object."""
    state = flow_execution.get_object_state(obj)
    if state is None:
        raise RuntimeError("Invalid target for package registration.")
    target = state.obj
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist as exc:
        raise RuntimeError("Unknown behavior package.") from exc
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
    **kwargs: Any,
) -> None:
    """Remove a behavior package from an object."""
    state = flow_execution.get_object_state(obj)
    if state is None:
        raise RuntimeError("Invalid target for package removal.")
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
