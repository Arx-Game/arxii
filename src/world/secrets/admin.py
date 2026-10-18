from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist

from world.admin_utils import OneRowPerFormSet
from world.secrets.constants import DEFAULT_VICTIM_SEVERITY_BY_LEVEL
from world.secrets.models import Secret, SecretCategory, SecretKnowledge, SecretVictim


@admin.register(SecretCategory)
class SecretCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


class SecretKnowledgeInline(admin.TabularInline):
    """Read-only: who knows this secret (#3679) — audit-only, edited via SecretKnowledgeAdmin."""

    model = SecretKnowledge
    formset = OneRowPerFormSet
    fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    readonly_fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False


class SecretVictimInline(admin.TabularInline):
    """Who the secret's underlying fact wronged (#4448): an organization or a persona.

    ``severity`` is left out on purpose: the size of an organization victim's reaction on
    exposure is always the secret's level default, never chosen per case.
    """

    model = SecretVictim
    verbose_name_plural = "Victims"
    fields = ["organization", "persona"]
    raw_id_fields = ["organization", "persona"]
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["organization"].help_text = (
            "Set exactly one of organization or persona, while authoring the secret. There is "
            "no per-victim size: the reaction is always the level default. An organization "
            "victim's reputation of the subject drops on the secret's first exposure; a "
            "persona victim is told and decides their own reaction. A spy job's residue "
            "secret fills this row from the job's target."
        )
        return formset


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    autocomplete_fields = ["scene", "subject_item_instance"]
    list_display = ["__str__", "level", "category", "provenance", "created_date"]
    list_filter = ["level", "provenance", "category"]
    search_fields = ["content", "consequences"]
    raw_id_fields = ["subject_sheet", "author_persona", "hook"]
    readonly_fields = [
        "created_date",
        "updated_date",
        "get_relocated_distinction",
        "get_default_victim_severity",
    ]
    inlines = [SecretVictimInline, SecretKnowledgeInline]

    @admin.display(description="Default victim severity")
    def get_default_victim_severity(self, obj: Secret) -> str:
        """What a victim organization's reputation drops by on this secret's first exposure."""
        if obj.pk is None:
            return "-"
        exposed = obj.societies_exposed.exists()
        return (
            f"{DEFAULT_VICTIM_SEVERITY_BY_LEVEL.get(obj.level, 0)} at level {obj.level}. "
            f"{'Already exposed.' if exposed else 'Not yet exposed.'}"
        )

    @admin.display(description="Relocated from distinction")
    def get_relocated_distinction(self, obj: Secret) -> str:
        try:
            return str(obj.distinction)
        except ObjectDoesNotExist:
            return "-"


@admin.register(SecretKnowledge)
class SecretKnowledgeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "knows_category", "knows_consequences", "found_at"]
    list_filter = ["knows_category", "knows_consequences"]
    raw_id_fields = ["roster_entry", "secret"]
    readonly_fields = ["found_at"]
