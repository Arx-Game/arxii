"""
Django admin configuration for evennia_extensions models.
"""

import contextlib
from typing import ClassVar

from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib import admin, messages
from django.utils.html import format_html

from evennia_extensions.models import (
    Artist,
    ObjectDisplayData,
    PlayerAllowList,
    PlayerBlockList,
    PlayerData,
    PlayerMedia,
)


@admin.register(PlayerData)
class PlayerDataAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "account",
        "display_name",
        "karma",
        "created_date",
        "profile_picture",
    ]
    list_filter: ClassVar[list[str]] = [
        "hide_from_watch",
        "private_mode",
        "created_date",
    ]
    search_fields: ClassVar[list[str]] = ["account__username", "display_name"]
    readonly_fields: ClassVar[list[str]] = ["created_date", "updated_date"]

    fieldsets = (
        ("Account Info", {"fields": ("account", "display_name")}),
        ("Preferences", {"fields": ("karma", "hide_from_watch", "private_mode")}),
        (
            "Media Settings",
            {"fields": ("profile_picture", "max_storage", "max_file_size")},
        ),
        ("Session Info", {"fields": ("last_login_ip",)}),
        ("Staff Notes", {"fields": ("gm_notes",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(PlayerAllowList)
class PlayerAllowListAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "owner",
        "allowed_player",
        "added_date",
        "notes",
    ]
    list_filter: ClassVar[list[str]] = ["added_date"]
    search_fields: ClassVar[list[str]] = [
        "owner__account__username",
        "allowed_player__account__username",
    ]
    readonly_fields: ClassVar[list[str]] = ["added_date"]


@admin.register(PlayerBlockList)
class PlayerBlockListAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "owner",
        "blocked_player",
        "blocked_date",
        "reason",
    ]
    list_filter: ClassVar[list[str]] = ["blocked_date"]
    search_fields: ClassVar[list[str]] = [
        "owner__account__username",
        "blocked_player__account__username",
    ]
    readonly_fields: ClassVar[list[str]] = ["blocked_date"]


@admin.register(PlayerMedia)
class PlayerMediaAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "player_data",
        "media_type",
        "title",
        "created_by",
        "uploaded_date",
    ]
    list_filter: ClassVar[list[str]] = ["media_type", "uploaded_date"]
    search_fields: ClassVar[list[str]] = ["player_data__account__username", "title"]
    readonly_fields: ClassVar[list[str]] = ["uploaded_date", "updated_date"]


@admin.register(ObjectDisplayData)
class ObjectDisplayDataAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "object",
        "longname",
        "colored_name",
        "has_thumbnail",
    ]
    search_fields: ClassVar[list[str]] = ["object__db_key", "longname"]
    readonly_fields: ClassVar[list[str]] = ["created_date", "updated_date"]

    def has_thumbnail(self, obj):
        return bool(obj.thumbnail)

    has_thumbnail.boolean = True
    has_thumbnail.short_description = "Has Thumbnail"


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["name", "player_data", "accepting_commissions"]
    list_filter: ClassVar[list[str]] = ["accepting_commissions"]
    search_fields: ClassVar[list[str]] = ["name", "player_data__account__username"]


# Custom admin for allauth EmailAddress model
# Unregister the default allauth admin if it exists
with contextlib.suppress(admin.sites.NotRegistered):
    admin.site.unregister(EmailAddress)


@admin.register(EmailAddress)
class EmailAddressAdmin(admin.ModelAdmin):
    list_display = [
        "email",
        "user",
        "verified",
        "primary",
        "has_pending_confirmation",
        "verification_link",
    ]
    list_filter = ["verified", "primary"]
    search_fields = ["email", "user__username"]
    actions = ["resend_verification_email", "mark_as_verified", "mark_as_unverified"]

    def has_pending_confirmation(self, obj):
        """Check if email has pending confirmation."""
        return EmailConfirmation.objects.filter(email_address=obj).exists()

    has_pending_confirmation.boolean = True
    has_pending_confirmation.short_description = "Has Pending Confirmation"

    def verification_link(self, obj):
        """Show verification link if unverified."""
        if not obj.verified:
            confirmation = EmailConfirmation.objects.filter(email_address=obj).first()
            if confirmation:
                from django.conf import settings

                frontend_url = getattr(
                    settings, "FRONTEND_URL", "http://localhost:3000"
                )
                verify_url = f"{frontend_url}/verify-email/{confirmation.key}"
                return format_html(
                    '<a href="{}" target="_blank">Verification Link</a>', verify_url
                )
        return "—"

    verification_link.short_description = "Verification Link"

    def resend_verification_email(self, request, queryset):
        """Admin action to resend verification emails."""
        sent_count = 0
        error_count = 0

        for email_address in queryset:
            if email_address.verified:
                continue  # Skip already verified emails

            try:
                # Remove any existing confirmations first
                EmailConfirmation.objects.filter(email_address=email_address).delete()

                # Create new confirmation
                confirmation = EmailConfirmation.create(email_address)

                # Set sent timestamp to avoid the None issue
                from django.utils import timezone

                confirmation.sent = timezone.now()
                confirmation.save()

                # Send the email
                confirmation.send()
                sent_count += 1

            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Failed to send verification to {email_address.email}: {e!s}",
                    level=messages.ERROR,
                )

        if sent_count > 0:
            self.message_user(
                request,
                f"Successfully sent {sent_count} verification email(s).",
                level=messages.SUCCESS,
            )

        if error_count > 0:
            self.message_user(
                request,
                f"Failed to send {error_count} verification email(s). "
                f"Check error messages above.",
                level=messages.WARNING,
            )

    resend_verification_email.short_description = (
        "Resend verification email to selected addresses"
    )

    def mark_as_verified(self, request, queryset):
        """Admin action to manually mark emails as verified."""
        updated = queryset.update(verified=True)
        # Clean up any confirmation records
        for email_address in queryset:
            EmailConfirmation.objects.filter(email_address=email_address).delete()

        self.message_user(
            request,
            f"Successfully verified {updated} email address(es).",
            level=messages.SUCCESS,
        )

    mark_as_verified.short_description = "Mark selected email addresses as verified"

    def mark_as_unverified(self, request, queryset):
        """Admin action to manually mark emails as unverified."""
        updated = queryset.update(verified=False)
        self.message_user(
            request,
            f"Successfully marked {updated} email address(es) as unverified.",
            level=messages.SUCCESS,
        )

    mark_as_unverified.short_description = "Mark selected email addresses as unverified"
