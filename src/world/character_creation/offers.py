"""Which distinctions a draft can pick where, and the picks its choices carry (#3675).

One authored ``DistinctionOffer`` row per place a distinction is shown. This module
is the only reader: ``offers_for`` lists a chapter's priced choices, ``closed_for``
the route's closed list, and ``reconcile_offer_picks`` applies carried and bundled
offers and removes picks whose offer has gone.
"""

from __future__ import annotations

from world.character_creation.constants import OfferArrival, OfferChapter, TraditionState
from world.character_creation.models import (
    BeginningTradition,
    CharacterDraft,
    DistinctionOffer,
    TraditionStateLine,
)
from world.character_creation.questionnaire import DraftAnswers, visible_slot_ids
from world.character_creation.types import ClosedDistinction, VisibleOffer
from world.distinctions.models import Distinction
from world.distinctions.types import DraftDistinctionEntry, build_distinction_entry


def _slate_line(draft: CharacterDraft) -> BeginningTradition | None:
    """The draft's picked tradition's row on its Beginning's slate, if any.

    Called by ``_context`` (to gate Tradition Step offers) and ``_carried_offer``
    (to find the state whose drawback the pick carries).
    """
    if draft.selected_beginnings_id is None or draft.selected_tradition_id is None:
        return None
    return next(
        (
            bt
            for bt in draft.selected_beginnings.cached_beginning_traditions
            if bt.tradition_id == draft.selected_tradition_id
        ),
        None,
    )


def _opener_satisfied(offer: DistinctionOffer, ctx: dict) -> bool:
    """Whether the draft has satisfied this offer's opener.

    Called by ``visible_offers`` for every active offer row. ``ctx`` (built by
    ``_context``) already carries every piece of draft state an opener check needs.
    """
    chapter = OfferChapter(offer.chapter)
    if chapter == OfferChapter.GLIMPSE:
        return offer.glimpse_tag_id in ctx["tag_ids"]
    if chapter == OfferChapter.LINEAGE:
        return offer.origin_choice_id in ctx["choice_ids"]
    if chapter == OfferChapter.TRADITION_STEP:
        line = ctx["slate_line"]
        return line is not None and line.state == TraditionState.LIVING_MASTERS
    return True


def _context(draft: CharacterDraft) -> dict:
    """The draft state every opener check needs, computed once per call.

    Called by ``visible_offers``.
    """
    answers = DraftAnswers.from_draft(draft)
    visible = visible_slot_ids(draft)
    return {
        "tag_ids": set(draft.draft_data.get("glimpse_tag_ids", [])),
        "choice_ids": {cid for sid, cid in answers.picks.items() if sid in visible},
        "slate_line": _slate_line(draft),
    }


def _closed_ids(draft: CharacterDraft) -> set[int]:
    """Ids the draft's route has closed. Called by ``visible_offers``."""
    route = draft.selected_origin_template
    if route is None:
        return set()
    return set(route.closed_distinctions.values_list("id", flat=True))


def _innate_ids(draft: CharacterDraft) -> set[int]:
    """Ids granted automatically by the draft's species. Called by ``visible_offers``."""
    if draft.selected_species_id is None:
        return set()
    from world.species.services import species_innate_distinction_ids  # noqa: PLC0415

    return set(species_innate_distinction_ids(draft.selected_species))


def visible_offers(draft: CharacterDraft) -> dict[int, DistinctionOffer]:
    """Every active offer whose opener the draft satisfies, minus closed and innate.

    Called by ``offers_for`` and ``reconcile_offer_picks``.
    """
    ctx = _context(draft)
    hidden = _closed_ids(draft) | _innate_ids(draft)
    rows = DistinctionOffer.objects.filter(is_active=True).select_related(
        "distinction__category", "glimpse_tag", "origin_choice", "schooling_line"
    )
    return {o.id: o for o in rows if o.distinction_id not in hidden and _opener_satisfied(o, ctx)}


def opener_label(offer: DistinctionOffer) -> str:
    """The name of the thing that opens this offer, for display and as a source string.

    Called by ``offers_for`` (a ``VisibleOffer``'s ``opener_label``) and by
    ``reconcile_offer_picks`` / Task 3's chapter views to record an entry's source.
    """
    if offer.glimpse_tag_id:
        return offer.glimpse_tag.name
    if offer.origin_choice_id:
        return offer.origin_choice.name
    if offer.schooling_line_id:
        return offer.schooling_line.name
    return ""


def offers_for(draft: CharacterDraft, chapter: OfferChapter) -> list[VisibleOffer]:
    """The priced choices this draft can see in one chapter, with lock state.

    Called by each chapter's view/serializer to render its offer list.
    """
    held = {d["distinction_id"] for d in draft.draft_data.get("distinctions", [])}
    out: list[VisibleOffer] = []
    for offer in visible_offers(draft).values():
        if offer.chapter != chapter or offer.arrives_as != OfferArrival.CHOICE:
            continue
        dist = offer.distinction
        conflict = next((x for x in dist.mutually_exclusive_with.all() if x.id in held), None)
        out.append(
            VisibleOffer(
                offer_id=offer.id,
                distinction_id=dist.id,
                name=offer.name,
                player_line=offer.player_line,
                chapter=offer.chapter,
                arrives_as=offer.arrives_as,
                opener_label=opener_label(offer),
                cost_per_rank=dist.cost_per_rank,
                max_rank=dist.max_rank,
                is_locked=conflict is not None,
                lock_reason=f"Cannot be held with {conflict.name}" if conflict else "",
            )
        )
    out.sort(key=lambda o: o.offer_id)
    return out


def closed_for(draft: CharacterDraft) -> list[ClosedDistinction]:
    """The route's closed-distinction list, for the chapter that would have shown them.

    Called by each chapter's view/serializer alongside ``offers_for``.
    """
    route = draft.selected_origin_template
    if route is None:
        return []
    return [
        ClosedDistinction(distinction_id=d.id, name=d.name, reason=route.closed_reason)
        for d in route.closed_distinctions.all()
    ]


def entry_price(entry: DraftDistinctionEntry, distinction: Distinction) -> int:
    """The CG-point price of a draft entry: free if any source arrived bundled or carried.

    Called by ``reconcile_offer_picks`` when repricing a kept entry.
    """
    if any(a in (OfferArrival.BUNDLED, OfferArrival.CARRIED) for a in entry.get("arrivals", [])):
        return 0
    return distinction.calculate_total_cost(entry.get("rank", 1))


def _carried_offer(draft: CharacterDraft) -> tuple[TraditionStateLine, Distinction] | None:
    """The drawback the draft's tradition pick carries, and its state line, if any.

    Called by ``reconcile_offer_picks``.
    """
    line = _slate_line(draft)
    if line is None:
        return None
    state_line = TraditionStateLine.objects.filter(state=line.state).first()
    if state_line is None or state_line.carries_id is None:
        return None
    return state_line, state_line.carries


def _drop_vanished_sources(
    entries: list[DraftDistinctionEntry],
    visible: dict[int, DistinctionOffer],
    carried_key: str | None,
) -> list[str]:
    """Strip an entry's sources whose offer is no longer visible, in place.

    Called by ``reconcile_offer_picks`` before the carried/bundled offers are applied,
    so a source that vanished this call (e.g. a tradition switch) never survives
    alongside a still-live one.
    """
    changed: list[str] = []
    for entry in entries:
        srcs = entry.setdefault("sources", [])
        arrs = entry.setdefault("arrivals", [])
        ids = entry.setdefault("offer_ids", [])
        keep = [(oid in visible) or (isinstance(oid, str) and oid == carried_key) for oid in ids]
        if not all(keep):
            entry["offer_ids"] = [x for x, k in zip(ids, keep, strict=True) if k]
            entry["sources"] = [x for x, k in zip(srcs, keep, strict=True) if k]
            entry["arrivals"] = [x for x, k in zip(arrs, keep, strict=True) if k]
            changed.append(entry["distinction_name"])
    return changed


def _apply_carried(
    entries: list[DraftDistinctionEntry],
    by_dist: dict[int, DraftDistinctionEntry],
    carried: tuple[TraditionStateLine, Distinction] | None,
) -> list[str]:
    """Add or restore the tradition state's carried drawback, in place.

    Called by ``reconcile_offer_picks``. A carried drawback has no ``DistinctionOffer``
    row, so its source key is the synthetic ``"state:<TraditionState value>"`` string.
    """
    if carried is None:
        return []
    state_line, drawback = carried
    carried_key = f"state:{state_line.state}"
    entry = by_dist.get(drawback.id)
    if entry is None:
        entry = build_distinction_entry(drawback, rank=1)
        entry["offer_ids"] = [carried_key]
        entry["sources"] = [state_line.entry_line]
        entry["arrivals"] = [OfferArrival.CARRIED]
        entry["cost"] = drawback.cost_per_rank
        entries.append(entry)
        by_dist[drawback.id] = entry
        return [drawback.name]
    if carried_key not in entry["offer_ids"]:
        entry["offer_ids"].append(carried_key)
        entry["sources"].append(state_line.entry_line)
        entry["arrivals"].append(OfferArrival.CARRIED)
        return [drawback.name]
    return []


def _apply_bundled(
    entries: list[DraftDistinctionEntry],
    by_dist: dict[int, DraftDistinctionEntry],
    visible: dict[int, DistinctionOffer],
) -> list[str]:
    """Add or extend every distinction bundled free with an answer the draft holds.

    Called by ``reconcile_offer_picks``.
    """
    changed: list[str] = []
    for offer in visible.values():
        if offer.arrives_as != OfferArrival.BUNDLED:
            continue
        entry = by_dist.get(offer.distinction_id)
        if entry is None:
            entry = build_distinction_entry(
                offer.distinction, rank=1, offer=offer, source=opener_label(offer)
            )
            entries.append(entry)
            by_dist[offer.distinction_id] = entry
            changed.append(offer.distinction.name)
        elif offer.id not in entry["offer_ids"]:
            entry["offer_ids"].append(offer.id)
            entry["sources"].append(opener_label(offer))
            entry["arrivals"].append(OfferArrival.BUNDLED)
            changed.append(offer.distinction.name)
    return changed


def _drop_empty_and_reprice(
    entries: list[DraftDistinctionEntry],
) -> tuple[list[DraftDistinctionEntry], list[str]]:
    """Drop entries whose last source just vanished, and reprice every survivor.

    Called by ``reconcile_offer_picks``. A carried-only entry is priced at the
    drawback's own ``cost_per_rank`` (Decision 3 of the #3675 spec: the refund
    lands even though it wasn't a choice); everything else goes through
    ``entry_price``.
    """
    changed: list[str] = []
    kept: list[DraftDistinctionEntry] = []
    dists = Distinction.objects.in_bulk([e["distinction_id"] for e in entries])
    for entry in entries:
        if not entry["offer_ids"]:
            changed.append(entry["distinction_name"])
            continue
        dist = dists[entry["distinction_id"]]
        carried_only = OfferArrival.CARRIED in entry["arrivals"] and len(entry["arrivals"]) == 1
        price = dist.cost_per_rank if carried_only else entry_price(entry, dist)
        if price != entry.get("cost"):
            entry["cost"] = price
            if entry["distinction_name"] not in changed:
                changed.append(entry["distinction_name"])
        kept.append(entry)
    return kept, changed


def reconcile_offer_picks(draft: CharacterDraft) -> list[str]:
    """Apply carried and bundled offers, drop picks whose offer has gone, reprice.

    Called after every draft patch that could change which offers are open (a
    Glimpse tag pick, a Lineage answer, a tradition select). Returns the
    distinction names dropped or repriced. Saves ``draft_data`` when anything
    changed.
    """
    original = draft.draft_data.get("distinctions", [])
    entries: list[DraftDistinctionEntry] = list(original)
    visible = visible_offers(draft)
    by_dist = {e["distinction_id"]: e for e in entries}
    carried = _carried_offer(draft)
    carried_key = f"state:{carried[0].state}" if carried else None

    changed: list[str] = []
    changed += _drop_vanished_sources(entries, visible, carried_key)
    changed += _apply_carried(entries, by_dist, carried)
    changed += _apply_bundled(entries, by_dist, visible)
    kept, repriced = _drop_empty_and_reprice(entries)
    changed += repriced

    if kept != original or changed:
        draft.draft_data["distinctions"] = kept
        draft.save(update_fields=["draft_data"])

    # de-duplicate while keeping order
    seen: set[str] = set()
    return [n for n in changed if not (n in seen or seen.add(n))]
