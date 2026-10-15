"""The Faction Rules page (#4361): one organization's or society's faction rules.

Pattern: the Standoff Profile Builder. One page writes every ``FactionRule`` the owner
holds, each test built with the predicate rule widget, beside a rail of what the owner
inherits from above (with the precedence rule), what it reaches below, and a staff-only
"test a character" picker that runs the rules (its own and inherited) against a chosen
character and says why each matched. Reached from the Organization and Society change
pages (``links.builder_url``). Faction rules are not credited content, so a save needs
no linked contributor.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Model
from django.forms import BaseInlineFormSet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from web.admin.faction_rules import live
from web.admin.faction_rules.forms import (
    CharacterTestForm,
    OrganizationRuleFormSet,
    SocietyRuleFormSet,
)
from web.admin.tuning.views import superuser_required
from world.societies.models import Organization, Society
from world.standoffs.models import FactionRule
from world.standoffs.services.faction_rules import run_rules_against
from world.standoffs.services.profile import (
    TEMPLATE_LEVEL,
    InheritedRule,
    affiliation_rules,
    society_rules,
)

CONTINUE_BUTTON = "save_continue"


@dataclass(frozen=True)
class _Owner:
    """The organization or society the page edits, and how to talk about it."""

    instance: Model
    noun: str
    page_url: str
    change_url: str
    changelist_url: str
    changelist_label: str
    own_level: int
    entries: list[InheritedRule]
    reach: live.Reach


def _organization_owner(org: Organization) -> _Owner:
    entries = affiliation_rules(org, first_level=TEMPLATE_LEVEL)
    return _Owner(
        instance=org,
        noun="organization",
        page_url=reverse("admin_faction_rules_organization", args=[org.pk]),
        change_url=reverse("admin:arxii_organization_change", args=[org.pk]),
        changelist_url=reverse("admin:arxii_organization_changelist"),
        changelist_label="Organizations",
        own_level=TEMPLATE_LEVEL,
        entries=entries,
        reach=live.organization_reach(org),
    )


def _society_owner(society: Society) -> _Owner:
    return _Owner(
        instance=society,
        noun="society",
        page_url=reverse("admin_faction_rules_society", args=[society.pk]),
        change_url=reverse("admin:arxii_society_change", args=[society.pk]),
        changelist_url=reverse("admin:arxii_society_changelist"),
        changelist_label="Societies",
        own_level=TEMPLATE_LEVEL,
        entries=society_rules(society),
        reach=live.society_reach(society),
    )


def _render(request: HttpRequest, owner: _Owner, formset: BaseInlineFormSet) -> HttpResponse:
    test_form = CharacterTestForm(request.GET or None)
    tested_name = ""
    results = None
    if test_form.is_valid() and test_form.cleaned_data["character"]:
        tested_name = test_form.cleaned_data["character"]
        sheet = live.find_character(tested_name)
        if sheet is not None:
            results = run_rules_against(sheet, owner.entries, owner.own_level)
    inherited = [entry for entry in owner.entries if entry.level != owner.own_level]
    return render(
        request,
        "admin/faction_rules/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Faction rules: {owner.instance}",
            "owner": owner,
            "rules": formset,
            "media": formset.media + test_form.media,
            "inherited": inherited,
            "test_form": test_form,
            "tested_name": tested_name,
            "results": results,
        },
    )


def _page(request: HttpRequest, owner: _Owner, formset_class: type) -> HttpResponse:
    data = request.POST if request.method == "POST" else None
    formset = formset_class(
        data,
        instance=owner.instance,
        prefix="rules",
        queryset=FactionRule.objects.select_related("drive", "deed_archetype").order_by("pk"),
    )
    if request.method != "POST":
        return _render(request, owner, formset)
    if not formset.is_valid():
        response = _render(request, owner, formset)
        # A refused edit must not linger on the identity-mapped rules every reader shares.
        for form in formset.forms:
            if form.instance.pk is not None:
                form.instance.flush_from_cache(force=True)
        return response
    with transaction.atomic():
        formset.save()
    messages.success(request, "Faction rules saved.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(owner.page_url)
    return redirect(owner.change_url)


@superuser_required
def organization_faction_rules(request: HttpRequest, org_pk: int) -> HttpResponse:
    """GET renders an organization's rules; POST saves them together."""
    org = get_object_or_404(Organization, pk=org_pk)
    return _page(request, _organization_owner(org), OrganizationRuleFormSet)


@superuser_required
def society_faction_rules(request: HttpRequest, society_pk: int) -> HttpResponse:
    """GET renders a society's rules; POST saves them together."""
    society = get_object_or_404(Society, pk=society_pk)
    return _page(request, _society_owner(society), SocietyRuleFormSet)
