"""The Power Builder (item 8 of #5066): one page per Application, every way to do it.

Pattern: the vow page. The page edits the Application's own fields and, in place, every
source of its capability: a technique's properties and its grant, a trained ability's
derivation, a condition's effect and properties, a distinction effect's value per rank.
It adds a new technique on a gift (and to a path's techniques for that gift). One Save
writes everything in one transaction and credits the Application and every credited row
it touched to the operator's linked ``ContentContributor``.

A refused or failed save leaves every identity-mapped row as stored: the Application's
``ModelForm`` and every row the save can write are kept in a ``CacheGuard`` before
anything validates, and restored on every path that does not commit. The source rows'
forms are plain forms, so validating them writes nothing onto a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from actions.constants import ActionCategory
from core.identity_map import CacheGuard
from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.power_builder import live
from web.admin.power_builder.constants import GrantMode, SourceKind
from web.admin.power_builder.forms import (
    ApplicationForm,
    ConditionRowForm,
    DistinctionRowForm,
    NewTechniqueForm,
    ReferenceForm,
    TechniqueRowForm,
    TraitRowForm,
)
from web.admin.tuning.views import superuser_required
from world.contributors.models import ContentContributor, CreditedContent
from world.magic.models import Gift, PathGiftGrant, Technique, TechniqueCapabilityGrant
from world.magic.services.technique_builder import create_technique
from world.magic.services.technique_effects import invalidate_technique_payload_caches
from world.magic.services.technique_marks import substance_mark_for
from world.mechanics.models import Application

#: What a technique added here starts with; "edit all" changes any of them.
NEW_TECHNIQUE_LEVEL = 1
NEW_TECHNIQUE_INTENSITY = 1
NEW_TECHNIQUE_CONTROL = 1

#: The "Compare at" controls' query parameters, in ``live.Reference`` order.
REFERENCE_PARAMS = ("power", "trait", "rank", "severity")


@dataclass
class _Forms:
    """Every form one page binds."""

    application: ApplicationForm
    techniques: dict[int, TechniqueRowForm] = field(default_factory=dict)
    traits: dict[int, TraitRowForm] = field(default_factory=dict)
    conditions: dict[int, ConditionRowForm] = field(default_factory=dict)
    distinctions: dict[int, DistinctionRowForm] = field(default_factory=dict)
    new: NewTechniqueForm | None = None

    def all(self) -> list[object]:
        forms: list[object] = [self.application]
        for group in (self.techniques, self.traits, self.conditions, self.distinctions):
            forms.extend(group.values())
        if self.new is not None:
            forms.append(self.new)
        return forms

    def is_valid(self) -> bool:
        # Every form validates (no short-circuit), so every error shows at once.
        results = [form.is_valid() for form in self.all()]
        return all(results)


def _reference(params: QueryDict) -> tuple[ReferenceForm, live.Reference]:
    bound = any(name in params for name in REFERENCE_PARAMS)
    form = ReferenceForm(params if bound else None)
    return form, live.Reference(*(form.value(name) for name in REFERENCE_PARAMS))


def _technique_forms(page: live.PowerPage, data: QueryDict | None) -> dict[int, TechniqueRowForm]:
    forms: dict[int, TechniqueRowForm] = {}
    modes = (
        (GrantMode.EDIT, page.doing),
        (GrantMode.SHOWN, page.lacks_property),
        (GrantMode.OFFER, page.lacks_grant),
    )
    for mode, rows in modes:
        for row in rows:
            initial: dict[str, object] = {"properties": sorted(row.property_ids)}
            if row.grant is not None:
                initial["grant_base"] = row.grant.base_value
                initial["grant_per_power"] = row.grant.intensity_multiplier
            form = TechniqueRowForm(
                data,
                prefix=f"t{row.technique.pk}",
                candidates=row.candidates,
                grant=mode,
                initial=initial,
            )
            row.form = form
            forms[row.technique.pk] = form
    return forms


def _other_forms(page: live.PowerPage, data: QueryDict | None, forms: _Forms) -> None:
    for row in page.others:
        source = row.row
        if row.kind == SourceKind.TRAINED:
            form = TraitRowForm(
                data,
                prefix=f"d{source.pk}",
                initial={
                    "base_value": source.base_value,
                    "trait_multiplier": source.trait_multiplier,
                },
            )
            forms.traits[source.pk] = form
        elif row.kind == SourceKind.CONDITION:
            form = ConditionRowForm(
                data,
                prefix=f"c{source.pk}",
                candidates=row.template_candidates if row.template is not None else None,
                initial={
                    "value": source.value,
                    "scales_with_severity": source.scales_with_severity,
                    "properties": sorted(row.template_property_ids),
                },
            )
            forms.conditions[source.pk] = form
        else:
            form = DistinctionRowForm(
                data, prefix=f"x{source.pk}", initial={"value_per_rank": source.value_per_rank}
            )
            forms.distinctions[source.pk] = form
        row.form = form


def _build_forms(request: HttpRequest, app: Application, page: live.PowerPage | None) -> _Forms:
    data = request.POST if request.method == "POST" else None
    initial: dict[str, object] = {}
    if app.pk is None and request.GET.get("capability", "").isdigit():
        initial["capability"] = int(request.GET["capability"])
    forms = _Forms(application=ApplicationForm(data, instance=app, initial=initial))
    if page is None:
        return forms
    forms.techniques = _technique_forms(page, data)
    _other_forms(page, data, forms)
    forms.new = NewTechniqueForm(
        data,
        prefix="new",
        initial={"grant_per_power": 0},
    )
    return forms


def _page_url(app: Application, request: HttpRequest) -> str:
    url = reverse("admin_power_builder", args=[app.pk])
    kept = QueryDict(mutable=True)
    for name in REFERENCE_PARAMS:
        if name in request.GET:
            kept[name] = request.GET[name]
    query = kept.urlencode()
    return f"{url}?{query}" if query else url


def _render(  # noqa: PLR0913 - the page's parts, named at the call
    request: HttpRequest,
    app: Application,
    page: live.PowerPage | None,
    forms: _Forms,
    reference_form: ReferenceForm,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    title = f"{app.name} · Power Builder" if app.pk else "New application · Power Builder"
    context: dict[str, object] = {
        **admin.site.each_context(request),
        "is_nav_sidebar_enabled": False,
        "title": title,
        "application": app,
        "form": forms.application,
        "page": page,
        "reference": reference_form,
        "needs_setup": needs_setup,
        "sentence": live.plain_words(app) if app.capability_id else "",
    }
    if page is not None:
        gifts = list(Gift.objects.order_by("name"))
        substances = live.substance_by_gift(gifts)
        context.update(
            {
                "new": forms.new,
                "gift_options": [
                    (gift, live.gift_label(gift), substances.get(gift.pk)) for gift in gifts
                ],
                "path_options": list(
                    PathGiftGrant.objects.select_related("path", "gift").order_by(
                        "path__name", "gift__name"
                    )
                ),
                "bands": live.bands(),
                "settings_url": live.movement_settings_url(),
                "new_application_url": (
                    f"{reverse('admin_power_builder_new')}?capability={page.capability.pk}"
                ),
                "default_effect_type": page.default_effect_type,
                "new_level": NEW_TECHNIQUE_LEVEL,
                "new_intensity": NEW_TECHNIQUE_INTENSITY,
                "new_control": NEW_TECHNIQUE_CONTROL,
            }
        )
    return render(request, "admin/power_builder/page.html", context)


def _set_properties(owner: object, current: set[int], wanted: set[int]) -> bool:
    """Make ``owner.properties`` hold ``wanted``; whether anything changed."""
    if wanted == current:
        return False
    if current - wanted:
        owner.properties.remove(*(current - wanted))
    if wanted - current:
        owner.properties.add(*(wanted - current))
    return True


def _save_techniques(page: live.PowerPage, forms: _Forms) -> list[Technique]:
    touched: list[Technique] = []
    for row in page.technique_rows:
        form = forms.techniques[row.technique.pk]
        data = form.cleaned_data
        candidate_ids = {prop.pk for prop in row.candidates}
        wanted = (row.property_ids - candidate_ids) | set(data["properties"])
        changed = _set_properties(row.technique, row.property_ids, wanted)
        grant = row.grant
        if form.grant_mode == GrantMode.EDIT and grant is not None:
            base, per_power = data["grant_base"], data["grant_per_power"]
            if grant.base_value != base or grant.intensity_multiplier != per_power:
                grant.base_value = base
                grant.intensity_multiplier = per_power
                grant.save(update_fields=["base_value", "intensity_multiplier"])
                changed = True
        if form.grant_mode == GrantMode.OFFER and data.get("grant_it"):
            TechniqueCapabilityGrant.objects.create(
                technique=row.technique,
                capability=page.capability,
                base_value=data["grant_base"],
                intensity_multiplier=data["grant_per_power"],
            )
            changed = True
        if changed:
            invalidate_technique_payload_caches(row.technique)
            touched.append(row.technique)
    return touched


def _save_others(page: live.PowerPage, forms: _Forms) -> list[CreditedContent]:
    touched: list[CreditedContent] = []
    for row in page.others:
        source = row.row
        if row.kind == SourceKind.TRAINED:
            data = forms.traits[source.pk].cleaned_data
            fields = ("base_value", "trait_multiplier")
        elif row.kind == SourceKind.CONDITION:
            data = forms.conditions[source.pk].cleaned_data
            fields = ("value", "scales_with_severity")
        else:
            data = forms.distinctions[source.pk].cleaned_data
            fields = ("value_per_rank",)
        changed = [name for name in fields if getattr(source, name) != data[name]]
        for name in changed:
            setattr(source, name, data[name])
        if changed:
            source.save(update_fields=changed)
        props_changed = False
        if row.kind == SourceKind.CONDITION and row.template is not None:
            form = forms.conditions[source.pk]
            current = row.template_property_ids
            candidate_ids = {pk for pk, _label in form.fields["properties"].choices}
            wanted = (current - candidate_ids) | set(data["properties"])
            props_changed = _set_properties(row.template, current, wanted)
        if row.kind == SourceKind.CONDITION and (changed or props_changed):
            touched.append(source.get_condition_template())
        elif row.kind == SourceKind.DISTINCTION and changed:
            touched.append(source)
    return touched


def _add_technique(app: Application, page: live.PowerPage, form: NewTechniqueForm) -> Technique:
    data = form.cleaned_data
    gift = data["gift"]
    effect_type = page.default_effect_type
    technique = create_technique(
        creator=None,
        name=data["name"],
        gift=gift,
        effect_type=effect_type,
        intensity=NEW_TECHNIQUE_INTENSITY,
        control=NEW_TECHNIQUE_CONTROL,
        anima_cost=effect_type.base_anima_cost,
        level=NEW_TECHNIQUE_LEVEL,
        action_category=ActionCategory.PHYSICAL,
        description="",
    )
    required = app.required_effect_property
    if required is not None and data["with_app_property"]:
        technique.properties.add(required)
    substance = substance_mark_for(gift)
    keep_required = required is not None and data["with_app_property"]
    if (
        substance is not None
        and not data["with_substance"]
        and not (keep_required and substance.pk == required.pk)
    ):
        technique.properties.remove(substance)
    TechniqueCapabilityGrant.objects.create(
        technique=technique,
        capability=page.capability,
        base_value=data["grant_base"],
        intensity_multiplier=data["grant_per_power"],
    )
    path_grant = data.get("path_grant")
    if path_grant is not None:
        path_grant.starter_techniques.add(technique)
    invalidate_technique_payload_caches(technique)
    return technique


def _save(
    request: HttpRequest,
    app: Application,
    page: live.PowerPage | None,
    forms: _Forms,
    contributor: ContentContributor,
) -> Application:
    """Write the whole page in one transaction and credit every credited row it touched."""
    adding = app.pk is None
    with transaction.atomic():
        saved = forms.application.save()
        touched: list[CreditedContent] = [saved]
        added: Technique | None = None
        if page is not None:
            touched.extend(_save_techniques(page, forms))
            touched.extend(_save_others(page, forms))
            if forms.new is not None and forms.new.adds:
                added = _add_technique(saved, page, forms.new)
                touched.append(added)
        stamped: set[tuple[type, int]] = set()
        for row in touched:
            key = (type(row), row.pk)
            if key not in stamped:
                stamped.add(key)
                stamp_written(row, contributor)
        LogEntry.objects.log_actions(
            request.user.pk,
            [saved],
            ADDITION if adding else CHANGE,
            change_message="Saved on the Power Builder (#5066)",
        )
        if added is not None:
            LogEntry.objects.log_actions(
                request.user.pk,
                [added],
                ADDITION,
                change_message=f"Added on the Power Builder for {saved.name} (#5066)",
            )
    return saved


def _new_technique_refusal(page: live.PowerPage | None, forms: _Forms) -> bool:
    """Refuse a new technique when no effect type exists to give it."""
    new = forms.new
    if page is None or new is None or not new.adds or page.default_effect_type is not None:
        return False
    new.add_error("name", "No effect type exists yet; add one before adding a technique.")
    return True


@superuser_required
def power_builder(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """GET renders the page; POST saves every row in one transaction and credits it."""
    app = Application() if pk is None else get_object_or_404(Application, pk=pk)
    contributor = current_contributor(request.user)
    reference_form, reference = _reference(request.GET)
    page = live.build_page(app, reference) if app.pk else None
    if request.method != "POST":
        forms = _build_forms(request, app, page)
        return _render(request, app, page, forms, reference_form, needs_setup=contributor is None)
    guard = CacheGuard()
    guard.watch_created(Application, Technique, TechniqueCapabilityGrant)
    guard.keep(app, *(page.kept_rows() if page is not None else []))
    committed = False
    try:
        forms = _build_forms(request, app, page)
        if contributor is None:
            return _render(request, app, page, forms, reference_form, needs_setup=True)
        if not forms.is_valid() or _new_technique_refusal(page, forms):
            return _render(request, app, page, forms, reference_form)
        saved = _save(request, app, page, forms, contributor)
        committed = True
    finally:
        # A refusal, the setup gate, or anything raised before or inside the transaction:
        # nothing was written, so every kept row gets its stored values back, after the
        # page (which shows the posted values) has rendered.
        if not committed:
            guard.restore()
    messages.success(request, "Saved and credited to you.")
    return redirect(_page_url(saved, request))


@superuser_required
def power_builder_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` redirect target for the Builders panel's application picker."""
    pk_raw = request.GET.get("pk", "")
    if not pk_raw.isdigit() or not Application.objects.filter(pk=pk_raw).exists():
        return HttpResponseBadRequest("Pick an application to open.")
    return redirect("admin_power_builder", pk=int(pk_raw))


@superuser_required
@require_POST
def power_builder_review(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark this Application reviewed."""
    app = get_object_or_404(Application, pk=pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking this reviewed.")
    else:
        stamp_reviewed(app, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_power_builder", args=[pk]))
