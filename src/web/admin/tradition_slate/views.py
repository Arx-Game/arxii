"""The tradition slate page (#3675): standard lines authored once, per-Beginning states.

Pattern: the Upbringing Builder (`web.admin.upbringing_builder.views`). Unlike a
route, the standard lines (`TraditionStateLine`, `SchoolingLine`) are shared by
every Beginning - the same three-plus-three rows are edited from whichever
Beginning's slate page an author happens to be on, and only the slate itself
(`BeginningTradition`) belongs to one Beginning. A still-unauthored state/rank
shows as an unsaved row with its identity fixed by the formset's own
``initial`` (`forms.state_line_formset`/`schooling_line_formset`) rather than
a row this view writes to the database just to have three to show
(#3675 demo-fidelity ruling: a GET-triggered ``get_or_create`` is a guard by
another name). Save writes all three formsets in one transaction, keeps every
schooling line's TRADITION_STEP offer in step with its grant (created,
distinction updated, or deactivated when the grant is cleared), and credits
every touched `CreditedContent` row - the standard lines and any offer this
save touched; `BeginningTradition` carries no authorship fields of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.db import transaction
from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.forms import BaseModelFormSet, Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.tradition_slate import live
from web.admin.tradition_slate.forms import (
    SlateFormSet,
    schooling_line_formset,
    state_line_formset,
)
from web.admin.tuning.views import superuser_required
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.models import (
    Beginnings,
    DistinctionOffer,
    SchoolingLine,
    TraditionStateLine,
)
from world.contributors.models import ContentContributor

#: Standard-line row order the demo approved: how a player is meant to read
#: them, not the alphabetical order the model's own ``state`` field sorts to.
_STATE_ORDER = (
    TraditionState.SELF_TAUGHT,
    TraditionState.TEACHERS_GONE,
    TraditionState.LIVING_MASTERS,
)

#: The three standard schooling ranks - fixed by the model's own shape (#3675
#: spec), not derived from any row that may or may not exist yet.
_SCHOOLING_RANKS = (0, 1, 2)


def _missing_states() -> list[str]:
    """``TraditionState`` values with no ``TraditionStateLine`` row yet, in demo order."""
    existing = set(TraditionStateLine.objects.values_list("state", flat=True))
    return [state for state in _STATE_ORDER if state not in existing]


def _missing_ranks() -> list[int]:
    """Schooling ranks with no ``SchoolingLine`` row yet."""
    existing = set(SchoolingLine.objects.values_list("rank", flat=True))
    return [rank for rank in _SCHOOLING_RANKS if rank not in existing]


def _state_queryset() -> QuerySet[TraditionStateLine]:
    order = Case(
        *(When(state=state, then=Value(index)) for index, state in enumerate(_STATE_ORDER)),
        output_field=IntegerField(),
    )
    return TraditionStateLine.objects.annotate(_display_order=order).order_by("_display_order")


@dataclass
class _SlateForms:
    """The three formsets one tradition slate page needs, bundled (ruff PLR0913).

    ``state``/``schooling`` are typed loosely: ``state_line_formset``/
    ``schooling_line_formset`` each build a fresh ``modelformset_factory``
    class per request (its ``extra`` count depends on how many rows are still
    missing), so there is no single named class to annotate them with.
    """

    state: BaseModelFormSet
    schooling: BaseModelFormSet
    slate: SlateFormSet

    @property
    def media(self) -> Media:
        return self.state.media + self.schooling.media + self.slate.media


def _build_forms(request: HttpRequest, beginning: Beginnings) -> _SlateForms:
    data = request.POST if request.method == "POST" else None
    state = state_line_formset(data, _state_queryset(), _missing_states())
    schooling = schooling_line_formset(
        data, SchoolingLine.objects.order_by("rank"), _missing_ranks()
    )
    slate = SlateFormSet(data, instance=beginning, prefix="slate")
    return _SlateForms(state, schooling, slate)


def _render_page(
    request: HttpRequest,
    beginning: Beginnings,
    forms: _SlateForms,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    return render(
        request,
        "admin/tradition_slate/page.html",
        {
            "title": f"Traditions offered to {beginning.name}",
            "beginning": beginning,
            "state_formset": forms.state,
            "state_rows": [
                (f, f.initial.get("state"), live.state_line_display(f.instance))
                for f in forms.state.forms
            ],
            "schooling_formset": forms.schooling,
            "schooling_rows": [
                (f, f.initial.get("rank"), live.schooling_line_display(f.instance))
                for f in forms.schooling.forms
            ],
            "slate_formset": forms.slate,
            "needs_setup": needs_setup,
            "media": forms.media,
            "rail": live.rail_counts(beginning),
            "checks": live.checks(beginning),
            "preview": live.preview_line(beginning),
        },
    )


def _sync_schooling_offers(request: HttpRequest, contributor: ContentContributor) -> None:
    """Every schooling line's TRADITION_STEP offer stays in step with its grant.

    A line with a grant gets its offer created (crediting the new row), or
    kept in step if the grant changed or the offer had gone inactive
    (crediting the change); a line with no grant has any existing active
    offer deactivated instead of left offering a distinction the line no
    longer names - also credited, since a `DistinctionOffer` is
    `CreditedContent` in its own right, not just the line that opens it.
    """
    for line in SchoolingLine.objects.all():
        offer = DistinctionOffer.objects.filter(
            schooling_line=line, chapter=OfferChapter.TRADITION_STEP
        ).first()
        if line.grants_id is None:
            if offer is not None and offer.is_active:
                offer.is_active = False
                offer.save(update_fields=["is_active"])
                stamp_written(offer, contributor)
            continue
        if offer is None:
            offer = DistinctionOffer.objects.create(
                schooling_line=line,
                chapter=OfferChapter.TRADITION_STEP,
                distinction=line.grants,
            )
            messages.info(request, f"Created the tradition-step offer for '{line.name}'.")
            stamp_written(offer, contributor)
            continue
        update_fields = []
        if offer.distinction_id != line.grants_id:
            offer.distinction = line.grants
            update_fields.append("distinction")
        if not offer.is_active:
            offer.is_active = True
            update_fields.append("is_active")
        if update_fields:
            offer.save(update_fields=update_fields)
            stamp_written(offer, contributor)


@superuser_required
def tradition_slate(request: HttpRequest, beginning_pk: int) -> HttpResponse:
    """GET renders the page; POST saves every formset atomically and credits the operator."""
    beginning = get_object_or_404(Beginnings, pk=beginning_pk)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, beginning)
    if request.method == "POST":
        if contributor is None:
            return _render_page(request, beginning, forms, needs_setup=True)
        valid = forms.state.is_valid() and forms.schooling.is_valid() and forms.slate.is_valid()
        if valid:
            with transaction.atomic():
                saved_state = forms.state.save()
                saved_schooling = forms.schooling.save()
                forms.slate.save()
                _sync_schooling_offers(request, contributor)
                for row in (*saved_state, *saved_schooling):
                    stamp_written(row, contributor)
            messages.success(request, "Saved and credited to you.")
            return redirect(reverse("admin_tradition_slate", args=[beginning.pk]))
        return _render_page(request, beginning, forms)
    return _render_page(request, beginning, forms, needs_setup=contributor is None)


@superuser_required
@require_POST
def tradition_slate_review(request: HttpRequest, beginning_pk: int) -> HttpResponse:
    """Mark every standard line reviewed; they are shared, so this is not per-Beginning."""
    beginning = get_object_or_404(Beginnings, pk=beginning_pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking the standard lines reviewed.")
    else:
        for row in (*TraditionStateLine.objects.all(), *SchoolingLine.objects.all()):
            stamp_reviewed(row, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_tradition_slate", args=[beginning.pk]))
