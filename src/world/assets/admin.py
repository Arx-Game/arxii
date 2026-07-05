from django.contrib import admin

from world.assets.models import NPCAsset


@admin.register(NPCAsset)
class NPCAssetAdmin(admin.ModelAdmin):
    list_display = ["asset_persona", "promoter_persona", "role_context", "status", "created_at"]
    list_filter = ["role_context", "status"]
    search_fields = ["asset_persona__name", "promoter_persona__name"]
    # source_functionary omitted: no ModelAdmin is registered for Functionary
    # in world.npc_services, and autocomplete_fields requires the target
    # model's admin to declare search_fields (admin.E039).
    autocomplete_fields = ["promoter_persona", "asset_persona"]
