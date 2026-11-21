"""Admin interface for the game clock system."""

from django.contrib import admin
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import format_html

from world.game_clock.models import GameClock, GameClockHistory, ScheduledTaskRecord


@admin.register(GameClock)
class GameClockAdmin(admin.ModelAdmin):
    """Admin for the game clock singleton.

    Seeding happens here: a fresh database has no clock, and this Add form is
    the sanctioned way to create it (the alternative is the staff-only
    `POST /api/clock/adjust/`). Every change to an existing clock goes through
    the clock services (`set_clock`, `set_time_ratio`, `pause_clock`,
    `unpause_clock`), which re-anchor it and write `GameClockHistory`; the staff
    hub's Game clock page calls them (#5248). So the change form is read-only.
    Saving `paused` or `time_ratio` here would store the field without moving
    the anchors, and the date would jump: unticking Paused counted all the time
    the clock had sat paused.
    """

    list_display = ["__str__", "anchor_ic_time", "time_ratio", "paused"]
    #: Where staff change a clock that already exists (the web client's staff hub).
    STAFF_CLOCK_PAGE = "/staff/clock"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Say what the anchor date means for the world's year."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "anchor_ic_time" and formfield:  # noqa: STRING_LITERAL
            formfield.help_text = (
                "The IC date and time the clock starts at. Its year is the world's "
                "current year. Do not set it before any heritage's first-appearance "
                "date."
            )
        return formfield

    def get_readonly_fields(self, _request: HttpRequest, obj: GameClock | None = None) -> list[str]:
        """Creating asks for the IC anchor; the real half is stamped at save."""
        if obj is None:
            return ["anchor_real_time"]
        return ["anchor_real_time", "anchor_ic_time", "time_ratio", "paused"]

    def get_fieldsets(self, request: HttpRequest, obj: GameClock | None = None) -> list:
        """Point the change form at the page that changes a clock safely."""
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        description = format_html(
            "To pause or resume the clock, set the date or change the speed, use the "
            '<a href="{}">Game clock page</a> in the staff hub. Those controls '
            "re-anchor the clock and record the change; this form only shows it.",
            self.STAFF_CLOCK_PAGE,
        )
        return [(None, {"fields": fieldsets[0][1]["fields"], "description": description})]

    def save_model(self, request: HttpRequest, obj: GameClock, form: object, change: bool) -> None:
        """Anchor a new clock to the moment it was created."""
        if not change:
            obj.anchor_real_time = timezone.now()
        super().save_model(request, obj, form, change)

    def has_add_permission(self, _request):
        """The clock is a singleton: Add is available only until it exists."""
        return not GameClock.objects.exists()

    def has_change_permission(self, request: HttpRequest, obj: GameClock | None = None) -> bool:
        """An existing clock is shown, never saved here: the change page has no Save."""
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, _request, _obj=None):
        """Prevent deletion via admin."""
        return False


@admin.register(GameClockHistory)
class GameClockHistoryAdmin(admin.ModelAdmin):
    """Admin for clock change audit log."""

    autocomplete_fields = ["changed_by"]

    list_display = [
        "changed_at",
        "changed_by",
        "old_anchor_ic_time",
        "new_anchor_ic_time",
        "old_time_ratio",
        "new_time_ratio",
        "change",
        "birth_year_shift",
        "reason",
    ]
    list_filter = ["change", "changed_by"]
    readonly_fields = [
        "changed_by",
        "changed_at",
        "old_anchor_real_time",
        "old_anchor_ic_time",
        "old_time_ratio",
        "new_anchor_real_time",
        "new_anchor_ic_time",
        "new_time_ratio",
        "change",
        "birth_year_shift",
        "reason",
    ]

    def has_add_permission(self, _request):
        """History entries are created by services, not manually."""
        return False

    def has_delete_permission(self, _request, _obj=None):
        """Audit log should not be deleted."""
        return False


@admin.register(ScheduledTaskRecord)
class ScheduledTaskRecordAdmin(admin.ModelAdmin):
    """Admin for scheduled task records."""

    list_display = ["task_key", "last_run_at", "enabled"]
    list_filter = ["enabled"]
    list_editable = ["enabled"]
    readonly_fields = ["task_key", "last_run_at", "last_ic_run_at"]

    def has_add_permission(self, _request: object) -> bool:
        """Task records are created by the scheduler, not manually."""
        return False
