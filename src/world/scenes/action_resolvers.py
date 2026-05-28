"""Action-key resolver registry for SceneActionRequest.

Generic seam: each app that wants to add post-resolution side-effects to
SceneActionRequests registers a callable here.

A resolver runs after respond_to_action_request() resolves an accepted SceneActionRequest.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.types import EnhancedSceneActionResult

ResolverFn = Callable[["SceneActionRequest", "EnhancedSceneActionResult"], None]

_RESOLVER_REGISTRY: dict[str, ResolverFn] = {}


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
