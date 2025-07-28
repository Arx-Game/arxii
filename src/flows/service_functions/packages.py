"""Service functions for managing behavior packages."""

from typing import Any

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from flows.flow_execution import FlowExecution


def register_behavior_package(
    flow_execution: FlowExecution,
    obj: str,
    package_name: str,
    data: dict | None = None,
    **kwargs: Any,
) -> None:
    """Attach a behavior package to an object."""
    target = flow_execution.get_object(obj)
    if target is None:
        raise RuntimeError("Invalid target for package registration.")
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist as exc:
        raise RuntimeError("Unknown behavior package.") from exc
    BehaviorPackageInstance.objects.create(
        definition=definition,
        obj=target,
        data=data or {},
    )


def remove_behavior_package(
    flow_execution: FlowExecution,
    obj: str,
    package_name: str,
    **kwargs: Any,
) -> None:
    """Remove a behavior package from an object."""
    target = flow_execution.get_object(obj)
    if target is None:
        raise RuntimeError("Invalid target for package removal.")
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist:
        return
    BehaviorPackageInstance.objects.filter(definition=definition, obj=target).delete()
