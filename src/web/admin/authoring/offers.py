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
from dataclasses import dataclass

from django import forms

from web.admin.authoring.copy import price_text
from world.character_creation.constants import OfferChapter
from world.character_creation.models import DistinctionOffer

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
    return PreviewLine(
        price=price_text(offer.distinction.cost_per_rank, per_rank=offer.distinction.max_rank > 1),
        name=offer.name or offer.distinction.name,
        player_line=offer.player_line,
    )
