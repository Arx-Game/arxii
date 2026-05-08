"""Action-key resolver + menu-contributor registry for SceneActionRequest.

Generic seam: each app that wants to add post-resolution side-effects to
SceneActionRequests (or contribute menu entries to AvailableSceneAction lists)
registers callables here.

A resolver runs after respond_to_action_request() resolves an accepted SceneActionRequest.
A menu contributor returns AvailableSceneAction entries for a given character + scene context.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.action_availability import AvailableSceneAction
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Scene
    from world.scenes.types import EnhancedSceneActionResult

ResolverFn = Callable[["SceneActionRequest", "EnhancedSceneActionResult"], None]
MenuContributorFn = Callable[["ObjectDB", "Scene | None"], "list[AvailableSceneAction]"]

_RESOLVER_REGISTRY: dict[str, ResolverFn] = {}
_MENU_CONTRIBUTORS: list[MenuContributorFn] = []


def register_resolver(action_key: str, fn: ResolverFn) -> None:
    """Register a post-resolution side-effect for a given action_key.

    Args:
        action_key: The action key string that triggers this resolver.
        fn: Callable invoked with (action_request, result) after accept resolution.
    """
    _RESOLVER_REGISTRY[action_key] = fn


def get_resolver(action_key: str) -> ResolverFn | None:
    """Look up a registered resolver by action_key.

    Args:
        action_key: The action key to look up.

    Returns:
        The registered resolver, or None if none is registered.
    """
    return _RESOLVER_REGISTRY.get(action_key)


def register_menu_contributor(fn: MenuContributorFn) -> None:
    """Register a menu contributor that injects entries into get_available_scene_actions().

    Idempotent — registering the same callable twice has no effect.

    Args:
        fn: Callable invoked with (character, scene) that returns a list of
            AvailableSceneAction entries. ``scene`` may be None when there is
            no current scene context (e.g. the general /available endpoint).
    """
    if fn not in _MENU_CONTRIBUTORS:
        _MENU_CONTRIBUTORS.append(fn)


def get_menu_contributors() -> list[MenuContributorFn]:
    """Return a snapshot of all registered menu contributors.

    Returns:
        A list of registered contributor callables (copy, not the internal list).
    """
    return list(_MENU_CONTRIBUTORS)
