"""Live checks, rail counts and the CG-line preview for the Distinction Builder (#3675)."""

from __future__ import annotations

from dataclasses import dataclass

from django.forms.models import BaseInlineFormSet

from web.admin.authoring.offers import PreviewLine, offer_sort_key, preview_from_offers
from world.character_creation.constants import OfferChapter
from world.character_creation.models import DistinctionOffer
from world.distinctions.models import CharacterDistinction, Distinction, DistinctionEffect

#: The placeholder marker `_placeholder_check` watches for - never typed by a
#: player, just staff shorthand for "description not written yet".
PLACEHOLDER_PREFIX = "PLACEHOLDER"


def effect_reads(effect: DistinctionEffect) -> str:
    """The player-facing gloss of one effect: "+1 Starting technique picks per rank"."""
    if effect.value_per_rank is not None:
        return f"{effect.value_per_rank:+d} {effect.target.name} per rank"
    if effect.grants_immunity_to_negative:
        return f"Immune to negative {effect.target.name}"
    if effect.amplifies_sources_by is not None:
        return f"Other {effect.target.name} sources {effect.amplifies_sources_by:+d}"
    return f"See {effect.target.name}"


def sorted_offer_forms(offers_formset: BaseInlineFormSet) -> list:
    """The offers formset's own bound forms, reordered for display only.

    Operates on the formset's already-fetched ``forms`` list rather than its
    ``queryset`` - the queryset itself stays in the formset's default DB
    order (needed intact for ``is_valid()``/``save()``); only the order
    ``page.html`` iterates them in for display changes here (#3675 review
    round 1, Demo-fidelity defect B). ``offer_sort_key`` is shared with the
    Glimpse tag admin's own preview (``web.admin.authoring.offers``).
    """
    return sorted(offers_formset.forms, key=lambda form: offer_sort_key(form.instance))


def opener_field_map() -> dict[str, str | None]:
    """Chapter value -> the opener field its offers use; ``None`` for no opener.

    Built off ``DistinctionOffer.opener_field`` (the model's own public lookup)
    rather than reaching for its private ``_OPENER_FOR_CHAPTER`` table, so the
    page's chapter-cascade JS always matches whatever the model's ``clean()``
    actually enforces.
    """
    return {
        chapter.value: DistinctionOffer(chapter=chapter.value).opener_field
        for chapter in OfferChapter
    }


@dataclass(frozen=True)
class RailCounts:
    effects: int
    exclusions: int
    offered_in: int
    held_by: int


def rail_counts(distinction: Distinction) -> RailCounts:
    """'This distinction' stat tiles: what is on the page right now."""
    offered_chapters = (
        DistinctionOffer.objects.filter(distinction=distinction, is_active=True)
        .values_list("chapter", flat=True)
        .distinct()
    )
    return RailCounts(
        effects=distinction.effects.count(),
        exclusions=distinction.mutually_exclusive_with.count(),
        offered_in=len(set(offered_chapters)),
        held_by=CharacterDistinction.objects.filter(distinction=distinction).count(),
    )


def _offered_check(distinction: Distinction) -> tuple[str, str]:
    if DistinctionOffer.objects.filter(distinction=distinction, is_active=True).exists():
        return ("ok", "Offered somewhere; a player can reach it.")
    return ("warn", "Not offered anywhere; a player can never reach it in CG.")


def _effect_target_check(distinction: Distinction) -> tuple[str, str]:
    # A target FK is required (on_delete=PROTECT, non-null), so this only ever
    # warns for a row that reached the database some other way (#3675 brief).
    missing = distinction.effects.filter(target__isnull=True).count()
    if missing:
        noun = "effect" if missing == 1 else "effects"
        return ("warn", f"{missing} {noun} name no modifier target.")
    return ("ok", "Every effect names a modifier target that exists.")


def _placeholder_check(distinction: Distinction) -> tuple[str, str]:
    if distinction.description.startswith(PLACEHOLDER_PREFIX):
        return ("warn", f"Description is a placeholder (starts with {PLACEHOLDER_PREFIX}).")
    return ("ok", "Description is not a placeholder.")


def _lineage_offer_checks(distinction: Distinction) -> list[tuple[str, str]]:
    offers = DistinctionOffer.objects.filter(
        distinction=distinction, chapter=OfferChapter.LINEAGE, origin_choice__isnull=False
    ).select_related("origin_choice")
    return [
        ("warn", f"The Lineage offer's answer '{offer.origin_choice.name}' is inactive.")
        for offer in offers
        if not offer.origin_choice.is_active
    ]


def _schooling_offer_checks(distinction: Distinction) -> list[tuple[str, str]]:
    offers = DistinctionOffer.objects.filter(
        distinction=distinction, chapter=OfferChapter.TRADITION_STEP, schooling_line__isnull=False
    ).select_related("schooling_line")
    return [
        (
            "warn",
            f"Schooling line '{offer.schooling_line.name}' grants a different distinction.",
        )
        for offer in offers
        if offer.schooling_line.grants_id != distinction.pk
    ]


def checks(distinction: Distinction) -> list[tuple[str, str]]:
    result = [
        _offered_check(distinction),
        _effect_target_check(distinction),
        _placeholder_check(distinction),
    ]
    result.extend(_lineage_offer_checks(distinction))
    result.extend(_schooling_offer_checks(distinction))
    return result


def preview_line(distinction: Distinction) -> PreviewLine | None:
    """The first active offer in chapter-declared order, drawn as a player would read it.

    Delegates to the shared ``web.admin.authoring.offers.preview_from_offers`` -
    the Glimpse tag admin's own preview (#3675) picks the same way among a
    different set of offers (a tag's own, not a distinction's).
    """
    offers = DistinctionOffer.objects.filter(distinction=distinction, is_active=True)
    return preview_from_offers(offers)
