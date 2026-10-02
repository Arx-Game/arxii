"""Transitive technique-prerequisite closure (#4097).

Ratified spec: "a thread woven into a technique also empowers the techniques
it is a prerequisite for (including hidden ultimates)", at the thread's full
level. ``_anchor_in_action`` (``world/magic/services/resonance.py``) is the
only caller that needs to widen a TECHNIQUE-kind thread's in-action check
from "the exact technique" to "the exact technique or anything it requires" -
this module owns the graph walk so that widening is a one-line membership
test against the returned closure.
"""

from __future__ import annotations

from collections.abc import Iterable


def prerequisite_technique_ids(technique_ids: Iterable[int]) -> frozenset[int]:
    """Return the transitive prerequisite closure of ``technique_ids``.

    Breadth-first walk over active ``TechniqueKnownRequirement`` rows
    (``world.progression.models``): ``technique=X, required_technique=Y``
    means "X requires Y", so a query from frontier ``{X}`` returns ``{Y}``.
    One query per depth level (batched over the whole frontier, never per
    technique), cycle-safe via a ``seen`` set, inactive requirements excluded.

    The result holds only *discovered prerequisites* - it excludes every id
    passed in via ``technique_ids``, even one rediscovered through a cycle
    (A requires B, B requires A: walking from A yields ``{B}``, not
    ``{A, B}``). Callers that need "the technique plus what it needs" union
    this with their own input set themselves.
    """
    from world.progression.models import TechniqueKnownRequirement  # noqa: PLC0415

    input_ids = frozenset(technique_ids)
    seen: set[int] = set(input_ids)
    frontier: set[int] = set(input_ids)
    prerequisites: set[int] = set()

    while frontier:
        required_ids = set(
            TechniqueKnownRequirement.objects.filter(
                technique_id__in=frontier, is_active=True
            ).values_list("required_technique_id", flat=True)
        )
        prerequisites.update(required_ids - input_ids)
        frontier = required_ids - seen
        seen.update(required_ids)

    return frozenset(prerequisites)
