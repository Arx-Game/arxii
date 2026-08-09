"""Admin registrations for invitation-gated account registration (#3054)."""

from typing import ClassVar

from django.contrib import admin

from world.registration.models import AccountInvite, RegistrationConfig


@admin.register(RegistrationConfig)
class RegistrationConfigAdmin(admin.ModelAdmin):
    """Staff flip the singleton open/closed toggle here — no deploy required."""

    autocomplete_fields: ClassVar[list[str]] = ["updated_by"]
    list_display: ClassVar[list[str]] = ["registration_open", "updated_at", "updated_by"]
    readonly_fields: ClassVar[list[str]] = ["updated_at"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        # Singleton — the row is created lazily by get_registration_config();
        # staff edit the existing row rather than adding a second one.
        return not RegistrationConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(AccountInvite)
class AccountInviteAdmin(admin.ModelAdmin):
    autocomplete_fields: ClassVar[list[str]] = ["invited_by", "redeemed_by"]
    list_display: ClassVar[list[str]] = [
        "email",
        "status",
        "created_at",
        "expires_at",
        "invited_by",
    ]
    list_filter: ClassVar[list[str]] = ["created_at"]
    search_fields: ClassVar[list[str]] = ["email", "invited_by__username"]
    readonly_fields: ClassVar[list[str]] = [
        "token",
        "created_at",
        "redeemed_at",
        "redeemed_by",
    ]
