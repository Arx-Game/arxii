"""Broadcast-exclusion registry — Axis 1 of the perception taxonomy (#2997).

Axis 1 answers "does this observer receive a room broadcast at all." It is the
one perception axis that already had a repeat-offender risk baked in: before
this module existed, ``_dreamside_occupants`` (``communication.py``) was
hand-rolled directly into ``message_location``'s ``exclude=`` kwarg. A second
consumer (a haunting: "characters without the Sight are excluded from this
pose") would otherwise hand-roll a second ``_xyz_occupants`` function and a
second edit to ``communication.py`` — this registry closes that gap by making
``message_location`` union every *registered* resolver's excluded set instead
of importing one mechanism by name.

Dependency-free by design (ADR-0010, specific-general FK direction generalized
to imports): this module must never import a specific mechanism (dreams, a
future haunting/vision/glamour system). Each mechanism registers its own
resolver against this registry instead — mirrors the existing
``commands.offer_registry.register_offer_handler`` plugin-registers-itself
shape, the closest precedent in this codebase for "an app hands the primitive
a callback rather than the primitive importing the app."

See ``docs/systems/scenes.md``'s "Perception & altered reality" section for
the full three-axis taxonomy this is Axis 1 of.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

BroadcastExclusionResolver = Callable[["ObjectDB"], Iterable["ObjectDB"]]

_RESOLVERS: list[BroadcastExclusionResolver] = []


def register_broadcast_exclusion(resolver: BroadcastExclusionResolver) -> None:
    """Register a room-broadcast exclusion resolver.

    ``resolver(location) -> iterable of ObjectDB`` — objects in ``location``
    that should NOT receive a room broadcast (e.g. dreamside occupants missing
    waking-room chatter). Call once per mechanism, at import/``ready()`` time —
    never per-message.
    """
    _RESOLVERS.append(resolver)


def resolve_broadcast_exclusions(location: ObjectDB) -> set[ObjectDB]:
    """Union every registered resolver's excluded set for ``location``.

    Empty when no resolver is registered — byte-identical to the pre-registry
    ``exclude=None`` fallback with zero mechanisms wired up.
    """
    excluded: set[ObjectDB] = set()
    for resolver in _RESOLVERS:
        excluded.update(resolver(location))
    return excluded
