from django.contrib import admin

from world.contributors.models import ContentContributor

#: Reusable fieldset for a ModelAdmin that declares ``fieldsets`` explicitly.
#: Without it, an admin with a fieldset list simply hides the credit fields -
#: the form shows only what the fieldsets name. Append it to those admins.
CREDIT_FIELDSET = (
    "Credit",
    {
        "fields": ("written_by", "written_on", "reviewed_by", "reviewed_on"),
        "classes": ("collapse",),
    },
)


@admin.register(ContentContributor)
class ContentContributorAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name", "notes"]

    # PlayerData.contributor's reverse accessor. PlayerData is a large table
    # (web_admin.checks.LARGE_TABLE_MODELS), but this reverse O2O is never
    # rendered as a form widget - it isn't listed in fieldsets/list_display -
    # so there is no <select> to blow up. Exempt rather than autocomplete.
    large_table_widget_exempt = ["player_data"]
