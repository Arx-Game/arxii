"""Reading and writing how substances stand to one another (#5125).

A relation between two substances is stored once, lower substance id first, so it reads the same
from either side. Relations never chain: this module only ever looks at rows that name the
substance asked about, never at a relation of a relation.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from world.magic.constants import SubstanceRelationKind
from world.magic.models import Substance, SubstanceRelation


def relation_kinds_for(substance: Substance) -> dict[int, str]:
    """Map the pk of each substance related or opposed to ``substance`` to the kind.

    One query reads the pair from whichever side ``substance`` is stored on. A substance with no
    relation row to ``substance`` is absent from the answer.
    """
    rows = SubstanceRelation.objects.filter(Q(substance_a=substance) | Q(substance_b=substance))
    return {
        row.substance_b_id if row.substance_a_id == substance.pk else row.substance_a_id: row.kind
        for row in rows
    }


def set_substance_relations(
    substance: Substance,
    *,
    related: Iterable[Substance],
    opposed: Iterable[Substance],
) -> None:
    """Make ``substance``'s relation rows exactly ``related`` and ``opposed``.

    Rows for a substance in neither set are deleted, rows whose kind changed are rewritten and
    missing rows are created, all in one transaction. A substance in both sets, or equal to
    ``substance`` itself, raises ``ValidationError`` before anything is written.
    """
    related_ids = {other.pk for other in related}
    opposed_ids = {other.pk for other in opposed}
    if substance.pk in related_ids | opposed_ids:
        msg = "A substance cannot stand in relation to itself."
        raise ValidationError(msg)
    if related_ids & opposed_ids:
        msg = "A substance cannot be both related and opposed to the same substance."
        raise ValidationError(msg)
    wanted: dict[int, str] = {
        **dict.fromkeys(related_ids, SubstanceRelationKind.RELATED),
        **dict.fromkeys(opposed_ids, SubstanceRelationKind.OPPOSED),
    }
    with transaction.atomic():
        rows = SubstanceRelation.objects.filter(Q(substance_a=substance) | Q(substance_b=substance))
        for row in rows:
            other_id = (
                row.substance_b_id if row.substance_a_id == substance.pk else row.substance_a_id
            )
            kind = wanted.pop(other_id, None)
            if kind is None:
                row.delete()
            elif kind != row.kind:
                row.kind = kind
                row.save(update_fields=["kind"])
        for other_id, kind in wanted.items():
            low, high = sorted((substance.pk, other_id))
            SubstanceRelation.objects.create(substance_a_id=low, substance_b_id=high, kind=kind)
