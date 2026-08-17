"""Models for scheduled-downtime announcements (#3194)."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class DowntimeWindow(SharedMemoryModel):
    """A staff-declared maintenance window players should be warned about.

    Authored in the admin (the same staff surface as ``RegistrationConfig``):
    a start time, an expected duration, and a short player-facing message.
    The automatic host reboot is deliberately NOT stored here — it is derived
    live from systemd's scheduled-shutdown file by
    ``services.get_next_downtime``, so the same fact is never typed twice.
    """

    starts_at = models.DateTimeField(db_index=True)
    expected_duration_minutes = models.PositiveIntegerField(
        help_text="How long players should expect the game to be unavailable."
    )
    message = models.CharField(
        max_length=255,
        help_text="Player-facing banner text, e.g. what is being done and why.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="downtime_windows_created",
    )
    canceled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the window is called off; a canceled window is never announced.",
    )

    class Meta:
        verbose_name = "Downtime Window"
        verbose_name_plural = "Downtime Windows"
        ordering = ["starts_at"]

    def __str__(self) -> str:
        state = "canceled" if self.canceled_at else "planned"
        return f"DowntimeWindow({self.starts_at:%Y-%m-%d %H:%M} UTC, {state})"
