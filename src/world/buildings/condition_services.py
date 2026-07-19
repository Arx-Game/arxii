"""Condition recovery + preparation services (#1930).

The player-facing loops around the condition-tier ladder:

* ``settle_upkeep_arrears`` — pay the bounded owed amount down to zero.
* ``refurbish_building`` — priced restore to EXCELLENT (the fast path;
  weekly paid upkeep is the slow one). Requires arrears settled first.
  ("Refurbish", not "renovate" — a *renovation* is the existing
  BUILDING_RENOVATION kind-swap project; see AGENT_GLOSSARY.md.)
* ``start_building_preparation`` — the cleaning/party-preparation loop
  (#1930, Apostate 2026-07-06): pushing one tier ABOVE normal (EXCELLENT
  → EXTRAVAGANT → IMMACULATE) is a small funded *project*, not an
  instant purchase. Its threshold is a proportion of the house's base
  prestige (floored), funded via ``project/donate`` (1 progress per
  100c) and sped along with AP Household Command checks
  (``ContributionMethod``). ``complete_building_preparation`` is the
  kind handler; the shine dwell-decays back (see ``upkeep_services``).
* ``set_ultra_upkeep`` — owner toggle for the premium that holds
  IMMACULATE past its dwell.

All charges are pure sinks through the audited currency ledger (#923).
Costs are PLACEHOLDER. Insufficient funds surface as
``django.core.exceptions.ValidationError`` (raised before any state
write), matching the station-repair precedent; refusals raise
``ConditionServiceError`` with a player-safe ``user_message``.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.constants import (
    COPPERS_PER_PROGRESS_POINT,
    PREPARATION_PROJECT_DAYS,
    PREPARE_COST_FLOOR_COPPERS,
    PREPARE_COST_PERCENT_OF_PRESTIGE,
    REFURBISH_COPPER_PER_TIER,
    ConditionTier,
)
from world.buildings.upkeep_services import set_condition_tier

if TYPE_CHECKING:
    from world.buildings.models import Building
    from world.currency.models import CharacterPurse
    from world.projects.models import Project
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


class ConditionServiceError(Exception):
    """A condition-service refusal, carrying a player-safe message."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def _sink(purse: CharacterPurse, amount: int, reason: str) -> None:
    from world.currency.services import transfer  # noqa: PLC0415

    transfer(amount=amount, reason=reason, from_purse=purse)


def _require_settled(building: Building, verb: str) -> None:
    if building.upkeep_arrears > 0:
        msg = f"building {building.pk} has {building.upkeep_arrears} arrears; {verb} refused"
        raise ConditionServiceError(
            msg,
            user_message="Outstanding upkeep must be settled first.",
        )


def refurbish_cost(building: Building) -> int:
    """Coppers to restore ``building`` to EXCELLENT (0 when already there)."""
    deficit = max(0, ConditionTier.EXCELLENT - building.condition_tier)
    return REFURBISH_COPPER_PER_TIER * deficit * building.target_size


def prepare_cost(building: Building) -> int:
    """Coppers to fund the next preparation step above the current tier.

    A proportion of the house's base prestige — the extra shine is priced
    against what the house already is — floored (× ``target_size``) so
    low-polish houses still pay something real. Raises
    ``ConditionServiceError`` when the building isn't eligible (below
    EXCELLENT, or already IMMACULATE).
    """
    from world.buildings.polish_services import building_prestige_base  # noqa: PLC0415

    target = _prepare_target_tier(building)
    proportional = PREPARE_COST_PERCENT_OF_PRESTIGE[target] * building_prestige_base(building)
    floor = PREPARE_COST_FLOOR_COPPERS[target] * building.target_size
    return max(proportional // 100, floor)


def _prepare_target_tier(building: Building) -> int:
    """The tier the next preparation would reach, validating eligibility."""
    if building.condition_tier < ConditionTier.EXCELLENT:
        msg = f"building {building.pk} below EXCELLENT; preparation refused"
        raise ConditionServiceError(
            msg,
            user_message="The building must be in excellent condition before it can be "
            "specially prepared — refurbish it first.",
        )
    target = building.condition_tier + 1
    if target > ConditionTier.IMMACULATE:
        msg = f"building {building.pk} already at IMMACULATE"
        raise ConditionServiceError(
            msg,
            user_message="The building is already immaculately prepared.",
        )
    return target


@transaction.atomic
def settle_upkeep_arrears(*, building: Building, payer_purse: CharacterPurse) -> int:
    """Pay ``building.upkeep_arrears`` down to zero. Returns the amount paid.

    Raises ``ValidationError`` (from ``transfer``) on insufficient funds;
    arrears are unchanged in that case. Returns 0 when nothing is owed.
    """
    owed = building.upkeep_arrears
    if owed <= 0:
        return 0
    _sink(payer_purse, owed, f"upkeep arrears: building {building.pk}")
    building.upkeep_arrears = 0
    building.save(update_fields=["upkeep_arrears"])
    return owed


@transaction.atomic
def refurbish_building(*, building: Building, payer_purse: CharacterPurse) -> int:
    """Restore ``building`` to EXCELLENT for coppers. Returns the cost paid.

    Aspiration-shaped recovery: one priced action back to normal — no
    repair-chore treadmill. Requires arrears settled; refuses when the
    building is already at or above EXCELLENT.
    """
    if building.property_granted_at is not None and building.property_activated_at is None:
        msg = f"building {building.pk} is a granted-not-activated property"
        raise ConditionServiceError(
            msg,
            user_message=(
                "This house hasn't been brought to life yet — it needs to be activated first."
            ),
        )
    _require_settled(building, "refurbish")
    if building.condition_tier >= ConditionTier.EXCELLENT:
        msg = f"building {building.pk} already at/above EXCELLENT"
        raise ConditionServiceError(
            msg,
            user_message="The building is already in excellent condition.",
        )
    cost = refurbish_cost(building)
    _sink(payer_purse, cost, f"refurbishment: building {building.pk}")
    building.consecutive_missed_upkeep = 0
    building.consecutive_paid_upkeep = 0
    building.save(update_fields=["consecutive_missed_upkeep", "consecutive_paid_upkeep"])
    set_condition_tier(building, ConditionTier.EXCELLENT)
    return cost


def _open_preparation_project(building: Building) -> Project | None:
    """The building's not-yet-resolved preparation Project, if one exists."""
    from world.buildings.models import BuildingPreparationDetails  # noqa: PLC0415
    from world.projects.constants import ProjectStatus  # noqa: PLC0415

    details = (
        BuildingPreparationDetails.objects.filter(
            building=building,
            project__status__in=(
                ProjectStatus.PLANNING,
                ProjectStatus.ACTIVE,
                ProjectStatus.RESOLVING,
            ),
        )
        .select_related("project")
        .first()
    )
    return details.project if details is not None else None


@transaction.atomic
def start_building_preparation(*, building: Building, persona: Persona) -> Project:
    """Commission the cleanup project pushing ``building`` one tier above normal.

    EXCELLENT → EXTRAVAGANT → IMMACULATE, one project per (increasingly
    steep) step. Requires arrears settled; refuses while another
    preparation is already underway. The project is created ACTIVE
    (ransom precedent) so funding can start immediately: coppers via
    ``project/donate``, speed via AP Household Command checks
    (``project/check``). The shine is temporary: above-normal tiers
    dwell-decay back unless IMMACULATE is held via ultra upkeep.
    """
    from world.buildings.models import BuildingPreparationDetails  # noqa: PLC0415
    from world.projects.constants import (  # noqa: PLC0415
        CompletionMode,
        ProjectKind,
        ProjectStatus,
    )
    from world.projects.models import Project  # noqa: PLC0415

    _require_settled(building, "preparation")
    existing = _open_preparation_project(building)
    if existing is not None:
        msg = f"building {building.pk} already has preparation project #{existing.pk}"
        raise ConditionServiceError(
            msg,
            user_message=f"A grand preparation is already underway (project #{existing.pk}).",
        )
    target = _prepare_target_tier(building)
    threshold = max(1, prepare_cost(building) // COPPERS_PER_PROGRESS_POINT)

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.BUILDING_PREPARATION,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        status=ProjectStatus.ACTIVE,
        owner_persona=persona,
        started_at=now,
        time_limit=now + timedelta(days=PREPARATION_PROJECT_DAYS),
        threshold_target=threshold,
        description=f"Grand preparation of building {building.pk} to {ConditionTier(target).label}",
    )
    BuildingPreparationDetails.objects.create(
        project=project,
        building=building,
        target_tier=target,
    )
    return project


def complete_building_preparation(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: climb the building's condition tier, exactly once.

    Registered with ``register_kind_handler`` at app-ready time; signature
    matches the framework's ``KindHandler``. Idempotent via the
    ``applied_at`` claim-filter (mirrors ``complete_building_renovation``).
    A lapsed, underfunded preparation fizzles — the tier is applied only
    when the threshold was actually met.
    """
    from world.buildings.models import BuildingPreparationDetails  # noqa: PLC0415

    if project.threshold_target is not None and project.current_progress < project.threshold_target:
        logger.info(
            "building preparation %s fizzled: progress %s < threshold %s.",
            project.pk,
            project.current_progress,
            project.threshold_target,
        )
        return

    with transaction.atomic():
        claimed = BuildingPreparationDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = BuildingPreparationDetails.objects.get(project=project)
        set_condition_tier(details.building, details.target_tier)

    logger.info(
        "building preparation %s applied: building %s now tier %s.",
        project.pk,
        details.building_id,
        details.target_tier,
    )


def set_ultra_upkeep(*, building: Building, enabled: bool) -> None:
    """Toggle the ultra-upkeep premium that holds IMMACULATE past its dwell."""
    if building.ultra_upkeep == enabled:
        return
    building.ultra_upkeep = enabled
    building.save(update_fields=["ultra_upkeep"])
