"""Admin registrations for scheduled-downtime announcements (#3194).

The admin IS the staff authoring surface for windows — the same pattern as
``RegistrationConfig`` (staff-tunable operational data, no deploy).
"""

from typing import ClassVar

from django.contrib import admin

from world.downtime.models import DowntimeWindow


@admin.register(DowntimeWindow)
class DowntimeWindowAdmin(admin.ModelAdmin):
    autocomplete_fields: ClassVar[list[str]] = ["created_by"]
    list_display: ClassVar[list[str]] = [
        "starts_at",
        "expected_duration_minutes",
        "message",
        "canceled_at",
        "created_by",
    ]
    list_filter: ClassVar[list[str]] = ["starts_at"]
    search_fields: ClassVar[list[str]] = ["message"]
    readonly_fields: ClassVar[list[str]] = ["created_at"]

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
