from django.contrib import admin

from world.secrets.models import Secret, SecretCategory


@admin.register(SecretCategory)
class SecretCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    list_display = ["__str__", "level", "category", "provenance", "created_date"]
    list_filter = ["level", "provenance", "category"]
    search_fields = ["content", "consequences"]
    raw_id_fields = ["subject_sheet", "second_party_sheet", "author_persona"]
    readonly_fields = ["created_date", "updated_date"]
