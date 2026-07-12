"""Admin for the room_features system."""

from django.contrib import admin

from world.room_features.models import (
    RoomFeatureInstance,
    RoomFeatureKind,
    RoomFeatureKindInstallRitual,
    RoomFeatureKindOwnerType,
    RoomFeatureProgressionDetails,
    Trap,
    VaultAccessEntry,
    VaultDetails,
)


@admin.register(RoomFeatureKind)
class RoomFeatureKindAdmin(admin.ModelAdmin):
    list_display = ("name", "service_strategy", "max_level", "install_mechanism")
    list_filter = ("install_mechanism",)
    search_fields = ("name",)


@admin.register(RoomFeatureInstance)
class RoomFeatureInstanceAdmin(admin.ModelAdmin):
    list_display = ("room_profile", "feature_kind", "level", "dissolved_at")
    list_filter = ("feature_kind",)
    readonly_fields = ("installed_at",)


@admin.register(RoomFeatureKindInstallRitual)
class RoomFeatureKindInstallRitualAdmin(admin.ModelAdmin):
    list_display = ("feature_kind", "ritual", "variant_label")


@admin.register(RoomFeatureKindOwnerType)
class RoomFeatureKindOwnerTypeAdmin(admin.ModelAdmin):
    list_display = ("feature_kind", "owner_type")


@admin.register(RoomFeatureProgressionDetails)
class RoomFeatureProgressionDetailsAdmin(admin.ModelAdmin):
    list_display = ("project", "target_room_profile", "target_feature_kind", "target_level")
    readonly_fields = ("project", "target_room_profile", "target_feature_kind", "target_level")


@admin.register(Trap)
class TrapAdmin(admin.ModelAdmin):
    list_display = ("name", "room_profile", "is_armed", "is_hidden")
    list_filter = ("is_armed", "is_hidden")


@admin.register(VaultDetails)
class VaultDetailsAdmin(admin.ModelAdmin):
    list_display = ("feature_instance", "founder_persona", "max_items")
    readonly_fields = ("feature_instance", "founder_persona", "max_items")


@admin.register(VaultAccessEntry)
class VaultAccessEntryAdmin(admin.ModelAdmin):
    list_display = (
        "vault_details",
        "holder_type",
        "holder_persona",
        "holder_organization",
        "added_by",
        "added_at",
    )
    readonly_fields = (
        "vault_details",
        "holder_type",
        "holder_persona",
        "holder_organization",
        "added_by",
        "added_at",
    )
