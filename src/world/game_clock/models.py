"""Models for the game clock system."""

from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.game_clock.constants import DEFAULT_TIME_RATIO


class GameClock(SharedMemoryModel):
    """Singleton model tracking the IC-to-real-time mapping.

    IC time is derived from a fixed anchor point plus elapsed real time
    multiplied by the time ratio. Pausing freezes IC time at the anchor.

    Uses SharedMemoryModel to cache the singleton in-process, since this
    model is read on nearly every IC time query but rarely modified.
    """

    anchor_real_time = models.DateTimeField(
        help_text="Real-world timestamp when the clock was last set."
    )
    anchor_ic_time = models.DateTimeField(
        help_text="IC datetime corresponding to anchor_real_time."
    )
    time_ratio = models.FloatField(
        default=DEFAULT_TIME_RATIO,
        help_text="IC seconds per real second.",
    )
    paused = models.BooleanField(
        default=False,
        help_text="When True, IC time is frozen at anchor_ic_time.",
    )

    class Meta:
        verbose_name = "Game Clock"
        verbose_name_plural = "Game Clock"

    SINGLETON_PK = 1

    def save(self, *args: object, **kwargs: object) -> None:
        """Enforce singleton — always writes to SINGLETON_PK."""
        self.pk = self.SINGLETON_PK
        # SharedMemoryModel sets force_insert on first save; switch to update
        # if the row already exists.
        if kwargs.get("force_insert") and GameClock.objects.filter(pk=self.SINGLETON_PK).exists():
            kwargs["force_insert"] = False
            kwargs["force_update"] = True
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def get_active(cls) -> "GameClock | None":
        """Return the singleton GameClock instance, or None if not yet created."""
        return cls.objects.first()

    def get_ic_now(self, *, real_now: datetime | None = None) -> datetime:
        """Derive the current IC datetime from the anchor and elapsed real time.

        Args:
            real_now: Override for the current real time (keyword-only, for testing).

        Returns:
            The current IC datetime.
        """
        if self.paused:
            return self.anchor_ic_time

        if real_now is None:
            real_now = timezone.now()

        elapsed_real: timedelta = real_now - self.anchor_real_time
        elapsed_ic = timedelta(seconds=elapsed_real.total_seconds() * self.time_ratio)
        return self.anchor_ic_time + elapsed_ic

    def __str__(self) -> str:
        state = "paused" if self.paused else "running"
        return f"GameClock (ratio={self.time_ratio}, {state})"


class GameClockHistory(SharedMemoryModel):
    """Audit log for changes to the GameClock."""

    changed_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Account that made the change.",
    )
    changed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the change was made.",
    )

    old_anchor_real_time = models.DateTimeField()
    old_anchor_ic_time = models.DateTimeField()
    old_time_ratio = models.FloatField()

    new_anchor_real_time = models.DateTimeField()
    new_anchor_ic_time = models.DateTimeField()
    new_time_ratio = models.FloatField()

    reason = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Game Clock History"
        verbose_name_plural = "Game Clock History"

    def __str__(self) -> str:
        return f"Clock change at {self.changed_at}"


class ScheduledTaskRecord(SharedMemoryModel):
    """Tracks when each periodic task was last run."""

    task_key = models.CharField(
        max_length=100,
        unique=True,
        help_text="String identifier for the periodic task.",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Real time when this task last completed.",
    )
    last_ic_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="IC time of last run (for IC-frequency tasks).",
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Staff can disable individual tasks.",
    )

    class Meta:
        verbose_name = "Scheduled Task"

    def __str__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"{self.task_key} ({status})"
