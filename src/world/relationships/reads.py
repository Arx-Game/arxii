"""Per-audience reads of one side of a tie (#3957). Writes live in services.py.

``build_tie_page`` is the batched entry point both the tie API's ``list`` and the sheet's
Ties cast share (#3957 review): it shapes a whole page of sides for one viewer in a small,
page-size-independent query budget, rather than the per-side reads below (``visible_labels``,
``depth_breakdown``) firing once per row. Single-row callers (``retrieve``, ``stream``) may
still use the per-side functions directly, or ``build_tie_page`` with a one-element list —
either is the same query cost for one row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, Q

from world.relationships.constants import KNOWN_AWARENESS, LabelAwareness, TieAudience
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipLabel,
    RelationshipTier,
    RelationshipType,
)
from world.relationships.types import DepthBreakdown, TieStreamItem

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet


def tie_audience(
    side: CharacterRelationship, viewer_sheet: CharacterSheet | None, is_staff: bool
) -> str:
    if is_staff:
        return TieAudience.STAFF
    if viewer_sheet is None:
        return TieAudience.THIRD_PARTY
    if viewer_sheet.pk == side.source_id:
        return TieAudience.OWNER
    if side.target_id is not None and viewer_sheet.pk == side.target_id:
        return TieAudience.OTHER_SIDE
    return TieAudience.THIRD_PARTY


def third_party_can_see(side: CharacterRelationship) -> bool:
    """A tie with no Public unended label is absent for everyone but the two parties."""
    return side.labels.filter(ended_at__isnull=True, awareness=LabelAwareness.PUBLIC).exists()


def has_open_public_label(labels: Iterable[RelationshipLabel]) -> bool:
    """Pure-Python sibling of ``third_party_can_see`` for an already-loaded label list (#3957)."""
    return any(
        label.ended_at is None and label.awareness == LabelAwareness.PUBLIC for label in labels
    )


def _labels_for_audience(
    labels: Iterable[RelationshipLabel], audience: str
) -> list[RelationshipLabel]:
    """Owner and staff: all (ended ones too, as former). Other side: known. Third party: public."""
    if audience in (TieAudience.OWNER, TieAudience.STAFF):
        return list(labels)
    if audience == TieAudience.OTHER_SIDE:
        return [label for label in labels if label.awareness in KNOWN_AWARENESS]
    return [label for label in labels if label.awareness == LabelAwareness.PUBLIC]


def visible_labels(side: CharacterRelationship, audience: str) -> list[RelationshipLabel]:
    """Query one side's labels and filter them for one audience (single-row reads)."""
    qs = side.labels.select_related("type", "type__counterpart", "replaced__type").order_by("since")
    return _labels_for_audience(qs, audience)


def _replaced_type_name(label: RelationshipLabel, audience: str) -> str | None:
    """The label's replaced type's name, or None (#3957 review).

    A shift's PRIOR label can be more private than the current one (e.g. Private ->
    Public), so naming it unconditionally would leak something the audience was never
    shown. Requires ``replaced__type`` to have been select_related — an unfetched
    ``label.replaced`` would otherwise cost one query per label.
    """
    replaced = label.replaced
    if replaced is None:
        return None
    if audience in (TieAudience.OWNER, TieAudience.STAFF):
        return replaced.type.name
    allowed = (LabelAwareness.PUBLIC,) if audience == TieAudience.THIRD_PARTY else KNOWN_AWARENESS
    return replaced.type.name if replaced.awareness in allowed else None


def label_payload(label: RelationshipLabel, audience: str, *, is_mutual: bool) -> dict[str, Any]:
    """The flat dict shape ``RelationshipLabelSerializer`` reads (#3957).

    Never stamps ``is_mutual`` (or anything else) onto the idmapper-shared
    ``RelationshipLabel`` instance itself — the row is a plain dict, computed fresh per
    request. ``note`` is owner/staff-only (#3957 review); everyone else gets an empty string.
    """
    owner_or_staff = audience in (TieAudience.OWNER, TieAudience.STAFF)
    return {
        "id": label.pk,
        "type": label.type_id,
        "type_name": label.type.name,
        "type_family": label.type.family,
        "type_valence": label.type.valence,
        "awareness": label.awareness,
        "since": label.since,
        "ended_at": label.ended_at,
        "replaced_type_name": _replaced_type_name(label, audience),
        "note": label.note if owner_or_staff else "",
        "is_mutual": is_mutual,
    }


def _label_counts_as_known(label: RelationshipLabel, type_id: int, allowed: set[str]) -> bool:
    """One label of the matching, unended, sufficiently-aware type, declared under a tenure
    that is still open (#3957 review) — the exact per-label test ``services.known_label_q``
    runs in SQL, mirrored here for the batched Python path.
    """
    return (
        label.type_id == type_id
        and label.ended_at is None
        and label.awareness in allowed
        and label.declared_by_tenure_id is not None
        and label.declared_by_tenure.end_date is None
    )


def _labels_are_mutual(  # noqa: PLR0913 - both sides' row + labels is the spec, not excess
    side: CharacterRelationship,
    my_labels: Iterable[RelationshipLabel],
    reverse: CharacterRelationship | None,
    their_labels: Iterable[RelationshipLabel],
    label_type: RelationshipType,
    *,
    public_only: bool,
) -> bool:
    """Pure-Python sibling of ``services.is_mutual`` for two already-loaded label lists.

    Used by the batched page read, where both sides' labels are already prefetched — this
    avoids the one-query-per-label cost ``services.is_mutual`` pays for a single-row read.
    Mirrors ``services.is_mutual``/``known_label_q`` exactly (#3957 review — the two
    spellings must never drift): both labels need an open ``declared_by_tenure``, and BOTH
    side rows (this side and its reverse) must be ``is_active`` — a frozen side or a label
    declared under a tenure that has since ended never counts, however public the label.
    ``my_labels``/``their_labels`` should carry ``select_related("declared_by_tenure")`` (a
    label without it still works, just at one query per label the first time it's touched).
    """
    if not side.is_active or reverse is None or not reverse.is_active:
        return False
    allowed = {LabelAwareness.PUBLIC} if public_only else set(KNOWN_AWARENESS)
    counterpart = label_type.counterpart_or_self
    mine = any(_label_counts_as_known(label, label_type.pk, allowed) for label in my_labels)
    theirs = any(_label_counts_as_known(label, counterpart.pk, allowed) for label in their_labels)
    return mine and theirs


def _depth_breakdown_from(
    side: CharacterRelationship, other: CharacterRelationship | None, audience: str
) -> DepthBreakdown | None:
    if audience == TieAudience.THIRD_PARTY:
        return None
    owner_or_staff = audience in (TieAudience.OWNER, TieAudience.STAFF)
    return DepthBreakdown(
        tier=side.tier,
        scenes=side.scene_depth,
        invested=side.invested_depth,
        their_added_depth=other.depth if other is not None else 0,
        affection=side.affection if owner_or_staff else None,
        conflict=side.conflict if owner_or_staff else None,
    )


def depth_breakdown(side: CharacterRelationship, audience: str) -> DepthBreakdown | None:
    if audience == TieAudience.THIRD_PARTY:
        return None
    return _depth_breakdown_from(side, side.reverse, audience)


def resolve_viewer_sheet(request: Any) -> CharacterSheet | None:
    """The caller's currently selected character's sheet, or None (plays nobody) (#3957).

    Shared by the tie API (``CharacterRelationshipViewSet``) and the character sheet's Ties
    cast (``_build_ties``) — both need "who is looking, as which of their own characters".
    """
    if request is None:
        return None
    from world.roster.services.selection import character_for_request  # noqa: PLC0415

    actor = character_for_request(request, entry_id=None)
    if actor is None:
        return None
    try:
        return actor.sheet_data
    except ObjectDoesNotExist:
        return None


def entry_id_for(sheet: CharacterSheet | None) -> int | None:
    """The sheet's ``RosterEntry`` pk, or None (no roster row, e.g. a test/NPC sheet) (#3957).

    ``CharacterSheet`` has no ``roster_entry_id`` column of its own — ``roster_entry`` is the
    reverse side of ``RosterEntry.character_sheet`` — so this reads the safe ``*_or_none``
    accessor rather than a nonexistent shortcut attribute.
    """
    if sheet is None:
        return None
    entry = sheet.roster_entry_or_none
    return entry.pk if entry is not None else None


def labels_by_relationship_id(
    relationship_ids: Iterable[int], *, open_only: bool = False
) -> dict[int, list[RelationshipLabel]]:
    """Every side's labels in ONE query, keyed by relationship id (#3957 final review).

    The per-request alternative to ``prefetch_related("labels")`` for callers that only
    need to render labels. A prefetch — bare string or ``Prefetch`` without ``to_attr``
    alike — writes ``_prefetched_objects_cache["labels"]`` onto the
    ``CharacterRelationship`` instance, which is idmapper-shared and outlives the request:
    every later reader of ``side.labels.all()`` in the process is then served whatever this
    request cached, with no query to make the staleness visible. A plain batched query has
    no such cache and cannot leak.

    Rows come back in ``RelationshipLabel.Meta.ordering``'s ``since`` order, so a caller
    after the earliest open label takes the first hit with ``open_only=True``.
    """
    ids = list(relationship_ids)
    if not ids:
        return {}
    labels = RelationshipLabel.objects.filter(relationship_id__in=ids).select_related("type")
    if open_only:
        labels = labels.filter(ended_at__isnull=True)
    by_id: dict[int, list[RelationshipLabel]] = {}
    for label in labels:
        by_id.setdefault(label.relationship_id, []).append(label)
    return by_id


def build_tie_page(
    sides: list[CharacterRelationship],
    *,
    viewer_sheet: CharacterSheet | None,
    is_staff: bool,
    force_audience: str | None = None,
    include_allocation: bool = True,
) -> list[dict[str, Any]]:
    """Shape a whole page of sides for one viewer, in a small page-size-independent query
    budget (#3957 review — batches what per-side reads used to do once per row).

    Exactly three extra queries total, regardless of page size: the reverse sides (for
    ``pair_depth``/``their_added_depth`` and mutuality), every side's newest open thread, and
    the tier ladder. Callers should already have ``sides`` carrying, per side, a labels
    prefetch (``Prefetch("labels", queryset=RelationshipLabel.objects.select_related("type",
    "type__counterpart", "replaced__type", "declared_by_tenure"))``, ordered by ``since``) and
    ``select_related("target", "target_companion")`` — ``allocation`` too, when
    ``include_allocation`` is left at its default (an OWNER/STAFF-visible ``ap_this_week``).
    The labels prefetch is REQUIRED, not an optimisation (#3957 final review): a side is
    idmapper-shared, so a caller that passes un-prefetched sides does not fall back to a
    per-side query — ``side.labels.all()`` serves whatever an earlier request left in that
    instance's ``_prefetched_objects_cache``, silently and with no query to notice it by.
    Pass ``include_allocation=False`` when the caller's output
    shape has no per-side AP field (the sheet's Ties cast) to skip the lookup entirely rather
    than fetch-and-discard it.

    Returns one dict per side: ``side`` (the model instance, never mutated), ``audience``,
    ``labels`` (a list of ``label_payload`` dicts), ``depth``, ``tier``,
    ``next_tier_threshold``, ``breakdown``, ``ap_this_week``, ``thread``
    (``{"level":..,"resonance_name":..}`` or None).
    """
    reverse_by_pair = _reverse_sides_by_pair(sides)
    threads_by_side = _newest_open_thread_by_side(sides)
    tiers_by_number = {tier.tier_number: tier for tier in RelationshipTier.objects.all()}

    rows: list[dict[str, Any]] = []
    for side in sides:
        audience = force_audience or tie_audience(side, viewer_sheet, is_staff)
        numbers = audience != TieAudience.THIRD_PARTY
        reverse = (
            reverse_by_pair.get((side.target_id, side.source_id))
            if side.target_id is not None
            else None
        )
        rows.append(
            _tie_page_row(
                side,
                reverse=reverse,
                audience=audience,
                next_tier=tiers_by_number.get(side.tier + 1) if numbers else None,
                thread=threads_by_side.get(side.pk) if numbers else None,
                include_allocation=include_allocation,
            )
        )
    return rows


def _reverse_sides_by_pair(
    sides: list[CharacterRelationship],
) -> dict[tuple[int, int], CharacterRelationship]:
    """The other side of every tie on the page, in ONE query, keyed on the (source, target)
    PAIR (#3957 review).

    No is_active filter (spec Decision 2): a frozen side takes no credit of either kind
    until reactivated, but it KEEPS the depth it already earned — displayed
    depth/breakdown.their_added_depth must match the model's own unfiltered
    ``pair_depth()``, which ``services.advance_tier`` also gates on. Mutuality is the one
    thing that DOES require both sides active, and that check lives inside
    ``_labels_are_mutual`` itself (``reverse.is_active``), not here.

    Keyed on the pair, not on source alone: two of the caller's own owned characters can
    each hold a side toward the same target, and both reverse rows then share one
    ``source_id`` — a source-only key would collide and hand one row the other's
    depth and labels.
    """
    pair_q = Q()
    for side in sides:
        if side.target_id is not None:
            pair_q |= Q(source_id=side.target_id, target_id=side.source_id)
    if not pair_q:
        return {}
    reverse_sides = CharacterRelationship.objects.filter(pair_q).prefetch_related(
        # Why this is suppressed (#3957 review): a Prefetch without to_attr writes
        # _prefetched_objects_cache["labels"] onto an idmapper-shared side exactly as a
        # bare string does. Contained because every reader re-prefetches on the queryset
        # it reads from; never read .labels.all() off a side this queryset did not load.
        Prefetch(  # noqa: PREFETCH_STRING - re-prefetched on every queryset that reads it
            "labels",
            queryset=RelationshipLabel.objects.select_related(
                "type", "type__counterpart", "declared_by_tenure"
            ),
        )
    )
    return {(r.source_id, r.target_id): r for r in reverse_sides}


def _newest_open_thread_by_side(sides: list[CharacterRelationship]) -> dict[int, Any]:
    """Each side's highest-level open thread, in ONE query for the whole page (#3957)."""
    from world.magic.models import Thread  # noqa: PLC0415

    threads_by_side: dict[int, Thread] = {}
    for thread in (
        Thread.objects.filter(target_relationship__in=sides, retired_at__isnull=True)
        .select_related("resonance")
        .order_by("-level")
    ):
        threads_by_side.setdefault(thread.target_relationship_id, thread)
    return threads_by_side


def _tie_page_row(  # noqa: PLR0913 - one row needs its side, its pair and the page's batches
    side: CharacterRelationship,
    *,
    reverse: CharacterRelationship | None,
    audience: str,
    next_tier: RelationshipTier | None,
    thread: Any | None,
    include_allocation: bool,
) -> dict[str, Any]:
    """One side's row of ``build_tie_page``'s output, for an audience already decided.

    Takes ``next_tier`` and ``thread`` already resolved (and already nulled for a
    THIRD_PARTY by the caller) rather than the page's maps: the numbers gate is one
    decision, made once per side where the audience is known, not re-asked per field.
    """
    numbers = audience != TieAudience.THIRD_PARTY
    my_labels = list(side.labels.all())
    their_labels = list(reverse.labels.all()) if reverse is not None else []
    label_rows = [
        label_payload(
            label,
            audience,
            is_mutual=(
                label.ended_at is None
                and _labels_are_mutual(
                    side,
                    my_labels,
                    reverse,
                    their_labels,
                    label.type,
                    public_only=audience == TieAudience.THIRD_PARTY,
                )
            ),
        )
        for label in _labels_for_audience(my_labels, audience)
    ]
    ap_this_week = None
    if include_allocation and audience in (TieAudience.OWNER, TieAudience.STAFF):
        try:
            ap_this_week = side.allocation.ap_amount
        except ObjectDoesNotExist:
            ap_this_week = None
    # A plain statement rather than a conditional inside the payload's conditional: the
    # pair's depth is one idea, and reading it took two nested ternaries to see (#3957 CI
    # round, Sonar MAJOR).
    their_added_depth = reverse.depth if reverse is not None else 0
    pair_depth = side.depth + their_added_depth
    thread_payload = (
        {"level": thread.level, "resonance_name": thread.resonance.name}
        if thread is not None
        else None
    )
    return {
        "side": side,
        "audience": audience,
        "labels": label_rows,
        "depth": pair_depth if numbers else None,
        "tier": side.tier if numbers else None,
        "next_tier_threshold": next_tier.depth_threshold if next_tier else None,
        "breakdown": _depth_breakdown_from(side, reverse, audience),
        "ap_this_week": ap_this_week,
        "thread": thread_payload,
    }


def tie_stream(
    side: CharacterRelationship,
    viewer_sheet: CharacterSheet | None,
    is_staff: bool,
    *,
    account: AccountDB | None,
) -> list[TieStreamItem]:
    """Entries by either side about the other + scenes both took part in, both gated.

    Both halves are visibility-filtered, and each through its own app's single source of
    truth: journals through ``visible_entries_q``, scenes through
    ``Scene.objects.viewable_by(account)`` (#3957 final review — the scene half used to
    list every shared scene regardless of ``ScenePrivacyMode``, so a stranger who could
    see one public label learned that the two had been alone together). ``account`` is
    the VIEWER's account, required rather than defaulted: ``None`` is the anonymous
    audience and sees public scenes only. Staff visibility is ``viewable_by``'s own rule,
    never a second one here, and ``is_public`` is each scene's own privacy mode.

    ``capstone_tier`` is null for a THIRD_PARTY audience — the tier number is the kind of
    numeric relationship state a stranger never sees — but ``is_capstone`` stays visible
    regardless: a stranger may see THAT an entry marked a capstone, just not which tier
    (#3957 review).
    """
    from world.journals.models import JournalEntry  # noqa: PLC0415
    from world.journals.services import visible_entries_q  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    if side.target_id is None:
        return []
    a, b = side.source_id, side.target_id
    numbers = tie_audience(side, viewer_sheet, is_staff) != TieAudience.THIRD_PARTY
    entries = (
        JournalEntry.objects.filter(visible_entries_q(viewer_sheet=viewer_sheet, is_staff=is_staff))
        .filter(Q(author_id=a, about_id=b) | Q(author_id=b, about_id=a), parent__isnull=True)
        .select_related("author__character")
        .order_by("-created_at")
    )
    capstone_by_entry = {
        c.journal_entry_id: c.tier_claimed
        for c in RelationshipCapstone.objects.filter(
            journal_entry__in=entries, relationship__source_id__in=(a, b)
        )
    }
    items: list[TieStreamItem] = [
        TieStreamItem(
            kind="entry",
            id=e.pk,
            title=e.title,
            author_id=e.author_id,
            author_name=e.author.character.db_key,
            body=e.body,
            is_public=e.is_public,
            is_capstone=e.pk in capstone_by_entry,
            capstone_tier=capstone_by_entry.get(e.pk) if numbers else None,
            created_at=e.created_at.isoformat(),
            ic_timestamp=e.ic_timestamp.isoformat() if e.ic_timestamp else None,
        )
        for e in entries
    ]
    scenes = (
        Scene.objects.viewable_by(account)
        .filter(interactions__persona__character_sheet_id=a)
        .filter(interactions__persona__character_sheet_id=b)
        .distinct()
        .order_by("-date_started")
    )
    items.extend(
        TieStreamItem(
            kind="scene",
            id=s.pk,
            title=s.name,
            author_id=None,
            author_name="",
            body="",
            is_public=s.is_public,
            is_capstone=False,
            capstone_tier=None,
            created_at=s.date_started.isoformat(),
            ic_timestamp=None,
        )
        for s in scenes
    )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items
