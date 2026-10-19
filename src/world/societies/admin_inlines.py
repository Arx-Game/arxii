"""Admin inlines shared by the apps that own an authored act (#4473, #4339).

``NamedOrganizationInline`` is how an author names the organizations a mission renown award
or a LEGEND_AWARD story consequence harms or helps. It lives here, not in the owners' admin
modules, because both owners need it and neither should import the other's admin.
"""

from django.contrib import admin

from world.admin_utils import OneRowPerFormSet
from world.societies.models import NamedOrganization


class NamedOrganizationInline(admin.TabularInline):
    """Organizations this act names, with what each would pay (staff-only estimate)."""

    model = NamedOrganization
    formset = OneRowPerFormSet
    extra = 0
    verbose_name_plural = "Organizations this act names"
    autocomplete_fields = ["organization"]
    readonly_fields = ["estimate"]

    @admin.display(description="Effective principles and estimate (read only)")
    def estimate(self, obj: NamedOrganization) -> str:
        """The organization's principles and what this row pays, from the saved values."""
        from world.societies.named_organizations import estimate_for_staff  # noqa: PLC0415

        if obj.pk is None:
            return "Save to see the estimate."
        return estimate_for_staff(obj)


class MissionAwardNamedOrganizationInline(NamedOrganizationInline):
    """On a mission renown award the base comes from the award's magnitude."""

    fk_name = "mission_award"
    template = "admin/societies/named_org_mission_inline.html"
    fields = ["organization", "role", "only_if_exposed", "estimate"]


class ConsequenceNamedOrganizationInline(NamedOrganizationInline):
    """On a LEGEND_AWARD consequence effect each row carries its own base amount."""

    fk_name = "consequence_effect"
    template = "admin/societies/named_org_consequence_inline.html"
    fields = ["organization", "role", "base_amount", "only_if_exposed", "estimate"]
