"""Handler for ModifyKwargsConfig effects."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from actions.constants import TransformType

if TYPE_CHECKING:
    from actions.models import ModifyKwargsConfig
    from actions.types import ActionContext

KWARG_TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    TransformType.UPPERCASE: lambda v: v.upper() if isinstance(v, str) else v,
    TransformType.LOWERCASE: lambda v: v.lower() if isinstance(v, str) else v,
}


def handle_modify_kwargs(context: ActionContext, config: ModifyKwargsConfig) -> None:
    """Apply a named transform to a kwarg value."""
    transform = KWARG_TRANSFORMS.get(config.transform)
    if transform and config.kwarg_name in context.kwargs:
        context.kwargs[config.kwarg_name] = transform(context.kwargs[config.kwarg_name])
