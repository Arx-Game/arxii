"""Admin for the captivity system (#931) — staff visibility into who is held."""

from django.contrib import admin

from world.captivity.models import Captivity, CaptivityConfig


@admin.register(Captivity)
class CaptivityAdmin(admin.ModelAdmin):
    autocomplete_fields = ["holding_room", "return_location"]
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
    raw_id_fields = ("captive", "cell", "captor_organization", "ransom_project")
    list_select_related = ("captive__character", "captor_organization")


@admin.register(CaptivityConfig)
class CaptivityConfigAdmin(admin.ModelAdmin):
    """#3831 - the singleton captivity-loop defaults (captive/rescue template, cell text)."""

    list_display = ("cell_name", "captive_template", "rescue_template", "clue_detect_difficulty")
    autocomplete_fields = ("captive_template", "rescue_template")

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not CaptivityConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False
