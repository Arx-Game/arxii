"""Ops metrics for the Game Ops dashboard (#1221 Task 7).

Pure-read analytics for the "how is the live game doing" surface: progression
throughput, the money supply, story/GM activity, and the player-submissions
queue. Every weekly series is a single `TruncWeek` aggregate query grouped
oldest -> newest over the last N ISO weeks (Monday-anchored, matching
Evennia's `TIME_ZONE = "UTC"` / `USE_TZ = True`), zero-filled so a week with no
rows still renders a bar. No queries in loops — the four `reports_snapshot`
buckets and `story_snapshot`'s counters are each one query per known,
fixed-size model, never per-row.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from django.db.models import Case, Count, Q, QuerySet, Sum, When
from django.db.models.functions import TruncWeek
from django.utils import timezone

from world.classes.models import CharacterClassLevel
from world.currency.models import CharacterPurse, CurrencyTransfer, OrganizationTreasury
from world.gm.constants import GMTableStatus
from world.gm.models import GMProfile, GMTable
from world.player_submissions.constants import SubmissionStatus
from world.player_submissions.models import (
    BugReport,
    PlayerFeedback,
    PlayerReport,
    SystemErrorReport,
)
from world.progression.models import (
    CharacterXPTransaction,
    ClassLevelAdvancement,
    DevelopmentTransaction,
)
from world.scenes.models import Scene
from world.stories.constants import SessionRequestStatus
from world.stories.models import BeatCompletion, SessionRequest, Story
from world.stories.types import StoryStatus

_GM_ACTIVE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class WeeklyPoint:
    """One zero-filled ISO-week bucket."""

    week_start: datetime.date
    value: float


@dataclass(frozen=True)
class WeeklySeries:
    """A named series of `WeeklyPoint`s, oldest -> newest."""

    label: str
    points: list[WeeklyPoint]


@dataclass(frozen=True)
class ReportBucket:
    """Open/total counts for one player-submissions queue, linking to its staff page."""

    kind: str
    open_count: int
    total: int
    staff_url: str


def _week_boundaries(*, weeks: int) -> list[datetime.date]:
    """Oldest -> newest Monday-anchored ISO-week start dates, ending this week.

    Uses `timezone.now().date()` (UTC, per `TIME_ZONE = "UTC"`) so this lines
    up with `TruncWeek`'s default truncation with no explicit tzinfo needed.
    """
    today = timezone.now().date()
    this_monday = today - datetime.timedelta(days=today.weekday())
    return [this_monday - datetime.timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]


def _weekly_series(
    queryset: QuerySet,
    *,
    label: str,
    date_field: str,
    aggregate: Count | Sum,
    weeks: int,
) -> WeeklySeries:
    """One `TruncWeek` aggregate query, zero-filled over the last `weeks` ISO weeks.

    `queryset` should already carry any row-selection filter (e.g. "minted
    transfers only"); this adds the date-range filter, groups by week, and
    zero-fills gaps — a single query regardless of `weeks`.
    """
    boundaries = _week_boundaries(weeks=weeks)
    cutoff = boundaries[0]
    rows = (
        queryset.filter(**{f"{date_field}__date__gte": cutoff})
        .annotate(week=TruncWeek(date_field))
        .values("week")
        .annotate(total=aggregate)
        .order_by("week")
    )
    totals_by_week = {row["week"].date(): row["total"] or 0 for row in rows}
    points = [
        WeeklyPoint(week_start=start, value=float(totals_by_week.get(start, 0)))
        for start in boundaries
    ]
    return WeeklySeries(label=label, points=points)


def progression_series(*, weeks: int = 8) -> list[WeeklySeries]:
    """XP earned, development points awarded, and level-ups, weekly."""
    return [
        _weekly_series(
            CharacterXPTransaction.objects.filter(amount__gt=0),
            label="XP earned",
            date_field="transaction_date",
            aggregate=Sum("amount"),
            weeks=weeks,
        ),
        _weekly_series(
            DevelopmentTransaction.objects.all(),
            label="Development points",
            date_field="transaction_date",
            aggregate=Sum("amount"),
            weeks=weeks,
        ),
        _weekly_series(
            ClassLevelAdvancement.objects.all(),
            label="Level-ups",
            date_field="created_at",
            aggregate=Count("id"),
            weeks=weeks,
        ),
    ]


def level_distribution() -> list[tuple[int, int]]:
    """(level, character count) for primary class-level assignments, one query."""
    rows = (
        CharacterClassLevel.objects.filter(is_primary=True)
        .values("level")
        .annotate(count=Count("id"))
        .order_by("level")
    )
    return [(row["level"], row["count"]) for row in rows]


def economy_series(*, weeks: int = 8) -> list[WeeklySeries]:
    """Minted, sunk, and transferred coppers, weekly.

    Per `CurrencyTransfer` (see `currency/services.py:86-95`): a null source
    (`from_purse` and `from_treasury` both null) is a mint/faucet; a null
    destination (`to_purse` and `to_treasury` both null) is a sink; a row with
    both source and destination populated is a plain transfer. Source and
    destination can never both be null, so these three buckets are mutually
    exclusive and exhaustive.
    """
    minted = CurrencyTransfer.objects.filter(from_purse__isnull=True, from_treasury__isnull=True)
    sunk = CurrencyTransfer.objects.filter(to_purse__isnull=True, to_treasury__isnull=True)
    transferred = CurrencyTransfer.objects.filter(
        Q(from_purse__isnull=False) | Q(from_treasury__isnull=False),
        Q(to_purse__isnull=False) | Q(to_treasury__isnull=False),
    )
    return [
        _weekly_series(
            minted, label="Minted", date_field="created_at", aggregate=Sum("amount"), weeks=weeks
        ),
        _weekly_series(
            sunk, label="Sunk", date_field="created_at", aggregate=Sum("amount"), weeks=weeks
        ),
        _weekly_series(
            transferred,
            label="Transferred",
            date_field="created_at",
            aggregate=Sum("amount"),
            weeks=weeks,
        ),
    ]


def money_supply() -> dict[str, int]:
    """Total coppers in circulation: `{"purses": n, "treasuries": n, "total": n}`.

    `purses`/`treasuries` are the summed balances held by each ledger kind
    (not entity counts) — the money supply is a quantity of currency, not a
    row count; `total` is their sum.
    """
    purses_total = CharacterPurse.objects.aggregate(total=Sum("balance"))["total"] or 0
    treasuries_total = OrganizationTreasury.objects.aggregate(total=Sum("balance"))["total"] or 0
    return {
        "purses": purses_total,
        "treasuries": treasuries_total,
        "total": purses_total + treasuries_total,
    }


def story_series(*, weeks: int = 8) -> list[WeeklySeries]:
    """Beats completed and scenes started, weekly."""
    return [
        _weekly_series(
            BeatCompletion.objects.all(),
            label="Beats completed",
            date_field="recorded_at",
            aggregate=Count("id"),
            weeks=weeks,
        ),
        _weekly_series(
            Scene.objects.all(),
            label="Scenes started",
            date_field="date_started",
            aggregate=Count("id"),
            weeks=weeks,
        ),
    ]


def story_snapshot() -> dict[str, int]:
    """Point-in-time story/GM activity counters — one query per counter."""
    active_cutoff = timezone.now() - datetime.timedelta(days=_GM_ACTIVE_WINDOW_DAYS)
    return {
        "active_stories": Story.objects.filter(status=StoryStatus.ACTIVE).count(),
        "active_gm_tables": GMTable.objects.filter(status=GMTableStatus.ACTIVE).count(),
        "pending_session_requests": SessionRequest.objects.filter(
            status=SessionRequestStatus.OPEN
        ).count(),
        "gms_active_30d": GMProfile.objects.filter(last_active_at__gte=active_cutoff).count(),
    }


# (kind label, model, open/total status field, staff page path)
_REPORT_KINDS: tuple[tuple[str, type, str], ...] = (
    ("Player Feedback", PlayerFeedback, "/staff/feedback"),
    ("Bug Reports", BugReport, "/staff/bug-reports"),
    ("Player Reports", PlayerReport, "/staff/player-reports"),
    ("System Errors", SystemErrorReport, "/staff/system-errors"),
)


def reports_snapshot() -> list[ReportBucket]:
    """Open/total counts for each player-submissions queue — one query per model.

    "Open" means `SubmissionStatus.OPEN` specifically (not merely
    non-terminal): the enum has exactly OPEN / REVIEWED / DISMISSED, and
    REVIEWED and DISMISSED are both terminal — a submission is either still
    awaiting staff action (OPEN) or it isn't.
    """
    buckets = []
    for kind, model, staff_url in _REPORT_KINDS:
        counts = model.objects.aggregate(
            open_count=Count(Case(When(status=SubmissionStatus.OPEN, then=1))),
            total=Count("id"),
        )
        buckets.append(
            ReportBucket(
                kind=kind,
                open_count=counts["open_count"],
                total=counts["total"],
                staff_url=staff_url,
            )
        )
    return buckets
