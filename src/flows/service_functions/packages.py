"""Service functions for managing behavior packages."""

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def register_behavior_package(
    obj: BaseState,
    package_name: str,
    hook: str,
    data: dict | None = None,
    **kwargs: object,
) -> None:
    """Attach a behavior package to an object.

    Args:
        obj: State of the target object.
        package_name: Name of the behavior package.
        hook: Hook name for package execution.
        data: Optional configuration dict.
        **kwargs: Additional keyword arguments.
    """
    target = obj.obj
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
    obj: BaseState,
    package_name: str,
    **kwargs: object,
) -> None:
    """Remove a behavior package from an object.

    Args:
        obj: State of the target object.
        package_name: Package to remove.
        **kwargs: Additional keyword arguments.
    """
    target = obj.obj
    try:
        definition = BehaviorPackageDefinition.objects.get(name=package_name)
    except BehaviorPackageDefinition.DoesNotExist:
        return
    BehaviorPackageInstance.objects.filter(definition=definition, obj=target).delete()


hooks = {
    "register_behavior_package": register_behavior_package,
    "remove_behavior_package": remove_behavior_package,
}
