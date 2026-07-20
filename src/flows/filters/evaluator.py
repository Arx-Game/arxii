"""Filter DSL evaluator.

Supports:
- {"path": <dotted>, "op": <op>, "value": <value>}
- {"and": [<filter>, ...]}
- {"or": [<filter>, ...]}
- {"not": <filter>}

`value` may be "self" (the handler owner) or "self.<dotted>" to walk
attributes of the handler owner.
"""

from typing import Any

from flows.filters.errors import FilterPathError

SENTINEL = object()

# Filter DSL operators
OP_AND = "and"
OP_OR = "or"
OP_NOT = "not"
OP_PATH = "path"
OP_OP = "op"
OP_VALUE = "value"
OP_EQ = "=="
OP_NE = "!="
OP_LT = "<"
OP_LE = "<="
OP_GT = ">"
OP_GE = ">="
OP_IN = "in"
OP_CONTAINS = "contains"
OP_HAS_PROPERTY = "has_property"
OP_HAS_CAPABILITY = "has_capability"
OP_SHARES_COVENANT = "shares_covenant"
OP_HAS_RESONANCE_AT_LEAST = "has_resonance_at_least"
OP_HAS_PUBLIC_DISTINCTION = "has_public_distinction"
OP_FAME_TIER_AT_LEAST = "fame_tier_at_least"
OP_HAS_LEGEND_DEEDS = "has_legend_deeds"

# Filter DSL self-reference token and dotted prefix
SELF_TOKEN = "self"  # noqa: S105
SELF_PREFIX = "self."


def evaluate_filter(
    filter_spec: dict | None,
    payload: Any,
    *,
    self_ref: Any,
) -> bool:
    """Evaluate ``filter_spec`` against ``payload``.

    Empty or None filter_spec always matches.
    Raises FilterPathError on unresolved paths.
    """
    if not filter_spec:
        return True
    if OP_AND in filter_spec:
        return all(evaluate_filter(f, payload, self_ref=self_ref) for f in filter_spec[OP_AND])
    if OP_OR in filter_spec:
        return any(evaluate_filter(f, payload, self_ref=self_ref) for f in filter_spec[OP_OR])
    if OP_NOT in filter_spec:
        return not evaluate_filter(filter_spec[OP_NOT], payload, self_ref=self_ref)
    return _eval_leaf(filter_spec, payload, self_ref=self_ref)


def _eval_leaf(spec: dict, payload: Any, *, self_ref: Any) -> bool:
    path = spec[OP_PATH]
    op = spec[OP_OP]
    raw_value = spec[OP_VALUE]
    resolved = _resolve_path(path, payload, self_ref=self_ref)
    value = _resolve_value(raw_value, self_ref=self_ref)

    return _apply_operator(op, resolved, value, path)


# Method-dispatched operators: op -> the method name to call on `resolved`.
# Each of these delegates entirely to a Character (or similar) method rather than
# comparing values directly — the reactive-filter DSL's escape hatch for logic too
# rich for a plain comparison operator.
METHOD_OPERATORS: dict[str, str] = {
    OP_HAS_PROPERTY: "has_property",
    OP_HAS_CAPABILITY: "has_capability",
    OP_SHARES_COVENANT: "shares_covenant_with",
    OP_HAS_RESONANCE_AT_LEAST: "has_resonance_at_least",
    OP_HAS_PUBLIC_DISTINCTION: "has_public_distinction",
    OP_FAME_TIER_AT_LEAST: "fame_tier_at_least",
    OP_HAS_LEGEND_DEEDS: "has_legend_deeds",
}


def _apply_operator(op: str, resolved: Any, value: Any, path: str) -> bool:
    """Apply comparison operator using dispatch table."""
    operators: dict[str, Any] = {
        OP_EQ: lambda r, v: r == v,
        OP_NE: lambda r, v: r != v,
        OP_LT: lambda r, v: r < v,
        OP_LE: lambda r, v: r <= v,
        OP_GT: lambda r, v: r > v,
        OP_GE: lambda r, v: r >= v,
        OP_IN: lambda r, v: r in v,
        OP_CONTAINS: lambda r, v: v in r,
    }
    if op in operators:
        return operators[op](resolved, value)
    if op in METHOD_OPERATORS:
        method_name = METHOD_OPERATORS[op]
        if not hasattr(resolved, method_name):
            msg = f"Value at '{path}' has no {method_name} method"
            raise FilterPathError(msg)
        return bool(getattr(resolved, method_name)(value))
    msg = f"Unknown operator: {op}"
    raise FilterPathError(msg)


def _resolve_path(path: str, payload: Any, *, self_ref: Any) -> Any:
    if path.startswith(SELF_PREFIX):
        return _walk_dotted(self_ref, path[len(SELF_PREFIX) :])
    return _walk_dotted(payload, path)


def _resolve_value(raw: Any, *, self_ref: Any) -> Any:
    if isinstance(raw, str):
        if raw == SELF_TOKEN:
            return self_ref
        if raw.startswith(SELF_PREFIX):
            return _walk_dotted(self_ref, raw[len(SELF_PREFIX) :])
    return raw


def _walk_dotted(obj: Any, dotted: str) -> Any:
    current = obj
    for part in dotted.split("."):
        if current is None:
            # None propagates (optional-chaining semantics): None.anything → None.
            # The subsequent comparison (e.g. None == "Celestial") evaluates False.
            return None
        # Suppression justified: dynamic DSL path segment; SENTINEL default raises loudly.
        result = getattr(current, part, SENTINEL)  # noqa: GETATTR_LITERAL
        if result is SENTINEL:
            msg = f"Cannot resolve '{part}' on {type(current).__name__} (full path: {dotted})"
            raise FilterPathError(msg)
        current = result
    return current
