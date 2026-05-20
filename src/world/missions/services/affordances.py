"""Resolve which authored bindings an acting character can actually use.

A mission challenge declares the set of affordances it accepts. Any durable
descriptor the acting character owns that is bound (Phase 1
``AffordanceBinding``) to one of those affordances surfaces as a
:class:`~world.missions.types.ResolvedOption`.

Ownership is **not** re-implemented here. Each binding's ``source_kind``
discriminator is dispatched to the corresponding Phase 0 leaf resolver in
``world.missions.predicates`` (the same code the predicate evaluator uses),
passing the bound descriptor's natural identifier. This keeps "does the
acting character own descriptor X" defined in exactly one place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.missions.models import (
    SOURCE_ACHIEVEMENT,
    SOURCE_CAPABILITY,
    SOURCE_CONDITION,
    SOURCE_DISTINCTION,
    SOURCE_TRAIT,
    AffordanceBinding,
)
from world.missions.predicates import (
    _resolve_has_achievement,
    _resolve_has_capability,
    _resolve_has_condition,
    _resolve_has_distinction,
    _resolve_min_trait,
)
from world.missions.types import ResolvedOption

if TYPE_CHECKING:
    from world.missions.models import Affordance

# source_kind -> (Phase 0 resolver, function building its kwargs from the
# binding's active descriptor). The resolvers live in
# world.missions.predicates and are the single definition of "does this
# acting character own descriptor X" — never re-query that here.
_OWNERSHIP_DISPATCH: dict[
    str,
    tuple[Callable[..., bool], Callable[[AffordanceBinding], dict[str, object]]],
] = {
    SOURCE_DISTINCTION: (
        _resolve_has_distinction,
        lambda b: {"slug": b.source_distinction.slug},
    ),
    SOURCE_ACHIEVEMENT: (
        _resolve_has_achievement,
        lambda b: {"slug": b.source_achievement.slug},
    ),
    SOURCE_CONDITION: (
        _resolve_has_condition,
        lambda b: {"key": b.source_condition.name},
    ),
    SOURCE_CAPABILITY: (
        _resolve_has_capability,
        lambda b: {"name": b.source_capability.name},
    ),
    # A trait binding means "owns a positive value in this trait"; reuse the
    # min_trait resolver at value=1 (covers stat and skill traits uniformly).
    SOURCE_TRAIT: (
        _resolve_min_trait,
        lambda b: {"trait": b.source_trait.name, "value": 1},
    ),
}


def _character_owns_descriptor(character: ObjectDB, binding: AffordanceBinding) -> bool:
    """Reuse the Phase 0 resolver matching the binding's discriminator."""
    resolver, kwargs_builder = _OWNERSHIP_DISPATCH[binding.source_kind]
    return resolver(character, **kwargs_builder(binding))


def bindings_for_character(
    character: ObjectDB,
    accepted: set[Affordance],
) -> list[ResolvedOption]:
    """Surface the options ``character`` can take given ``accepted`` affordances.

    For each ``AffordanceBinding`` whose ``affordance`` is in ``accepted`` and
    whose bound descriptor the acting ``character`` owns (decided by the Phase
    0 resolvers), build one :class:`ResolvedOption`. Bindings whose affordance
    is not accepted, or whose descriptor the character lacks, are excluded.

    Args:
        character: The acting character (an ``ObjectDB``).
        accepted: The set of ``Affordance`` instances the challenge accepts.

    Returns:
        Resolved options in a deterministic order (affordance name, then
        binding pk). Empty when nothing matches.
    """
    if not accepted:
        return []

    bindings = (
        AffordanceBinding.objects.filter(affordance__in=accepted)
        .select_related(
            "affordance",
            "check_type",
            "rider",
            "source_trait",
            "source_distinction",
            "source_achievement",
            "source_capability",
            "source_condition",
        )
        .order_by("affordance__name", "pk")
    )

    options: list[ResolvedOption] = []
    for binding in bindings:
        if not _character_owns_descriptor(character, binding):
            continue
        options.append(
            ResolvedOption(
                binding=binding,
                produces=binding.produces,
                check_type=binding.check_type,
                base_risk=binding.base_risk,
                ic_framing=binding.ic_framing,
                rider=binding.rider,
                owner=character,
            )
        )
    return options
