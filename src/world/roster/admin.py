"""
Django admin configuration for roster models.
"""

from django.contrib import admin

from world.roster.models import (
    PlayerMail,
    Roster,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    TenureDisplaySettings,
    TenureMedia,
)


@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "is_active", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]


@admin.register(RosterEntry)
class RosterEntryAdmin(admin.ModelAdmin):
    list_display = ["character", "roster", "joined_roster", "frozen"]
    list_filter = ["roster", "frozen", "joined_roster"]
    search_fields = ["character__name"]
    readonly_fields = ["joined_roster", "created_date", "updated_date"]

    # Use autocomplete for ObjectDB (characters) - could be thousands
    autocomplete_fields = ["character"]
    # Roster is a lookup table with few entries, keep default widget

    fieldsets = (
        ("Character Info", {"fields": ("character", "roster")}),
        ("Status", {"fields": ("frozen",)}),
        (
            "History",
            {"fields": ("joined_roster", "previous_roster"), "classes": ("collapse",)},
        ),
        ("Staff Notes", {"fields": ("gm_notes",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(RosterTenure)
class RosterTenureAdmin(admin.ModelAdmin):
    list_display = ["character", "display_name", "start_date", "end_date", "is_current"]
    list_filter = ["start_date", "end_date", "player_number"]
    search_fields = ["character__name", "player_data__account__username"]
    readonly_fields = ["display_name"]
    date_hierarchy = "start_date"

    # Use autocomplete for user-populated tables that could be large
    autocomplete_fields = ["character", "player_data", "approved_by"]

    fieldsets = (
        (
            "Tenure Info",
            {"fields": ("player_data", "character", "player_number", "display_name")},
        ),
        (
            "Timeline",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "applied_date",
                    "approved_date",
                    "approved_by",
                )
            },
        ),
        ("Media", {"fields": ("photo_folder",), "classes": ("collapse",)}),
        ("Staff Notes", {"fields": ("tenure_notes",), "classes": ("collapse",)}),
    )

    def is_current(self, obj):
        return obj.is_current

    is_current.boolean = True
    is_current.short_description = "Current"


@admin.register(RosterApplication)
class RosterApplicationAdmin(admin.ModelAdmin):
    list_display = ["player_data", "character", "status", "applied_date", "reviewed_by"]
    list_filter = ["status", "applied_date", "reviewed_date"]
    search_fields = ["player_data__account__username", "character__name"]
    readonly_fields = ["applied_date", "reviewed_date"]
    date_hierarchy = "applied_date"

    # Use autocomplete for user-populated tables that could be large
    autocomplete_fields = ["character", "player_data", "reviewed_by"]

    fieldsets = (
        ("Application Info", {"fields": ("player_data", "character", "status")}),
        ("Timeline", {"fields": ("applied_date", "reviewed_date", "reviewed_by")}),
        ("Content", {"fields": ("application_text",)}),
        ("Review", {"fields": ("review_notes",), "classes": ("collapse",)}),
    )

    actions = ["approve_applications", "deny_applications"]

    def approve_applications(self, request, queryset):
        count = 0
        staff_player_data = getattr(request.user, "player_data", None)
        if not staff_player_data:
            self.message_user(
                request,
                "You must have PlayerData to approve applications.",
                level="ERROR",
            )
            return

        for application in queryset.filter(status="pending"):
            if application.approve(staff_player_data):
                count += 1

        self.message_user(request, f"Approved {count} applications.")

    approve_applications.short_description = "Approve selected applications"

    def deny_applications(self, request, queryset):
        count = 0
        staff_player_data = getattr(request.user, "player_data", None)
        if not staff_player_data:
            self.message_user(
                request, "You must have PlayerData to deny applications.", level="ERROR"
            )
            return

        for application in queryset.filter(status="pending"):
            if application.deny(staff_player_data, "Denied via admin action"):
                count += 1

        self.message_user(request, f"Denied {count} applications.")

    deny_applications.short_description = "Deny selected applications"


@admin.register(TenureDisplaySettings)
class TenureDisplaySettingsAdmin(admin.ModelAdmin):
    list_display = [
        "tenure",
        "public_character_info",
        "show_online_status",
        "plot_involvement",
    ]
    list_filter = [
        "public_character_info",
        "show_online_status",
        "allow_pages",
        "plot_involvement",
    ]
    search_fields = ["tenure__character__name"]
    readonly_fields = ["created_date", "updated_date"]

    # Use autocomplete for tenure (there could be many)
    autocomplete_fields = ["tenure"]

    fieldsets = (
        (
            "Display Preferences",
            {"fields": ("tenure", "public_character_info", "show_online_status")},
        ),
        ("Communication", {"fields": ("allow_pages", "allow_tells")}),
        ("Roleplay", {"fields": ("rp_preferences", "plot_involvement")}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(TenureMedia)
class TenureMediaAdmin(admin.ModelAdmin):
    list_display = [
        "tenure",
        "media_type",
        "title",
        "is_primary",
        "is_public",
        "uploaded_date",
    ]
    list_filter = ["media_type", "is_primary", "is_public", "uploaded_date"]
    search_fields = ["tenure__character__name", "title", "description"]
    readonly_fields = ["uploaded_date", "updated_date"]
    date_hierarchy = "uploaded_date"

    # Use autocomplete for tenure (there could be many)
    autocomplete_fields = ["tenure"]

    fieldsets = (
        ("Media Info", {"fields": ("tenure", "media_type", "title", "description")}),
        ("Cloudinary", {"fields": ("cloudinary_public_id", "cloudinary_url")}),
        ("Settings", {"fields": ("sort_order", "is_primary", "is_public")}),
        (
            "Timestamps",
            {"fields": ("uploaded_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(PlayerMail)
class PlayerMailAdmin(admin.ModelAdmin):
    list_display = [
        "sender_account",
        "recipient_tenure",
        "subject",
        "sent_date",
        "is_read",
        "archived",
    ]
    list_filter = ["sent_date", "read_date", "archived"]
    search_fields = [
        "sender_account__username",
        "recipient_tenure__character__name",
        "subject",
    ]
    readonly_fields = ["sent_date", "read_date"]
    date_hierarchy = "sent_date"

    # Use autocomplete for user-populated tables
    autocomplete_fields = [
        "sender_account",
        "sender_character",
        "recipient_tenure",
        "in_reply_to",
    ]

    fieldsets = (
        (
            "Message Info",
            {
                "fields": (
                    "sender_account",
                    "sender_character",
                    "recipient_tenure",
                    "subject",
                )
            },
        ),
        ("Content", {"fields": ("message",)}),
        ("Threading", {"fields": ("in_reply_to",), "classes": ("collapse",)}),
        ("Status", {"fields": ("sent_date", "read_date", "archived")}),
    )

    def is_read(self, obj):
        return obj.is_read

    is_read.boolean = True
    is_read.short_description = "Read"
