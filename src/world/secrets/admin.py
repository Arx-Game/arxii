from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist

from world.secrets.models import Secret, SecretCategory, SecretKnowledge


@admin.register(SecretCategory)
class SecretCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


class SecretKnowledgeInline(admin.TabularInline):
    """Read-only: who knows this secret (#3679) — audit-only, edited via SecretKnowledgeAdmin."""

    model = SecretKnowledge
    fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    readonly_fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    autocomplete_fields = ["scene", "subject_item_instance"]
    list_display = ["__str__", "level", "category", "provenance", "created_date"]
    list_filter = ["level", "provenance", "category"]
    search_fields = ["content", "consequences"]
    raw_id_fields = ["subject_sheet", "author_persona"]
    readonly_fields = ["created_date", "updated_date", "get_relocated_distinction"]
    inlines = [SecretKnowledgeInline]

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
