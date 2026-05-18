"""Type declarations for the missions predicate evaluator.

Phase 0 ships the structural rule-tree evaluator plus its leaf-resolver
registry. The rule tree itself is the one sanctioned dynamic-JSON case in
this codebase (it mirrors the shape of
``world.distinctions.models.DistinctionPrerequisite.rule_json``), so the
evaluator accepts a plain ``dict`` as *input*. Everything else stays typed.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class PredicateContext(Protocol):
    """Read-only durable-state accessor for the acting character.

    Phase 0 ships the structural evaluator + leaf-resolver registry only.
    A leaf node in the rule tree is resolved by calling ``has_leaf`` with
    the leaf name and the leaf's authored params; the implementation tests
    the *acting character's own durable state* and never inspects a target.
    """

    def has_leaf(self, leaf: str, **params: object) -> bool: ...
