"""Service functions for managing behavior packages."""

from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def register_behavior_package(
    obj: BaseState,
    package_id: int,
    hook: str,
    data: dict | None = None,
    **kwargs: object,
) -> None:
    """Attach a behavior package to an object.

    Args:
        obj: State of the target object.
        package_id: Primary key of the BehaviorPackageDefinition.
        hook: Hook name for package execution.
        data: Optional configuration dict.
        **kwargs: Additional keyword arguments.
    """
    target = obj.obj
    try:
        definition = BehaviorPackageDefinition.objects.get(pk=package_id)
    except BehaviorPackageDefinition.DoesNotExist as exc:
        msg = f"Unknown behavior package (pk={package_id})."
        raise RuntimeError(msg) from exc
    BehaviorPackageInstance.objects.create(
        definition=definition,
        obj=target,
        hook=hook,
        data=data or {},
    )


def remove_behavior_package(
    obj: BaseState,
    package_id: int,
    **kwargs: object,
) -> None:
    """Remove a behavior package from an object.

    Args:
        obj: State of the target object.
        package_id: Primary key of the BehaviorPackageDefinition to remove.
        **kwargs: Additional keyword arguments.
    """
    target = obj.obj
    BehaviorPackageInstance.objects.filter(definition_id=package_id, obj=target).delete()


hooks = {
    "register_behavior_package": register_behavior_package,
    "remove_behavior_package": remove_behavior_package,
}
