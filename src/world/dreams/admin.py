"""Admin for DreamReflection and Dream Peril config."""

from django.contrib import admin

from world.dreams.models import DreamPerilConfig, DreamReflection


@admin.register(DreamReflection)
class DreamReflectionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["descent_target", "dream_room", "waking_room"]
    list_display = ("waking_room", "dream_room", "descent_target", "is_active")
    list_filter = ("is_active",)
    search_fields = ("waking_room__objectdb__db_key", "dream_room__objectdb__db_key")


@admin.register(DreamPerilConfig)
class DreamPerilConfigAdmin(admin.ModelAdmin):
    """#3831 - the singleton Dream Peril collapse resolution config (#2290)."""

    list_display = ("pk", "resist_check_type", "resist_difficulty")
    autocomplete_fields = ["resist_check_type"]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not DreamPerilConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False
