from django.contrib import admin
from django.utils.html import format_html

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


#: Query-string values for CreditStatusListFilter's three states (also reused
#: as credit_status's cell text below). Module-level constants, not bare
#: string literals, per tools/lint_string_literal.py.
_CREDIT_UNWRITTEN = "unwritten"
_CREDIT_WRITTEN = "written"
_CREDIT_REVIEWED = "reviewed"


class CreditStatusListFilter(admin.SimpleListFilter):
    """Three-way derived credit state for any CreditedContent changelist (#3020).

    Derived from ``written_by``/``reviewed_by`` on every evaluation - no
    stored enum, per ``CreditedContent``'s docstring. Distinct from
    ``web.admin.constants.BacklogStatusFilter``, the workbench queue's
    ``?status=`` vocabulary (placeholder/unwritten/unreviewed): this filter
    partitions every row into exactly one of unwritten/written/reviewed.
    Attached to every registered credited-model admin by
    ``web.admin.apps._attach_credit_admin_extras``, never listed by hand.
    """

    title = "credit status"
    parameter_name = "credit"

    #: Django passes both hook arguments positionally, so the leading underscores
    #: mark them unused without needing a suppression.
    def lookups(self, _request, _model_admin):
        return [
            (_CREDIT_UNWRITTEN, "Unwritten"),
            (_CREDIT_WRITTEN, "Written, unreviewed"),
            (_CREDIT_REVIEWED, "Reviewed"),
        ]

    def queryset(self, _request, queryset):
        if self.value() == _CREDIT_UNWRITTEN:
            return queryset.filter(written_by__isnull=True)
        if self.value() == _CREDIT_WRITTEN:
            return queryset.filter(written_by__isnull=False, reviewed_by__isnull=True)
        if self.value() == _CREDIT_REVIEWED:
            return queryset.filter(reviewed_by__isnull=False)
        return queryset


@admin.display(description="Credit")
def credit_status(obj):
    """Changelist cell: the row's derived credit state, linked into the workbench.

    Plain text for a credited model with no prose fields - a real path, not
    defensive (the backlog applies the same guard, ``backlog.py``'s
    ``if not prose_names``); the workbench editor has nothing to edit there.
    """
    from core.app_domains import domain_of  # noqa: PLC0415
    from core_management.prose_fields import prose_fields_for  # noqa: PLC0415
    from web.admin.authoring.links import workbench_editor_url  # noqa: PLC0415

    if obj.reviewed_by_id is not None:
        state = _CREDIT_REVIEWED
    elif obj.written_by_id is not None:
        state = _CREDIT_WRITTEN
    else:
        state = _CREDIT_UNWRITTEN
    model = type(obj)
    if not prose_fields_for(model):
        return state
    url = workbench_editor_url(f"{domain_of(model)}.{model.__name__}", obj.pk)
    return format_html('<a href="{}">{}</a>', url, state)


@admin.register(ContentContributor)
class ContentContributorAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name", "notes"]

    # PlayerData.contributor's reverse accessor. PlayerData is a large table
    # (web_admin.checks.LARGE_TABLE_MODELS), but this reverse O2O is never
    # rendered as a form widget - it isn't listed in fieldsets/list_display -
    # so there is no <select> to blow up. Exempt rather than autocomplete.
    large_table_widget_exempt = ["player_data"]
