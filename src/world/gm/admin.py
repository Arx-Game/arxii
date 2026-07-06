"""GM admin configuration."""

from django.contrib import admin

from world.gm.models import (
    GMApplication,
    GMLevelCap,
    GMLevelChange,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
)


@admin.register(GMProfile)
class GMProfileAdmin(admin.ModelAdmin):
    list_display = ["account", "level", "approved_at"]
    list_filter = ["level"]
    raw_id_fields = ["account", "approved_by"]


@admin.register(GMApplication)
class GMApplicationAdmin(admin.ModelAdmin):
    list_display = ["account", "status", "created_at", "reviewed_by"]
    list_filter = ["status"]
    raw_id_fields = ["account", "reviewed_by"]


@admin.register(GMTable)
class GMTableAdmin(admin.ModelAdmin):
    list_display = ["name", "gm", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["gm"]


@admin.register(GMTableMembership)
class GMTableMembershipAdmin(admin.ModelAdmin):
    list_display = ["table", "persona", "joined_at", "left_at"]
    list_filter = ["left_at"]
    raw_id_fields = ["table", "persona"]


@admin.register(GMRosterInvite)
class GMRosterInviteAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "roster_entry",
        "created_by",
        "created_at",
        "expires_at",
        "is_public",
        "claimed_by",
    ]
    list_filter = ["is_public", "claimed_at"]
    search_fields = ["code", "invited_email"]
    raw_id_fields = ["roster_entry", "created_by", "claimed_by"]


@admin.register(GMLevelCap)
class GMLevelCapAdmin(admin.ModelAdmin):
    list_display = [
        "level",
        "max_beat_risk",
        "allow_custom_stakes",
        "allow_global_scope_authoring",
    ]
    list_filter = ["max_beat_risk", "allow_custom_stakes", "allow_global_scope_authoring"]


@admin.register(GMLevelChange)
class GMLevelChangeAdmin(admin.ModelAdmin):
    """Audit row for a staff-driven GM level change — written by ``promote_gm`` only.

    Read-only in admin: no add/change/delete, so the audit trail can't be
    hand-edited or backdated.
    """

    list_display = ["profile", "old_level", "new_level", "changed_by", "created_at"]
    list_filter = ["old_level", "new_level"]
    raw_id_fields = ["profile", "changed_by"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
