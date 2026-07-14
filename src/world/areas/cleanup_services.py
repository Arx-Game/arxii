"""CLEANUP project kind: area quality improvement via collective effort (#1889).

A TIERED_PERIOD project mirroring GANG_TURF. Players contribute over a period;
at the deadline accumulated progress is graded into a CheckOutcome tier via
CleanupTierThreshold rows, and the tier's quality_delta bumps AreaQuality.
Crime heat and combat encounters erode quality; a weekly sweep handles
dwell-decay and regain.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.areas.constants import (
    AREA_QUALITY_MAX,
    AREA_QUALITY_MIN,
    AREA_QUALITY_NORMAL,
    CLEANUP_DWELL_DAYS,
    CLEANUP_EROSION_AMOUNT,
    CLEANUP_PROJECT_DAYS,
    CLEANUP_REGAIN_WEEKS,
    CLEANUP_SOCIETY_REPUTATION_DELTA,
    AreaLevel,
)
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.services import resolve_project

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


def _select_tier(thresholds, current_progress: int):
    """Return the highest min_progress row at or below current_progress.

    Mirrors GANG_TURF's _select_tier. Seeded rows always include a
    min_progress=0 baseline, so a match always exists.
    """
    for row in thresholds:
        if row.min_progress <= current_progress:
            return row
    return thresholds[-1]


def _default_thresholds() -> list[tuple[str, int, int]]:
    """Canonical default tier ladder: (outcome_name, min_progress, quality_delta)."""
    return [
        ("Failure", 0, 0),
        ("Partial Success", 25, 1),
        ("Success", 50, 1),
        ("Critical Success", 100, 2),
    ]


@transaction.atomic
def start_cleanup_project(
    *,
    area: Area,
    owner_persona: Persona,
    period_days: int = CLEANUP_PROJECT_DAYS,
) -> Project:
    """Open a CLEANUP project for a neighborhood area.

    Validates area is NEIGHBORHOOD level. Anyone can start — no leader-rank
    gate (public good). Creates the TIERED_PERIOD project + details + seeded
    tier thresholds.

    Args:
        area: the neighborhood area to clean up.
        owner_persona: the persona initiating the project.
        period_days: real-time span until the grading deadline.

    Returns:
        The created Project (with details + thresholds).

    Raises:
        ValueError: if area is not NEIGHBORHOOD level.
    """
    from world.areas.models import (  # noqa: PLC0415
        CleanupProjectDetails,
        CleanupTierThreshold,
    )
    from world.projects.models import Project  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    if area.level != AreaLevel.NEIGHBORHOOD:
        msg = (
            f"Area {area.pk} level is {area.level}, not NEIGHBORHOOD — "
            "CLEANUP targets neighborhood-level areas only."
        )
        raise ValueError(msg)

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.CLEANUP,
        completion_mode=CompletionMode.TIERED_PERIOD,
        status=ProjectStatus.ACTIVE,
        owner_persona=owner_persona,
        started_at=now,
        time_limit=now + timedelta(days=period_days),
        threshold_target=None,
        description=f"Area cleanup of {area.name}",
    )
    # Set the celestial resonance FK if the seed content exists.
    from world.magic.models.affinity import Resonance  # noqa: PLC0415

    hope = Resonance.objects.filter(name="Hope").first()
    if hope is not None:
        project.resonance = hope
        project.save(update_fields=["resonance"])
    details = CleanupProjectDetails.objects.create(
        project=project,
        target_area=area,
    )
    for outcome_name, min_progress, quality_delta in _default_thresholds():
        outcome = CheckOutcome.objects.filter(name=outcome_name).first()
        if outcome is not None:
            CleanupTierThreshold.objects.create(
                details=details,
                outcome_tier=outcome,
                min_progress=min_progress,
                quality_delta=quality_delta,
            )
    return project


def resolve_cleanup(project: Project) -> None:
    """Grade a RESOLVING CLEANUP project by progress and finalize it.

    Reads CleanupTierThreshold rows, selects the tier reached, and calls
    resolve_project. Registered via register_tiered_resolver.
    """
    details = project.cleanup_details
    thresholds = list(details.tier_thresholds.all())
    tier = _select_tier(thresholds, project.current_progress)
    resolve_project(project, outcome_tier=tier.outcome_tier)


@transaction.atomic
def complete_cleanup(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """Kind handler: bump AreaQuality by the tier's quality_delta.

    Registered with register_kind_handler at app-ready. On success tier
    (success_level >= 0), bumps quality (clamped to AREA_QUALITY_MAX).
    Idempotent via applied_at marker. On failure, no-op.
    """
    from world.areas.models import (  # noqa: PLC0415
        AreaQuality,
        CleanupProjectDetails,
    )

    if outcome_tier is None or outcome_tier.success_level < 0:
        return

    details = CleanupProjectDetails.objects.get(project=project)
    threshold = details.tier_thresholds.filter(outcome_tier=outcome_tier).first()
    if threshold is None or threshold.quality_delta <= 0:
        return

    claimed = CleanupProjectDetails.objects.filter(project=project, applied_at__isnull=True).update(
        applied_at=timezone.now()
    )
    if not claimed:
        return

    area = details.target_area
    quality, _ = AreaQuality.objects.get_or_create(area=area)
    quality.quality = min(AREA_QUALITY_MAX, quality.quality + threshold.quality_delta)
    quality.condition_since = timezone.now()
    quality.save(update_fields=["quality", "condition_since"])

    logger.info(
        "cleanup %s applied: area %s quality now %s.",
        project.pk,
        area.pk,
        quality.quality,
    )


def erode_area_quality(area: Area, amount: int = CLEANUP_EROSION_AMOUNT) -> None:
    """Decrement an area's quality (clamped at AREA_QUALITY_MIN).

    Called from crime heat and combat hooks.
    """
    from world.areas.models import AreaQuality  # noqa: PLC0415

    try:
        quality = AreaQuality.objects.get(area=area)
    except AreaQuality.DoesNotExist:
        return
    if amount <= 0:
        return
    quality.quality = max(AREA_QUALITY_MIN, quality.quality - amount)
    quality.condition_since = timezone.now()
    quality.save(update_fields=["quality", "condition_since"])


def cleanup_quality_decay_tick() -> int:
    """Weekly sweep: decay above-normal quality, regain below-normal.

    Returns count of AreaQuality rows changed.
    """
    from world.areas.models import AreaQuality  # noqa: PLC0415

    now = timezone.now()
    changed = 0
    for quality in AreaQuality.objects.all():
        if quality.quality > AREA_QUALITY_NORMAL:
            if now >= quality.condition_since + timedelta(days=CLEANUP_DWELL_DAYS):
                quality.quality -= 1
                quality.condition_since = now
                quality.save(update_fields=["quality", "condition_since"])
                changed += 1
        elif quality.quality < AREA_QUALITY_NORMAL:
            regain_days = CLEANUP_REGAIN_WEEKS * 7
            if now >= quality.condition_since + timedelta(days=regain_days):
                quality.quality += 1
                quality.condition_since = now
                quality.save(update_fields=["quality", "condition_since"])
                changed += 1
    return changed


def _maybe_grant_cleanup_society_reputation(project: Project, contributor_persona: Persona) -> None:
    """Grant society reputation to a cleanup contributor (public good reward).

    Called from the contribution path when the project is a CLEANUP kind and
    the target area has a dominant_society. Lives here (not in
    projects/services.py) per AGENTS.md: service functions must be generic
    utilities, not embed hardcoded gameplay logic.
    """
    from world.areas.models import CleanupProjectDetails  # noqa: PLC0415
    from world.societies.renown import bump_society_reputation  # noqa: PLC0415

    try:
        details = project.cleanup_details
    except CleanupProjectDetails.DoesNotExist:
        return
    area = details.target_area
    society = area.dominant_society
    if society is None:
        return
    bump_society_reputation(contributor_persona, society, CLEANUP_SOCIETY_REPUTATION_DELTA)


# Description suffixes for room display (PLACEHOLDER prose, staff-tunable).
_QUALITY_SUFFIXES_ABOVE = {
    4: "The streets here are tidy and well-maintained.",
    5: "The area is pristine — every surface gleams with care and pride.",
}
_QUALITY_SUFFIXES_BELOW = {
    0: "The area is blighted — decay and ruin are everywhere.",
    1: "Trash litters the gutters and the buildings look neglected.",
    2: "The streets here are rundown and in need of repair.",
}


def area_quality_description_suffix(area: Area) -> str | None:
    """Return a description suffix for the area's quality, or None if normal.

    Read-time composition — does not mutate the room's stored description.
    Quality 3 (Ordinary) returns None (no suffix).
    """
    from world.areas.models import AreaQuality  # noqa: PLC0415

    try:
        quality = AreaQuality.objects.get(area=area)
    except AreaQuality.DoesNotExist:
        return None
    if quality.quality > AREA_QUALITY_NORMAL:
        return _QUALITY_SUFFIXES_ABOVE.get(quality.quality)
    if quality.quality < AREA_QUALITY_NORMAL:
        return _QUALITY_SUFFIXES_BELOW.get(quality.quality)
    return None
