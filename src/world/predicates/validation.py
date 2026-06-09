"""Server-side well-formedness validation for predicate rule trees (#870).

The structural evaluator (``predicates.evaluate``) assumes a well-formed
tree and a real character; a malformed rule saved through the API crashes
*every later availability check* that touches it (an unknown leaf name is
a ``KeyError`` inside ``offer_missions``/trigger dispatch). This module
rejects malformed trees at author time instead, so the serializer can 400.

Ports the checks the FE builder already runs (``validatePredicate`` in
``PredicateBuilder.tsx``) and adds param *type* and *value* checks against
the same introspected catalog the builder renders from
(``catalog.leaf_params``):

- structure: every node is ``{}``, a ``{"op", "of"}`` group, or a
  ``{"leaf", "params"}`` leaf; ``op`` ∈ AND/OR/NOT; ``of`` is a list;
  NOT has exactly one operand
- leaf names: non-empty and present in ``LEAF_RESOLVERS``
- params: every declared param present and non-blank, no undeclared
  extras (they'd ``TypeError`` at resolver call time), values matching
  the declared type tag, and values within the allowed set for params
  whose resolver raises on out-of-set values (tier strings)

Returns human-readable error strings (empty list == valid) rather than
raising, so callers compose the errors into their own ValidationError
shape. A shared FE/BE contract (one schema both sides consume) is a
deliberate follow-up; for now the two implementations are kept in sync
by the shared introspected catalog.
"""

from __future__ import annotations

from world.predicates.catalog import leaf_params
from world.predicates.predicates import (
    _TIER_ORDER,
    KEY_LEAF,
    KEY_OF,
    KEY_OP,
    KEY_PARAMS,
    LEAF_RESOLVERS,
    OP_AND,
    OP_NOT,
    OP_OR,
)

_VALID_OPS = (OP_AND, OP_OR, OP_NOT)

# Type-tag -> runtime check. ``bool`` is a subclass of ``int`` in Python,
# so the int/float checks exclude bools explicitly (a leaf declaring
# ``rank: int`` must not silently accept ``true``).
_TAG_CHECKS = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
}

# Params constrained beyond their primitive type, keyed (leaf, param).
# ``_tier_rank`` raises KeyError for any value outside ``_TIER_ORDER``
# (deliberately loud — but the loud failure fires inside every later
# availability check, so reject out-of-set values at author time too).
_PARAM_ALLOWED_VALUES: dict[tuple[str, str], tuple[str, ...]] = {
    ("min_org_reputation", "tier"): _TIER_ORDER,
    ("min_society_standing", "tier"): _TIER_ORDER,
}


def validate_predicate_tree(rule: object) -> list[str]:
    """Validate a rule tree's well-formedness; return error strings (empty == valid)."""
    errors: list[str] = []
    _walk(rule, errors, path="root")
    return errors


def _walk(node: object, errors: list[str], path: str) -> None:
    if not isinstance(node, dict):
        errors.append(f"{path}: node must be an object, got {type(node).__name__}.")
        return
    if not node:  # {} == no gate
        return
    if KEY_OP in node:
        _walk_group(node, errors, path)
        return
    if KEY_LEAF in node:
        _walk_leaf(node, errors, path)
        return
    errors.append(f"{path}: node must be empty, an op group, or a leaf.")


def _walk_group(node: dict, errors: list[str], path: str) -> None:
    op = node[KEY_OP]
    if op not in _VALID_OPS:
        errors.append(f"{path}: unknown op {op!r} (expected one of {', '.join(_VALID_OPS)}).")
        return
    of = node.get(KEY_OF, [])
    if not isinstance(of, list):
        errors.append(f"{path}: 'of' must be a list.")
        return
    if op == OP_NOT and len(of) != 1:
        errors.append(f"{path}: NOT must have exactly one operand, got {len(of)}.")
    for i, child in enumerate(of):
        _walk(child, errors, f"{path}.{op}[{i}]")


def _walk_leaf(node: dict, errors: list[str], path: str) -> None:
    leaf = node[KEY_LEAF]
    if not leaf or not isinstance(leaf, str):
        errors.append(f"{path}: leaf name must be a non-empty string.")
        return
    resolver = LEAF_RESOLVERS.get(leaf)
    if resolver is None:
        errors.append(f"{path}: unknown leaf {leaf!r}.")
        return
    params = node.get(KEY_PARAMS, {})
    if not isinstance(params, dict):
        errors.append(f"{path}: 'params' must be an object.")
        return
    declared = leaf_params(resolver)
    declared_names = {spec["name"] for spec in declared}
    errors.extend(
        f"{path}: leaf {leaf!r} got unexpected param {extra!r}."
        for extra in sorted(set(params) - declared_names)
    )
    for spec in declared:
        name, tag = spec["name"], spec["type"]
        value = params.get(name)
        if value is None or value == "":
            errors.append(f"{path}: leaf {leaf!r} param {name!r} is required.")
            continue
        if not _TAG_CHECKS.get(tag, _TAG_CHECKS["str"])(value):
            errors.append(
                f"{path}: leaf {leaf!r} param {name!r} must be of type {tag}, "
                f"got {type(value).__name__}."
            )
            continue
        allowed = _PARAM_ALLOWED_VALUES.get((leaf, name))
        if allowed is not None and value not in allowed:
            errors.append(
                f"{path}: leaf {leaf!r} param {name!r} must be one of "
                f"{', '.join(allowed)}; got {value!r}."
            )
