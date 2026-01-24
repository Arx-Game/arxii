"""Django admin configuration for the permissions system."""

from django.contrib import admin

from world.permissions.models import PermissionGroup, PermissionGroupMember


class PermissionGroupMemberInline(admin.TabularInline):
    """Inline admin for group members."""

    model = PermissionGroupMember
    extra = 1
    raw_id_fields = ["character"]


@admin.register(PermissionGroup)
class PermissionGroupAdmin(admin.ModelAdmin):
    """Admin interface for PermissionGroup."""

    list_display = ["name", "owner", "member_count", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "owner__db_key"]
    raw_id_fields = ["owner"]
    inlines = [PermissionGroupMemberInline]

    def member_count(self, obj: PermissionGroup) -> int:
        return obj.members.count()

    member_count.short_description = "Members"


@admin.register(PermissionGroupMember)
class PermissionGroupMemberAdmin(admin.ModelAdmin):
    """Admin interface for PermissionGroupMember."""

    list_display = ["character", "group", "added_at"]
    list_filter = ["added_at"]
    search_fields = ["character__db_key", "group__name"]
    raw_id_fields = ["character", "group"]
