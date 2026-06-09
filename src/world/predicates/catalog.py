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

from world.predicates.predicates import LEAF_RESOLVERS
from world.predicates.types import LeafResolver

_TYPE_TAGS: dict[type, str] = {int: "int", bool: "bool", str: "str", float: "float"}


def annotation_tag(annotation: object) -> str:
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
        # "str" via the isinstance check in annotation_tag.
        hints = {}
    return [
        {"name": name, "type": annotation_tag(hints.get(name, param.annotation))}
        for name, param in list(sig.parameters.items())[1:]
        if param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]


def leaf_param_specs() -> dict[str, list[dict[str, str]]]:
    """Param specs for every registered leaf, keyed by leaf name."""
    return {name: leaf_params(resolver) for name, resolver in LEAF_RESOLVERS.items()}
