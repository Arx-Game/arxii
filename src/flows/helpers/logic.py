import functools
import json
import operator
from typing import TYPE_CHECKING, Any, cast
from collections.abc import Callable

if TYPE_CHECKING:
    from flows.flow_execution import FlowExecution

OP_FUNCS: dict[str, Callable[..., Any]] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "truediv": operator.truediv,
    "floordiv": operator.floordiv,
    "mod": operator.mod,
    "pow": operator.pow,
    "neg": operator.neg,
    "pos": operator.pos,
    "abs": operator.abs,
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}


def _coerce_modifier_data(mod_spec: object) -> dict[str, Any]:
    """Coerce a modifier spec into a dictionary."""

    if isinstance(mod_spec, dict):
        return cast(dict[str, Any], {str(key): value for key, value in mod_spec.items()})
    if isinstance(mod_spec, str):
        try:
            data = json.loads(mod_spec)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            msg = "Modifier must be a JSON object string or dict."
            raise ValueError(msg) from exc
        if not isinstance(data, dict):
            msg = "Modifier JSON must decode to a dict."
            raise ValueError(msg)
        return data
    msg = "Modifier must be a JSON object string or dict."
    raise ValueError(msg)


def _validate_modifier_data(data: dict[str, Any]) -> None:
    allowed_keys = {"name", "args", "kwargs"}
    if set(data.keys()) - allowed_keys:
        msg = f"Modifier contains unknown keys: {set(data.keys()) - allowed_keys}"
        raise ValueError(msg)
    if "name" not in data or not isinstance(data["name"], str):
        msg = "Modifier must have a 'name' key of type str."
        raise ValueError(msg)
    if "args" in data and not isinstance(data["args"], list):
        msg = "Modifier 'args' must be a list if present."
        raise ValueError(msg)
    if "kwargs" in data and not isinstance(data["kwargs"], dict):
        msg = "Modifier 'kwargs' must be a dict if present."
        raise ValueError(msg)


def resolve_modifier(
    flow_execution: "FlowExecution",
    mod_spec: int | str | dict[str, Any],
) -> Callable[..., Any]:
    """Convert ``mod_spec`` into a callable modifier."""
    if isinstance(mod_spec, int):
        return functools.partial(operator.add, mod_spec)

    data = _coerce_modifier_data(mod_spec)
    _validate_modifier_data(data)

    func_name = data["name"]
    if func_name not in OP_FUNCS:
        msg = f"Unknown modifier/operator: {func_name}"
        raise ValueError(msg)

    func = OP_FUNCS[func_name]
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})
    resolved_args = [flow_execution.resolve_flow_reference(a) for a in args]
    resolved_kwargs = {k: flow_execution.resolve_flow_reference(v) for k, v in kwargs.items()}
    return functools.partial(func, *resolved_args, **resolved_kwargs)


def resolve_self_placeholders(
    conditions: dict[str, object] | None,
    obj: object,
) -> dict[str, object]:
    """Replace ``@self`` placeholders in ``conditions`` with ``obj``."""
    if not conditions:
        return {}
    resolved = {}
    for key, value in conditions.items():
        if value == "@self":
            resolved[key] = obj
        elif value == "@self.pk":
            resolved[key] = getattr(obj, "pk", obj)
        else:
            resolved[key] = value
    return resolved
