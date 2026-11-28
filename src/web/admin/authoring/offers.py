"""Shared "how it reads to a player" offer preview for authoring pages (#3675).

The Distinction Builder (every offer of one Distinction, across every
chapter) and a Glimpse tag's own change form (every offer of one tag, all
chapter GLIMPSE) both pick "the first active offer in chapter-declared
order" and draw it the same way: the offer's own distinction's derived
price, plus the offer's own name/player line (falling back to the
distinction's name when the offer left it blank, matching
``DistinctionOffer.save()``). This module is the one place that
pick-and-draw logic lives so neither page reimplements it - the two pages
differ only in which offers they hand it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django import forms
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction

from web.admin.authoring.copy import price_text
from web.admin.authoring.credit import stamp_written
from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.models import DistinctionOffer
from world.contributors.models import ContentContributor
from world.distinctions.models import Distinction

#: Chapters in declared, player-facing order (the demo's own worked example:
#: Gift/tradition step, Gift/Glimpse, Lineage, Appearance, Identity) - the
#: model's ``chapter`` column is a plain ``CharField``, so alphabetical DB
#: ordering does not match this at all (#3675 review round 1, Demo-fidelity
#: defect B).
CHAPTER_ORDER = tuple(OfferChapter)


def offer_sort_key(offer: DistinctionOffer) -> tuple[int, int, int]:
    """Chapter's declared order, then ``sort_order``, then id.

    A row with no recognised chapter yet (a fresh, unsaved formset row) sorts
    last rather than raising.
    """
    try:
        chapter_index = CHAPTER_ORDER.index(OfferChapter(offer.chapter))
    except ValueError:
        chapter_index = len(CHAPTER_ORDER)
    return (chapter_index, offer.sort_order or 0, offer.pk or 0)


class DistinctionOfferFormSetMixin:
    """Rejects the same distinction offered twice by one owner (#3675 Task 10 review).

    Promoted out of two identical ``clean()`` bodies: the Upbringing
    Builder's per-answer offer formset (``upbringing_builder.forms
    ._OfferBaseFormSet``) and the Glimpse tag admin's own offer inline
    (``world.magic.admin.GlimpseTagOfferFormSet``) each duplicated this same
    check, differing only in which noun names the owner in the message.
    Mixed in ahead of ``BaseInlineFormSet``; a subclass sets ``owner_noun``.
    """

    owner_noun = "row"

    def clean(self):
        super().clean()
        seen: set[int] = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            distinction = form.cleaned_data.get("distinction")
            if distinction is None:
                continue
            if distinction.pk in seen:
                dupe_message = f"'{distinction.name}' is already offered by this {self.owner_noun}."
                raise forms.ValidationError(dupe_message)
            seen.add(distinction.pk)


@dataclass(frozen=True)
class PreviewLine:
    price: str
    name: str
    player_line: str


def preview_from_offers(offers: Iterable[DistinctionOffer]) -> PreviewLine | None:
    """The first active offer in ``offers``, drawn as a player would read it.

    ``None`` when ``offers`` is empty - the caller's template shows its own
    "add an active offer to preview" line in that case.
    """
    offers = list(offers)
    if not offers:
        return None
    offer = min(offers, key=offer_sort_key)
    # A line that arrives bundled or carried costs the player nothing whatever the
    # card's own price (``offers.entry_price``); every Glimpse line is one (#5292).
    cost = offer.distinction.cost_per_rank if offer.arrives_as == OfferArrival.CHOICE else 0
    return PreviewLine(
        price=price_text(cost, per_rank=offer.distinction.max_rank > 1),
        name=offer.name or offer.distinction.name,
        player_line=offer.player_line,
    )


@dataclass(frozen=True)
class IdentityPlacement:
    """What ``offer_on_identity`` did with the cards it was given (#5255)."""

    created: list[DistinctionOffer]
    #: Cards with an active Identity line already.
    already: list[Distinction]
    #: Cards whose Identity line staff switched off; left off.
    switched_off: list[Distinction]
    #: Cards that are not active; a player could not take one, so it is not placed.
    inactive: list[Distinction]
    #: Cards the Glimpse gives (#5292): no other stage offers one, so it is not placed.
    glimpse: list[Distinction] = field(default_factory=list)


def offer_on_identity(
    distinctions: Iterable[Distinction], contributor: ContentContributor, user_id: int
) -> IdentityPlacement:
    """Place each card on the Identity stage, and say which were left as they were (#5255).

    The Identity chapter takes no opener, so placing a card there is one offer line with
    nothing else to choose; this is the many-at-once form of adding that row on the
    Distinction Builder, for the Distinction list's "Offer on the Identity stage" action.
    A card with an Identity line already is left as it is, a switched-off line included
    (running the action is no way round a line staff turned off), and so is a card that
    is not active. New lines are taken by choice, sorted after the lines already there in
    the order given, credited to ``contributor``, and logged once per card under
    ``user_id``. One transaction; the model's own constraint refuses a second line if
    two operators run this at once.
    """
    cards = list(distinctions)
    created: list[DistinctionOffer] = []
    already: list[Distinction] = []
    switched_off: list[Distinction] = []
    inactive: list[Distinction] = []
    glimpse: list[Distinction] = []
    with transaction.atomic():
        glimpse_ids = set(
            DistinctionOffer.objects.filter(
                chapter=OfferChapter.GLIMPSE, is_active=True, distinction__in=cards
            ).values_list("distinction_id", flat=True)
        )
        placed = dict(
            DistinctionOffer.objects.filter(
                chapter=OfferChapter.IDENTITY, distinction__in=cards
            ).values_list("distinction_id", "is_active")
        )
        last = (
            DistinctionOffer.objects.filter(chapter=OfferChapter.IDENTITY)
            .order_by("-sort_order")
            .values_list("sort_order", flat=True)
            .first()
        )
        next_order = 0 if last is None else last + 1
        for card in cards:
            if card.pk in placed:
                (already if placed[card.pk] else switched_off).append(card)
                continue
            if not card.is_active:
                inactive.append(card)
                continue
            if card.pk in glimpse_ids:
                # The model's own rule (``DistinctionOffer.clean``), which a bare
                # ``create`` does not run.
                glimpse.append(card)
                continue
            offer = DistinctionOffer.objects.create(
                distinction=card,
                chapter=OfferChapter.IDENTITY,
                arrives_as=OfferArrival.CHOICE,
                sort_order=next_order,
            )
            next_order += 1
            stamp_written(offer, contributor)
            created.append(offer)
        if created:
            LogEntry.objects.log_actions(
                user_id,
                [offer.distinction for offer in created],
                CHANGE,
                change_message="Offered on the Identity stage (#5255)",
            )
    return IdentityPlacement(created, already, switched_off, inactive, glimpse)
