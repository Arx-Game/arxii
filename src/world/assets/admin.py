from django.contrib import admin

from world.assets.models import CluePool, CluePoolEntry, DistinctionAssetGrant, NPCAsset


@admin.register(NPCAsset)
class NPCAssetAdmin(admin.ModelAdmin):
    list_display = [
        "asset_persona",
        "promoter_persona",
        "role_context",
        "acquisition_source",
        "status",
        "weekly_income",
        "uncollected_pool",
        "created_at",
    ]
    list_filter = ["role_context", "acquisition_source", "status"]
    search_fields = ["asset_persona__name", "promoter_persona__name"]
    # source_functionary omitted: no ModelAdmin is registered for Functionary
    # in world.npc_services, and autocomplete_fields requires the target
    # model's admin to declare search_fields (admin.E039).
    autocomplete_fields = ["promoter_persona", "asset_persona"]


@admin.register(DistinctionAssetGrant)
class DistinctionAssetGrantAdmin(admin.ModelAdmin):
    list_display = [
        "distinction",
        "npc_role",
        "role_context",
        "starting_affection",
        "asset_display_name",
    ]
    list_filter = ["role_context"]
    search_fields = ["distinction__name", "asset_display_name"]
    # npc_role omitted from autocomplete_fields: no ModelAdmin is registered
    # for NPCRole in world.npc_services, and autocomplete_fields requires the
    # target model's admin to declare search_fields (admin.E039).
    autocomplete_fields = ["distinction"]


class CluePoolEntryInline(admin.TabularInline):
    model = CluePoolEntry
    extra = 1
    autocomplete_fields = ["clue"]


@admin.register(CluePool)
class CluePoolAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]
    inlines = [CluePoolEntryInline]
