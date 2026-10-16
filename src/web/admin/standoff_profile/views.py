"""The Standoff Profile Builder (#4354): one creature's cause, drives and faction rules.

Pattern: the Distinction Builder. One page writes ``CreatureTemplate.cause``,
``cause_margin_percent`` and ``organization`` (the default affiliation, #4361), every
``CreatureDrive`` and every template-owned ``FactionRule`` in one transaction, with a
context rail (inherited rules, grade preview, cause check, placements) so the author never
needs a second tab. Replaces the two stock inlines on the creature template's
change page. Save credits the template to the operator's linked contributor; an unlinked
operator sees the setup guidance and nothing is saved, as on every Builder page.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin, messages
from django.db import transaction
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_written
from web.admin.standoff_profile import live
from web.admin.standoff_profile.forms import (
    CreatureDriveFormSet,
    FactionRuleFormSet,
    StandoffProfileForm,
)
from web.admin.tuning.views import superuser_required
from world.combat.models import CreatureTemplate
from world.standoffs.models import CreatureDrive, FactionRule
from world.standoffs.services.profile import TEMPLATE_LEVEL, inherited_rules

#: The submit button's name that stays on this page after saving; "Save" returns to the
#: creature's change page, as a stock change form does.
CONTINUE_BUTTON = "save_continue"


@dataclass
class _ProfileForms:
    form: StandoffProfileForm
    drives: CreatureDriveFormSet
    rules: FactionRuleFormSet

    @property
    def media(self) -> Media:
        return self.form.media + self.drives.media + self.rules.media

    def is_valid(self) -> bool:
        return self.form.is_valid() and self.drives.is_valid() and self.rules.is_valid()


def _build_forms(request: HttpRequest, template: CreatureTemplate) -> _ProfileForms:
    data = request.POST if request.method == "POST" else None
    return _ProfileForms(
        form=StandoffProfileForm(data, instance=template),
        drives=CreatureDriveFormSet(
            data,
            instance=template,
            prefix="drives",
            queryset=CreatureDrive.objects.select_related("property"),
        ),
        rules=FactionRuleFormSet(
            data,
            instance=template,
            prefix="rules",
            queryset=FactionRule.objects.select_related("drive", "deed_archetype").order_by("pk"),
        ),
    )


def _render_page(
    request: HttpRequest,
    template: CreatureTemplate,
    forms: _ProfileForms,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    level = live.preview_number(request.GET.get("level"), live.DEFAULT_PREVIEW_LEVEL)
    party = live.preview_number(request.GET.get("party"), live.DEFAULT_PREVIEW_PARTY)
    drive_context = live.drive_context(template)
    drive_rows = [(form, drive_context.get(form.instance.pk)) for form in forms.drives.forms]
    placements = live.placements(template)
    inherited = [
        entry
        for entry in inherited_rules(template, template.organization)
        if entry.level != TEMPLATE_LEVEL
    ]
    return render(
        request,
        "admin/standoff_profile/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Standoff profile: {template.name}",
            "creature": template,
            "form": forms.form,
            "drives": forms.drives,
            "drive_rows": drive_rows,
            "rules": forms.rules,
            "media": forms.media,
            "needs_setup": needs_setup,
            "preview_level": level,
            "preview_party": party,
            "preview": live.grade_preview(template, level),
            "cause_check": live.cause_check(template, level, party),
            "placements": placements,
            "inherited": inherited,
            "change_url": reverse("admin:arxii_creaturetemplate_change", args=[template.pk]),
        },
    )


@superuser_required
def standoff_profile(request: HttpRequest, template_pk: int) -> HttpResponse:
    """GET renders the page; POST saves the cause, drives and faction rules together."""
    template = get_object_or_404(CreatureTemplate, pk=template_pk)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, template)
    if request.method != "POST":
        return _render_page(request, template, forms, needs_setup=contributor is None)
    if contributor is None:
        return _render_page(request, template, forms, needs_setup=True)
    if not forms.is_valid():
        response = _render_page(request, template, forms)
        # Validating a ModelForm writes the posted values onto its instance, and the
        # template is the identity-mapped one every other reader shares: drop it so the
        # next reader loads what the database holds, not this refused edit.
        template.flush_from_cache(force=True)
        for form in (*forms.drives.forms, *forms.rules.forms):
            if form.instance.pk is not None:
                form.instance.flush_from_cache(force=True)
        return response
    with transaction.atomic():
        saved = forms.form.save()
        forms.drives.instance = saved
        forms.drives.save()
        forms.rules.instance = saved
        forms.rules.save()
        stamp_written(saved, contributor)
    messages.success(request, "Saved and credited to you.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(reverse("admin_standoff_profile", args=[saved.pk]))
    return redirect(reverse("admin:arxii_creaturetemplate_change", args=[saved.pk]))
