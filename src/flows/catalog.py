"""Authoring catalog for the flows DSL - the single source of truth.

Hand-declared because per-action parameter schemas exist only implicitly in
FlowStepDefinition's handler bodies (params.get("attribute") etc.);
introspection cannot recover them. test_catalog.py enforces completeness
against FlowActionChoices, so a new action cannot ship undescribed.
Consumed by BOTH flows.step_validation (serializer-side) and the
/api/flows/catalog/ endpoint (frontend palette), so they cannot drift.

Every ``accepts_reference`` flag below is transcribed from the matching
handler in ``flows.models.flows.FlowStepDefinition``: a param is
``accepts_reference=True`` only when the handler resolves it through
``FlowExecution.resolve_flow_reference`` (directly, or indirectly via
``resolve_modifier``, which resolves references inside a modifier's
``args``/``kwargs``). A param the handler reads and uses as a raw literal
(e.g. an attribute name, a dict key literal, an op string) is
``accepts_reference=False`` - marking it otherwise would let an author type
``@some_variable`` into a field the runtime treats as a plain string.

Note: every builder below takes its ``FlowActionChoices`` member as a
parameter and reads its DB value via ``str(action)`` rather than
``action.value``. ``ty`` infers ``TextChoices.value`` as the raw
``tuple[str, str]`` used to define the member instead of the resolved str,
so ``.value`` type-checks as non-``str`` here; ``str(action)`` is exact
(``TextChoices`` subclasses ``str``) and ty has no trouble with it.
``.label`` is unaffected and used directly.
"""

from collections.abc import Callable
from dataclasses import dataclass, fields
from enum import StrEnum
import inspect
import typing

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import PAYLOAD_FOR_EVENT
from flows.filters import evaluator
from flows.models.flows import CONDITIONAL_ACTIONS


class VariableNameRole(StrEnum):
    """What a step's ``variable_name`` field means for a given action."""

    FLOW_VARIABLE = "flow_variable"
    OBJECT_PK_VARIABLE = "object_pk_variable"
    SERVICE_FUNCTION_NAME = "service_function_name"
    EVENT_STORE_KEY = "event_store_key"
    UNUSED = "unused"


@dataclass(frozen=True)
class ParamSpec:
    """Describes one entry in a step's ``parameters`` JSON blob."""

    name: str
    type: str  # "str" | "int" | "float" | "bool" | "json" | "dict"
    required: bool = False
    description: str = ""
    accepts_reference: bool = True
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepActionSpec:
    """Full authoring description of one ``FlowActionChoices`` action."""

    action: str
    label: str
    description: str
    variable_name_role: str
    variable_name_required: bool
    params: tuple[ParamSpec, ...]
    is_conditional: bool = False
    allows_extra_params: bool = False


def _conditional(action: FlowActionChoices) -> StepActionSpec:
    """Build the spec shared by the six ``evaluate_*`` actions.

    Mirrors ``FlowStepDefinition._execute_conditional`` / ``_handle_conditional``:
    the flow variable named by ``variable_name`` is compared against the
    literal ``value`` param (coerced to the variable's runtime type), and the
    comparison result steers execution to this step's children (pass) or its
    next sibling (fail).
    """
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Compare the flow variable named by variable_name against 'value'. "
            "On pass, execution enters this step's children; on fail, its next sibling."
        ),
        variable_name_role=VariableNameRole.FLOW_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="value",
                type="str",
                required=True,
                accepts_reference=False,
                description="Literal to compare against (coerced to the variable's type).",
            ),
        ),
        is_conditional=True,
    )


def _set_context_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_set_context_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Set an attribute to a literal value on the object state named by variable_name."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the attribute to set on the object state.",
            ),
            ParamSpec(
                name="value",
                type="json",
                required=False,
                accepts_reference=False,
                description="Literal value to store (used as-is; not resolved as a reference).",
            ),
        ),
    )


def _modify_context_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_modify_context_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Modify an attribute on the object state named by variable_name using a modifier."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the attribute to modify on the object state.",
            ),
            ParamSpec(
                name="modifier",
                type="json",
                required=True,
                description=(
                    "Modifier spec: {'name': op, 'args': [...], 'kwargs': {...}}. "
                    "args/kwargs values may themselves be flow variable references."
                ),
            ),
        ),
    )


def _add_context_list_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_add_context_list_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Append a value to a list attribute on the object state named by variable_name."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the list attribute to append to.",
            ),
            ParamSpec(
                name="value",
                type="json",
                required=False,
                description="Value to append (may be a flow variable reference).",
            ),
        ),
    )


def _remove_context_list_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_remove_context_list_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Remove a value from a list attribute on the object state named by variable_name."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the list attribute to remove from.",
            ),
            ParamSpec(
                name="value",
                type="json",
                required=False,
                description="Value to remove (may be a flow variable reference).",
            ),
        ),
    )


def _set_context_dict_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_set_context_dict_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Set a key/value pair on a dict attribute on the object state named by variable_name."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the dict attribute to write to.",
            ),
            ParamSpec(
                name="key",
                type="json",
                required=False,
                description="Dict key to set (may be a flow variable reference).",
            ),
            ParamSpec(
                name="value",
                type="json",
                required=False,
                description="Value to store at that key (may be a flow variable reference).",
            ),
        ),
    )


def _remove_context_dict_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_remove_context_dict_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Remove a key from a dict attribute on the object state named by variable_name."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the dict attribute to remove from.",
            ),
            ParamSpec(
                name="key",
                type="json",
                required=False,
                description="Dict key to remove (may be a flow variable reference).",
            ),
        ),
    )


def _modify_context_dict_value(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_modify_context_dict_value``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Modify a value stored in a dict attribute on the object state named by "
            "variable_name using a modifier."
        ),
        variable_name_role=VariableNameRole.OBJECT_PK_VARIABLE.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="attribute",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the dict attribute to modify.",
            ),
            ParamSpec(
                name="key",
                type="json",
                required=False,
                description="Dict key to modify (may be a flow variable reference).",
            ),
            ParamSpec(
                name="modifier",
                type="json",
                required=True,
                description=(
                    "Modifier spec: {'name': op, 'args': [...], 'kwargs': {...}}. "
                    "args/kwargs values may themselves be flow variable references."
                ),
            ),
        ),
    )


def _call_service_function(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_call_service_function``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Call the service function named by variable_name, resolving flow variable "
            "references in every extra parameter, and optionally store its result."
        ),
        variable_name_role=VariableNameRole.SERVICE_FUNCTION_NAME.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="result_variable",
                type="str",
                required=False,
                accepts_reference=False,
                description="Flow variable name to store the service function's return value in.",
            ),
        ),
        allows_extra_params=True,
    )


def _emit_flow_event(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_emit_flow_event``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description=(
            "Dispatch an event to the resolved location and store it under variable_name "
            "for downstream steps to read."
        ),
        variable_name_role=VariableNameRole.EVENT_STORE_KEY.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="event_type",
                type="str",
                required=False,
                accepts_reference=False,
                description="Event name to emit; defaults to variable_name when omitted.",
            ),
            ParamSpec(
                name="data",
                type="dict",
                required=False,
                description="Event payload data; each value may be a flow variable reference.",
            ),
        ),
    )


def _emit_flow_event_for_each(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_emit_flow_event_for_each``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description="Emit an event for every item in an iterable, dispatching once per item.",
        variable_name_role=VariableNameRole.EVENT_STORE_KEY.value,
        variable_name_required=True,
        params=(
            ParamSpec(
                name="iterable",
                type="json",
                required=True,
                description="Flow variable reference resolving to the iterable to loop over.",
            ),
            ParamSpec(
                name="event_type",
                type="str",
                required=False,
                accepts_reference=False,
                description="Event name to emit per item; defaults to variable_name when omitted.",
            ),
            ParamSpec(
                name="data",
                type="dict",
                required=False,
                description=(
                    "Event payload data; each value may be a flow variable reference "
                    "('@item' is replaced with the current loop item)."
                ),
            ),
            ParamSpec(
                name="item_key",
                type="str",
                required=False,
                accepts_reference=False,
                description="Key under which the current item is stored in the payload data.",
            ),
        ),
    )


def _cancel_event(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_cancel_event``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description="Mark the current dispatch result and flow stack as cancelled.",
        variable_name_role=VariableNameRole.UNUSED.value,
        variable_name_required=False,
        params=(),
    )


def _modify_payload(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_modify_payload``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description="Mutate a field on the current event payload dataclass in place.",
        variable_name_role=VariableNameRole.UNUSED.value,
        variable_name_required=False,
        params=(
            ParamSpec(
                name="field",
                type="str",
                required=True,
                accepts_reference=False,
                description="Name of the payload field to mutate.",
            ),
            ParamSpec(
                name="op",
                type="str",
                required=True,
                accepts_reference=False,
                choices=("set", "multiply", "add", "min", "max"),
                description="How to combine the current field value with 'value'.",
            ),
            ParamSpec(
                name="value",
                type="json",
                required=True,
                accepts_reference=False,
                description=(
                    "Literal operand used with 'op' (used as-is; not resolved as a reference)."
                ),
            ),
        ),
    )


def _prompt_player(action: FlowActionChoices) -> StepActionSpec:
    """Mirrors ``FlowStepDefinition._execute_prompt_player``."""
    return StepActionSpec(
        action=str(action),
        label=action.label,
        description="Suspend the flow until the player's account responds to a prompt.",
        variable_name_role=VariableNameRole.UNUSED.value,
        variable_name_required=False,
        params=(
            ParamSpec(
                name="account",
                type="json",
                required=True,
                description="Flow variable reference resolving to the account to prompt.",
            ),
            ParamSpec(
                name="result_variable",
                type="str",
                required=True,
                accepts_reference=False,
                description="Flow variable name to store the player's answer in.",
            ),
            ParamSpec(
                name="default_answer",
                type="json",
                required=False,
                accepts_reference=False,
                description=(
                    "Literal answer used if the prompt resolves without an explicit response "
                    "(used as-is; not resolved as a reference)."
                ),
            ),
        ),
    )


_NON_CONDITIONAL_SPECS: tuple[StepActionSpec, ...] = (
    _set_context_value(FlowActionChoices.SET_CONTEXT_VALUE),
    _modify_context_value(FlowActionChoices.MODIFY_CONTEXT_VALUE),
    _add_context_list_value(FlowActionChoices.ADD_CONTEXT_LIST_VALUE),
    _remove_context_list_value(FlowActionChoices.REMOVE_CONTEXT_LIST_VALUE),
    _set_context_dict_value(FlowActionChoices.SET_CONTEXT_DICT_VALUE),
    _remove_context_dict_value(FlowActionChoices.REMOVE_CONTEXT_DICT_VALUE),
    _modify_context_dict_value(FlowActionChoices.MODIFY_CONTEXT_DICT_VALUE),
    _call_service_function(FlowActionChoices.CALL_SERVICE_FUNCTION),
    _emit_flow_event(FlowActionChoices.EMIT_FLOW_EVENT),
    _emit_flow_event_for_each(FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH),
    _cancel_event(FlowActionChoices.CANCEL_EVENT),
    _modify_payload(FlowActionChoices.MODIFY_PAYLOAD),
    _prompt_player(FlowActionChoices.PROMPT_PLAYER),
)

STEP_ACTION_SPECS: dict[str, StepActionSpec] = {
    **{str(a): _conditional(a) for a in CONDITIONAL_ACTIONS},
    **{spec.action: spec for spec in _NON_CONDITIONAL_SPECS},
}

FILTER_OPS: tuple[str, ...] = (
    evaluator.OP_EQ,
    evaluator.OP_NE,
    evaluator.OP_LT,
    evaluator.OP_LE,
    evaluator.OP_GT,
    evaluator.OP_GE,
    evaluator.OP_IN,
    evaluator.OP_CONTAINS,
    evaluator.OP_HAS_PROPERTY,
    evaluator.OP_HAS_CAPABILITY,
    evaluator.OP_SHARES_COVENANT,
    evaluator.OP_HAS_RESONANCE_AT_LEAST,
    evaluator.OP_HAS_PUBLIC_DISTINCTION,
    evaluator.OP_FAME_TIER_AT_LEAST,
    evaluator.OP_HAS_LEGEND_DEEDS,
)


def event_catalog() -> list[dict]:
    """Every EventName with its payload dataclass fields (None when unmapped)."""
    entries = []
    for name, label in EventName.choices:
        payload_cls = PAYLOAD_FOR_EVENT.get(name)
        fields_out = None
        if payload_cls is not None:
            fields_out = [{"name": f.name, "type": str(f.type)} for f in fields(payload_cls)]
        entries.append({"name": name, "label": label, "payload_fields": fields_out})
    return entries


_SERVICE_FUNCTION_JSON_TAG = "json"

_SERVICE_FUNCTION_TYPE_TAGS: dict[type, str] = {
    int: "int",
    bool: "bool",
    str: "str",
    float: "float",
}

# A module using `from __future__ import annotations` stringifies every
# annotation, so `param.annotation` is the literal source text (e.g. "str"),
# not the `str` type object. When `typing.get_type_hints` can't resolve the
# WHOLE function (e.g. a TYPE_CHECKING-only forward reference on a sibling
# param), this lets the still-plain-text builtin annotations on OTHER params
# resolve correctly instead of every param on the function falling back to
# the JSON tag together.
_SERVICE_FUNCTION_STRING_ANNOTATION_TAGS: dict[str, str] = {
    "int": "int",
    "bool": "bool",
    "str": "str",
    "float": "float",
}


def _service_function_annotation_tag(annotation: object) -> str:
    """Map a service-function param annotation to a string tag the FE can switch on.

    Unknown / unannotated / unresolvable params fall back to the JSON tag —
    the catalog would rather hand the authoring UI a free-text/JSON field
    than guess wrong and coerce a value into the wrong Python type at call
    time.
    """
    if isinstance(annotation, type):
        return _SERVICE_FUNCTION_TYPE_TAGS.get(annotation, _SERVICE_FUNCTION_JSON_TAG)
    if isinstance(annotation, str):
        return _SERVICE_FUNCTION_STRING_ANNOTATION_TAGS.get(annotation, _SERVICE_FUNCTION_JSON_TAG)
    return _SERVICE_FUNCTION_JSON_TAG


def _service_function_params(func: Callable) -> list[dict[str, str]]:
    """Return ``func``'s keyword-capable param names + type tags.

    Same inspect-signature + ``typing.get_type_hints`` technique as
    ``world/predicates/catalog.py:leaf_params`` (re-implemented here rather
    than shared, since ``flows`` must not import ``world.*`` — see this
    module's docstring on ``str(action)`` vs ``.value`` for the sibling
    "small deliberate duplication vs. a cross-app import" trade-off this
    module already makes). A module using ``from __future__ import
    annotations`` stringifies every annotation, so if ANY param on the
    function has an unresolvable forward reference (e.g. a name only
    imported under ``TYPE_CHECKING``), ``get_type_hints`` raises for the
    WHOLE function and every param falls back to the raw (string)
    annotation from ``inspect.signature``. ``_service_function_annotation_tag``
    still recovers the concrete tag for a builtin-named param in that
    situation (e.g. ``condition_name: str`` tags ``"str"`` even when a
    sibling ``target: ObjectDB`` param can't resolve) — only a param whose
    raw annotation isn't a literal ``"int"``/``"bool"``/``"str"``/``"float"``
    falls all the way back to ``"json"``.
    """
    sig = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except (NameError, AttributeError, TypeError):
        hints = {}
    return [
        {
            "name": name,
            "type": _service_function_annotation_tag(hints.get(name, param.annotation)),
        }
        for name, param in sig.parameters.items()
        if param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]


def service_function_catalog() -> list[dict]:
    """Every registered service function, with its params' names and type tags.

    Enumerates ``flows.service_functions.list_service_functions()`` — the
    ``SERVICE_MODULES`` hooks dicts plus anything registered out-of-app via
    ``register_service_function`` (e.g. the world-side condition verbs
    ``world.apps.ready()`` registers). Consumed by the CALL_SERVICE_FUNCTION
    step editor so authors can pick a verb and see its parameters without
    reading source.

    Returns:
        A list of ``{"name", "description", "params": [{"name", "type"}]}``
        dicts, sorted by ``name``. ``description`` is the first line of the
        function's docstring (``""`` if it has none).
    """
    from flows.service_functions import list_service_functions  # noqa: PLC0415

    entries = []
    for name, func in list_service_functions().items():
        doc = inspect.getdoc(func)
        description = doc.splitlines()[0] if doc else ""
        entries.append(
            {
                "name": name,
                "description": description,
                "params": _service_function_params(func),
            }
        )
    entries.sort(key=lambda entry: entry["name"])
    return entries
