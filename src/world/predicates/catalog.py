"""Leaf-catalog introspection — the single source of truth for leaf params.

Reads each registered resolver's signature to produce ``{"name", "type"}``
param specs. Consumed by BOTH the predicate-leaf catalog endpoint (the FE
builder's palette — ``world.missions.views.PredicateLeafCatalogViewSet``)
and the server-side tree validator (``world.predicates.validation``), so
the params the builder renders and the params the validator enforces can
never drift.
"""

from __future__ import annotations

import inspect
import typing

from world.predicates.predicates import _TIER_ORDER, LEAF_RESOLVERS
from world.predicates.types import LeafResolver

_TYPE_TAGS: dict[type, str] = {int: "int", bool: "bool", str: "str", float: "float"}


def _annotation_tag(annotation: object) -> str:
    """Map a resolver param annotation to a string tag the FE can switch on.

    The FE builder coerces ``<Input>`` strings into the right Python type
    before save based on this tag — without it, int-typed leaves (e.g.
    ``min_character_level``) blow up at evaluate time with ``TypeError``.

    Unknown / unannotated params fall back to ``"str"`` (the safe default
    — most resolvers either accept a slug or ``int(...)``-coerce on read).
    """
    return _TYPE_TAGS.get(annotation, "str") if isinstance(annotation, type) else "str"


def leaf_params(resolver: LeafResolver) -> list[dict[str, str]]:
    """Return the leaf's authored param names + type tags (everything after ctx).

    The resolver module uses ``from __future__ import annotations``, so
    ``Parameter.annotation`` is a string rather than the type object.
    Re-resolve via ``typing.get_type_hints`` so the tag mapping works.
    """
    sig = inspect.signature(resolver)
    try:
        hints = typing.get_type_hints(resolver)
    except (NameError, AttributeError, TypeError):
        # If a resolver's annotations reference an as-yet-unresolvable
        # forward reference (NameError) or a non-evaluable annotation
        # (TypeError / AttributeError on inner typing surfaces), fall
        # back to the raw (string) annotation — which falls through to
        # "str" via the isinstance check in _annotation_tag.
        hints = {}
    return [
        {"name": name, "type": _annotation_tag(hints.get(name, param.annotation))}
        for name, param in list(sig.parameters.items())[1:]
        if param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]


# Params constrained beyond their primitive type, keyed (leaf, param). ``_tier_rank``
# raises KeyError for any value outside ``_TIER_ORDER`` (deliberately loud, but the loud
# failure fires inside every later evaluation), so the validator rejects out-of-set
# values at author time and the builders offer them as a pick list.
PARAM_ALLOWED_VALUES: dict[tuple[str, str], tuple[str, ...]] = {
    ("min_org_reputation", "tier"): _TIER_ORDER,
    ("min_society_standing", "tier"): _TIER_ORDER,
    ("max_org_reputation", "tier"): _TIER_ORDER,
    ("max_society_standing", "tier"): _TIER_ORDER,
}


def leaf_catalog() -> list[dict]:
    """Every registered leaf with its typed params, sorted by name.

    Each param is ``{"name", "type"}``, plus ``"choices"`` when the param only takes a
    fixed set of values. Served by the mission studio's leaf catalog endpoint and the
    admin predicate widget, so both builders offer the same palette.
    """
    catalog = []
    for name, resolver in sorted(LEAF_RESOLVERS.items()):
        params = []
        for spec in leaf_params(resolver):
            allowed = PARAM_ALLOWED_VALUES.get((name, spec["name"]))
            params.append({**spec, "choices": list(allowed)} if allowed else spec)
        catalog.append({"name": name, "params": params})
    return catalog
