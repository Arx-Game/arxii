"""The Distinction Builder (#3675): effects, exclusions and offers on one page.

Pattern: the Upbringing Builder / the tradition slate page. One "distinction"
here is a `Distinction` plus every `DistinctionEffect` and `DistinctionOffer`
hanging off it, plus its own `mutually_exclusive_with` M2M. Save writes the
whole page in one transaction and credits every touched `CreditedContent` row
(the distinction, every effect, every offer - all three inherit it) once the
operator has a linked `ContentContributor`; an unlinked operator sees the
setup guidance instead and nothing is saved, mirroring the Workbench's own gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.db import transaction
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.distinction_builder import live
from web.admin.distinction_builder.forms import (
    DistinctionEffectFormSet,
    DistinctionForm,
    DistinctionOfferFormSet,
)
from web.admin.tuning.views import superuser_required
from world.character_creation.constants import OfferChapter
from world.character_creation.models import DistinctionOffer
from world.contributors.models import ContentContributor
from world.distinctions.models import Distinction, DistinctionEffect


@dataclass
class _BuilderForms:
    """The three form layers one distinction's page needs, bundled (ruff PLR0913)."""

    form: DistinctionForm
    effects: DistinctionEffectFormSet
    offers: DistinctionOfferFormSet

    @property
    def media(self) -> Media:
        return self.form.media + self.effects.media + self.offers.media


def _build_forms(request: HttpRequest, distinction: Distinction) -> _BuilderForms:
    data = request.POST if request.method == "POST" else None
    form = DistinctionForm(data, instance=distinction)
    effects = DistinctionEffectFormSet(
        data,
        instance=distinction,
        prefix="effects",
        queryset=DistinctionEffect.objects.select_related("target"),
    )
    offers = DistinctionOfferFormSet(
        data,
        instance=distinction,
        prefix="offers",
        queryset=DistinctionOffer.objects.select_related(
            "schooling_line", "glimpse_tag", "origin_choice"
        ),
    )
    return _BuilderForms(form, effects, offers)


def _sync_tradition_step_offer_copy(
    distinction: Distinction, contributor: ContentContributor
) -> None:
    """A TRADITION_STEP offer's name/player_line mirror its schooling line, always.

    Never typed on this page for that chapter - whatever the form posted for
    ``name``/``player_line`` on a TRADITION_STEP row is overwritten here from
    the schooling line itself, the one place that wording is authored (#3675
    review round 1, Demo-fidelity defect A). Runs over every current
    TRADITION_STEP offer on the distinction, not just rows this request's
    formset touched, so a row created this save is corrected too.
    """
    offers = DistinctionOffer.objects.filter(
        distinction=distinction, chapter=OfferChapter.TRADITION_STEP, schooling_line__isnull=False
    ).select_related("schooling_line")
    for offer in offers:
        line = offer.schooling_line
        if offer.name != line.name or offer.player_line != line.player_line:
            offer.name = line.name
            offer.player_line = line.player_line
            offer.save(update_fields=["name", "player_line"])
            stamp_written(offer, contributor)


def _render_page(
    request: HttpRequest,
    distinction: Distinction,
    forms: _BuilderForms,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    return render(
        request,
        "admin/distinction_builder/page.html",
        {
            "title": distinction.name if distinction.pk else "New Distinction",
            "distinction": distinction,
            "form": forms.form,
            "effects": forms.effects,
            "offers": forms.offers,
            "offer_rows": live.sorted_offer_forms(forms.offers),
            "opener_field_map": live.opener_field_map(),
            "needs_setup": needs_setup,
            "media": forms.media,
            "rail": live.rail_counts(distinction) if distinction.pk else None,
            "checks": live.checks(distinction) if distinction.pk else [],
            "preview": live.preview_line(distinction) if distinction.pk else None,
        },
    )


@superuser_required
def distinction_builder(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """GET renders the page; POST saves every row in one transaction and credits the operator."""
    distinction = Distinction() if pk is None else get_object_or_404(Distinction, pk=pk)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, distinction)
    if request.method == "POST":
        if contributor is None:
            return _render_page(request, distinction, forms, needs_setup=True)
        valid = forms.form.is_valid() and forms.effects.is_valid() and forms.offers.is_valid()
        if valid:
            with transaction.atomic():
                saved = forms.form.save()
                forms.effects.instance = saved
                saved_effects = forms.effects.save()
                forms.offers.instance = saved
                saved_offers = forms.offers.save()
                stamp_written(saved, contributor)
                for row in (*saved_effects, *saved_offers):
                    stamp_written(row, contributor)
                _sync_tradition_step_offer_copy(saved, contributor)
            messages.success(request, "Saved and credited to you.")
            return redirect(reverse("admin_distinction_builder", args=[saved.pk]))
        return _render_page(request, distinction, forms)
    return _render_page(request, distinction, forms, needs_setup=contributor is None)


@superuser_required
@require_POST
def distinction_builder_review(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark this distinction, its effects and its offers reviewed."""
    distinction = get_object_or_404(Distinction, pk=pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking this distinction reviewed.")
    else:
        stamp_reviewed(distinction, contributor)
        for effect in distinction.effects.all():
            stamp_reviewed(effect, contributor)
        for offer in distinction.offers.all():
            stamp_reviewed(offer, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_distinction_builder", args=[pk]))
