"""Live-match preview for the Upbringing Builder (#3660).

Task 7's minimal cut was enough to render the "Matches N group today" line for
a POOL or LISTED "pick a group" question, so an author can see which real
``Organization`` rows a prompt resolves against without leaving the page.
Task 8 fills out the right rail: live-match lines an author can click through
to the group's own admin page, a placeholder count, how many open Vacancies
this route can reach today, a set of authoring checks, and backlog counts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from evennia.accounts.models import AccountDB

from world.character_creation.constants import AnchorSource, QuestionKind
from world.character_creation.models import (
    CharacterDraft,
    DistinctionOffer,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)
from world.character_creation.serializers import _batch_listed_groups, _batch_pool_groups
from world.distinctions.models import Distinction
from world.roster.models import Family
from world.societies.vacancy_services import reachable_vacancies

if TYPE_CHECKING:
    from world.character_creation.models import OriginTemplate
    from world.societies.models import Organization

logger = logging.getLogger(__name__)

#: A group named this way is a stand-in an author hasn't replaced yet
#: (``core_management.content_fixtures.PLACEHOLDER_MARK``'s convention).
_PLACEHOLDER_MARK = "PLACEHOLDER"

#: ``LivePanel.open_places`` when ``reachable_vacancies`` can't be evaluated -
#: a proper module-level constant rather than a bare literal (repo's
#: no-bare-string-identifiers rule).
OPEN_PLACES_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LivePanel:
    """The Builder page's right rail: live matches, checks, and backlog counts.

    ``groups_by_slot`` and ``placeholder_counts`` are keyed by
    ``OriginTemplateSlot.pk``. ``open_places`` is the count of Vacancies this
    route can reach today, or the string ``"unavailable"`` when
    ``reachable_vacancies`` can't be evaluated (draft resolution needs a
    ``selected_area``, which an in-progress route may not have set yet).
    ``checks`` is every authoring-time finding, ``("ok"|"warn", text)``.
    """

    groups_by_slot: dict[int, list[Organization]] = field(default_factory=dict)
    placeholder_counts: dict[int, int] = field(default_factory=dict)
    open_places: int | str = 0
    checks: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_placeholders(self) -> int:
        """Every placeholder group matched anywhere on the route, for the rail's stat tile."""
        return sum(self.placeholder_counts.values())


def _matched_groups(slots: list[OriginTemplateSlot]) -> dict[int, list[Organization]]:
    """Groups every GROUP question offers, batched across the whole template.

    SAME_AS, SERVED_HOUSE and OWN_FAMILY need a draft to resolve against and
    are left empty here (draft-time-only sources); POOL and LISTED are
    resolved with the same batched helpers ``CGOriginTemplateSerializer`` uses
    (one query per source for the whole template, not one per slot) rather
    than ``questionnaire.resolve_groups`` in a loop.
    """
    batched = {**_batch_listed_groups(slots), **_batch_pool_groups(slots)}
    return {slot.pk: batched.get(slot.pk, []) for slot in slots if slot.kind == QuestionKind.GROUP}


def _placeholder_counts(groups_by_slot: dict[int, list[Organization]]) -> dict[int, int]:
    return {
        slot_id: sum(1 for org in orgs if _PLACEHOLDER_MARK in org.name)
        for slot_id, orgs in groups_by_slot.items()
    }


def _open_places(template: OriginTemplate, user: AccountDB) -> int | str:
    """Open Vacancies this route can reach today, or ``OPEN_PLACES_UNAVAILABLE`` on failure.

    Built on an unsaved ``CharacterDraft`` - never written to the database -
    the same shape ``reachable_vacancies`` expects from the guided flow. An
    in-progress route with no ``beginning``/``starting_area`` set yet, a bad
    queryset evaluation, or an odd ``account.trust`` all degrade this one
    rail tile rather than 500ing the whole Builder page (#3660 review Ruling
    I, amended): concrete exception classes only, never a blind catch-all
    (the repo's broad-except ratchet count may only go down, so a new site
    here is not allowed regardless of justification).
    """
    try:
        draft = CharacterDraft(
            selected_origin_template=template,
            selected_area=template.beginning.starting_area,
            account=user,
        )
        return reachable_vacancies(draft).count()
    except (DatabaseError, ObjectDoesNotExist, AttributeError, ValueError, TypeError) as exc:
        logger.warning("Open places unavailable for Upbringing %s: %s", template.pk, exc)
        return OPEN_PLACES_UNAVAILABLE


def _slots_with_branch_choices(template_id: int) -> set[int]:
    """Slot ids with a non-empty ``shown_for_choices``, one flat query over the M2M."""
    through = OriginTemplateSlot.shown_for_choices.through
    return set(
        through.objects.filter(origintemplateslot__template_id=template_id)
        .values_list("origintemplateslot_id", flat=True)
        .distinct()
    )


def _source_checks(
    slot: OriginTemplateSlot, placeholder_counts: dict[int, int]
) -> list[tuple[str, str]]:
    if slot.anchor_source:
        checks = [("ok", f"'{slot.name}' has a group source.")]
    else:
        checks = [("warn", f"'{slot.name}' is a group question with no group source set.")]
    count = placeholder_counts.get(slot.pk, 0)
    if slot.anchor_source == AnchorSource.POOL and count:
        checks.append(("warn", f"'{slot.name}' pool includes {count} placeholder group(s)."))
    return checks


def _link_checks(slot: OriginTemplateSlot, position: dict[int, int]) -> list[tuple[str, str]]:
    """``same_anchor_as``/``follow_up_to`` each point at an earlier question, or a warn."""
    checks: list[tuple[str, str]] = []
    for target_id, label in (
        (slot.same_anchor_as_id, "Same group as / belongs to"),
        (slot.follow_up_to_id, "Shown after"),
    ):
        if target_id is None:
            continue
        if target_id in position and position[target_id] < position[slot.pk]:
            checks.append(("ok", f"'{slot.name}': {label} points at an earlier question."))
        else:
            checks.append(
                ("warn", f"'{slot.name}': {label} does not point at an earlier question.")
            )
    return checks


def _branch_check(slot: OriginTemplateSlot, branch_slot_ids: set[int]) -> list[tuple[str, str]]:
    """A branch condition with no follow-up target to gate it is a warn.

    The reverse - a follow-up with no branch condition - is fine (shown for
    whatever the answer was), so this only ever emits a warning, never an ok.
    """
    if slot.follow_up_to_id is None and slot.pk in branch_slot_ids:
        return [
            (
                "warn",
                f"'{slot.name}' only shows for certain answers but has no follow-up target set.",
            )
        ]
    return []


def _distinction_checks(template: OriginTemplate) -> list[tuple[str, str]]:
    """Every offered Distinction is active, or a warn; one flat query (#3675).

    Scoped to active answers only - an inactive answer is never offered to a
    player, so a Distinction offered through it is not this route's problem
    (mirrors ``CGOriginTemplateSerializer.get_slots``'s own ``is_active=True``
    filter on choices, #3660 review Ruling 2).
    """
    checks: list[tuple[str, str]] = []
    offers = DistinctionOffer.objects.filter(
        origin_choice__slot__template=template,
        origin_choice__is_active=True,
        is_active=True,
    ).select_related("distinction", "origin_choice")
    for offer in offers:
        dist = offer.distinction
        choice_name = offer.origin_choice.name
        if dist.is_active:
            checks.append(("ok", f"'{choice_name}' grants '{dist.name}', which is active."))
        else:
            checks.append(("warn", f"'{choice_name}' grants '{dist.name}', which is inactive."))
    return checks


def _closed_contradiction_checks(template: OriginTemplate) -> list[tuple[str, str]]:
    """A distinction both closed by this route and offered by one of its own answers (#3675).

    Scoped to active answers/offers only, matching every other check here - an
    inactive row is never reached by a player either way, so it is not this
    route's contradiction to flag.
    """
    closed_ids = set(template.closed_distinctions.values_list("id", flat=True))
    if not closed_ids:
        return []
    offered_ids = set(
        DistinctionOffer.objects.filter(
            origin_choice__slot__template=template,
            origin_choice__is_active=True,
            is_active=True,
            distinction_id__in=closed_ids,
        ).values_list("distinction_id", flat=True)
    )
    if not offered_ids:
        return []
    names = Distinction.objects.filter(id__in=offered_ids).values_list("name", flat=True)
    return [
        ("warn", f"'{name}' is both closed by this route and offered by one of its answers.")
        for name in names
    ]


def _closed_reason_check(template: OriginTemplate) -> list[tuple[str, str]]:
    """A non-empty closed list with no line for the player to read is a warn (#3675)."""
    if template.closed_distinctions.exists() and not template.closed_reason:
        return [("warn", "This route closes distinctions but has no line for the player to read.")]
    return []


def _own_family_house_check(
    template: OriginTemplate, slots: list[OriginTemplateSlot], position: dict[int, int]
) -> list[tuple[str, str]]:
    """OWN_FAMILY GROUP questions warn when a claimable family has no house (#3660 ruling L).

    The own-family GROUP source resolves through ``house_for_family`` (the family's
    first ``Organization``, ``questionnaire.resolve_groups``), so any playable family
    this Upbringing's claim path can offer with no house at all leaves the question
    unresolvable for whoever claims it. At most two queries regardless of how many
    OWN_FAMILY questions the template has: the claimable families, and whether any of
    them lacks a house.
    """
    own_family_slots = [
        slot
        for slot in slots
        if slot.kind == QuestionKind.GROUP and slot.anchor_source == AnchorSource.OWN_FAMILY
    ]
    if not own_family_slots:
        return []
    claimable = Family.objects.filter(is_playable=True)
    kind_ids = list(template.claimable_kinds.values_list("id", flat=True))
    if kind_ids:
        claimable = claimable.filter(kind_id__in=kind_ids)
    if not claimable.filter(organizations__isnull=True).exists():
        return []
    return [
        (
            "warn",
            f"Question {position[slot.pk] + 1}: some claimable families have no house; "
            "the own-family group cannot resolve for them.",
        )
        for slot in own_family_slots
    ]


def _checks(
    template: OriginTemplate,
    slots: list[OriginTemplateSlot],
    placeholder_counts: dict[int, int],
) -> list[tuple[str, str]]:
    position = {slot.pk: index for index, slot in enumerate(slots)}
    branch_slot_ids = _slots_with_branch_choices(template.id)
    checks: list[tuple[str, str]] = []
    for slot in slots:
        if slot.kind == QuestionKind.GROUP:
            checks.extend(_source_checks(slot, placeholder_counts))
        checks.extend(_link_checks(slot, position))
        checks.extend(_branch_check(slot, branch_slot_ids))
    checks.extend(_own_family_house_check(template, slots, position))
    checks.extend(_distinction_checks(template))
    checks.extend(_closed_contradiction_checks(template))
    checks.extend(_closed_reason_check(template))
    return checks


def for_template(template: OriginTemplate, user: AccountDB) -> LivePanel:
    """The full right-rail live panel for ``template``: matches, checks, open places."""
    slots = list(template.slots.order_by("sort_order", "id"))
    groups_by_slot = _matched_groups(slots)
    placeholder_counts = _placeholder_counts(groups_by_slot)
    return LivePanel(
        groups_by_slot=groups_by_slot,
        placeholder_counts=placeholder_counts,
        open_places=_open_places(template, user),
        checks=_checks(template, slots, placeholder_counts),
    )


def rail_counts(template: OriginTemplate) -> dict[str, int | str]:
    """Backlog counts for the right rail: questions, groups, people, answers, cost spread.

    "Cheapest complete answer" / "dearest" / "largest refund" are computed over
    required questions that have at least one answer: the sum of each such
    question's cheapest answer (``cost_for(0)`` - influence 0, since no draft
    exists here) is the cheapest total; the sum of each's dearest answer is the
    dearest total. A negative cheapest total means some required answers are
    refunds; ``largest_refund`` is that shortfall's magnitude, or 0.

    Every count here is scoped to active answers (``is_active=True``) - an
    inactive answer is never offered to a player, so it counts toward none of
    "answers", "distinctions used", or the cost spread (mirrors
    ``CGOriginTemplateSerializer.get_slots``'s own choices filter, #3660
    review Ruling 2). "Distinctions used" counts distinct active
    ``DistinctionOffer`` rows opened by this template's active answers
    (#3675), scoped by both the offer's own ``is_active`` and its
    ``origin_choice``'s. "Closed by this route" is the route's own
    ``closed_distinctions`` M2M count - unrelated to activity on any answer.
    """
    slots = list(OriginTemplateSlot.objects.filter(template=template).order_by("sort_order", "id"))
    choices = list(
        OriginTemplateSlotChoice.objects.filter(slot__in=slots, is_active=True).select_related(
            "slot"
        )
    )
    choices_by_slot: dict[int, list[OriginTemplateSlotChoice]] = defaultdict(list)
    for choice in choices:
        choices_by_slot[choice.slot_id].append(choice)

    distinctions_used = (
        DistinctionOffer.objects.filter(
            origin_choice__slot__template=template,
            origin_choice__is_active=True,
            is_active=True,
        )
        .values("distinction")
        .distinct()
        .count()
    )

    cheapest_total = 0
    dearest_total = 0
    for slot in slots:
        if not slot.is_required:
            continue
        slot_choices = choices_by_slot.get(slot.pk)
        if not slot_choices:
            continue
        costs = [choice.cost_for(0) for choice in slot_choices]
        cheapest_total += min(costs)
        dearest_total += max(costs)

    return {
        "questions": len(slots),
        "groups_asked_about": sum(1 for slot in slots if slot.kind == QuestionKind.GROUP),
        "people_named": sum(1 for slot in slots if slot.kind == QuestionKind.PERSON),
        "answers": len(choices),
        "distinctions_used": distinctions_used,
        "closed_distinctions": template.closed_distinctions.count(),
        "cheapest_complete_answer": cheapest_total,
        "dearest_complete_answer": dearest_total,
        "largest_refund": max(0, -cheapest_total),
    }
