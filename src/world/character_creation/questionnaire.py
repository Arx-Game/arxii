"""Evaluate an Upbringing's questionnaire against a draft (#3660).

Pure reads: which questions are shown, which groups a group question offers,
what influence prices an answer, and which Distinctions the picked answers bundle.
Models, validators, serializers and finalize all call this rather than
re-deriving the rules. A hidden question's stored answers are ignored
everywhere (the same rule the family-path switch has followed since #3617).

``anchor_for`` is the one resolver every caller uses to find the organization
behind a question's answer. A GROUP question sourced from the player's own
family or the house they served needs no ``origin_anchors`` entry at all — the
frontend cannot know the family's org id ahead of time, so ``anchor_for``
derives it from the draft itself. Validation, pricing and finalize all call
through here so the three never drift apart (#3660 controller ruling A).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from world.character_creation.constants import AnchorSource, FamilyPath, QuestionKind

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft, OriginTemplateSlot
    from world.societies.models import Organization


@dataclass(frozen=True)
class DraftAnswers:
    """The Lineage answers held in ``draft_data``, keyed by slot id (int)."""

    texts: dict[int, str] = field(default_factory=dict)
    picks: dict[int, int] = field(default_factory=dict)
    anchors: dict[int, int] = field(default_factory=dict)
    figures: dict[int, str] = field(default_factory=dict)

    @classmethod
    def from_draft(cls, draft: CharacterDraft) -> DraftAnswers:
        data = draft.draft_data

        def ints(key: str) -> dict[int, int]:
            return {int(k): int(v) for k, v in (data.get(key) or {}).items() if v is not None}

        def strs(key: str) -> dict[int, str]:
            return {int(k): str(v).strip() for k, v in (data.get(key) or {}).items()}

        return cls(
            texts=strs("origin_slots"),
            picks=ints("origin_choices"),
            anchors=ints("origin_anchors"),
            figures=strs("origin_figures"),
        )


class BundledDistinction(TypedDict):
    distinction_id: int
    name: str
    cost_per_rank: int
    secret_by_default: bool
    slot_id: int
    slot_name: str
    choice_id: int
    choice_name: str
    organization_id: int | None
    organization_name: str


def _resolve_pool_groups(slot: OriginTemplateSlot) -> list[Organization]:
    """POOL source: every active org matching the slot's type/society filters."""
    from world.societies.models import Organization  # noqa: PLC0415

    qs = Organization.objects.all()
    if slot.anchor_org_type_id:
        qs = qs.filter(org_type_id=slot.anchor_org_type_id)
    if slot.anchor_society_id:
        qs = qs.filter(society_id=slot.anchor_society_id)
    if slot.exclude_covert:
        qs = qs.exclude(org_type__is_covert=True)
    return list(qs.select_related("family").order_by("name"))


def _resolve_same_as_group(slot: OriginTemplateSlot, answers: DraftAnswers) -> list[Organization]:
    """SAME_AS source: the org answered on the earlier group question, if any."""
    from world.societies.models import Organization  # noqa: PLC0415

    org_id = answers.anchors.get(slot.same_anchor_as_id or -1)
    if org_id is None:
        return []
    org = Organization.objects.filter(pk=org_id).select_related("family").first()
    return [org] if org else []


def resolve_groups(
    slot: OriginTemplateSlot, draft: CharacterDraft, answers: DraftAnswers
) -> list[Organization]:
    """The groups a GROUP question offers this draft, in name order."""
    from world.societies.houses.services import house_for_family  # noqa: PLC0415

    if slot.kind != QuestionKind.GROUP:
        return []
    source = slot.anchor_source
    if source == AnchorSource.POOL:
        return _resolve_pool_groups(slot)
    if source == AnchorSource.LISTED:
        return list(slot.anchor_orgs.select_related("family").order_by("name"))
    if source == AnchorSource.SAME_AS:
        return _resolve_same_as_group(slot, answers)
    if source == AnchorSource.SERVED_HOUSE:
        return [draft.served_house] if draft.served_house_id else []
    if source == AnchorSource.OWN_FAMILY:
        org = house_for_family(draft.family)
        return [org] if org else []
    return []


def anchor_for(
    slot: OriginTemplateSlot, draft: CharacterDraft, answers: DraftAnswers
) -> int | None:
    """The organization id this question's answer is about, by kind (#3660 ruling A).

    A GROUP question sourced from the family or the served house has no stored
    anchor to look up — it is derived fresh from the draft each time, through
    ``resolve_groups``, so it stays correct across a family-path switch. Every
    other GROUP source (POOL, LISTED, SAME_AS) still stores the player's pick in
    ``origin_anchors``. A PERSON question that names someone inside an earlier
    group question's anchor defers to that question's own resolution.
    """
    if slot.kind == QuestionKind.GROUP:
        if slot.anchor_source in (AnchorSource.OWN_FAMILY, AnchorSource.SERVED_HOUSE):
            groups = resolve_groups(slot, draft, answers)
            return groups[0].pk if groups else None
        return answers.anchors.get(slot.id)
    if slot.kind == QuestionKind.PERSON and slot.same_anchor_as_id is not None:
        return anchor_for(slot.same_anchor_as, draft, answers)
    return None


def is_answered(
    slot: OriginTemplateSlot,
    draft: CharacterDraft,
    answers: DraftAnswers,
    choice_ids_by_slot: dict[int, set[int]],
) -> bool:
    """Whether the draft has answered ``slot`` in the way its kind needs."""
    picked = answers.picks.get(slot.id)
    valid_pick = picked is not None and picked in choice_ids_by_slot.get(slot.id, set())
    text = bool(answers.texts.get(slot.id))
    if slot.kind == QuestionKind.TEXT:
        return text
    if slot.kind == QuestionKind.PICK:
        return valid_pick or (slot.allows_text and text)
    if slot.kind == QuestionKind.PERSON:
        return bool(answers.figures.get(slot.id))
    # GROUP: an anchor, plus a stance when the question offers any
    has_anchor = anchor_for(slot, draft, answers) is not None
    if not choice_ids_by_slot.get(slot.id):
        return has_anchor
    return has_anchor and valid_pick


def is_shown(  # noqa: PLR0913 — each arg is a distinct piece of evaluation state
    slot: OriginTemplateSlot,
    path: str,
    draft: CharacterDraft,
    answers: DraftAnswers,
    shown_so_far: set[int],
    choice_ids_by_slot: dict[int, set[int]],
    branch_choice_ids: dict[int, set[int]],
    slots_by_id: dict[int, OriginTemplateSlot],
) -> bool:
    """Path scope AND (no follow-up, or its target is shown and answered, and branch matches)."""
    if slot.applies_to not in (FamilyPath.ANY, path):
        return False
    if slot.follow_up_to_id is None:
        return True
    target = slots_by_id.get(slot.follow_up_to_id)
    if target is None or target.id not in shown_so_far:
        return False
    if not is_answered(target, draft, answers, choice_ids_by_slot):
        return False
    wanted = branch_choice_ids.get(slot.id)
    if not wanted:
        return True
    return answers.picks.get(target.id) in wanted


def _load_choice_maps(
    template_id: int,
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """Two flat queries: active choice ids per slot, and branch choice ids per slot."""
    from world.character_creation.models import (  # noqa: PLC0415
        OriginTemplateSlot,
        OriginTemplateSlotChoice,
    )

    choice_ids_by_slot: dict[int, set[int]] = {}
    for slot_id, choice_id in OriginTemplateSlotChoice.objects.filter(
        slot__template_id=template_id, is_active=True
    ).values_list("slot_id", "id"):
        choice_ids_by_slot.setdefault(slot_id, set()).add(choice_id)
    branch: dict[int, set[int]] = {}
    for slot_id, choice_id in OriginTemplateSlot.shown_for_choices.through.objects.filter(
        origintemplateslot__template_id=template_id
    ).values_list("origintemplateslot_id", "origintemplateslotchoice_id"):
        branch.setdefault(slot_id, set()).add(choice_id)
    return choice_ids_by_slot, branch


def visible_slot_ids(draft: CharacterDraft) -> set[int]:
    """Ids of the questions shown to this draft, evaluated in sort order (#3660)."""
    template = draft.selected_origin_template
    if template is None:
        return set()
    path = draft.resolve_family_path()
    answers = DraftAnswers.from_draft(draft)
    slots = list(template.slots.order_by("sort_order", "id"))
    slots_by_id = {s.id: s for s in slots}
    choice_ids_by_slot, branch = _load_choice_maps(template.id)
    shown: set[int] = set()
    for slot in slots:
        if is_shown(slot, path, draft, answers, shown, choice_ids_by_slot, branch, slots_by_id):
            shown.add(slot.id)
    return shown


def question_influence(
    slot: OriginTemplateSlot, draft: CharacterDraft, answers: DraftAnswers, path: str
) -> int:
    """Influence that multiplies ``cost_per_influence`` for this question's answer.

    Resolves the GROUP anchor through ``anchor_for`` rather than reading
    ``origin_anchors`` directly, so an OWN_FAMILY/SERVED_HOUSE answer (which has
    no stored anchor) still prices against the right family (#3660 ruling A).
    """
    from world.societies.models import Organization  # noqa: PLC0415

    if slot.kind == QuestionKind.GROUP:
        org_id = anchor_for(slot, draft, answers)
        if org_id is None:
            return 0
        org = Organization.objects.filter(pk=org_id).select_related("family").first()
        return org.family.influence if org and org.family_id else 0
    if path == FamilyPath.CLAIMED and draft.family_id:
        return draft.family.influence
    return 0


def bundled_distinctions(draft: CharacterDraft) -> list[BundledDistinction]:
    """Distinctions the draft's visible, picked answers grant (#3660)."""
    from world.character_creation.models import OriginTemplateSlotChoice  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    template = draft.selected_origin_template
    if template is None:
        return []
    answers = DraftAnswers.from_draft(draft)
    visible = visible_slot_ids(draft)
    choice_ids = [cid for sid, cid in answers.picks.items() if sid in visible]
    if not choice_ids:
        return []
    rows = (
        OriginTemplateSlotChoice.objects.filter(
            pk__in=choice_ids,
            slot__template=template,
            is_active=True,
            grants_distinction__isnull=False,
        )
        .select_related("slot", "grants_distinction")
        .order_by("slot__sort_order")
    )
    org_ids = {anchor_for(c.slot, draft, answers) for c in rows} - {None}
    orgs = {o.pk: o for o in Organization.objects.filter(pk__in=org_ids)}
    out: list[BundledDistinction] = []
    for choice in rows:
        org = orgs.get(anchor_for(choice.slot, draft, answers))
        dist = choice.grants_distinction
        out.append(
            BundledDistinction(
                distinction_id=dist.id,
                name=dist.name,
                cost_per_rank=dist.cost_per_rank,
                secret_by_default=dist.secret_by_default,
                slot_id=choice.slot_id,
                slot_name=choice.slot.name,
                choice_id=choice.id,
                choice_name=choice.name,
                organization_id=org.pk if org else None,
                organization_name=org.name if org else "",
            )
        )
    return out
