"""The Being Service builder (#4333 slice 2, design 10): one being's favored
resonances, favored facets (with their worn rates, #4520), pledge types, the items its
pledges and rites ask for (#4530) and its pact offers with their commitments (#4341),
written together.

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
from django.db.models import Q
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.authoring.identity_map import CacheGuard
from web.admin.being_service import live
from web.admin.being_service.forms import (
    BeingFacetFormSet,
    BeingResonanceFormSet,
    PactOfferCommitmentFormSet,
    PactOfferFormSet,
    PledgeFormSet,
    RequestedItemFormSet,
)
from web.admin.tuning.views import superuser_required
from world.pacts.models import PactOffer, PactOfferCommitment
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.invocation_services import get_devotion_config
from world.worship.models import (
    BeingFacet,
    BeingResonance,
    Pledge,
    RequestedItem,
    WorshippedBeing,
)

#: The submit button's name that stays on this page after saving; "Save" returns to
#: the being's change page, as a stock change form does.
CONTINUE_BUTTON = "save_continue"


@dataclass
class _ServiceForms:
    resonances: BeingResonanceFormSet
    facets: BeingFacetFormSet
    pledges: PledgeFormSet
    requests: RequestedItemFormSet
    offers: PactOfferFormSet
    commitments: PactOfferCommitmentFormSet

    @property
    def all(self) -> tuple:
        return (
            self.resonances,
            self.facets,
            self.pledges,
            self.requests,
            self.offers,
            self.commitments,
        )

    @property
    def media(self) -> Media:
        media = Media()
        for formset in self.all:
            media += formset.media
        return media

    def is_valid(self) -> bool:
        # Every formset validates (a list, not a generator) so each shows its own errors.
        results = [formset.is_valid() for formset in self.all]
        return all(results)


def _build_forms(request: HttpRequest, being: WorshippedBeing) -> _ServiceForms:
    data = request.POST if request.method == "POST" else None
    return _ServiceForms(
        resonances=BeingResonanceFormSet(
            data,
            instance=being,
            prefix="resonances",
            # Favored first: "favored" sorts after "associated", so the tier goes descending.
            queryset=BeingResonance.objects.select_related("resonance").order_by("-tier", "pk"),
        ),
        facets=BeingFacetFormSet(
            data,
            instance=being,
            prefix="facets",
            queryset=BeingFacet.objects.select_related("facet").order_by("facet__name"),
        ),
        pledges=PledgeFormSet(
            data,
            instance=being,
            prefix="pledges",
            queryset=Pledge.objects.select_related("closing_rite__kind").order_by("pk"),
        ),
        requests=RequestedItemFormSet(
            data,
            being=being,
            prefix="requests",
            queryset=RequestedItem.objects.filter(Q(pledge__being=being) | Q(rite__being=being))
            .select_related("item_template", "facet")
            .order_by("pk"),
        ),
        offers=PactOfferFormSet(
            data,
            instance=being,
            prefix="pact_offers",
            queryset=PactOffer.objects.select_related("condition").order_by("pk"),
        ),
        commitments=PactOfferCommitmentFormSet(
            data,
            being=being,
            prefix="pact_commitments",
            queryset=PactOfferCommitment.objects.filter(offer__being=being).order_by(
                "offer__pk", "pk"
            ),
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
        (
            form,
            live.pledge_pacing(form.instance) if form.instance.pk else "",
            live.pledge_answers(form.instance) if form.instance.pk else None,
            live.pact_offer_brief(form.instance.pact_offer)
            if form.instance.pk and form.instance.pact_offer_id is not None
            else None,
        )
        for form in forms.pledges.forms
    ]
    offer_rows = [
        (form, live.pact_offer_context(form.instance) if form.instance.pk else None)
        for form in forms.offers.forms
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
            "supplier_rail": live.facet_suppliers(being),
            "pledges": forms.pledges,
            "pledge_rows": pledge_rows,
            "requests": forms.requests,
            "request_supply": live.request_suppliers(being),
            "request_max_points": get_devotion_config().requested_item_max_points,
            "request_max_value": get_devotion_config().requested_item_max_value,
            "active_pledges": active_pledges,
            "offers": forms.offers,
            "offer_rows": offer_rows,
            "commitments": forms.commitments,
            "favored_chips": live.favored_resonance_chips(being),
            "modifier_rows": live.favor_modifier_rows(being),
            "media": forms.media,
            "needs_setup": needs_setup,
            "stats": live.being_stats(being),
            "checks": live.checks(being),
            "credit": live.credit_summary(being),
            "change_url": reverse("admin:arxii_worshippedbeing_change", args=[being.pk]),
            "deity_editor_url": _deity_editor_url(being),
            "answer_builder_url": reverse("admin_answer_builder", args=[being.pk]),
        },
    )


def _cache_guard(being: WorshippedBeing, forms: _ServiceForms) -> CacheGuard:
    """A guard over every cached row these forms validate onto. Take it before validating.

    Validating a ModelForm writes the posted values onto its instance, and those
    instances are the identity-mapped ones other readers hold too (a signed pact's
    ``offer``, a period's ``commitment``, which the weekly grading reads). Dropping them
    from the map would leave those holders on the refused values, so a path that does
    not commit puts the kept values back onto the same objects and evicts any row a
    rolled-back save created.
    """
    guard = CacheGuard()
    guard.watch_created(
        BeingResonance, BeingFacet, Pledge, RequestedItem, PactOffer, PactOfferCommitment
    )
    guard.keep(being)
    for formset in forms.all:
        guard.keep(*(form.instance for form in formset.forms))
    return guard


@superuser_required
def being_service(request: HttpRequest, being_pk: int) -> HttpResponse:
    """GET renders the page; POST saves resonances, facets, pledge types, requests and
    pact offers with their commitments together."""
    being = get_object_or_404(WorshippedBeing, pk=being_pk)
    ensure_being_modifier_targets(being)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, being)
    if request.method != "POST":
        return _render_page(request, being, forms, needs_setup=contributor is None)
    if contributor is None:
        return _render_page(request, being, forms, needs_setup=True)
    guard = _cache_guard(being, forms)
    committed = False
    try:
        if not forms.is_valid():
            return _render_page(request, being, forms)
        with transaction.atomic():
            forms.resonances.save()
            forms.facets.save()
            saved_pledges = forms.pledges.save()
            for pledge in saved_pledges:
                stamp_written(pledge, contributor)
            forms.requests.save()
            # Commitments first: a row may belong to an offer this same save deletes.
            forms.commitments.save()
            for offer in forms.offers.save():
                stamp_written(offer, contributor)
        committed = True
    finally:
        # A refusal, or anything raised before or inside the transaction: nothing was
        # written, so every bound row gets its kept values back, after the page (which
        # shows the posted values) has rendered.
        if not committed:
            guard.restore()
    messages.success(request, "Saved and credited to you.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(reverse("admin_being_service", args=[being.pk]))
    return redirect(reverse("admin:arxii_worshippedbeing_change", args=[being.pk]))


@superuser_required
@require_POST
def being_service_review(request: HttpRequest, being_pk: int) -> HttpResponse:
    """Mark every pledge type and pact offer of this being reviewed; authorship untouched."""
    being = get_object_or_404(WorshippedBeing, pk=being_pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking these pledge types reviewed.")
    else:
        for pledge in Pledge.objects.filter(being=being):
            stamp_reviewed(pledge, contributor)
        for offer in PactOffer.objects.filter(being=being):
            stamp_reviewed(offer, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_being_service", args=[being.pk]))
