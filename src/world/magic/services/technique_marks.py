"""A technique's marks: the properties that say how it works (#5066).

A technique is how a gift is used, so what it does is its own ``Technique.properties``,
ticked per technique by staff (a blink carries ``teleport``, a smoke form
``incorporeal``). The gift's resonances never decide it: resonance is how she feels
when she casts, not what the magic does. Capability sources, applications and clash
opposition all read the marks through ``effect_property_ids_by_technique``.

A major gift's substance names one property (``Substance.property``). Every technique of
that gift, and of its child gifts, always carries it: it is read at call time through
``effect_property_ids_by_technique`` and stored nowhere, so staff cannot untick it and a
change to the substance's property reaches every technique at once. A minor gift has no
substance, so its techniques carry only their own marks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def substance_property_ids_by_technique(technique_ids: Iterable[int]) -> dict[int, int]:
    """The substance property pk each technique carries from its gift, for those that do.

    One query for the techniques' gifts; the property is resolved once per distinct gift
    through the gift lineage (``gift_substance``), so a child gift carries its parent's and a
    minor gift carries none. Techniques that carry none are left out.
    """
    from world.magic.models import Technique  # noqa: PLC0415
    from world.magic.services.primum import gift_substance  # noqa: PLC0415

    ids = set(technique_ids)
    if not ids:
        return {}
    property_by_gift: dict[int, int | None] = {}
    carried: dict[int, int] = {}
    for technique in Technique.objects.filter(pk__in=ids).select_related("gift"):
        gift = technique.gift
        if gift.pk not in property_by_gift:
            substance = gift_substance(gift)
            property_by_gift[gift.pk] = substance.property_id if substance else None
        property_id = property_by_gift[gift.pk]
        if property_id is not None:
            carried[technique.pk] = property_id
    return carried


def effect_property_ids_by_technique(technique_ids: Iterable[int]) -> dict[int, frozenset[int]]:
    """Each technique's mark pks: its own ticked marks plus its gift substance's property.

    The ticked marks are read from the table rather than a ``to_attr`` on the
    identity-mapped technique, so a mark staff tick or untick reaches the next read in every
    process. The substance's property is added on top (``substance_property_ids_by_technique``).
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
    for technique_id, property_id in substance_property_ids_by_technique(ids).items():
        marks[technique_id].add(property_id)
    return {technique_id: frozenset(marks.get(technique_id, ())) for technique_id in ids}
