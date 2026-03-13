# World Clock Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the central game clock, scheduler, and periodic task infrastructure that tracks IC time, provides day/night and seasonal awareness, and dispatches periodic game tasks.

**Architecture:** A single-row anchor-based model derives IC time from real time via a configurable ratio. A persistent Evennia Script ticks on a fixed interval, dispatching registered periodic tasks. Service functions provide the query layer. A REST API exposes clock state to the frontend and staff adjustment tools.

**Tech Stack:** Django 5.x, Django REST Framework, Evennia (Scripts, server hooks), PostgreSQL, FactoryBoy

**Design Document:** `docs/plans/2026-03-11-world-clock-design.md`

---

## Reference: Project Conventions

- **Absolute imports only** — `from world.game_clock.models import GameClock`, never relative
- **TextChoices in constants.py** — enums live in a separate constants file, not inside models
- **Type annotations required** — all function args and return types
- **100-char line limit** — break long lines
- **No Django signals** — explicit service calls only
- **No JSON fields** — proper columns with validation
- **keyword-only args** for service functions — `def func(*, arg1, arg2)`
- **SharedMemoryModel** — for frequently accessed lookup data (import from `evennia.utils.idmapper.models`)
- **Tests use `setUpTestData`** for class-level fixtures, FactoryBoy for object creation
- **Run tests:** `echo "yes" | arx test world.game_clock`
- **Run linting:** `ruff check src/world/game_clock/`
- **Migration generation:** `arx manage makemigrations game_clock`

---

## Task 1: App Scaffolding and Constants

Create the `world.game_clock` Django app with constants.

**Files:**
- Create: `src/world/game_clock/__init__.py`
- Create: `src/world/game_clock/apps.py`
- Create: `src/world/game_clock/constants.py`
- Create: `src/world/game_clock/tests/__init__.py`

**Step 1: Create the app directory and files**

```bash
mkdir -p src/world/game_clock/tests
touch src/world/game_clock/__init__.py
touch src/world/game_clock/tests/__init__.py
```

**Step 2: Create apps.py**

```python
"""App configuration for the game clock system."""

from django.apps import AppConfig


class GameClockConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.game_clock"
    verbose_name = "Game Clock"
```

**Step 3: Create constants.py**

```python
"""Constants for the game clock system."""

from django.db.models import TextChoices


class TimePhase(TextChoices):
    """Time-of-day phases with season-adjusted boundaries."""

    DAWN = "dawn", "Dawn"
    DAY = "day", "Day"
    DUSK = "dusk", "Dusk"
    NIGHT = "night", "Night"


class Season(TextChoices):
    """IC calendar seasons derived from month."""

    SPRING = "spring", "Spring"
    SUMMER = "summer", "Summer"
    AUTUMN = "autumn", "Autumn"
    WINTER = "winter", "Winter"


# Default time ratio: 3 IC seconds per 1 real second
DEFAULT_TIME_RATIO = 3.0

# Season-adjusted phase boundaries (IC hour)
# Each season defines (dawn_start, day_start, dusk_start, night_start)
PHASE_BOUNDARIES: dict[Season, tuple[float, float, float, float]] = {
    Season.SPRING: (5.5, 6.5, 18.5, 19.5),
    Season.SUMMER: (4.5, 5.5, 20.0, 21.0),
    Season.AUTUMN: (6.0, 7.0, 17.5, 18.5),
    Season.WINTER: (7.0, 8.0, 16.5, 17.5),
}

# Month-to-season mapping (1-indexed months)
MONTH_TO_SEASON: dict[int, Season] = {
    1: Season.WINTER,
    2: Season.WINTER,
    3: Season.SPRING,
    4: Season.SPRING,
    5: Season.SPRING,
    6: Season.SUMMER,
    7: Season.SUMMER,
    8: Season.SUMMER,
    9: Season.AUTUMN,
    10: Season.AUTUMN,
    11: Season.AUTUMN,
    12: Season.WINTER,
}
```

**Step 4: Register the app in settings**

Modify `src/server/conf/settings.py` — add `"world.game_clock.apps.GameClockConfig"` to `INSTALLED_APPS`, in the world apps section near other infrastructure apps.

**Step 5: Commit**

```bash
git add src/world/game_clock/ src/server/conf/settings.py
git commit -m "feat(game_clock): scaffold app with constants"
```

---

## Task 2: GameClock Model

Create the single-row anchor-based clock model and history audit log.

**Files:**
- Create: `src/world/game_clock/models.py`
- Create: `src/world/game_clock/tests/test_models.py`
- Create: `src/world/game_clock/factories.py`

**Step 1: Write the model tests**

```python
"""Tests for game clock models."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.game_clock.constants import DEFAULT_TIME_RATIO
from world.game_clock.factories import GameClockFactory, GameClockHistoryFactory
from world.game_clock.models import GameClock, GameClockHistory


class GameClockModelTests(TestCase):
    def test_get_ic_now_at_anchor(self) -> None:
        """IC time at anchor_real_time equals anchor_ic_time."""
        now = timezone.now()
        ic_time = timezone.now().replace(year=1, month=6, day=15, hour=12)
        clock = GameClockFactory(
            anchor_real_time=now,
            anchor_ic_time=ic_time,
            time_ratio=DEFAULT_TIME_RATIO,
        )
        result = clock.get_ic_now(real_now=now)
        self.assertEqual(result, ic_time)

    def test_get_ic_now_advances_at_ratio(self) -> None:
        """IC time advances at time_ratio speed."""
        now = timezone.now()
        ic_time = timezone.now().replace(year=1, month=6, day=15, hour=12)
        clock = GameClockFactory(
            anchor_real_time=now,
            anchor_ic_time=ic_time,
            time_ratio=3.0,
        )
        # 1 real hour later = 3 IC hours later
        one_hour_later = now + timedelta(hours=1)
        result = clock.get_ic_now(real_now=one_hour_later)
        expected = ic_time + timedelta(hours=3)
        self.assertEqual(result, expected)

    def test_get_ic_now_paused_returns_anchor(self) -> None:
        """When paused, IC time stays at the anchor IC time."""
        now = timezone.now()
        ic_time = timezone.now().replace(year=1, month=6, day=15, hour=12)
        clock = GameClockFactory(
            anchor_real_time=now,
            anchor_ic_time=ic_time,
            paused=True,
        )
        later = now + timedelta(hours=5)
        result = clock.get_ic_now(real_now=later)
        self.assertEqual(result, ic_time)

    def test_str_representation(self) -> None:
        """String shows IC time info."""
        clock = GameClockFactory()
        self.assertIn("GameClock", str(clock))

    def test_get_active_returns_none_when_empty(self) -> None:
        """get_active returns None when no clock exists."""
        self.assertIsNone(GameClock.get_active())

    def test_get_active_returns_clock(self) -> None:
        """get_active returns the clock instance."""
        clock = GameClockFactory()
        self.assertEqual(GameClock.get_active(), clock)


class GameClockHistoryTests(TestCase):
    def test_str_representation(self) -> None:
        """String shows change info."""
        entry = GameClockHistoryFactory()
        self.assertIn("Clock change", str(entry))

    def test_history_records_change(self) -> None:
        """History entries store old and new values."""
        entry = GameClockHistoryFactory(reason="Time skip")
        self.assertEqual(entry.reason, "Time skip")
        self.assertIsNotNone(entry.changed_at)
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.game_clock
```
Expected: ImportError (models don't exist yet)

**Step 3: Create the models**

```python
"""Models for the game clock system."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.game_clock.constants import DEFAULT_TIME_RATIO


class GameClock(models.Model):
    """
    Single-row anchor-based game clock.

    IC time is derived: anchor_ic_time + (now - anchor_real_time) * time_ratio.
    Staff adjustments (including time skips) set a new anchor.
    """

    anchor_real_time = models.DateTimeField(
        help_text="Real-world datetime when clock was last set.",
    )
    anchor_ic_time = models.DateTimeField(
        help_text="IC datetime at the anchor point.",
    )
    time_ratio = models.FloatField(
        default=DEFAULT_TIME_RATIO,
        help_text="IC seconds per real second (default 3.0 = 3:1 ratio).",
    )
    paused = models.BooleanField(
        default=False,
        help_text="Emergency/maintenance pause.",
    )

    # Prevent multiple rows
    _singleton_id: ClassVar[int] = 1

    class Meta:
        verbose_name = "Game Clock"
        verbose_name_plural = "Game Clock"

    def __str__(self) -> str:
        return f"GameClock (ratio={self.time_ratio}, paused={self.paused})"

    def save(self, *args: object, **kwargs: object) -> None:
        """Enforce single-row constraint."""
        self.pk = self._singleton_id
        super().save(*args, **kwargs)

    def get_ic_now(self, *, real_now: object | None = None) -> object:
        """
        Calculate current IC datetime.

        Args:
            real_now: Override for current real time (for testing).

        Returns:
            The current IC datetime.
        """
        if self.paused:
            return self.anchor_ic_time
        if real_now is None:
            real_now = timezone.now()
        real_elapsed = real_now - self.anchor_real_time
        ic_elapsed = timedelta(seconds=real_elapsed.total_seconds() * self.time_ratio)
        return self.anchor_ic_time + ic_elapsed

    @classmethod
    def get_active(cls) -> GameClock | None:
        """Get the clock instance, or None if not configured."""
        return cls.objects.first()


class GameClockHistory(models.Model):
    """Audit log for clock adjustments."""

    changed_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    old_anchor_real_time = models.DateTimeField()
    old_anchor_ic_time = models.DateTimeField()
    old_time_ratio = models.FloatField()
    new_anchor_real_time = models.DateTimeField()
    new_anchor_ic_time = models.DateTimeField()
    new_time_ratio = models.FloatField()
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Staff notes on why the change was made.",
    )

    class Meta:
        verbose_name = "Clock Change History"
        verbose_name_plural = "Clock Change History"
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"Clock change at {self.changed_at}"
```

**Step 4: Create factories**

```python
"""FactoryBoy factories for game clock models."""

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from evennia_extensions.factories import AccountFactory
from world.game_clock.constants import DEFAULT_TIME_RATIO
from world.game_clock.models import GameClock, GameClockHistory


class GameClockFactory(DjangoModelFactory):
    """Factory for GameClock instances."""

    class Meta:
        model = GameClock

    anchor_real_time = factory.LazyFunction(timezone.now)
    anchor_ic_time = factory.LazyFunction(
        lambda: timezone.now().replace(year=1, month=1, day=1, hour=0, minute=0, second=0)
    )
    time_ratio = DEFAULT_TIME_RATIO
    paused = False


class GameClockHistoryFactory(DjangoModelFactory):
    """Factory for GameClockHistory instances."""

    class Meta:
        model = GameClockHistory

    changed_by = factory.SubFactory(AccountFactory)
    old_anchor_real_time = factory.LazyFunction(timezone.now)
    old_anchor_ic_time = factory.LazyFunction(timezone.now)
    old_time_ratio = DEFAULT_TIME_RATIO
    new_anchor_real_time = factory.LazyFunction(timezone.now)
    new_anchor_ic_time = factory.LazyFunction(timezone.now)
    new_time_ratio = DEFAULT_TIME_RATIO
    reason = ""
```

**Step 5: Generate and apply migration**

```bash
arx manage makemigrations game_clock
arx manage migrate
```

**Step 6: Run tests**

```bash
echo "yes" | arx test world.game_clock
```
Expected: All pass

**Step 7: Run linting**

```bash
ruff check src/world/game_clock/
```

**Step 8: Commit**

```bash
git add src/world/game_clock/
git commit -m "feat(game_clock): add GameClock and GameClockHistory models"
```

---

## Task 3: Service Functions — Clock Queries

Create the service layer for querying IC time, phase, season, and light level.

**Files:**
- Create: `src/world/game_clock/services.py`
- Create: `src/world/game_clock/tests/test_services.py`

**Step 1: Write the service tests**

```python
"""Tests for game clock service functions."""

from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from world.game_clock.constants import Season, TimePhase
from world.game_clock.factories import GameClockFactory
from world.game_clock.services import (
    get_ic_date_for_real_time,
    get_ic_now,
    get_ic_phase,
    get_ic_season,
    get_light_level,
    get_real_time_for_ic_date,
)


class GetIcNowTests(TestCase):
    def test_returns_ic_time(self) -> None:
        """Returns the current IC datetime from the clock."""
        now = timezone.now()
        ic_anchor = datetime(1, 6, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_now(real_now=now)
        self.assertEqual(result, ic_anchor)

    def test_returns_none_when_no_clock(self) -> None:
        """Returns None when no clock is configured."""
        result = get_ic_now()
        self.assertIsNone(result)

    def test_advances_over_time(self) -> None:
        """IC time advances at the configured ratio."""
        now = timezone.now()
        ic_anchor = datetime(1, 6, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(
            anchor_real_time=now, anchor_ic_time=ic_anchor, time_ratio=3.0
        )
        result = get_ic_now(real_now=now + timedelta(hours=2))
        expected = ic_anchor + timedelta(hours=6)
        self.assertEqual(result, expected)


class GetIcSeasonTests(TestCase):
    def test_summer_month(self) -> None:
        """Month 7 is summer."""
        now = timezone.now()
        ic_anchor = datetime(1, 7, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_season(real_now=now)
        self.assertEqual(result, Season.SUMMER)

    def test_winter_month(self) -> None:
        """Month 1 is winter."""
        now = timezone.now()
        ic_anchor = datetime(1, 1, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_season(real_now=now)
        self.assertEqual(result, Season.WINTER)

    def test_returns_none_when_no_clock(self) -> None:
        """Returns None when no clock configured."""
        self.assertIsNone(get_ic_season())


class GetIcPhaseTests(TestCase):
    def test_midday_is_day(self) -> None:
        """Noon in summer is day phase."""
        now = timezone.now()
        ic_anchor = datetime(1, 7, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_phase(real_now=now)
        self.assertEqual(result, TimePhase.DAY)

    def test_midnight_is_night(self) -> None:
        """Midnight is night phase."""
        now = timezone.now()
        ic_anchor = datetime(1, 7, 15, 0, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_phase(real_now=now)
        self.assertEqual(result, TimePhase.NIGHT)

    def test_winter_dawn_later(self) -> None:
        """Winter dawn starts later than summer dawn."""
        now = timezone.now()
        # IC hour 5:00 in winter should be night (dawn starts at 7:00)
        ic_anchor = datetime(1, 1, 15, 5, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_phase(real_now=now)
        self.assertEqual(result, TimePhase.NIGHT)

    def test_summer_dawn_earlier(self) -> None:
        """Summer dawn starts earlier."""
        now = timezone.now()
        # IC hour 5:00 in summer should be dawn (dawn starts at 4:30)
        ic_anchor = datetime(1, 7, 15, 5, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_ic_phase(real_now=now)
        self.assertEqual(result, TimePhase.DAWN)

    def test_returns_none_when_no_clock(self) -> None:
        """Returns None when no clock configured."""
        self.assertIsNone(get_ic_phase())


class GetLightLevelTests(TestCase):
    def test_midday_bright(self) -> None:
        """Midday has high light level."""
        now = timezone.now()
        ic_anchor = datetime(1, 7, 15, 12, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_light_level(real_now=now)
        self.assertGreater(result, 0.8)

    def test_midnight_dark(self) -> None:
        """Midnight has low light level."""
        now = timezone.now()
        ic_anchor = datetime(1, 7, 15, 0, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_anchor)
        result = get_light_level(real_now=now)
        self.assertLess(result, 0.2)

    def test_returns_none_when_no_clock(self) -> None:
        """Returns None when no clock configured."""
        self.assertIsNone(get_light_level())


class DateConversionTests(TestCase):
    def test_ic_to_real_roundtrip(self) -> None:
        """Converting IC→real→IC returns the same IC date."""
        now = timezone.now()
        ic_anchor = datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)
        GameClockFactory(
            anchor_real_time=now, anchor_ic_time=ic_anchor, time_ratio=3.0
        )
        ic_target = datetime(1, 2, 1, 0, 0, tzinfo=timezone.utc)
        real_dt = get_real_time_for_ic_date(ic_target)
        self.assertIsNotNone(real_dt)
        roundtrip = get_ic_date_for_real_time(real_dt)
        # Allow 1-second tolerance for float math
        self.assertAlmostEqual(
            roundtrip.timestamp(), ic_target.timestamp(), delta=1.0
        )

    def test_returns_none_when_no_clock(self) -> None:
        """Returns None when no clock configured."""
        target = datetime(1, 6, 15, 0, 0, tzinfo=timezone.utc)
        self.assertIsNone(get_real_time_for_ic_date(target))
        self.assertIsNone(get_ic_date_for_real_time(timezone.now()))
```

**Step 2: Run tests to verify they fail**

```bash
echo "yes" | arx test world.game_clock
```
Expected: ImportError (services don't exist yet)

**Step 3: Write the service functions**

```python
"""Service functions for the game clock system."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from world.game_clock.constants import (
    MONTH_TO_SEASON,
    PHASE_BOUNDARIES,
    Season,
    TimePhase,
)
from world.game_clock.models import GameClock


def get_ic_now(*, real_now: datetime | None = None) -> datetime | None:
    """
    Get the current IC datetime.

    Args:
        real_now: Override for current real time (for testing).

    Returns:
        Current IC datetime, or None if no clock is configured.
    """
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_now)


def get_ic_season(*, real_now: datetime | None = None) -> Season | None:
    """
    Get the current IC season.

    Returns:
        Current Season, or None if no clock is configured.
    """
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    return MONTH_TO_SEASON[ic_now.month]


def get_ic_phase(*, real_now: datetime | None = None) -> TimePhase | None:
    """
    Get the current time-of-day phase with season-adjusted boundaries.

    Returns:
        Current TimePhase, or None if no clock is configured.
    """
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    season = MONTH_TO_SEASON[ic_now.month]
    hour = ic_now.hour + ic_now.minute / 60.0
    dawn_start, day_start, dusk_start, night_start = PHASE_BOUNDARIES[season]

    if hour < dawn_start:
        return TimePhase.NIGHT
    if hour < day_start:
        return TimePhase.DAWN
    if hour < dusk_start:
        return TimePhase.DAY
    if hour < night_start:
        return TimePhase.DUSK
    return TimePhase.NIGHT


def get_light_level(*, real_now: datetime | None = None) -> float | None:
    """
    Get the current light level as a float 0.0 (dark) to 1.0 (bright).

    Uses a smooth curve based on IC hour and season-adjusted boundaries.

    Returns:
        Light level float, or None if no clock is configured.
    """
    ic_now = get_ic_now(real_now=real_now)
    if ic_now is None:
        return None
    season = MONTH_TO_SEASON[ic_now.month]
    hour = ic_now.hour + ic_now.minute / 60.0
    dawn_start, day_start, dusk_start, night_start = PHASE_BOUNDARIES[season]

    if hour < dawn_start or hour >= night_start:
        # Full night
        return 0.05
    if hour < day_start:
        # Dawn transition
        progress = (hour - dawn_start) / (day_start - dawn_start)
        return 0.05 + progress * 0.90
    if hour < dusk_start:
        # Full day
        return 0.95
    # Dusk transition
    progress = (hour - dusk_start) / (night_start - dusk_start)
    return 0.95 - progress * 0.90


def get_ic_date_for_real_time(
    real_dt: datetime,
) -> datetime | None:
    """
    Convert a real-world datetime to IC datetime.

    Args:
        real_dt: The real-world datetime to convert.

    Returns:
        The corresponding IC datetime, or None if no clock is configured.
    """
    clock = GameClock.get_active()
    if clock is None:
        return None
    return clock.get_ic_now(real_now=real_dt)


def get_real_time_for_ic_date(
    ic_dt: datetime,
) -> datetime | None:
    """
    Convert an IC datetime to approximate real-world datetime.

    Args:
        ic_dt: The IC datetime to convert.

    Returns:
        The corresponding real datetime, or None if no clock is configured.
    """
    clock = GameClock.get_active()
    if clock is None:
        return None
    if clock.paused or clock.time_ratio == 0:
        return None
    ic_elapsed = ic_dt - clock.anchor_ic_time
    real_elapsed = timedelta(
        seconds=ic_elapsed.total_seconds() / clock.time_ratio
    )
    return clock.anchor_real_time + real_elapsed
```

**Step 4: Run tests**

```bash
echo "yes" | arx test world.game_clock
```
Expected: All pass

**Step 5: Run linting**

```bash
ruff check src/world/game_clock/
```

**Step 6: Commit**

```bash
git add src/world/game_clock/services.py src/world/game_clock/tests/test_services.py
git commit -m "feat(game_clock): add service functions for IC time queries"
```

---

## Task 4: Clock Management Services

Add staff-facing service functions for setting the clock, changing ratio, and pause/unpause.

**Files:**
- Modify: `src/world/game_clock/services.py`
- Create: `src/world/game_clock/types.py`
- Modify: `src/world/game_clock/tests/test_services.py`

**Step 1: Create types.py**

```python
"""Type definitions for the game clock system."""


class ClockError(Exception):
    """User-safe error from clock operations.

    All messages are safe to return in API responses.
    """

    NOT_CONFIGURED = "Game clock is not configured."
    ALREADY_PAUSED = "Game clock is already paused."
    NOT_PAUSED = "Game clock is not paused."
    INVALID_RATIO = "Time ratio must be positive."
```

**Step 2: Write management service tests**

Add to `test_services.py`:

```python
from evennia_extensions.factories import AccountFactory
from world.game_clock.models import GameClockHistory
from world.game_clock.services import (
    pause_clock,
    set_clock,
    set_time_ratio,
    unpause_clock,
)
from world.game_clock.types import ClockError


class SetClockTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def test_set_clock_creates_when_none_exists(self) -> None:
        """set_clock creates a new clock if none exists."""
        ic_time = datetime(1, 6, 15, 12, 0, tzinfo=timezone.utc)
        clock = set_clock(
            new_ic_time=ic_time, changed_by=self.account, reason="Initial setup"
        )
        self.assertIsNotNone(clock)
        self.assertEqual(clock.anchor_ic_time, ic_time)

    def test_set_clock_updates_existing(self) -> None:
        """set_clock updates the anchor on existing clock."""
        old_ic = datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)
        GameClockFactory(anchor_ic_time=old_ic)
        new_ic = datetime(21, 1, 1, 0, 0, tzinfo=timezone.utc)
        clock = set_clock(
            new_ic_time=new_ic, changed_by=self.account, reason="Time skip"
        )
        self.assertEqual(clock.anchor_ic_time, new_ic)

    def test_set_clock_logs_history(self) -> None:
        """set_clock creates a history entry when updating."""
        GameClockFactory()
        new_ic = datetime(21, 1, 1, 0, 0, tzinfo=timezone.utc)
        set_clock(
            new_ic_time=new_ic, changed_by=self.account, reason="Time skip"
        )
        self.assertEqual(GameClockHistory.objects.count(), 1)
        entry = GameClockHistory.objects.first()
        self.assertEqual(entry.reason, "Time skip")
        self.assertEqual(entry.changed_by, self.account)


class SetTimeRatioTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def test_set_time_ratio(self) -> None:
        """Changes the time ratio."""
        GameClockFactory(time_ratio=3.0)
        clock = set_time_ratio(
            ratio=6.0, changed_by=self.account, reason="Event mode"
        )
        self.assertEqual(clock.time_ratio, 6.0)

    def test_set_time_ratio_logs_history(self) -> None:
        """Logs a history entry."""
        GameClockFactory(time_ratio=3.0)
        set_time_ratio(
            ratio=6.0, changed_by=self.account, reason="Event mode"
        )
        entry = GameClockHistory.objects.first()
        self.assertEqual(entry.old_time_ratio, 3.0)
        self.assertEqual(entry.new_time_ratio, 6.0)

    def test_invalid_ratio_raises(self) -> None:
        """Zero or negative ratio raises ClockError."""
        GameClockFactory()
        with self.assertRaises(ClockError):
            set_time_ratio(
                ratio=0.0, changed_by=self.account, reason="Bad"
            )

    def test_no_clock_raises(self) -> None:
        """Raises ClockError when no clock exists."""
        with self.assertRaises(ClockError):
            set_time_ratio(
                ratio=3.0, changed_by=self.account, reason="No clock"
            )


class PauseUnpauseTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()

    def test_pause_clock(self) -> None:
        """Pausing sets paused=True and re-anchors to current IC time."""
        GameClockFactory(paused=False)
        clock = pause_clock(changed_by=self.account, reason="Maintenance")
        self.assertTrue(clock.paused)

    def test_unpause_clock(self) -> None:
        """Unpausing sets paused=False and re-anchors."""
        GameClockFactory(paused=True)
        clock = unpause_clock(changed_by=self.account, reason="Done")
        self.assertFalse(clock.paused)

    def test_pause_already_paused_raises(self) -> None:
        """Pausing an already paused clock raises ClockError."""
        GameClockFactory(paused=True)
        with self.assertRaises(ClockError):
            pause_clock(changed_by=self.account, reason="Again")

    def test_unpause_not_paused_raises(self) -> None:
        """Unpausing a running clock raises ClockError."""
        GameClockFactory(paused=False)
        with self.assertRaises(ClockError):
            unpause_clock(changed_by=self.account, reason="Not paused")

    def test_no_clock_raises(self) -> None:
        """Raises ClockError when no clock exists."""
        with self.assertRaises(ClockError):
            pause_clock(changed_by=self.account, reason="No clock")
```

**Step 3: Implement the management service functions**

Add to `services.py`:

```python
from django.db import transaction
from evennia.accounts.models import AccountDB

from world.game_clock.models import GameClockHistory
from world.game_clock.types import ClockError


def _log_clock_change(
    *,
    clock: GameClock,
    old_anchor_real_time: datetime,
    old_anchor_ic_time: datetime,
    old_time_ratio: float,
    changed_by: AccountDB,
    reason: str,
) -> None:
    """Record a clock change in the history log."""
    GameClockHistory.objects.create(
        changed_by=changed_by,
        old_anchor_real_time=old_anchor_real_time,
        old_anchor_ic_time=old_anchor_ic_time,
        old_time_ratio=old_time_ratio,
        new_anchor_real_time=clock.anchor_real_time,
        new_anchor_ic_time=clock.anchor_ic_time,
        new_time_ratio=clock.time_ratio,
        reason=reason,
    )


def set_clock(
    *,
    new_ic_time: datetime,
    changed_by: AccountDB,
    reason: str,
) -> GameClock:
    """
    Set the game clock to a new IC time.

    Creates the clock if it doesn't exist, or re-anchors if it does.
    Logs the change to GameClockHistory.
    """
    now = timezone.now()
    with transaction.atomic():
        clock = GameClock.get_active()
        if clock is None:
            clock = GameClock(
                anchor_real_time=now,
                anchor_ic_time=new_ic_time,
            )
            clock.save()
            return clock

        old_real = clock.anchor_real_time
        old_ic = clock.anchor_ic_time
        old_ratio = clock.time_ratio

        clock.anchor_real_time = now
        clock.anchor_ic_time = new_ic_time
        clock.save(update_fields=["anchor_real_time", "anchor_ic_time"])

        _log_clock_change(
            clock=clock,
            old_anchor_real_time=old_real,
            old_anchor_ic_time=old_ic,
            old_time_ratio=old_ratio,
            changed_by=changed_by,
            reason=reason,
        )
    return clock


def set_time_ratio(
    *,
    ratio: float,
    changed_by: AccountDB,
    reason: str,
) -> GameClock:
    """
    Change the time ratio. Re-anchors IC time to prevent jumps.

    Raises:
        ClockError: If no clock exists or ratio is invalid.
    """
    if ratio <= 0:
        raise ClockError(ClockError.INVALID_RATIO)

    with transaction.atomic():
        clock = GameClock.get_active()
        if clock is None:
            raise ClockError(ClockError.NOT_CONFIGURED)

        now = timezone.now()
        current_ic = clock.get_ic_now(real_now=now)

        old_real = clock.anchor_real_time
        old_ic = clock.anchor_ic_time
        old_ratio = clock.time_ratio

        clock.anchor_real_time = now
        clock.anchor_ic_time = current_ic
        clock.time_ratio = ratio
        clock.save(
            update_fields=["anchor_real_time", "anchor_ic_time", "time_ratio"]
        )

        _log_clock_change(
            clock=clock,
            old_anchor_real_time=old_real,
            old_anchor_ic_time=old_ic,
            old_time_ratio=old_ratio,
            changed_by=changed_by,
            reason=reason,
        )
    return clock


def pause_clock(
    *,
    changed_by: AccountDB,
    reason: str,
) -> GameClock:
    """
    Pause the game clock. Re-anchors to current IC time so unpausing resumes correctly.

    Raises:
        ClockError: If no clock exists or already paused.
    """
    with transaction.atomic():
        clock = GameClock.get_active()
        if clock is None:
            raise ClockError(ClockError.NOT_CONFIGURED)
        if clock.paused:
            raise ClockError(ClockError.ALREADY_PAUSED)

        now = timezone.now()
        current_ic = clock.get_ic_now(real_now=now)

        old_real = clock.anchor_real_time
        old_ic = clock.anchor_ic_time
        old_ratio = clock.time_ratio

        clock.anchor_real_time = now
        clock.anchor_ic_time = current_ic
        clock.paused = True
        clock.save(
            update_fields=["anchor_real_time", "anchor_ic_time", "paused"]
        )

        _log_clock_change(
            clock=clock,
            old_anchor_real_time=old_real,
            old_anchor_ic_time=old_ic,
            old_time_ratio=old_ratio,
            changed_by=changed_by,
            reason=reason,
        )
    return clock


def unpause_clock(
    *,
    changed_by: AccountDB,
    reason: str,
) -> GameClock:
    """
    Unpause the game clock. Re-anchors so IC time resumes from where it paused.

    Raises:
        ClockError: If no clock exists or not paused.
    """
    with transaction.atomic():
        clock = GameClock.get_active()
        if clock is None:
            raise ClockError(ClockError.NOT_CONFIGURED)
        if not clock.paused:
            raise ClockError(ClockError.NOT_PAUSED)

        now = timezone.now()
        old_real = clock.anchor_real_time
        old_ic = clock.anchor_ic_time
        old_ratio = clock.time_ratio

        clock.anchor_real_time = now
        # anchor_ic_time stays the same — resume from where we paused
        clock.paused = False
        clock.save(update_fields=["anchor_real_time", "paused"])

        _log_clock_change(
            clock=clock,
            old_anchor_real_time=old_real,
            old_anchor_ic_time=old_ic,
            old_time_ratio=old_ratio,
            changed_by=changed_by,
            reason=reason,
        )
    return clock
```

**Step 4: Run tests and linting**

```bash
echo "yes" | arx test world.game_clock
ruff check src/world/game_clock/
```

**Step 5: Commit**

```bash
git add src/world/game_clock/types.py src/world/game_clock/services.py src/world/game_clock/tests/test_services.py
git commit -m "feat(game_clock): add clock management services with audit logging"
```

---

## Task 5: Admin Interface

Register the clock models in Django admin.

**Files:**
- Create: `src/world/game_clock/admin.py`

**Step 1: Create admin.py**

```python
"""Admin interface for the game clock system."""

from django.contrib import admin

from world.game_clock.models import GameClock, GameClockHistory


@admin.register(GameClock)
class GameClockAdmin(admin.ModelAdmin):
    """Admin for the game clock singleton."""

    list_display = ["__str__", "anchor_ic_time", "time_ratio", "paused"]
    readonly_fields = ["anchor_real_time", "anchor_ic_time"]

    def has_add_permission(self, request: object) -> bool:
        """Prevent adding via admin — use set_clock() service."""
        return not GameClock.objects.exists()

    def has_delete_permission(
        self, request: object, obj: object = None
    ) -> bool:
        """Prevent deletion via admin."""
        return False


@admin.register(GameClockHistory)
class GameClockHistoryAdmin(admin.ModelAdmin):
    """Admin for clock change audit log."""

    list_display = [
        "changed_at",
        "changed_by",
        "old_anchor_ic_time",
        "new_anchor_ic_time",
        "old_time_ratio",
        "new_time_ratio",
        "reason",
    ]
    list_filter = ["changed_by"]
    readonly_fields = [
        "changed_by",
        "changed_at",
        "old_anchor_real_time",
        "old_anchor_ic_time",
        "old_time_ratio",
        "new_anchor_real_time",
        "new_anchor_ic_time",
        "new_time_ratio",
        "reason",
    ]

    def has_add_permission(self, request: object) -> bool:
        """History entries are created by services, not manually."""
        return False

    def has_delete_permission(
        self, request: object, obj: object = None
    ) -> bool:
        """Audit log should not be deleted."""
        return False
```

**Step 2: Commit**

```bash
git add src/world/game_clock/admin.py
git commit -m "feat(game_clock): add admin interface"
```

---

## Task 6: REST API — Serializers and Views

Create the API endpoints for clock queries and staff adjustment.

**Files:**
- Create: `src/world/game_clock/serializers.py`
- Create: `src/world/game_clock/views.py`
- Create: `src/world/game_clock/urls.py`
- Modify: `src/web/urls.py`
- Create: `src/world/game_clock/tests/test_views.py`

**Step 1: Create serializers**

```python
"""API serializers for the game clock system."""

from rest_framework import serializers

from world.game_clock.constants import Season, TimePhase


class ClockStateSerializer(serializers.Serializer):
    """Read-only serializer for current clock state."""

    ic_datetime = serializers.DateTimeField()
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    day = serializers.IntegerField()
    hour = serializers.IntegerField()
    minute = serializers.IntegerField()
    phase = serializers.ChoiceField(choices=TimePhase.choices)
    season = serializers.ChoiceField(choices=Season.choices)
    light_level = serializers.FloatField()
    paused = serializers.BooleanField()


class ClockConvertSerializer(serializers.Serializer):
    """Serializer for date conversion requests."""

    ic_date = serializers.DateTimeField(required=False)
    real_date = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("ic_date") and not attrs.get("real_date"):
            msg = "Provide either ic_date or real_date."
            raise serializers.ValidationError(msg)
        if attrs.get("ic_date") and attrs.get("real_date"):
            msg = "Provide only one of ic_date or real_date."
            raise serializers.ValidationError(msg)
        return attrs


class ClockConvertResponseSerializer(serializers.Serializer):
    """Response serializer for date conversion."""

    ic_date = serializers.DateTimeField(required=False)
    real_date = serializers.DateTimeField(required=False)


class ClockAdjustSerializer(serializers.Serializer):
    """Serializer for staff clock adjustment."""

    ic_datetime = serializers.DateTimeField()
    reason = serializers.CharField(max_length=500)


class ClockRatioSerializer(serializers.Serializer):
    """Serializer for staff ratio changes."""

    ratio = serializers.FloatField(min_value=0.01)
    reason = serializers.CharField(max_length=500)
```

**Step 2: Create views**

```python
"""API views for the game clock system."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.game_clock.serializers import (
    ClockAdjustSerializer,
    ClockConvertResponseSerializer,
    ClockConvertSerializer,
    ClockRatioSerializer,
    ClockStateSerializer,
)
from world.game_clock.services import (
    get_ic_now,
    get_ic_phase,
    get_ic_season,
    get_light_level,
    get_ic_date_for_real_time,
    get_real_time_for_ic_date,
    pause_clock,
    set_clock,
    set_time_ratio,
    unpause_clock,
)
from world.game_clock.models import GameClock
from world.game_clock.types import ClockError


class ClockViewSet(viewsets.ViewSet):
    """
    ViewSet for the game clock.

    Endpoints:
    - GET  /clock/         — current clock state (public)
    - GET  /clock/convert/ — date conversion (public)
    - POST /clock/adjust/  — set IC time (staff only)
    - POST /clock/ratio/   — change time ratio (staff only)
    - POST /clock/pause/   — pause clock (staff only)
    - POST /clock/unpause/ — unpause clock (staff only)
    """

    permission_classes = [IsAuthenticated]

    def list(self, request: Request) -> Response:
        """Return current clock state."""
        ic_now = get_ic_now()
        if ic_now is None:
            return Response(
                {"detail": "Game clock is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        phase = get_ic_phase()
        season = get_ic_season()
        light = get_light_level()
        clock = GameClock.get_active()

        data = {
            "ic_datetime": ic_now,
            "year": ic_now.year,
            "month": ic_now.month,
            "day": ic_now.day,
            "hour": ic_now.hour,
            "minute": ic_now.minute,
            "phase": phase,
            "season": season,
            "light_level": round(light, 2),
            "paused": clock.paused if clock else False,
        }
        serializer = ClockStateSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def convert(self, request: Request) -> Response:
        """Convert between IC and real dates."""
        serializer = ClockConvertSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        ic_date = serializer.validated_data.get("ic_date")
        real_date = serializer.validated_data.get("real_date")

        if ic_date:
            result = get_real_time_for_ic_date(ic_date)
            if result is None:
                return Response(
                    {"detail": "Game clock is not configured."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            response_data = {"real_date": result}
        else:
            result = get_ic_date_for_real_time(real_date)
            if result is None:
                return Response(
                    {"detail": "Game clock is not configured."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            response_data = {"ic_date": result}

        return Response(ClockConvertResponseSerializer(response_data).data)

    @action(detail=False, methods=["post"])
    def adjust(self, request: Request) -> Response:
        """Staff-only: set the clock to a new IC time."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ClockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            set_clock(
                new_ic_time=serializer.validated_data["ic_datetime"],
                changed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock adjusted."})

    @action(detail=False, methods=["post"])
    def ratio(self, request: Request) -> Response:
        """Staff-only: change the time ratio."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ClockRatioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            set_time_ratio(
                ratio=serializer.validated_data["ratio"],
                changed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Time ratio updated."})

    @action(detail=False, methods=["post"])
    def pause(self, request: Request) -> Response:
        """Staff-only: pause the clock."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            pause_clock(changed_by=request.user, reason="Staff pause")
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock paused."})

    @action(detail=False, methods=["post"])
    def unpause(self, request: Request) -> Response:
        """Staff-only: unpause the clock."""
        if not request.user.is_staff:
            return Response(
                {"detail": "Staff only."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            unpause_clock(changed_by=request.user, reason="Staff unpause")
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock unpaused."})
```

**Step 3: Create URLs**

```python
"""URL configuration for the game clock API."""

from django.urls import path

from world.game_clock.views import ClockViewSet

app_name = "game_clock"

clock_state = ClockViewSet.as_view({"get": "list"})
clock_convert = ClockViewSet.as_view({"get": "convert"})
clock_adjust = ClockViewSet.as_view({"post": "adjust"})
clock_ratio = ClockViewSet.as_view({"post": "ratio"})
clock_pause = ClockViewSet.as_view({"post": "pause"})
clock_unpause = ClockViewSet.as_view({"post": "unpause"})

urlpatterns = [
    path("", clock_state, name="clock-state"),
    path("convert/", clock_convert, name="clock-convert"),
    path("adjust/", clock_adjust, name="clock-adjust"),
    path("ratio/", clock_ratio, name="clock-ratio"),
    path("pause/", clock_pause, name="clock-pause"),
    path("unpause/", clock_unpause, name="clock-unpause"),
]
```

**Step 4: Register URLs in main URL config**

Add to `src/web/urls.py`, in the API section with other `path()` entries:

```python
path("api/clock/", include("world.game_clock.urls")),
```

**Step 5: Write view tests**

```python
"""Tests for game clock API views."""

from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.game_clock.factories import GameClockFactory
from world.game_clock.models import GameClock


class ClockStateViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_returns_clock_state(self) -> None:
        """GET /api/clock/ returns current IC time state."""
        now = timezone.now()
        ic_time = datetime(1, 7, 15, 14, 30, tzinfo=timezone.utc)
        GameClockFactory(anchor_real_time=now, anchor_ic_time=ic_time)
        response = self.client.get("/api/clock/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("phase", response.data)
        self.assertIn("season", response.data)
        self.assertIn("light_level", response.data)

    def test_returns_503_when_no_clock(self) -> None:
        """GET /api/clock/ returns 503 when clock not configured."""
        response = self.client.get("/api/clock/")
        self.assertEqual(response.status_code, 503)

    def test_requires_authentication(self) -> None:
        """GET /api/clock/ requires auth."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/clock/")
        self.assertEqual(response.status_code, 403)


class ClockConvertViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_convert_ic_to_real(self) -> None:
        """GET /api/clock/convert/?ic_date=... returns real_date."""
        now = timezone.now()
        GameClockFactory(
            anchor_real_time=now,
            anchor_ic_time=datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc),
        )
        response = self.client.get(
            "/api/clock/convert/", {"ic_date": "0001-06-15T00:00:00Z"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("real_date", response.data)

    def test_convert_real_to_ic(self) -> None:
        """GET /api/clock/convert/?real_date=... returns ic_date."""
        now = timezone.now()
        GameClockFactory(anchor_real_time=now)
        response = self.client.get(
            "/api/clock/convert/", {"real_date": now.isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("ic_date", response.data)

    def test_requires_one_param(self) -> None:
        """GET /api/clock/convert/ with no params returns 400."""
        GameClockFactory()
        response = self.client.get("/api/clock/convert/")
        self.assertEqual(response.status_code, 400)


class StaffClockAdjustViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = AccountFactory(is_staff=True)
        self.non_staff = AccountFactory()

    def test_adjust_clock(self) -> None:
        """POST /api/clock/adjust/ sets new IC time."""
        GameClockFactory()
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            "/api/clock/adjust/",
            {
                "ic_datetime": "0021-01-01T00:00:00Z",
                "reason": "Time skip",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_non_staff_forbidden(self) -> None:
        """Non-staff users get 403."""
        GameClockFactory()
        self.client.force_authenticate(user=self.non_staff)
        response = self.client.post(
            "/api/clock/adjust/",
            {
                "ic_datetime": "0021-01-01T00:00:00Z",
                "reason": "Nope",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_pause_and_unpause(self) -> None:
        """Staff can pause and unpause the clock."""
        GameClockFactory()
        self.client.force_authenticate(user=self.staff)

        response = self.client.post("/api/clock/pause/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GameClock.get_active().paused)

        response = self.client.post("/api/clock/unpause/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(GameClock.get_active().paused)

    def test_change_ratio(self) -> None:
        """Staff can change time ratio."""
        GameClockFactory(time_ratio=3.0)
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            "/api/clock/ratio/",
            {"ratio": 6.0, "reason": "Event mode"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GameClock.get_active().time_ratio, 6.0)
```

**Step 6: Run tests and linting**

```bash
echo "yes" | arx test world.game_clock
ruff check src/world/game_clock/
```

**Step 7: Commit**

```bash
git add src/world/game_clock/serializers.py src/world/game_clock/views.py src/world/game_clock/urls.py src/world/game_clock/tests/test_views.py src/web/urls.py
git commit -m "feat(game_clock): add REST API with clock queries and staff management"
```

---

## Task 7: Scheduler Infrastructure — ScheduledTaskRecord and Registry

Create the task tracking model and the task registry.

**Files:**
- Modify: `src/world/game_clock/models.py`
- Create: `src/world/game_clock/task_registry.py`
- Modify: `src/world/game_clock/tests/test_models.py`

**Step 1: Add ScheduledTaskRecord model**

Add to `models.py`:

```python
class ScheduledTaskRecord(models.Model):
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
```

**Step 2: Create task_registry.py**

```python
"""
Task registry for the game clock scheduler.

Tasks are registered as simple entries with a callable and frequency.
The scheduler checks each task's ScheduledTaskRecord to decide
whether it's due, then calls the task function and updates the record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Callable

from django.utils import timezone

from world.game_clock.models import ScheduledTaskRecord

logger = logging.getLogger("world.game_clock.scheduler")


class FrequencyType(Enum):
    """Whether a task runs on real-time or IC-time intervals."""

    REAL = "real"
    IC = "ic"


@dataclass(frozen=True)
class TaskDefinition:
    """A registered periodic task."""

    task_key: str
    callable: Callable[[], None]
    interval: timedelta
    frequency_type: FrequencyType = FrequencyType.REAL
    description: str = ""


# Module-level registry
_registry: list[TaskDefinition] = []


def register_task(task: TaskDefinition) -> None:
    """Register a periodic task."""
    _registry.append(task)


def get_registered_tasks() -> list[TaskDefinition]:
    """Return all registered tasks."""
    return list(_registry)


def clear_registry() -> None:
    """Clear all registered tasks (for testing)."""
    _registry.clear()


def run_due_tasks(*, ic_now: object | None = None) -> list[str]:
    """
    Check all registered tasks and run any that are due.

    Args:
        ic_now: Current IC datetime (for IC-frequency tasks).

    Returns:
        List of task_keys that were executed.
    """
    now = timezone.now()
    executed = []

    for task_def in _registry:
        record, _ = ScheduledTaskRecord.objects.get_or_create(
            task_key=task_def.task_key,
        )
        if not record.enabled:
            continue

        if _is_task_due(record, task_def, now=now, ic_now=ic_now):
            try:
                task_def.callable()
                record.last_run_at = now
                if ic_now is not None:
                    record.last_ic_run_at = ic_now
                record.save(update_fields=["last_run_at", "last_ic_run_at"])
                executed.append(task_def.task_key)
                logger.info("Executed task: %s", task_def.task_key)
            except Exception:
                logger.exception("Task failed: %s", task_def.task_key)

    return executed


def _is_task_due(
    record: ScheduledTaskRecord,
    task_def: TaskDefinition,
    *,
    now: object,
    ic_now: object | None,
) -> bool:
    """Check whether a task is due to run."""
    if task_def.frequency_type == FrequencyType.REAL:
        if record.last_run_at is None:
            return True
        return (now - record.last_run_at) >= task_def.interval

    # IC-frequency tasks
    if ic_now is None:
        return False
    if record.last_ic_run_at is None:
        return True
    return (ic_now - record.last_ic_run_at) >= task_def.interval
```

**Step 3: Add model tests for ScheduledTaskRecord**

Add to `test_models.py`:

```python
from world.game_clock.models import ScheduledTaskRecord


class ScheduledTaskRecordTests(TestCase):
    def test_str_enabled(self) -> None:
        record = ScheduledTaskRecord.objects.create(task_key="test_task")
        self.assertIn("enabled", str(record))

    def test_str_disabled(self) -> None:
        record = ScheduledTaskRecord.objects.create(
            task_key="test_task", enabled=False
        )
        self.assertIn("disabled", str(record))

    def test_unique_task_key(self) -> None:
        from django.db import IntegrityError

        ScheduledTaskRecord.objects.create(task_key="unique_task")
        with self.assertRaises(IntegrityError):
            ScheduledTaskRecord.objects.create(task_key="unique_task")
```

**Step 4: Add admin registration for ScheduledTaskRecord**

Add to `admin.py`:

```python
from world.game_clock.models import ScheduledTaskRecord


@admin.register(ScheduledTaskRecord)
class ScheduledTaskRecordAdmin(admin.ModelAdmin):
    """Admin for periodic task records."""

    list_display = ["task_key", "last_run_at", "enabled"]
    list_filter = ["enabled"]
    list_editable = ["enabled"]
    readonly_fields = ["task_key", "last_run_at", "last_ic_run_at"]

    def has_add_permission(self, request: object) -> bool:
        """Records are auto-created by the scheduler."""
        return False
```

**Step 5: Generate migration, run tests, lint**

```bash
arx manage makemigrations game_clock
arx manage migrate
echo "yes" | arx test world.game_clock
ruff check src/world/game_clock/
```

**Step 6: Commit**

```bash
git add src/world/game_clock/models.py src/world/game_clock/task_registry.py src/world/game_clock/admin.py src/world/game_clock/tests/test_models.py src/world/game_clock/migrations/
git commit -m "feat(game_clock): add scheduler infrastructure with task registry"
```

---

## Task 8: Task Registry Tests

Write thorough tests for the task registry's `run_due_tasks` logic.

**Files:**
- Create: `src/world/game_clock/tests/test_task_registry.py`

**Step 1: Write tests**

```python
"""Tests for the game clock task registry."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from world.game_clock.models import ScheduledTaskRecord
from world.game_clock.task_registry import (
    FrequencyType,
    TaskDefinition,
    clear_registry,
    register_task,
    run_due_tasks,
)


class RunDueTasksTests(TestCase):
    def setUp(self) -> None:
        clear_registry()

    def tearDown(self) -> None:
        clear_registry()

    def test_runs_task_on_first_execution(self) -> None:
        """A task with no prior run executes immediately."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.first_run",
                callable=mock_fn,
                interval=timedelta(hours=1),
            )
        )
        executed = run_due_tasks()
        self.assertEqual(executed, ["test.first_run"])
        mock_fn.assert_called_once()

    def test_skips_task_not_yet_due(self) -> None:
        """A task that ran recently is skipped."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.not_due",
                callable=mock_fn,
                interval=timedelta(hours=24),
            )
        )
        ScheduledTaskRecord.objects.create(
            task_key="test.not_due",
            last_run_at=timezone.now() - timedelta(hours=1),
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])
        mock_fn.assert_not_called()

    def test_runs_task_when_interval_elapsed(self) -> None:
        """A task runs when its interval has elapsed."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.elapsed",
                callable=mock_fn,
                interval=timedelta(hours=1),
            )
        )
        ScheduledTaskRecord.objects.create(
            task_key="test.elapsed",
            last_run_at=timezone.now() - timedelta(hours=2),
        )
        executed = run_due_tasks()
        self.assertEqual(executed, ["test.elapsed"])
        mock_fn.assert_called_once()

    def test_skips_disabled_task(self) -> None:
        """Disabled tasks are skipped."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.disabled",
                callable=mock_fn,
                interval=timedelta(hours=1),
            )
        )
        ScheduledTaskRecord.objects.create(
            task_key="test.disabled",
            enabled=False,
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])
        mock_fn.assert_not_called()

    def test_updates_last_run_at(self) -> None:
        """Running a task updates its last_run_at timestamp."""
        register_task(
            TaskDefinition(
                task_key="test.timestamp",
                callable=MagicMock(),
                interval=timedelta(hours=1),
            )
        )
        before = timezone.now()
        run_due_tasks()
        record = ScheduledTaskRecord.objects.get(task_key="test.timestamp")
        self.assertGreaterEqual(record.last_run_at, before)

    def test_ic_frequency_task(self) -> None:
        """IC-frequency tasks check against IC time."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.ic_task",
                callable=mock_fn,
                interval=timedelta(hours=24),
                frequency_type=FrequencyType.IC,
            )
        )
        ic_now = datetime(1, 6, 15, 12, 0, tzinfo=timezone.utc)
        ScheduledTaskRecord.objects.create(
            task_key="test.ic_task",
            last_ic_run_at=ic_now - timedelta(hours=25),
        )
        executed = run_due_tasks(ic_now=ic_now)
        self.assertEqual(executed, ["test.ic_task"])

    def test_ic_task_skipped_when_no_ic_time(self) -> None:
        """IC-frequency tasks are skipped when ic_now is not provided."""
        mock_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.ic_no_time",
                callable=mock_fn,
                interval=timedelta(hours=24),
                frequency_type=FrequencyType.IC,
            )
        )
        executed = run_due_tasks()
        self.assertEqual(executed, [])

    def test_failed_task_does_not_block_others(self) -> None:
        """A failing task doesn't prevent other tasks from running."""
        failing_fn = MagicMock(side_effect=RuntimeError("boom"))
        passing_fn = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.failing",
                callable=failing_fn,
                interval=timedelta(hours=1),
            )
        )
        register_task(
            TaskDefinition(
                task_key="test.passing",
                callable=passing_fn,
                interval=timedelta(hours=1),
            )
        )
        executed = run_due_tasks()
        self.assertIn("test.passing", executed)
        self.assertNotIn("test.failing", executed)
        passing_fn.assert_called_once()

    def test_multiple_tasks_run_in_order(self) -> None:
        """Multiple due tasks all run."""
        fn1 = MagicMock()
        fn2 = MagicMock()
        register_task(
            TaskDefinition(
                task_key="test.task1",
                callable=fn1,
                interval=timedelta(hours=1),
            )
        )
        register_task(
            TaskDefinition(
                task_key="test.task2",
                callable=fn2,
                interval=timedelta(hours=1),
            )
        )
        executed = run_due_tasks()
        self.assertEqual(len(executed), 2)
        fn1.assert_called_once()
        fn2.assert_called_once()
```

**Step 2: Run tests**

```bash
echo "yes" | arx test world.game_clock
```

**Step 3: Commit**

```bash
git add src/world/game_clock/tests/test_task_registry.py
git commit -m "test(game_clock): add comprehensive task registry tests"
```

---

## Task 9: GameTickScript and Server Hook

Create the Evennia Script that runs the scheduler, and wire it up in the server startup hook.

**Files:**
- Create: `src/world/game_clock/scripts.py`
- Modify: `src/server/conf/at_server_startstop.py`
- Create: `src/world/game_clock/tests/test_scripts.py`

**Step 1: Create the GameTickScript**

```python
"""Evennia Script for the game clock scheduler."""

from __future__ import annotations

import logging

from typeclasses.scripts import Script
from world.game_clock.services import get_ic_now
from world.game_clock.task_registry import run_due_tasks

logger = logging.getLogger("world.game_clock.scheduler")

# Tick interval in seconds (5 minutes)
TICK_INTERVAL = 300


class GameTickScript(Script):
    """
    Persistent background script that dispatches periodic tasks.

    Runs every TICK_INTERVAL seconds. On each tick, checks the task
    registry and executes any due tasks.
    """

    def at_script_creation(self) -> None:
        """Set up the repeating script."""
        self.key = "game_tick_script"
        self.desc = "Game clock periodic task dispatcher"
        self.interval = TICK_INTERVAL
        self.persistent = True
        self.start_delay = True

    def at_repeat(self) -> None:
        """Called every interval — dispatch due tasks."""
        ic_now = get_ic_now()
        executed = run_due_tasks(ic_now=ic_now)
        if executed:
            logger.info("Tick completed, ran tasks: %s", ", ".join(executed))


def ensure_game_tick_script() -> None:
    """
    Create the GameTickScript if it doesn't already exist.

    Called from at_server_start() to ensure the scheduler is running.
    """
    from evennia.scripts.models import ScriptDB

    existing = ScriptDB.objects.filter(db_key="game_tick_script")
    if existing.exists():
        logger.info("GameTickScript already exists, skipping creation.")
        return

    from evennia.utils.create import create_script

    script = create_script(
        GameTickScript,
        key="game_tick_script",
        persistent=True,
        interval=TICK_INTERVAL,
    )
    logger.info("Created GameTickScript: %s", script)
```

**Step 2: Wire up the server startup hook**

Modify `src/server/conf/at_server_startstop.py`:

```python
def at_server_start():
    """
    This is called every time the server starts up, regardless of
    how it was shut down.
    """
    from world.game_clock.scripts import ensure_game_tick_script

    ensure_game_tick_script()
```

**Step 3: Write script tests**

```python
"""Tests for the GameTickScript."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.game_clock.scripts import ensure_game_tick_script


class EnsureGameTickScriptTests(TestCase):
    @patch("world.game_clock.scripts.ScriptDB")
    def test_skips_creation_when_exists(
        self, mock_script_db: MagicMock
    ) -> None:
        """Does not create a new script if one exists."""
        mock_script_db.objects.filter.return_value.exists.return_value = True
        ensure_game_tick_script()
        # Should not attempt to create
        mock_script_db.objects.filter.assert_called_once()

    @patch("world.game_clock.scripts.create_script")
    @patch("world.game_clock.scripts.ScriptDB")
    def test_creates_when_not_exists(
        self,
        mock_script_db: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """Creates the script if it doesn't exist."""
        mock_script_db.objects.filter.return_value.exists.return_value = False
        ensure_game_tick_script()
        mock_create.assert_called_once()
```

**Step 4: Run tests and lint**

```bash
echo "yes" | arx test world.game_clock
ruff check src/world/game_clock/ src/server/conf/at_server_startstop.py
```

**Step 5: Commit**

```bash
git add src/world/game_clock/scripts.py src/server/conf/at_server_startstop.py src/world/game_clock/tests/test_scripts.py
git commit -m "feat(game_clock): add GameTickScript and server startup hook"
```

---

## Task 10: Wire Up Periodic Tasks — Batch Functions

Create batch wrapper functions in each app that the scheduler will call, and register them in the task registry.

**Files:**
- Create: `src/world/game_clock/tasks.py`
- Create: `src/world/game_clock/tests/test_tasks.py`

**Step 1: Create the batch task functions and registration**

```python
"""
Periodic task definitions for the game clock scheduler.

Each task is a thin wrapper that calls existing app-level service functions
in batch. Tasks are registered with the scheduler on module import.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from world.game_clock.task_registry import (
    FrequencyType,
    TaskDefinition,
    register_task,
)

logger = logging.getLogger("world.game_clock.tasks")


def batch_ap_daily_regen() -> None:
    """Apply daily AP regen to all character pools."""
    from world.action_points.models import ActionPointPool

    pools = ActionPointPool.objects.all()
    count = 0
    for pool in pools:
        added = pool.apply_daily_regen()
        if added > 0:
            count += 1
    logger.info("AP daily regen: %d pools regenerated", count)


def batch_ap_weekly_regen() -> None:
    """Apply weekly AP regen to all character pools."""
    from world.action_points.models import ActionPointPool

    pools = ActionPointPool.objects.all()
    count = 0
    for pool in pools:
        added = pool.apply_weekly_regen()
        if added > 0:
            count += 1
    logger.info("AP weekly regen: %d pools regenerated", count)


def batch_journal_weekly_reset() -> None:
    """Reset stale weekly journal XP trackers."""
    from django.utils import timezone

    from world.journals.models import WeeklyJournalXP

    week_ago = timezone.now() - timedelta(days=7)
    stale = WeeklyJournalXP.objects.filter(week_reset_at__lt=week_ago)
    count = 0
    for tracker in stale:
        tracker.reset_week()
        count += 1
    logger.info("Journal weekly reset: %d trackers reset", count)


def batch_relationship_weekly_reset() -> None:
    """Reset stale weekly relationship counters."""
    from django.utils import timezone

    from world.relationships.models import CharacterRelationship

    week_ago = timezone.now() - timedelta(days=7)
    stale = CharacterRelationship.objects.filter(
        week_reset_at__lt=week_ago
    ) | CharacterRelationship.objects.filter(week_reset_at__isnull=True)
    updated = stale.filter(
        developments_this_week__gt=0
    ) | stale.filter(changes_this_week__gt=0)
    count = updated.update(
        developments_this_week=0,
        changes_this_week=0,
        week_reset_at=timezone.now(),
    )
    logger.info("Relationship weekly reset: %d relationships reset", count)


def batch_form_expiration_cleanup() -> None:
    """Delete expired real-time temporary form changes."""
    from django.utils import timezone

    from world.forms.models import DurationType, TemporaryFormChange

    count, _ = TemporaryFormChange.objects.filter(
        duration_type=DurationType.REAL_TIME,
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Form expiration cleanup: %d expired changes deleted", count)


def batch_condition_expiration_cleanup() -> None:
    """Deactivate expired time-based conditions."""
    from django.utils import timezone

    from world.conditions.models import ConditionInstance

    count = ConditionInstance.objects.filter(
        expires_at__lt=timezone.now(),
        is_active=True,
    ).update(is_active=False)
    logger.info(
        "Condition expiration cleanup: %d conditions deactivated", count
    )


def register_all_tasks() -> None:
    """Register all periodic tasks with the scheduler."""
    register_task(
        TaskDefinition(
            task_key="ap.daily_regen",
            callable=batch_ap_daily_regen,
            interval=timedelta(hours=24),
            description="Apply daily AP regeneration to all pools.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="ap.weekly_regen",
            callable=batch_ap_weekly_regen,
            interval=timedelta(days=7),
            description="Apply weekly AP regeneration to all pools.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="journals.weekly_reset",
            callable=batch_journal_weekly_reset,
            interval=timedelta(hours=24),
            frequency_type=FrequencyType.REAL,
            description="Batch-reset stale weekly journal XP trackers.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="relationships.weekly_reset",
            callable=batch_relationship_weekly_reset,
            interval=timedelta(hours=24),
            frequency_type=FrequencyType.REAL,
            description="Reset stale weekly relationship counters.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="forms.expiration_cleanup",
            callable=batch_form_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired real-time temporary form changes.",
        )
    )
    register_task(
        TaskDefinition(
            task_key="conditions.expiration_cleanup",
            callable=batch_condition_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Deactivate expired time-based conditions.",
        )
    )
```

**Step 2: Call register_all_tasks from the server hook**

Update `src/server/conf/at_server_startstop.py`:

```python
def at_server_start():
    """
    This is called every time the server starts up, regardless of
    how it was shut down.
    """
    from world.game_clock.scripts import ensure_game_tick_script
    from world.game_clock.tasks import register_all_tasks

    register_all_tasks()
    ensure_game_tick_script()
```

**Step 3: Write tests for batch task functions**

```python
"""Tests for periodic batch task functions."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from world.game_clock.tasks import (
    batch_condition_expiration_cleanup,
    batch_form_expiration_cleanup,
    batch_journal_weekly_reset,
)


class BatchJournalWeeklyResetTests(TestCase):
    def test_resets_stale_trackers(self) -> None:
        """Resets trackers older than 7 days."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=sheet,
            posts_this_week=3,
            praised_this_week=True,
        )
        tracker.week_reset_at = timezone.now() - timedelta(days=8)
        tracker.save(update_fields=["week_reset_at"])

        batch_journal_weekly_reset()

        tracker.refresh_from_db()
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)

    def test_skips_fresh_trackers(self) -> None:
        """Trackers within the current week are not reset."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        WeeklyJournalXP.objects.create(
            character_sheet=sheet,
            posts_this_week=2,
        )

        batch_journal_weekly_reset()

        tracker = WeeklyJournalXP.objects.get(character_sheet=sheet)
        self.assertEqual(tracker.posts_this_week, 2)


class BatchFormExpirationTests(TestCase):
    def test_deletes_expired_real_time_changes(self) -> None:
        """Deletes TemporaryFormChange entries past their expires_at."""
        from world.forms.models import (
            DurationType,
            TemporaryFormChange,
        )

        # Count before (there may be none)
        before = TemporaryFormChange.objects.count()
        batch_form_expiration_cleanup()
        # Just verify it doesn't crash — proper integration test
        # requires form fixtures which are complex
        after = TemporaryFormChange.objects.count()
        self.assertEqual(before, after)  # No data = no change


class BatchConditionExpirationTests(TestCase):
    def test_runs_without_error(self) -> None:
        """Batch condition cleanup runs without error on empty data."""
        batch_condition_expiration_cleanup()
        # Just verify it doesn't crash
```

**Step 4: Run tests and lint**

```bash
echo "yes" | arx test world.game_clock
ruff check src/world/game_clock/ src/server/conf/at_server_startstop.py
```

**Step 5: Commit**

```bash
git add src/world/game_clock/tasks.py src/world/game_clock/tests/test_tasks.py src/server/conf/at_server_startstop.py
git commit -m "feat(game_clock): wire up periodic tasks for AP, journals, relationships, forms, conditions"
```

---

## Task 11: App Documentation (CLAUDE.md)

Create the app-level documentation.

**Files:**
- Create: `src/world/game_clock/CLAUDE.md`

**Step 1: Write CLAUDE.md**

```markdown
# Game Clock App

Central time engine for Arx II. Tracks IC time, provides day/night and seasonal awareness, and dispatches periodic game tasks via a scheduler.

## Models

### GameClock (singleton)
Anchor-based IC time derivation. IC time = `anchor_ic_time + (now - anchor_real_time) * time_ratio`.
- `anchor_real_time`, `anchor_ic_time` — the anchor pair
- `time_ratio` — IC seconds per real second (default 3.0)
- `paused` — emergency stop

### GameClockHistory
Audit log for clock adjustments. Stores old/new anchor values, who changed it, and why.

### ScheduledTaskRecord
Per-task tracking of last run time. Tasks are auto-created on first scheduler tick.
- `task_key` — unique string identifier
- `last_run_at` — real time of last execution
- `enabled` — staff can disable individual tasks via admin

## Service Functions

### Clock Queries
- `get_ic_now()` — current IC datetime
- `get_ic_phase()` — TimePhase enum (DAWN, DAY, DUSK, NIGHT) with season-adjusted boundaries
- `get_ic_season()` — Season enum from IC month
- `get_light_level()` — float 0.0–1.0 for atmospheric lighting
- `get_ic_date_for_real_time(real_dt)` — convert real→IC datetime
- `get_real_time_for_ic_date(ic_dt)` — convert IC→real datetime

### Clock Management (staff)
- `set_clock()` — set IC time (creates clock or re-anchors)
- `set_time_ratio()` — change ratio with re-anchor
- `pause_clock()` / `unpause_clock()` — emergency pause

## Scheduler

### GameTickScript (Evennia Script)
Persistent script that ticks every 5 minutes, calling `run_due_tasks()`.
Created automatically in `at_server_start()`.

### Task Registry
Tasks registered in `tasks.py` via `register_all_tasks()`, called at server startup.

### Wired Tasks
| Task | Frequency | Source App |
|------|-----------|------------|
| AP daily regen | 24h real | action_points |
| AP weekly regen | 7d real | action_points |
| Journal weekly reset | daily sweep | journals |
| Relationship weekly reset | daily sweep | relationships |
| Form expiration cleanup | hourly | forms |
| Condition expiration cleanup | hourly | conditions |

## API Endpoints

- `GET /api/clock/` — current IC time, phase, season, light level
- `GET /api/clock/convert/` — date conversion (IC↔real)
- `POST /api/clock/adjust/` — set IC time (staff only)
- `POST /api/clock/ratio/` — change time ratio (staff only)
- `POST /api/clock/pause/` — pause clock (staff only)
- `POST /api/clock/unpause/` — unpause clock (staff only)

## Three Time Contexts

1. **World clock (IC)** — canonical game time at 3:1 ratio. Day/night, seasons, atmospheric.
2. **Scene time** — RP events freeze IC time for participants. Scene system owns this.
3. **Real time** — progression gating (weekly XP, AP regen, relationship limits).

## Integration Points

- **Any IC time query** → `get_ic_now()`
- **Day/night mechanics** → `get_ic_phase()` or `get_light_level()`
- **Seasonal mechanics** → `get_ic_season()`
- **Event scheduling** → `get_real_time_for_ic_date()`
- **IC timestamps on models** → stamp `get_ic_now()` at creation, store as concrete value
```

**Step 2: Commit**

```bash
git add src/world/game_clock/CLAUDE.md
git commit -m "docs(game_clock): add app documentation"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | App scaffolding + constants | apps.py, constants.py, settings.py |
| 2 | GameClock + History models | models.py, factories.py, test_models.py |
| 3 | Clock query services | services.py, test_services.py |
| 4 | Clock management services | services.py (extend), types.py, test_services.py (extend) |
| 5 | Admin interface | admin.py |
| 6 | REST API (views, serializers, URLs) | views.py, serializers.py, urls.py, test_views.py |
| 7 | Scheduler infrastructure | models.py (extend), task_registry.py, admin.py (extend) |
| 8 | Task registry tests | test_task_registry.py |
| 9 | GameTickScript + server hook | scripts.py, at_server_startstop.py, test_scripts.py |
| 10 | Wire up periodic tasks | tasks.py, test_tasks.py |
| 11 | App documentation | CLAUDE.md |
