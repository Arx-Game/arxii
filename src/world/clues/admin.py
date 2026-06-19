from django.contrib import admin

from world.clues.models import (
    CharacterClue,
    Clue,
    ClueTrigger,
    ItemClueTrigger,
    RoomClue,
)


@admin.register(Clue)
class ClueAdmin(admin.ModelAdmin):
    """Authoring surface for clues — add/remove/rename freely (data, not code)."""

    list_display = ["name", "target_kind", "get_active_target_name", "resolution_mode"]
    list_filter = ["target_kind", "resolution_mode"]
    search_fields = ["name", "description"]

    @admin.display(description="Target")
    def get_active_target_name(self, obj: Clue) -> str:
        return obj.get_active_target_name()


@admin.register(CharacterClue)
class CharacterClueAdmin(admin.ModelAdmin):
    """Read-only debugging view of who holds which clues."""

    list_display = ["roster_entry", "clue", "found_at"]
    list_filter = ["clue__target_kind"]
    readonly_fields = ["found_at"]


@admin.register(RoomClue)
class RoomClueAdmin(admin.ModelAdmin):
    """Authoring surface for placing clues in rooms (data, not code)."""

    list_display = ["clue", "room_profile", "detect_difficulty", "is_active"]
    list_filter = ["is_active", "clue__target_kind"]
    search_fields = ["clue__name"]


@admin.register(ClueTrigger)
class ClueTriggerAdmin(admin.ModelAdmin):
    """Authoring surface for passive clue triggers (data, not code)."""

    list_display = ["clue", "room_profile", "is_active"]
    list_filter = ["is_active", "clue__target_kind"]
    search_fields = ["clue__name"]


@admin.register(ItemClueTrigger)
class ItemClueTriggerAdmin(admin.ModelAdmin):
    """Authoring surface for passive item-acquisition clue triggers (data, not code)."""

    list_display = ["clue", "item_template", "is_active"]
    list_filter = ["is_active", "clue__target_kind"]
    search_fields = ["clue__name", "item_template__name"]
