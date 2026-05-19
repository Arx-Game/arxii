"""Type declarations for the missions predicate evaluator.

Phase 0 ships the structural rule-tree evaluator plus its leaf-resolver
registry. The rule tree itself is the one sanctioned dynamic-JSON case in
this codebase (it mirrors the shape of
``world.distinctions.models.DistinctionPrerequisite.rule_json``), so the
evaluator accepts a plain ``dict`` as *input*. Everything else stays typed.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

# A leaf resolver tests one slice of the acting character's own durable
# state. It receives the acting character (ObjectDB) plus the leaf's
# authored params (keyword-only) and returns a bool. The registry maps a
# leaf name to one resolver.
LeafResolver = Callable[..., bool]
LeafRegistry = dict[str, LeafResolver]


@runtime_checkable
class PredicateContext(Protocol):
    """Read-only durable-state accessor for the acting character.

    Phase 0 ships the structural evaluator + leaf-resolver registry only.
    A leaf node in the rule tree is resolved by calling ``has_leaf`` with
    the leaf name and the leaf's authored params; the implementation tests
    the *acting character's own durable state* and never inspects a target.
    """

    def has_leaf(self, leaf: str, **params: object) -> bool: ...
