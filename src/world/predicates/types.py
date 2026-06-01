"""Type declarations for the shared predicate engine.

The rule tree is the one sanctioned dynamic-JSON case in this codebase
(it mirrors the shape of
``world.distinctions.models.DistinctionPrerequisite.rule_json``), so the
evaluator accepts a plain ``dict`` as input. Everything else stays
typed.

Lifted from ``world.missions.types`` when the predicate engine was
extracted from missions into its own neutral app. Mission-specific
types (``DeedRewardLine`` etc.) stayed in ``world.missions.types``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona


@dataclass(frozen=True)
class ResolverContext:
    """What a predicate-leaf resolver gets called with.

    ``sheet`` is the acting CharacterSheet — the canonical character
    handle per the project's "Avoid direct FKs to ObjectDB" rule.
    Resolvers that gate on sheet-keyed state (achievements, threads,
    resonance, codex knowledge, etc.) use ``ctx.sheet`` directly.
    The handful of resolvers that gate on models still keyed by
    ObjectDB (CharacterDistinction.character, ConditionInstance.target
    via the conditions service, CharacterTraitValue.character) walk
    ``ctx.character`` — a convenience property that returns
    ``ctx.sheet.character``.

    ``presented_persona`` is the persona the character is currently
    presenting as (the mask they're wearing), or None if the caller
    did not specify one. Persona-aware resolvers consult it; non-
    persona resolvers ignore it.

    See ``CharacterPredicateContext`` for the runtime that constructs
    this and dispatches to the registry.
    """

    sheet: CharacterSheet
    presented_persona: Persona | None = None

    @property
    def character(self) -> ObjectDB:
        """Convenience: walk back to the ObjectDB for models that key on it.

        Most resolvers should prefer ``ctx.sheet`` directly. This
        property exists for the handful of legacy-keyed models
        (CharacterDistinction, ConditionInstance, CharacterTraitValue)
        that FK ObjectDB. SharedMemoryModel identity map keeps the
        ObjectDB cached on the sheet — this is a cheap attribute walk,
        not a query.
        """
        return self.sheet.character


# A leaf resolver tests one slice of the acting character's state. It
# receives a ResolverContext (character + optional presented_persona) plus
# the leaf's authored params (keyword-only) and returns a bool. The
# registry maps a leaf name to one resolver.
LeafResolver = Callable[..., bool]
LeafRegistry = dict[str, LeafResolver]


@runtime_checkable
class PredicateContext(Protocol):
    """Read-only durable-state accessor for the acting character.

    A leaf node in the rule tree is resolved by calling ``has_leaf`` with
    the leaf name and the leaf's authored params; the implementation
    tests the *acting character's own durable state* and never inspects
    a target.
    """

    def has_leaf(self, leaf: str, **params: object) -> bool: ...
