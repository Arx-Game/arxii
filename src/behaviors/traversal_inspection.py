"""Inspect explicitly supported existing traversal inputs without running hooks."""

from __future__ import annotations

from collections.abc import Iterator
from inspect import getattr_static
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn, cast

from behaviors.instance_entrance_package import run_admits
from behaviors.matching_value_package import matching_value_refusal
from behaviors.models import BehaviorPackageInstance
from behaviors.state_values_package import state_values
from commands.exceptions import CommandError
from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import builtin_traversal_allowed
from flows.service_functions.movement import check_exit_traversal_after_permission

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from flows.scene_data_manager import SceneDataManager

INSPECTION_UNAVAILABLE = "This exit's requirements cannot be checked from this menu."
MATCHING_PATH = "behaviors.matching_value_package.require_matching_value"
INSTANCE_PATH = "behaviors.instance_entrance_package.restrict_to_run"
VALUES_PATH = "behaviors.state_values_package.initialize_state"
# Exact implementation metadata, not authored gameplay choices or dynamic plugins.
SUPPORTED_TRAVERSAL = MappingProxyType(
    {
        ("can_traverse", MATCHING_PATH): "matching_value",
        ("can_traverse", INSTANCE_PATH): "instance_admission",
    }
)
SUPPORTED_INITIALIZERS = frozenset({("initialize_state", VALUES_PATH)})
_INITIALIZE_HOOK = "initialize_state"
_TRAVERSE_HOOK = "can_traverse"
_MATCHING_KIND = "matching_value"
_MISSING = object()
_MAX_VALUE_DEPTH = 64
_TRAVERSAL_REFUSAL = "You cannot go that way."
_BASE_DEFAULTS = {
    "fake_name": None,
    "real_name_viewers": set(),
    "name_prefix": "",
    "name_suffix": "",
    "name_prefix_map": {},
    "name_suffix_map": {},
}


def _unavailable() -> NoReturn:
    raise CommandError(INSPECTION_UNAVAILABLE)


def _packages(obj: ObjectDB) -> list[BehaviorPackageInstance]:
    # Match loader queryset order: do not add a new priority convention.
    return list(BehaviorPackageInstance.objects.select_related("definition").filter(obj=obj))


def _plain_value(value: object, ancestors: tuple[int, ...] = ()) -> object:
    if value is None or type(value) in (str, bool, int, float):
        return value
    if id(value) in ancestors or len(ancestors) >= _MAX_VALUE_DEPTH:
        _unavailable()
    ancestors = (*ancestors, id(value))
    if type(value) is list:
        return [_plain_value(part, ancestors) for part in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _plain_value(part, ancestors) for key, part in value.items()}
    _unavailable()


def _attribute(obj: ObjectDB, attr: object, scene_data: SceneDataManager | None) -> object:
    if not isinstance(attr, str) or attr in {
        "obj",
        "context",
        "packages",
        "_resolved_persona",
        "thumbnail_url",
    }:
        _unavailable()
    attr = cast("str", attr)
    packages = _packages(obj)
    if any(
        pkg.hook == _INITIALIZE_HOOK
        and (pkg.hook, pkg.definition.service_function_path) not in SUPPORTED_INITIALIZERS
        for pkg in packages
    ):
        _unavailable()
    state = None if scene_data is None else scene_data.states.get(obj.pk)
    if state is not None:
        attributes = object.__getattribute__(state, "__dict__")
        if attr in attributes:
            return _plain_value(attributes[attr])
        if getattr_static(type(state), attr, _MISSING) is not _MISSING:
            _unavailable()
        return None
    if getattr_static(BaseState, attr, _MISSING) is not _MISSING:
        _unavailable()
    values = dict(_BASE_DEFAULTS)
    for pkg in packages:
        if pkg.hook == _INITIALIZE_HOOK:
            values.update(
                {name: value for name, value in state_values(pkg).items() if isinstance(name, str)}
            )
    return _plain_value(values.get(attr))


def inspect_exit_traversal(
    actor: ObjectDB | None, exit_obj: ObjectDB, *, scene_data: SceneDataManager | None = None
) -> None:
    """Check bounded traversal inputs without constructing or initializing states.

    Args:
        actor: Actual character ObjectDB, not a client-supplied state wrapper.
        exit_obj: Already viewer-scoped actual exit ObjectDB.
        scene_data: An explicitly owned existing manager, or None for cold input.

    Raises:
        CommandError: Existing refusal or safe unsupported-inspection reason.
    """
    if not builtin_traversal_allowed(exit_obj, actor):
        raise CommandError(_TRAVERSAL_REFUSAL)
    traversal_packages = (pkg for pkg in _packages(exit_obj) if pkg.hook == _TRAVERSE_HOOK)
    for pkg in traversal_packages:
        kind = SUPPORTED_TRAVERSAL.get((pkg.hook, pkg.definition.service_function_path))
        if kind is None:
            _unavailable()
        if kind == _MATCHING_KIND:

            def values(pkg: BehaviorPackageInstance = pkg) -> Iterator[object]:
                attr = pkg.get_from_data("attribute")
                yield _attribute(cast("ObjectDB", actor), attr, scene_data)
                for item in actor.contents:
                    yield _attribute(item, attr, scene_data)

            reason = matching_value_refusal(pkg, actor is not None, values())
            if reason is not None:
                raise CommandError(reason)
            # Matching-value execution returns None, so keep walking packages.
        else:
            if not run_admits(exit_obj.destination, actor):
                raise CommandError(_TRAVERSAL_REFUSAL)
            break
    if actor is None:
        raise CommandError(_TRAVERSAL_REFUSAL)
    check_exit_traversal_after_permission(actor, exit_obj, read_only=True)
