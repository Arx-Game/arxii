"""The Being Service builder (#4333 slice 2, design 10): one being's favored
resonances, favored facets and pledge types, written together.

Pattern: the Standoff Profile and Distinction Builders. One page writes every
``BeingResonance``, the being's ``BeingFacet`` rows and every ``Pledge`` in one
transaction, with a context rail (the being's worship numbers, checks, credit)
and read-only context beside each row (where a resonance comes from in play, the
favor modifiers authored against the being, how long a favor target takes).
Opening the page creates the being's two favor targets if they are missing
(``ensure_being_modifier_targets``). Save credits every pledge type to the
operator's linked contributor; an unlinked operator sees the setup guidance and
nothing is saved, as on every Builder page.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin, messages
from django.db import transaction
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.being_service import live
from web.admin.being_service.forms import (
    BeingResonanceFormSet,
    FavoredFacetsForm,
    PledgeFormSet,
)
from web.admin.tuning.views import superuser_required
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.models import BeingResonance, Pledge, WorshippedBeing

#: The submit button's name that stays on this page after saving; "Save" returns to
#: the being's change page, as a stock change form does.
CONTINUE_BUTTON = "save_continue"


@dataclass
class _ServiceForms:
    resonances: BeingResonanceFormSet
    facets: FavoredFacetsForm
    pledges: PledgeFormSet

    @property
    def media(self) -> Media:
        return self.resonances.media + self.facets.media + self.pledges.media

    def is_valid(self) -> bool:
        return all((self.resonances.is_valid(), self.facets.is_valid(), self.pledges.is_valid()))


def _build_forms(request: HttpRequest, being: WorshippedBeing) -> _ServiceForms:
    data = request.POST if request.method == "POST" else None
    return _ServiceForms(
        resonances=BeingResonanceFormSet(
            data,
            instance=being,
            prefix="resonances",
            queryset=BeingResonance.objects.select_related("resonance").order_by("tier", "pk"),
        ),
        facets=FavoredFacetsForm(
            data,
            prefix="facets",
            initial={"favored_facets": list(being.being_facets.values_list("facet", flat=True))},
        ),
        pledges=PledgeFormSet(
            data,
            instance=being,
            prefix="pledges",
            queryset=Pledge.objects.select_related("closing_rite__kind").order_by("pk"),
        ),
    )


def _deity_editor_url(being: WorshippedBeing) -> str:
    """The React Deity Editor page for the being, a same-origin path as admin's other
    links into the staff client are (``web/admin/tuning/metrics.py``)."""
    return f"/staff/pantheon/{being.pk}"


def _render_page(
    request: HttpRequest,
    being: WorshippedBeing,
    forms: _ServiceForms,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    resonance_context = live.resonance_context(being)
    resonance_rows = [
        (form, resonance_context.get(form.instance.pk)) for form in forms.resonances.forms
    ]
    pledge_rows = [
        (form, live.pledge_pacing(form.instance) if form.instance.pk else "")
        for form in forms.pledges.forms
    ]
    active_pledges = Pledge.objects.filter(being=being, is_active=True).count()
    return render(
        request,
        "admin/being_service/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Being Service builder: {being.name}",
            "being": being,
            "resonances": forms.resonances,
            "resonance_rows": resonance_rows,
            "facets": forms.facets,
            "pledges": forms.pledges,
            "pledge_rows": pledge_rows,
            "active_pledges": active_pledges,
            "modifier_rows": live.favor_modifier_rows(being),
            "media": forms.media,
            "needs_setup": needs_setup,
            "stats": live.being_stats(being),
            "checks": live.checks(being),
            "credit": live.credit_summary(being),
            "change_url": reverse("admin:arxii_worshippedbeing_change", args=[being.pk]),
            "deity_editor_url": _deity_editor_url(being),
        },
    )


def _forget_refused_edits(being: WorshippedBeing, forms: _ServiceForms) -> None:
    """Validating a ModelForm writes the posted values onto its instance, and those
    instances are the identity-mapped ones every other reader shares: drop them so
    the next reader loads what the database holds, not this refused edit."""
    for form in (*forms.resonances.forms, *forms.pledges.forms):
        if form.instance.pk is not None:
            form.instance.flush_from_cache(force=True)
    being.flush_from_cache(force=True)


@superuser_required
def being_service(request: HttpRequest, being_pk: int) -> HttpResponse:
    """GET renders the page; POST saves resonances, facets and pledge types together."""
    being = get_object_or_404(WorshippedBeing, pk=being_pk)
    ensure_being_modifier_targets(being)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, being)
    if request.method != "POST":
        return _render_page(request, being, forms, needs_setup=contributor is None)
    if contributor is None:
        return _render_page(request, being, forms, needs_setup=True)
    if not forms.is_valid():
        response = _render_page(request, being, forms)
        _forget_refused_edits(being, forms)
        return response
    with transaction.atomic():
        forms.resonances.save()
        forms.facets.save(being)
        saved_pledges = forms.pledges.save()
        for pledge in saved_pledges:
            stamp_written(pledge, contributor)
    messages.success(request, "Saved and credited to you.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(reverse("admin_being_service", args=[being.pk]))
    return redirect(reverse("admin:arxii_worshippedbeing_change", args=[being.pk]))


@superuser_required
@require_POST
def being_service_review(request: HttpRequest, being_pk: int) -> HttpResponse:
    """Mark every pledge type of this being reviewed; authorship untouched."""
    being = get_object_or_404(WorshippedBeing, pk=being_pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking these pledge types reviewed.")
    else:
        for pledge in Pledge.objects.filter(being=being):
            stamp_reviewed(pledge, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_being_service", args=[being.pk]))
