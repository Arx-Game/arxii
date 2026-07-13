"""CITY_DEFENSE project kind: staff-bespoke battle preparation graded at deadline (#1892).

A ``TIERED_PERIOD`` kind mirroring GANG_TURF. Staff create the project linked
to an Area; players contribute over a period; at the deadline accumulated
progress is graded into a ``CheckOutcome`` tier via ``CityDefenseTierThreshold``
rows, and the handler stores the tier on ``CityDefenseDetails``. Later, when a
battle is staged in that area, ``create_fortification`` reads the stored
tier's ``CityDefenseIntegrityBonus`` and boosts the defending side's
fortifications.

Decoupled from the battle lifecycle: the project grades at its deadline
regardless of whether a battle exists yet. ``get_city_defense_integrity_bonus``
is the read seam — called by ``create_fortification`` when the battle has a
region.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind
from world.projects.services import resolve_project

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


def _select_tier(thresholds, current_progress: int):
    """Return the highest ``min_progress`` row at or below ``current_progress``.

    ``thresholds`` must be ordered by ``-min_progress`` (the model's default).
    Seeded rows always include a ``min_progress=0`` baseline failure tier, so a
    match always exists — this never returns None.

    Args:
        thresholds: iterable of ``CityDefenseTierThreshold`` rows, ordered
            by ``-min_progress``.
        current_progress: the project's accumulated progress at deadline.

    Returns:
        The matching ``CityDefenseTierThreshold`` row.
    """
    for row in thresholds:
        if row.min_progress <= current_progress:
            return row
    # Unreachable when the baseline min_progress=0 row is seeded; defensive.
    return thresholds[-1]


def resolve_city_defense(project: Project) -> None:
    """Grade a RESOLVING CITY_DEFENSE project by progress and finalize it.

    Reads ``CityDefenseTierThreshold`` rows, selects the tier reached, and calls
    ``resolve_project`` (which dispatches ``complete_city_defense`` before
    setting COMPLETED/FAILED). Registered via ``register_tiered_resolver`` and
    invoked by ``scan_active_projects`` in the same tick the project transitions
    to RESOLVING.
    """
    details = project.city_defense_details
    thresholds = list(details.tier_thresholds.all())
    tier = _select_tier(thresholds, project.current_progress)
    resolve_project(project, outcome_tier=tier.outcome_tier)


def complete_city_defense(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """Kind handler: store the graded tier on the details, exactly once.

    Registered with ``register_kind_handler`` at app-ready; runs from
    ``resolve_project`` before COMPLETED/FAILED is set. The tier is also stored
    on ``project.outcome_tier`` by ``resolve_project``, but the details copy is
    needed so ``get_city_defense_integrity_bonus`` can read it via the details
    FK without a Project join.

    Idempotent via DB-level claim-filter (same pattern as
    ``complete_fortification_upgrade``): a second call sees the non-null
    ``applied_at`` and no-ops.
    """
    from world.battles.models import CityDefenseDetails  # noqa: PLC0415

    # The claim filter hits the DB, so a second call sees the non-null
    # applied_at and no-ops even though the cached instance is stale.
    claimed = CityDefenseDetails.objects.filter(project=project, applied_at__isnull=True).update(
        applied_at=timezone.now()
    )
    if not claimed:
        return
    # Instance mutation, not queryset .update(): SharedMemoryModel keeps one
    # live instance per row — see the same pattern in
    # complete_fortification_upgrade.
    details = CityDefenseDetails.objects.get(project=project)
    details.outcome_tier = outcome_tier
    details.save(update_fields=["outcome_tier"])


def get_city_defense_integrity_bonus(area: Area) -> int:
    """Return the integrity bonus for the most recent completed CITY_DEFENSE on ``area``.

    Looks up the most recently applied ``CityDefenseDetails`` for the given area
    (``filter(area=area, applied_at__isnull=False).order_by("-applied_at").first()``),
    reads the stored ``outcome_tier``, looks up the ``CityDefenseIntegrityBonus``
    for that tier, and returns the ``integrity_bonus`` value. Returns 0 if no
    project exists, no tier is stored, or no award row exists (all content gaps,
    not crashes — same try/except pattern as ``gang_turf._tier_to_reputation_delta``).

    Args:
        area: The Area to check for a completed city-defense project.

    Returns:
        The integrity bonus, or 0 if none applies.
    """
    from world.battles.models import (  # noqa: PLC0415
        CityDefenseDetails,
        CityDefenseIntegrityBonus,
    )

    details = (
        CityDefenseDetails.objects.filter(area=area, applied_at__isnull=False)
        .select_related("outcome_tier")
        .order_by("-applied_at")
        .first()
    )
    if details is None or details.outcome_tier_id is None:
        return 0
    try:
        bonus = CityDefenseIntegrityBonus.objects.get(outcome_tier=details.outcome_tier)
    except CityDefenseIntegrityBonus.DoesNotExist:
        return 0
    return bonus.integrity_bonus


@transaction.atomic
def start_city_defense_project(
    *,
    area: Area,
    owner_persona: Persona,
    period_days: int = 30,
    tier_thresholds: list[tuple[CheckOutcome, int]] | None = None,
) -> Project:
    """Open a CITY_DEFENSE project for an area, created by staff.

    Creates the ``Project`` (TIERED_PERIOD, no threshold_target) +
    ``CityDefenseDetails`` + seeded ``CityDefenseTierThreshold`` rows.
    No membership gate — staff-created. ``owner_persona`` is the staff's
    persona for attribution. Default tier ladder if none supplied.

    Args:
        area: The defended region.
        owner_persona: The staff persona for project attribution.
        period_days: Real-time span until the grading deadline.
        tier_thresholds: optional ``(CheckOutcome, min_progress)`` ladder; if
            omitted, the canonical default ladder is looked up by name.

    Returns:
        The created ``Project`` (with details + thresholds).
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.battles.models import (  # noqa: PLC0415
        CityDefenseDetails,
        CityDefenseTierThreshold,
    )
    from world.projects.constants import ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.CITY_DEFENSE,
        completion_mode=CompletionMode.TIERED_PERIOD,
        status=ProjectStatus.ACTIVE,
        owner_persona=owner_persona,
        started_at=now,
        time_limit=now + timedelta(days=period_days),
        threshold_target=None,
        description=f"City defense preparations for {area.name}",
    )
    details = CityDefenseDetails.objects.create(project=project, area=area)
    for outcome_tier, min_progress in tier_thresholds or _default_thresholds():
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=outcome_tier, min_progress=min_progress
        )
    return project


def _default_thresholds() -> list[tuple[CheckOutcome, int]]:
    """Canonical default tier ladder, looked up by CheckOutcome natural key.

    The canonical *bonuses* come from the seed migration; the threshold *bands*
    are a per-project default ladder so a caller can omit ``tier_thresholds``.
    Looked up lazily (no import-time DB query). Mirrors the cast-seed names
    (world/magic/seeds_cast.py) and the seed migration.
    """
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    ladder = [
        ("Failure", 0),
        ("Partial Success", 25),
        ("Success", 50),
        ("Critical Success", 100),
    ]
    rows: list[tuple[CheckOutcome, int]] = []
    for name, min_progress in ladder:
        outcome = CheckOutcome.objects.filter(name=name).first()
        if outcome is not None:
            rows.append((outcome, min_progress))
    return rows
