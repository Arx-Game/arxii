"""Admin for the captivity system (#931) — staff visibility into who is held."""

from django.contrib import admin

from world.captivity.models import Captivity


@admin.register(Captivity)
class CaptivityAdmin(admin.ModelAdmin):
    list_display = (
        "captive",
        "status",
        "captor_organization",
        "offscreen_loss_allowed",
        "captured_at",
        "resolved_at",
    )
    list_filter = ("status", "offscreen_loss_allowed")
    search_fields = ("captive__character__db_key", "captor_organization__name")
    raw_id_fields = ("captive", "cell", "captor_organization", "ransom_contract")
    list_select_related = ("captive__character", "captor_organization")
