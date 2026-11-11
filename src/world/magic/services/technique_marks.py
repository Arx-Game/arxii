"""A technique's marks: the properties that say how it works (#5066).

A technique is how a gift is used, so what it does is its own ``Technique.properties``,
ticked per technique by staff (a blink carries ``teleport``, a smoke form
``incorporeal``). The gift's resonances never decide it: resonance is how she feels
when she casts, not what the magic does. Capability sources, applications and clash
opposition all read the marks through ``effect_property_ids_by_technique``.

A gift's substance names one property (``GiftSubstance.property``). A new technique on
that gift starts with it ticked, as an authoring convenience; staff untick it where it
does not belong, and nothing reads the substance at play time.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Gift, Technique
    from world.mechanics.models import Property


def effect_property_ids_by_technique(technique_ids: Iterable[int]) -> dict[int, frozenset[int]]:
    """Each technique's mark pks, in one query over the marks table.

    Read from the table rather than a ``to_attr`` on the identity-mapped technique, so
    a mark staff tick or untick reaches the next read in every process.
    """
    from world.magic.models import Technique  # noqa: PLC0415

    ids = set(technique_ids)
    if not ids:
        return {}
    marks: dict[int, set[int]] = defaultdict(set)
    rows = Technique.properties.through.objects.filter(technique_id__in=ids).values_list(
        "technique_id", "property_id"
    )
    for technique_id, property_id in rows:
        marks[technique_id].add(property_id)
    return {technique_id: frozenset(marks.get(technique_id, ())) for technique_id in ids}


def substance_mark_for(gift: Gift | None) -> Property | None:
    """The property a new technique on ``gift`` starts with ticked, or None.

    The gift's substance (or its nearest ancestor's, as a child gift uses its parent's)
    names it.
    """
    from world.magic.services.substance import substance_for_gift  # noqa: PLC0415

    substance = substance_for_gift(gift)
    if substance is None or substance.property_id is None:
        return None
    return substance.property


def tick_substance_mark(technique: Technique) -> None:
    """Tick the gift's substance mark on a technique just created."""
    mark = substance_mark_for(technique.gift)
    if mark is not None:
        technique.properties.add(mark)
