"""The vow page (#4880, slice 2 of #4843): one vow, its specialties, focus picks and limits.

Pattern: the Distinction Builder. One vow here is a ``CovenantRole`` plus its
``CovenantRoleTechniqueSpecialty`` rows, its ``VowFocusPick`` catalog and each pick's
``VowFocusPickLimit`` rows, saved in one transaction and credited to the operator's
linked ``ContentContributor``. Payload rows (added effects, situational perks, stat
scalings) are summarised here and edited on their stock admin forms in the popup.

A save that changes the price of a pick live characters hold, or deletes one, first
re-renders with each holder's old and new total for that level against the budget and
a confirm button; nothing is written until the operator confirms. Nobody's picks are
changed by the save: a deleted pick's holder rows go with it (CASCADE).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.authoring.identity_map import flush_refused_instances
from web.admin.tuning.views import superuser_required
from web.admin.vow_builder import live
from web.admin.vow_builder.forms import (
    VOW_FLAG_FIELDS,
    LimitFormSet,
    PickFormSet,
    SpecialtyFormSet,
    VowForm,
    limit_formset_for,
)
from world.contributors.models import ContentContributor
from world.covenants.constants import (
    FOCUS_PICK_FREQUENCY_LIMIT_KINDS,
    FOCUS_PICK_LIMIT_FREQUENCY_FULL,
    FOCUS_PICK_REDUCTION_LIMIT_KINDS,
    VOW_FOCUS_PICK_MAX_LEVEL,
)
from world.covenants.focus_picks import MIN_PICK_PRICE, pick_price, price_for
from world.covenants.models import CovenantRole, VowFocusPick, VowFocusPickLimit

_DELETE = "DELETE"
#: The POST field the "Save anyway" button in the holder warning sends.
CONFIRM_FIELD = "confirm_holders"


@dataclass
class _VowForms:
    """Every form layer one vow's page binds, bundled."""

    vow: VowForm
    specialties: SpecialtyFormSet
    picks: PickFormSet
    limits: dict[int, LimitFormSet]

    def deleted_pick_ids(self) -> set[int]:
        return {
            form.instance.pk
            for form in self.picks.forms
            if form.instance.pk is not None and form.is_valid() and form.cleaned_data.get(_DELETE)
        }

    def is_valid(self) -> bool:
        valid = self.vow.is_valid() & self.specialties.is_valid() & self.picks.is_valid()
        deleted = self.deleted_pick_ids()
        for pick_id, limits in self.limits.items():
            if pick_id not in deleted:
                valid &= limits.is_valid()
        return bool(valid)

    def bound(self) -> tuple:
        return (self.vow, self.specialties, self.picks, *self.limits.values())


def _build_forms(request: HttpRequest, role: CovenantRole) -> _VowForms:
    data = request.POST if request.method == "POST" else None
    picks = PickFormSet(
        data,
        instance=role,
        prefix="picks",
        queryset=VowFocusPick.objects.order_by("pick_level", "name"),
    )
    limits = {
        form.instance.pk: limit_formset_for(form.instance, data)
        for form in picks.forms
        if form.instance.pk is not None
    }
    return _VowForms(
        vow=VowForm(data, instance=role),
        specialties=SpecialtyFormSet(data, instance=role, prefix="specialties"),
        picks=picks,
        limits=limits,
    )


def _limit_from(form: object) -> VowFocusPickLimit | None:
    """An unsaved limit carrying what a valid, kept limit form would save."""
    data = form.cleaned_data
    if not data or data.get(_DELETE) or not data.get("kind"):
        return None
    return VowFocusPickLimit(
        kind=data["kind"],
        frequency_tenths=data.get("frequency_tenths") or FOCUS_PICK_LIMIT_FREQUENCY_FULL,
        reduction=data.get("reduction") or 0,
    )


def _new_prices(forms: _VowForms) -> dict[int, int | None]:
    """The price every saved pick would have after this edit; ``None`` for a deleted one."""
    prices: dict[int, int | None] = {}
    for form in forms.picks.forms:
        pick_id = form.instance.pk
        if pick_id is None:
            continue
        if form.cleaned_data.get(_DELETE):
            prices[pick_id] = None
            continue
        limits_formset = forms.limits.get(pick_id)
        limits = [
            limit
            for limit in (_limit_from(f) for f in (limits_formset.forms if limits_formset else []))
            if limit is not None
        ]
        prices[pick_id] = price_for(form.cleaned_data["value"], limits)
    return prices


@dataclass
class _PickEntry:
    """One pick row on the page: its form, its limits formset, and what it reads now."""

    form: object
    limits: LimitFormSet | None
    price: int | None
    held_by: int
    limits_text: str
    payload: list[live.PayloadLine]
    add_links: list[tuple[str, str]]


@dataclass
class _LevelSection:
    level: int
    entries: list[_PickEntry] = field(default_factory=list)


def _payload_add_links(role: CovenantRole, pick: VowFocusPick | None) -> list[tuple[str, str]]:
    return [
        ("added effect", live.add_url("vowaddedeffect", role, pick)),
        ("situational perk", live.add_url("vowsituationalperk", role, pick)),
        ("stat scaling", live.add_url("vowstatscaling", role, pick)),
    ]


def _form_level(form: object) -> int:
    raw = form["pick_level"].value()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _level_sections(role: CovenantRole, forms: _VowForms) -> list[_LevelSection]:
    held = live.holders_by_pick(role)
    payload = live.payload_summaries(role)
    sections = {
        level: _LevelSection(level=level) for level in range(1, VOW_FOCUS_PICK_MAX_LEVEL + 1)
    }
    for form in forms.picks.forms:
        pick = form.instance
        saved = pick.pk is not None
        level = _form_level(form)
        section = sections.setdefault(level, _LevelSection(level=level))
        section.entries.append(
            _PickEntry(
                form=form,
                limits=forms.limits.get(pick.pk) if saved else None,
                price=pick_price(pick) if saved else None,
                held_by=held.get(pick.pk, 0) if saved else 0,
                limits_text=live.limits_text(pick.cached_limits) if saved else "none",
                payload=payload.get(pick.pk, []) if saved else [],
                add_links=_payload_add_links(role, pick) if saved else [],
            )
        )
    return [sections[level] for level in sorted(sections)]


def _price_rules() -> dict[str, object]:
    """The price formula's constants, embedded for the page's live price script."""
    return {
        "frequency_kinds": sorted(FOCUS_PICK_FREQUENCY_LIMIT_KINDS),
        "reduction_kinds": sorted(FOCUS_PICK_REDUCTION_LIMIT_KINDS),
        "full": FOCUS_PICK_LIMIT_FREQUENCY_FULL,
        "min_price": MIN_PICK_PRICE,
    }


def _render_page(
    request: HttpRequest,
    role: CovenantRole,
    forms: _VowForms,
    *,
    needs_setup: bool = False,
    impacts: list[live.HolderImpact] | None = None,
) -> HttpResponse:
    payload = live.payload_summaries(role)
    return render(
        request,
        "admin/vow_builder/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": role.name,
            "role": role,
            "form": forms.vow,
            "flag_fields": [forms.vow[name] for name in VOW_FLAG_FIELDS],
            "specialties": forms.specialties,
            "picks": forms.picks,
            "level_sections": _level_sections(role, forms),
            "base_payload": payload.get(None, []),
            "base_add_links": _payload_add_links(role, None),
            "sub_role_count": role.sub_roles.count(),
            "sub_roles_url": (
                f"{reverse('admin:arxii_covenantrole_changelist')}?parent_role__id__exact={role.pk}"
            ),
            "budget_rows": live.budget_rows(role),
            "budget": live.focus_pick_budget(),
            "rides": live.rides_summary(role),
            "price_rules": _price_rules(),
            "impacts": impacts or [],
            "confirm_field": CONFIRM_FIELD,
            "needs_setup": needs_setup,
        },
    )


def _save(request: HttpRequest, forms: _VowForms, contributor: ContentContributor) -> None:
    """Write every layer in one transaction and credit the vow and every touched row."""
    deleted = forms.deleted_pick_ids()
    with transaction.atomic():
        saved_role = forms.vow.save()
        forms.specialties.save()
        saved_picks = list(forms.picks.save())
        touched = {pick.pk: pick for pick in saved_picks}
        saved_limits: list[VowFocusPickLimit] = []
        for pick_id, limits in forms.limits.items():
            if pick_id in deleted:
                continue
            rows = limits.save()
            saved_limits.extend(rows)
            if rows or limits.deleted_objects:
                touched.setdefault(pick_id, limits.instance)
        stamp_written(saved_role, contributor)
        for row in (*touched.values(), *saved_limits):
            stamp_written(row, contributor)
        LogEntry.objects.log_actions(
            request.user.pk, [saved_role], CHANGE, change_message="Saved on the vow page (#4880)"
        )


def _render_refused(
    request: HttpRequest,
    role: CovenantRole,
    forms: _VowForms,
    impacts: list[live.HolderImpact] | None = None,
) -> HttpResponse:
    """Re-render with the posted values, then drop every bound row from the identity map.

    Nothing was saved, so the next reader has to load what the database holds, even
    when the render itself raises.
    """
    try:
        return _render_page(request, role, forms, impacts=impacts)
    finally:
        flush_refused_instances(*forms.bound())


@superuser_required
def vow_builder(request: HttpRequest, pk: int) -> HttpResponse:
    """GET renders the page; POST saves every layer in one transaction, warning holders first."""
    role = get_object_or_404(CovenantRole, pk=pk)
    contributor = current_contributor(request.user)
    if request.method != "POST":
        forms = _build_forms(request, role)
        return _render_page(request, role, forms, needs_setup=contributor is None)
    # Read before any form binds: validation writes the posted values onto the shared rows.
    stored = live.stored_picks(role)
    forms = _build_forms(request, role)
    if contributor is None:
        return _render_page(request, role, forms, needs_setup=True)
    if not forms.is_valid():
        return _render_refused(request, role, forms)
    impacts = live.holder_impact(role, _new_prices(forms), stored)
    if impacts and request.POST.get(CONFIRM_FIELD) != "1":
        return _render_refused(request, role, forms, impacts)
    saved = False
    try:
        _save(request, forms, contributor)
        saved = True
    finally:
        if not saved:
            # The transaction rolled the database back; the shared rows still hold the
            # posted values, so drop them as the error propagates.
            flush_refused_instances(*forms.bound())
    messages.success(request, "Saved and credited to you.")
    return redirect(reverse("admin_vow_builder", args=[role.pk]))


@superuser_required
def vow_builder_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` redirect target for the Combat roles panel's vow picker."""
    pk_raw = request.GET.get("pk", "")
    if not pk_raw.isdigit() or not CovenantRole.objects.filter(pk=pk_raw).exists():
        return HttpResponseBadRequest("Pick a vow to open.")
    return redirect("admin_vow_builder", pk=int(pk_raw))


@superuser_required
@require_POST
def vow_builder_review(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark this vow, its picks and their limits reviewed."""
    role = get_object_or_404(CovenantRole, pk=pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking this vow reviewed.")
    else:
        stamp_reviewed(role, contributor)
        for pick in role.focus_picks.all():
            stamp_reviewed(pick, contributor)
            for limit in pick.limits.all():
                stamp_reviewed(limit, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_vow_builder", args=[pk]))
