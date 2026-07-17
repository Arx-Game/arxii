from django.contrib import admin

from world.secrets.models import Secret, SecretCategory, SecretKnowledge


@admin.register(SecretCategory)
class SecretCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    autocomplete_fields = ["scene"]
    list_display = ["__str__", "level", "category", "provenance", "created_date"]
    list_filter = ["level", "provenance", "category"]
    search_fields = ["content", "consequences"]
    raw_id_fields = ["subject_sheet", "author_persona"]
    readonly_fields = ["created_date", "updated_date"]


@admin.register(SecretKnowledge)
class SecretKnowledgeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "knows_category", "knows_consequences", "found_at"]
    list_filter = ["knows_category", "knows_consequences"]
    raw_id_fields = ["roster_entry", "secret"]
    readonly_fields = ["found_at"]
