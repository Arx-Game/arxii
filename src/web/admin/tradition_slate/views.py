"""The tradition slate page (#3675): standard lines authored once, per-Beginning states.

Pattern: the Upbringing Builder (`web.admin.upbringing_builder.views`). Unlike a
route, the standard lines (`TraditionStateLine`, `SchoolingLine`) are shared by
every Beginning - the same three-plus-three rows are edited from whichever
Beginning's slate page an author happens to be on, and only the slate itself
(`BeginningTradition`) belongs to one Beginning. Save writes all three
formsets in one transaction, creates any TRADITION_STEP offer a newly
granting schooling line is missing, and credits every touched
`CreditedContent` row - the standard lines only; `BeginningTradition` carries
no authorship fields of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.db import transaction
from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.tradition_slate import live
from web.admin.tradition_slate.forms import SchoolingLineFormSet, SlateFormSet, StateLineFormSet
from web.admin.tuning.views import superuser_required
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.models import (
    Beginnings,
    DistinctionOffer,
    SchoolingLine,
    TraditionStateLine,
)

#: Standard-line row order the demo approved: how a player is meant to read
#: them, not the alphabetical order the model's own ``state`` field sorts to.
_STATE_ORDER = (
    TraditionState.SELF_TAUGHT,
    TraditionState.TEACHERS_GONE,
    TraditionState.LIVING_MASTERS,
)


def _ensure_standard_lines() -> None:
    """The three state lines and three schooling lines always exist to edit.

    ``get_or_create`` so a fresh database, or a state/rank an earlier author
    never touched, still shows a row rather than the formset silently
    carrying fewer than three.
    """
    for state in TraditionState.values:
        TraditionStateLine.objects.get_or_create(state=state)
    for rank in range(3):
        SchoolingLine.objects.get_or_create(rank=rank)


def _state_queryset() -> QuerySet[TraditionStateLine]:
    order = Case(
        *(When(state=state, then=Value(index)) for index, state in enumerate(_STATE_ORDER)),
        output_field=IntegerField(),
    )
    return TraditionStateLine.objects.annotate(_display_order=order).order_by("_display_order")


@dataclass
class _SlateForms:
    """The three formsets one tradition slate page needs, bundled (ruff PLR0913)."""

    state: StateLineFormSet
    schooling: SchoolingLineFormSet
    slate: SlateFormSet

    @property
    def media(self) -> Media:
        return self.state.media + self.schooling.media + self.slate.media


def _build_forms(request: HttpRequest, beginning: Beginnings) -> _SlateForms:
    data = request.POST if request.method == "POST" else None
    state = StateLineFormSet(data, prefix="state", queryset=_state_queryset())
    schooling = SchoolingLineFormSet(
        data, prefix="schooling", queryset=SchoolingLine.objects.order_by("rank")
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
            "state_rows": [(f, live.state_line_display(f.instance)) for f in forms.state.forms],
            "schooling_formset": forms.schooling,
            "schooling_rows": [
                (f, live.schooling_line_display(f.instance)) for f in forms.schooling.forms
            ],
            "slate_formset": forms.slate,
            "needs_setup": needs_setup,
            "media": forms.media,
            "rail": live.rail_counts(beginning),
            "checks": live.checks(beginning),
            "preview": live.preview_line(beginning),
        },
    )


def _sync_schooling_offers(request: HttpRequest) -> None:
    """Every schooling line with a grant gets its TRADITION_STEP offer, creating it if missing.

    A schooling line's grant can change on this same save, so an existing
    offer's ``distinction`` is kept in step rather than left pointing at
    whatever it was opened with originally.
    """
    for line in SchoolingLine.objects.filter(grants__isnull=False):
        offer, created = DistinctionOffer.objects.get_or_create(
            schooling_line=line,
            chapter=OfferChapter.TRADITION_STEP,
            defaults={"distinction": line.grants},
        )
        if created:
            messages.info(request, f"Created the tradition-step offer for '{line.name}'.")
        elif offer.distinction_id != line.grants_id:
            offer.distinction = line.grants
            offer.save(update_fields=["distinction"])


@superuser_required
def tradition_slate(request: HttpRequest, beginning_pk: int) -> HttpResponse:
    """GET renders the page; POST saves every formset atomically and credits the operator."""
    beginning = get_object_or_404(Beginnings, pk=beginning_pk)
    _ensure_standard_lines()
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
                _sync_schooling_offers(request)
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
