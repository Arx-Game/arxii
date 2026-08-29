"""Catalog-driven validation for an authored (unsaved) flow step tree.

Consumed by the flows authoring API's step serializer (``validate_steps``) so
an author can never save a step tree the runtime would choke on. Pure Django
(no DRF import) so other callers can validate directly too.
"""

from collections.abc import Callable

from django.core.exceptions import ValidationError

from flows.catalog import STEP_ACTION_SPECS, ParamSpec, StepActionSpec

_TYPE_CHECKS: dict[str, Callable[[object], bool]] = {
    "str": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "dict": lambda v: isinstance(v, dict),
    "json": lambda _v: True,
}


def validate_step_tree(steps: list[dict]) -> None:
    """Validate an authored step tree against ``STEP_ACTION_SPECS``.

    ``steps`` items: ``{"client_id", "parent_client_id", "action",
    "variable_name", "parameters"}``. Raises ``ValidationError`` naming the
    offending ``client_id`` on the first violation found. An empty list is a
    valid (zero-step draft) tree.
    """
    if not steps:
        return
    by_id = _check_ids(steps)
    _check_tree_shape(steps, by_id)
    for step in steps:
        spec = STEP_ACTION_SPECS.get(step["action"])
        if spec is None:
            msg = f"Step '{step['client_id']}': unknown action '{step['action']}'."
            raise ValidationError(msg)
        _check_step_against_spec(step, spec)


def _check_ids(steps: list[dict]) -> dict[str, dict]:
    """Rule 1: unique, non-empty ``client_id`` values. Returns the id->step map."""
    by_id: dict[str, dict] = {}
    for step in steps:
        client_id = step.get("client_id") or ""
        if not client_id:
            msg = "A step has a blank client_id."
            raise ValidationError(msg)
        if client_id in by_id:
            msg = f"Step '{client_id}': duplicate client_id."
            raise ValidationError(msg)
        by_id[client_id] = step
    return by_id


def _check_tree_shape(steps: list[dict], by_id: dict[str, dict]) -> None:
    """Rules 2-3: valid parent references, exactly one root, no cycles."""
    root_count = 0
    for step in steps:
        parent_id = step["parent_client_id"]
        if parent_id is None:
            root_count += 1
        elif parent_id not in by_id:
            msg = f"Step '{step['client_id']}': parent_client_id '{parent_id}' not found."
            raise ValidationError(msg)
    if root_count != 1:
        msg = f"Step tree must have exactly one root; found {root_count}."
        raise ValidationError(msg)
    for step in steps:
        visited = {step["client_id"]}
        node = step
        while node["parent_client_id"] is not None:
            parent_id = node["parent_client_id"]
            if parent_id in visited:
                msg = f"Step '{step['client_id']}': cycle detected via parent chain."
                raise ValidationError(msg)
            visited.add(parent_id)
            node = by_id[parent_id]


def _check_step_against_spec(step: dict, spec: StepActionSpec) -> None:
    """Rules 5-9: variable_name, required/typed/choice-restricted parameters."""
    client_id = step["client_id"]
    if spec.variable_name_required and not (step.get("variable_name") or "").strip():
        msg = f"Step '{client_id}': variable_name is required for action '{spec.action}'."
        raise ValidationError(msg)
    parameters = step.get("parameters") or {}
    declared = {param.name: param for param in spec.params}
    for name, param_spec in declared.items():
        if param_spec.required and name not in parameters:
            msg = f"Step '{client_id}': missing required parameter '{name}'."
            raise ValidationError(msg)
    for name, value in parameters.items():
        param_spec = declared.get(name)
        if param_spec is None:
            if spec.allows_extra_params:
                continue
            msg = f"Step '{client_id}': unknown parameter '{name}'."
            raise ValidationError(msg)
        _check_param_value(client_id, param_spec, value)


def _check_param_value(client_id: str, param_spec: ParamSpec, value: object) -> None:
    """Rules 7-8: type check (with '@reference' exemption) and choice restriction."""
    is_reference = param_spec.accepts_reference and isinstance(value, str) and value.startswith("@")
    if not is_reference:
        checker = _TYPE_CHECKS.get(param_spec.type, lambda _v: True)
        if not checker(value):
            msg = (
                f"Step '{client_id}': parameter '{param_spec.name}' is not a valid "
                f"'{param_spec.type}' value."
            )
            raise ValidationError(msg)
    if param_spec.choices and value not in param_spec.choices:
        msg = (
            f"Step '{client_id}': parameter '{param_spec.name}' must be one of "
            f"{param_spec.choices}."
        )
        raise ValidationError(msg)
