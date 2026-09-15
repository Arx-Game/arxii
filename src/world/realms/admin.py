from django.contrib import admin

from world.realms.models import Realm, RealmTestamentSection


class RealmTestamentSectionInline(admin.TabularInline):
    """The realm's testament, one row per movement (#3725)."""

    model = RealmTestamentSection
    extra = 0
    fields = ["sort_order", "body", "motto"]
    ordering = ["sort_order"]


@admin.register(Realm)
class RealmAdmin(admin.ModelAdmin):
    list_display = ["name", "formal_name", "theme"]
    search_fields = ["name", "formal_name"]
    fields = ["name", "formal_name", "description", "crest_asset", "theme"]
    inlines = [RealmTestamentSectionInline]
