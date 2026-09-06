"""Live-match preview for the Upbringing Builder (#3660).

Task 7's minimal cut: enough to render the "Matches N group today" line for a
POOL or LISTED "pick a group" question, so an author can see which real
``Organization`` rows a prompt resolves against without leaving the page.
Task 8 adds the right rail's fuller live-preview lines and backlog counts;
``rail_counts`` is a placeholder until then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from evennia.accounts.models import AccountDB

from world.character_creation.constants import AnchorSource, QuestionKind
from world.character_creation.questionnaire import DraftAnswers, resolve_groups

if TYPE_CHECKING:
    from world.character_creation.models import OriginTemplate
    from world.societies.models import Organization

#: Sources ``resolve_groups`` can answer with no draft in hand. SAME_AS,
#: SERVED_HOUSE and OWN_FAMILY all read the draft itself, which does not
#: exist yet on the Builder's authoring-time page.
_TEMPLATE_ONLY_SOURCES = frozenset({AnchorSource.POOL, AnchorSource.LISTED})


@dataclass(frozen=True)
class LivePreview:
    """The Builder page's live-match data: matched groups per GROUP question."""

    groups_by_slot: dict[int, list[Organization]] = field(default_factory=dict)


def for_template(template: OriginTemplate, user: AccountDB) -> LivePreview:  # noqa: ARG001
    """Matched groups for every GROUP question on ``template``, POOL/LISTED only.

    SAME_AS, SERVED_HOUSE and OWN_FAMILY need a draft to resolve against and
    are left empty here (Task 8 territory). ``resolve_groups`` never reads
    its ``draft`` argument for POOL or LISTED, so ``template`` stands in for
    it safely for those two sources only.
    """
    groups_by_slot: dict[int, list[Organization]] = {}
    for slot in template.slots.order_by("sort_order", "id"):
        if slot.kind != QuestionKind.GROUP:
            continue
        if slot.anchor_source in _TEMPLATE_ONLY_SOURCES:
            groups_by_slot[slot.pk] = resolve_groups(slot, template, DraftAnswers())
        else:
            groups_by_slot[slot.pk] = []
    return LivePreview(groups_by_slot=groups_by_slot)


def rail_counts(template: OriginTemplate) -> dict:  # noqa: ARG001
    """Right-rail backlog counts; Task 8 fills this in."""
    return {}
