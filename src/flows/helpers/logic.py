import functools
import json
import operator
from typing import TYPE_CHECKING, Any, Callable, Dict, Union

if TYPE_CHECKING:
    from flows.flow_execution import FlowExecution

OP_FUNCS: Dict[str, Callable[..., Any]] = {
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


def resolve_modifier(
    flow_execution: "FlowExecution", mod_spec: Union[int, str, Dict[str, Any]]
) -> Callable[..., Any]:
    """Convert ``mod_spec`` into a callable modifier."""
    if isinstance(mod_spec, int):
        return functools.partial(operator.add, mod_spec)

    if isinstance(mod_spec, str):
        try:
            data = json.loads(mod_spec)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("Modifier must be a JSON object string or dict.") from exc
    elif isinstance(mod_spec, dict):
        data = mod_spec
    else:
        raise ValueError("Modifier must be a JSON object string or dict.")

    allowed_keys = {"name", "args", "kwargs"}
    if not isinstance(data, dict):
        raise ValueError("Modifier must be a dict.")
    if set(data.keys()) - allowed_keys:
        raise ValueError(
            f"Modifier contains unknown keys: {set(data.keys()) - allowed_keys}"
        )
    if "name" not in data or not isinstance(data["name"], str):
        raise ValueError("Modifier must have a 'name' key of type str.")
    if "args" in data and not isinstance(data["args"], list):
        raise ValueError("Modifier 'args' must be a list if present.")
    if "kwargs" in data and not isinstance(data["kwargs"], dict):
        raise ValueError("Modifier 'kwargs' must be a dict if present.")

    func_name = data["name"]
    if func_name not in OP_FUNCS:
        raise ValueError(f"Unknown modifier/operator: {func_name}")
    func = OP_FUNCS[func_name]

    args = data.get("args", [])
    kwargs = data.get("kwargs", {})
    resolved_args = [flow_execution.resolve_flow_reference(a) for a in args]
    resolved_kwargs = {
        k: flow_execution.resolve_flow_reference(v) for k, v in kwargs.items()
    }
    return functools.partial(func, *resolved_args, **resolved_kwargs)


def resolve_self_placeholders(
    conditions: Dict[str, object] | None, obj: object
) -> Dict[str, object]:
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
