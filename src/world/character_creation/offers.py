"""Which distinctions a draft can pick where, and the picks its choices carry (#3675).

One authored ``DistinctionOffer`` row per place a distinction is shown. This module
is the only reader: ``offers_for`` lists a chapter's priced choices, ``closed_for``
the route's closed list, and ``reconcile_offer_picks`` applies carried and bundled
offers and removes picks whose offer has gone.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Q

from world.character_creation.constants import (
    ActorSheetPrompt,
    OfferArrival,
    OfferChapter,
    QuestionKind,
    TraditionState,
)
from world.character_creation.models import (
    BeginningTradition,
    CharacterDraft,
    DistinctionOffer,
    OfferFirstLook,
    TraditionStateLine,
)
from world.character_creation.questionnaire import DraftAnswers, anchor_for, visible_slot_ids
from world.character_creation.types import ClosedDistinction, VisibleOffer
from world.character_sheets.types import EnemyDegree
from world.distinctions.models import Distinction, DistinctionEffect
from world.distinctions.types import DraftDistinctionEntry, build_distinction_entry

if TYPE_CHECKING:
    from world.character_creation.models import Beginnings
    from world.magic.models import Tradition
    from world.societies.models import Organization


def tradition_is_self_taught(tradition: Tradition) -> bool:
    """Whether ``tradition`` is SELF_TAUGHT on any Beginning's slate (#3675).

    Runtime code's only sanctioned way to answer "is this CG's tradition-agnostic
    default" - never a name match against "Unbound." Called by
    ``world.character_creation.services._finalize_academy_entrance_obligation``
    and ``world.progression.services.durance_registration``.
    """
    return BeginningTradition.objects.filter(
        tradition=tradition, state=TraditionState.SELF_TAUGHT
    ).exists()


def slate_state(beginning: Beginnings, tradition: Tradition) -> TraditionState | None:
    """The slate state ``tradition`` reads as on ``beginning``, if the pairing exists.

    ``None`` when the tradition isn't on this Beginning's slate at all. Callers that
    already hold a ``BeginningTradition`` row should read its ``state`` field
    directly; this is for callers that only hold the (beginning, tradition) pair.
    """
    raw = (
        BeginningTradition.objects.filter(beginning=beginning, tradition=tradition)
        .values_list("state", flat=True)
        .first()
    )
    return TraditionState(raw) if raw is not None else None


def self_taught_drawback() -> Distinction | None:
    """The drawback the SELF_TAUGHT ``TraditionStateLine`` carries, if any (#3675).

    Called by ``world.magic.services.tradition_membership._reapply_unbound_drawback``
    on leaving a tradition - the live-play "traditionless once again" re-grant, never
    a tag or slug lookup.
    """
    line = TraditionStateLine.objects.filter(state=TraditionState.SELF_TAUGHT).first()
    return line.carries if line is not None else None


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
    if chapter == OfferChapter.ACTORS_SHEET:
        # The question is always on the leaf; the prompt only says which block (#3709).
        return bool(offer.prompt)
    if chapter == OfferChapter.APPEARANCE:
        return offer.appearance_section_id is not None
    if chapter == OfferChapter.ENEMY:
        if offer.enemy_reason_id is not None:
            return offer.enemy_reason_id == ctx["enemy_reason_id"]
        return bool(offer.enemy_degree) and offer.enemy_degree == ctx["enemy_degree"]
    return False


def _context(draft: CharacterDraft) -> dict:
    """The draft state every opener check needs, computed once per call.

    Called by ``visible_offers``.
    """
    answers = DraftAnswers.from_draft(draft)
    visible = visible_slot_ids(draft)
    enemy = draft.draft_data.get("enemy") or {}
    return {
        "tag_ids": set(draft.draft_data.get("glimpse_tag_ids", [])),
        "choice_ids": {cid for sid, cid in answers.picks.items() if sid in visible},
        "slate_line": _slate_line(draft),
        # The enemy chapter's two openers (#3709): the reason picked, the degree picked.
        "enemy_reason_id": enemy.get("reason_id"),
        "enemy_degree": enemy.get("degree", ""),
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
        "distinction__category",
        "glimpse_tag",
        "origin_choice__slot",
        "schooling_line",
        "enemy_reason",
        "appearance_section",
    )
    return {o.id: o for o in rows if o.distinction_id not in hidden and _opener_satisfied(o, ctx)}


def _origin_opener_label(offer: DistinctionOffer, draft: CharacterDraft | None) -> str:
    """Return an origin choice label, including its anchored organization."""
    label = offer.origin_choice.name
    if draft is None:
        return label
    slot = offer.origin_choice.slot
    if slot.kind != QuestionKind.GROUP:
        return label
    answers = DraftAnswers.from_draft(draft)
    org_id = anchor_for(slot, draft, answers)
    if org_id is None:
        return label

    from world.societies.models import Organization  # noqa: PLC0415

    org = Organization.objects.filter(pk=org_id).first()
    return f"{label}, {org.name}" if org is not None else label


def opener_label(offer: DistinctionOffer, *, draft: CharacterDraft | None = None) -> str:
    """The name of the thing that opens this offer, for display and as a source string.

    Called by ``offers_for`` (a ``VisibleOffer``'s ``opener_label``, no ``draft`` --
    a not-yet-picked offer in the picker has nothing to anchor against) and, with
    ``draft`` given, by ``reconcile_offer_picks`` and the sync path in
    ``distinctions/views.py`` to record an entry's ``source`` / ``sources`` (review
    round 2, ruling B): the pairing table this offer replaced
    (pre-#3675 ``_grant_connection_distinctions``) recorded which GROUP answer's
    anchored organization a connection distinction was about, not just the answer's
    own name, and ``CharacterDistinction.source_description`` needs that same
    provenance. Only a LINEAGE offer on a GROUP question carries an anchor to
    resolve; every other opener is unaffected by ``draft``.
    """
    if offer.prompt:
        return ActorSheetPrompt(offer.prompt).label
    if offer.enemy_reason_id:
        return offer.enemy_reason.name
    if offer.enemy_degree:
        return EnemyDegree(offer.enemy_degree).label
    if offer.appearance_section_id:
        return offer.appearance_section.name
    if offer.glimpse_tag_id:
        return offer.glimpse_tag.name
    if offer.origin_choice_id:
        return _origin_opener_label(offer, draft)
    if offer.schooling_line_id:
        return offer.schooling_line.name
    return ""


def _mutual_exclusions(dist_ids: set[int]) -> dict[int, set[int]]:
    """Every id in ``dist_ids``'s mutual-exclusion partners, in one flat query.

    Reads the symmetrical M2M's through table directly instead of
    ``Distinction.mutually_exclusive_with.all()`` per distinction (#3675 final fix
    B2) -- never a to-attr ``Prefetch`` (ADR-0278) and never
    ``cached_mutually_exclusive_with``, both of which only help a query already
    scoped to one model's rows. Checks both through-table columns rather than
    trusting Django's symmetrical-insert behavior to have written both directions.
    Called by ``offers_for``.
    """
    if not dist_ids:
        return {}
    through = Distinction.mutually_exclusive_with.through
    rows = through.objects.filter(
        Q(from_distinction_id__in=dist_ids) | Q(to_distinction_id__in=dist_ids)
    ).values_list("from_distinction_id", "to_distinction_id")
    exclusions: dict[int, set[int]] = defaultdict(set)
    for from_id, to_id in rows:
        if from_id in dist_ids:
            exclusions[from_id].add(to_id)
        if to_id in dist_ids:
            exclusions[to_id].add(from_id)
    return exclusions


def _effect_word(effect: DistinctionEffect) -> str:
    """One effect as the leaf prints it: ``+Deception``, ``-Willpower``, ``Immune to X``."""
    name = effect.target.name.replace("_", " ").strip().capitalize()
    if effect.grants_immunity_to_negative:
        return f"Immune to negative {name}"
    value = effect.value_per_rank
    if value is None and effect.scaling_values:
        value = effect.scaling_values[0]
    if value is None and effect.amplifies_sources_by is not None:
        value = effect.amplifies_sources_by
    if value is None:
        return name
    sign = "-" if value < 0 else "+"
    return f"{sign}{name}"


def effect_line(effects: list[DistinctionEffect]) -> str:
    """The compact mechanics line under an offer, ``+Deception; -Willpower`` (#3709).

    Called by ``offers_for``. Sign and target name only: the numbers are the
    distinction's own business and the leaf is not a rules sheet.
    """
    return "; ".join(_effect_word(e) for e in effects)


def _effects_by_distinction(dist_ids: set[int]) -> dict[int, list[DistinctionEffect]]:
    out: dict[int, list[DistinctionEffect]] = defaultdict(list)
    rows = DistinctionEffect.objects.filter(distinction_id__in=dist_ids).select_related("target")
    for effect in rows.order_by("id"):
        out[effect.distinction_id].append(effect)
    return out


def _pinned_offer_ids(draft: CharacterDraft, offer_ids: set[int]) -> set[int]:
    """The offers the draft's Beginning pinned into the first look (#3709)."""
    if draft.selected_beginnings_id is None or not offer_ids:
        return set()
    rows = OfferFirstLook.objects.filter(
        beginning_id=draft.selected_beginnings_id, offer_id__in=offer_ids
    )
    return set(rows.values_list("offer_id", flat=True))


def offers_for(draft: CharacterDraft, chapter: OfferChapter) -> list[VisibleOffer]:
    """The priced choices this draft can see in one chapter, with lock state.

    Called by each chapter's view/serializer to render its offer list. Pinned
    (first look) offers sort first, then ``sort_order``, then id (#3709).
    """
    entries = {d["distinction_id"]: d for d in draft.draft_data.get("distinctions", [])}
    held = set(entries)
    chapter_offers = [
        offer
        for offer in visible_offers(draft).values()
        if offer.chapter == chapter and offer.arrives_as == OfferArrival.CHOICE
    ]
    exclusions = _mutual_exclusions({offer.distinction_id for offer in chapter_offers})
    conflict_ids = {cid for ids in exclusions.values() for cid in ids if cid in held}
    conflict_names = dict(Distinction.objects.filter(id__in=conflict_ids).values_list("id", "name"))
    effects = _effects_by_distinction({offer.distinction_id for offer in chapter_offers})
    pinned = _pinned_offer_ids(draft, {offer.id for offer in chapter_offers})

    out: list[VisibleOffer] = []
    for offer in chapter_offers:
        dist = offer.distinction
        conflict_id = next((x for x in exclusions.get(dist.id, ()) if x in held), None)
        conflict_name = conflict_names.get(conflict_id) if conflict_id is not None else None
        entry = entries.get(dist.id)
        # Held elsewhere: the draft has it, and not from this line (a legacy entry with
        # no offer_ids key counts as elsewhere too).
        held_elsewhere = entry is not None and offer.id not in entry.get("offer_ids", [])
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
                is_locked=conflict_name is not None,
                lock_reason=f"Cannot be held with {conflict_name}" if conflict_name else "",
                opener_key=offer.opener_key,
                first_look=offer.id in pinned,
                held=held_elsewhere,
                effect_line=effect_line(effects.get(dist.id, [])),
            )
        )
    # Appearance groups by section, in the sections' own order; within a group the
    # pinned lines lead, then sort_order, then id.
    group_orders = {
        offer.id: (offer.appearance_section.sort_order if offer.appearance_section_id else 0)
        for offer in chapter_offers
    }
    sort_orders = {offer.id: offer.sort_order for offer in chapter_offers}
    out.sort(
        key=lambda o: (
            group_orders[o.offer_id],
            not o.first_look,
            sort_orders[o.offer_id],
            o.offer_id,
        )
    )
    return out


def degree_marks() -> dict[str, list[str]]:
    """Degree value -> the distinction names its bundled enemy-chapter lines carry (#3709).

    Called by ``enemies.degree_grants`` so the leaf's degree row can say "bundles X"
    before anyone picks. Read from the authored offer lines, never from a constant.
    """
    rows = DistinctionOffer.objects.filter(
        is_active=True,
        chapter=OfferChapter.ENEMY,
        arrives_as=OfferArrival.BUNDLED,
    ).exclude(enemy_degree="")
    out: dict[str, list[str]] = defaultdict(list)
    for offer in rows.select_related("distinction").order_by("sort_order", "id"):
        out[offer.enemy_degree].append(offer.distinction.name)
    return dict(out)


def closed_for(draft: CharacterDraft, chapter: OfferChapter) -> list[ClosedDistinction]:
    """The route's closed-distinction list, for the one chapter that would have shown them.

    Called by each chapter's view/serializer alongside ``offers_for``. Each row
    carries ``opener_labels``: the opener labels of this chapter's own active
    CHOICE offers for the closed distinction whose opener the draft has satisfied
    (the same ``_opener_satisfied`` check ``visible_offers`` applies, evaluated
    directly here since ``visible_offers`` itself excludes anything closed before
    a caller ever sees it). Empty when no offer in this chapter opens it (the
    route closed something a different chapter offers); since #3709 every
    chapter's offers carry an opener (a prompt, a reason or degree, a section). A chapter
    mount (``GlimpseAxes``) uses this to print the closed hint once, under the
    specific pick that would have opened it, instead of under every pick.
    ``opener_ids`` (#3675 final fix B4) carries the same offers' ids, index-aligned
    with ``opener_labels``, so a caller can match a closed row to a specific offer
    (e.g. a Glimpse tag's own offer ids) without a name/label match.
    """
    route = draft.selected_origin_template
    if route is None:
        return []
    closed = list(route.closed_distinctions.all())
    if not closed:
        return []
    closed_ids = {d.id for d in closed}
    ctx = _context(draft)
    rows = DistinctionOffer.objects.filter(
        is_active=True,
        chapter=chapter,
        arrives_as=OfferArrival.CHOICE,
        distinction_id__in=closed_ids,
    ).select_related(
        "glimpse_tag", "origin_choice", "schooling_line", "enemy_reason", "appearance_section"
    )
    openers: dict[int, list[str]] = defaultdict(list)
    opener_ids: dict[int, list[int]] = defaultdict(list)
    for offer in rows:
        if _opener_satisfied(offer, ctx):
            label = opener_label(offer)
            if label:
                openers[offer.distinction_id].append(label)
                opener_ids[offer.distinction_id].append(offer.id)
    return [
        ClosedDistinction(
            distinction_id=d.id,
            name=d.name,
            reason=route.closed_reason,
            opener_labels=openers.get(d.id, []),
            opener_ids=opener_ids.get(d.id, []),
        )
        for d in closed
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
    alongside a still-live one. An entry with no ``offer_ids`` key at all is a legacy
    pick: drafts saved before 0106 (when the offers system landed) hold catalogue
    picks the player made against no ``DistinctionOffer`` at all, since none existed
    yet, and there is nothing to re-derive their offer from now. Such an entry is
    left exactly as stored -- not touched here, not dropped or repriced in
    ``_drop_empty_and_reprice`` -- until the player changes it through a path that
    does carry ``offer_ids`` (review round 2, ruling A).
    """
    changed: list[str] = []
    for entry in entries:
        if "offer_ids" not in entry:  # noqa: STRING_LITERAL
            continue
        srcs = entry.setdefault("sources", [])
        arrs = entry.setdefault("arrivals", [])
        ids = entry["offer_ids"]
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
    if carried_key not in entry.get("offer_ids", []):
        # A legacy entry (see _drop_vanished_sources) has no offer_ids key at all;
        # setdefault converts it into an offer-tracked entry the moment a live
        # source actually needs to record itself against it, without disturbing it
        # on every other reconcile pass.
        entry.setdefault("offer_ids", []).append(carried_key)
        entry.setdefault("sources", []).append(state_line.entry_line)
        entry.setdefault("arrivals", []).append(OfferArrival.CARRIED)
        return [drawback.name]
    return []


def _group_offer_anchors(
    offers: list[DistinctionOffer], draft: CharacterDraft, answers: DraftAnswers
) -> tuple[dict[int, int | None], set[int]]:
    """Resolve GROUP-question anchors and collect their organization ids."""
    anchor_by_offer: dict[int, int | None] = {}
    org_ids: set[int] = set()
    for offer in offers:
        if not offer.origin_choice_id:
            continue
        slot = offer.origin_choice.slot
        if slot.kind != QuestionKind.GROUP:
            continue
        org_id = anchor_for(slot, draft, answers)
        anchor_by_offer[offer.id] = org_id
        if org_id is not None:
            org_ids.add(org_id)
    return anchor_by_offer, org_ids


def _bundled_label(
    offer: DistinctionOffer,
    anchor_by_offer: dict[int, int | None],
    orgs: dict[int, Organization],
    enemy_name: str = "",
) -> str:
    """Build a bundled offer label using the prefetched organization cache.

    An enemy-chapter line's source names the enemy too ("They want you ruined: the
    Rouault"), the way a Lineage line names its anchored organization (#3709);
    ``enemy_name`` is resolved once by the caller.
    """
    label = opener_label(offer)
    if offer.chapter == OfferChapter.ENEMY:
        return f"{label}: {enemy_name}" if enemy_name else label
    org_id = anchor_by_offer.get(offer.id)
    if org_id is None:
        return label
    org = orgs.get(org_id)
    return f"{label}, {org.name}" if org is not None else label


def _bundled_opener_labels(offers: list[DistinctionOffer], draft: CharacterDraft) -> dict[int, str]:
    """``opener_label(offer, draft=draft)`` for every ``offers`` row, batched.

    Called by ``_apply_bundled``. Mirrors ``questionnaire.bundled_distinctions``'s
    own batching: every GROUP-question offer's anchor is resolved first, the
    Organizations it names are bulk-fetched once, then each label is built from
    that shared cache -- never one ``Organization.objects.filter(pk=...)`` query
    per offer, which the naive per-offer ``opener_label(draft=...)`` call did
    (#3675 fix round 3).
    """
    if not offers:
        return {}
    answers = DraftAnswers.from_draft(draft)
    anchor_by_offer, org_ids = _group_offer_anchors(offers, draft, answers)

    from world.societies.models import Organization  # noqa: PLC0415

    orgs = {o.pk: o for o in Organization.objects.filter(pk__in=org_ids)} if org_ids else {}
    enemy_name = ""
    if any(offer.chapter == OfferChapter.ENEMY for offer in offers):
        from world.character_creation.enemies import resolve_enemy  # noqa: PLC0415

        resolved = resolve_enemy(draft)
        enemy_name = resolved.name if resolved is not None else ""
    return {offer.id: _bundled_label(offer, anchor_by_offer, orgs, enemy_name) for offer in offers}


def _apply_bundled(
    entries: list[DraftDistinctionEntry],
    by_dist: dict[int, DraftDistinctionEntry],
    visible: dict[int, DistinctionOffer],
    draft: CharacterDraft,
) -> list[str]:
    """Add or extend every distinction bundled free with an answer the draft holds.

    Called by ``reconcile_offer_picks``.
    """
    changed: list[str] = []
    bundled = [o for o in visible.values() if o.arrives_as == OfferArrival.BUNDLED]
    labels = _bundled_opener_labels(bundled, draft)
    for offer in bundled:
        entry = by_dist.get(offer.distinction_id)
        label = labels[offer.id]
        if entry is None:
            entry = build_distinction_entry(offer.distinction, rank=1, offer=offer, source=label)
            entries.append(entry)
            by_dist[offer.distinction_id] = entry
            changed.append(offer.distinction.name)
        elif offer.id not in entry.get("offer_ids", []):
            # See _apply_carried's identical setdefault: converts a legacy entry
            # (no offer_ids key) into an offer-tracked one only when a live offer
            # actually needs to record itself against it.
            entry.setdefault("offer_ids", []).append(offer.id)
            entry.setdefault("sources", []).append(label)
            entry.setdefault("arrivals", []).append(OfferArrival.BUNDLED)
            changed.append(offer.distinction.name)
    return changed


def _drop_empty_and_reprice(
    entries: list[DraftDistinctionEntry],
) -> tuple[list[DraftDistinctionEntry], list[str]]:
    """Drop entries whose last source just vanished, and reprice every survivor.

    Called by ``reconcile_offer_picks``. A carried-only entry is priced at the
    drawback's own ``cost_per_rank`` (Decision 3 of the #3675 spec: the refund
    lands even though it wasn't a choice); everything else goes through
    ``entry_price``. A legacy entry with no ``offer_ids`` key (see
    ``_drop_vanished_sources``) is kept exactly as stored and never repriced -- it
    predates the offers system, so there is no offer to price it against.
    """
    changed: list[str] = []
    kept: list[DraftDistinctionEntry] = []
    dists = Distinction.objects.in_bulk([e["distinction_id"] for e in entries])
    for entry in entries:
        if "offer_ids" not in entry:  # noqa: STRING_LITERAL
            kept.append(entry)
            continue
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
    changed += _apply_bundled(entries, by_dist, visible, draft)
    kept, repriced = _drop_empty_and_reprice(entries)
    changed += repriced

    if kept != original or changed:
        draft.draft_data["distinctions"] = kept
        draft.save(update_fields=["draft_data"])

    # de-duplicate while keeping order
    seen: set[str] = set()
    return [n for n in changed if not (n in seen or seen.add(n))]
