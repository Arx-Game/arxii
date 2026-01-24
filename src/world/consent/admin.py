"""Django admin configuration for the consent system."""

from django.contrib import admin

from world.consent.models import ConsentGroup, ConsentGroupMember


class ConsentGroupMemberInline(admin.TabularInline):
    """Inline admin for group members."""

    model = ConsentGroupMember
    extra = 1
    raw_id_fields = ["tenure"]


@admin.register(ConsentGroup)
class ConsentGroupAdmin(admin.ModelAdmin):
    """Admin interface for ConsentGroup."""

    list_display = ["name", "owner", "member_count", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "owner__roster_entry__character__db_key"]
    raw_id_fields = ["owner"]
    inlines = [ConsentGroupMemberInline]

    def member_count(self, obj: ConsentGroup) -> int:
        return obj.members.count()

    member_count.short_description = "Members"


@admin.register(ConsentGroupMember)
class ConsentGroupMemberAdmin(admin.ModelAdmin):
    """Admin interface for ConsentGroupMember."""

    list_display = ["tenure", "group", "added_at"]
    list_filter = ["added_at"]
    search_fields = ["tenure__roster_entry__character__db_key", "group__name"]
    raw_id_fields = ["tenure", "group"]
