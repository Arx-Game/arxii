"""WAR_FUNDING project kind: covenant war-preparation drive graded at deadline.

A ``TIERED_PERIOD`` kind mirroring CITY_DEFENSE. A covenant leader opens a
war-funding project; members contribute during the preparation window; at the
deadline accumulated progress is graded into a ``CheckOutcome`` tier via
``WarFundingTierThreshold`` rows, and the handler stores the tier on
``WarFundingDetails`` and updates ``CovenantMilitaryReadiness``. When units are
mustered into a battle for that covenant, ``get_war_funding_bonus`` returns the
combined bonus (per-tier + readiness-gated quality steps) for ``add_unit``.

Decoupled from the battle lifecycle: the project grades at its deadline
regardless of whether a battle exists yet. ``get_war_funding_bonus`` is the
read seam — called by ``add_unit`` when the battle side has a covenant.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind
from world.projects.services import resolve_project

if TYPE_CHECKING:
    from world.covenants.models import Covenant
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

# UnitQuality ordering for step-based upgrades (index = rank, higher = better).
_QUALITY_ORDER = [
    "militia",
    "levy",
    "trained",
    "veteran",
    "elite",
]


@dataclass
class WarFundingBonus:
    """Combined war-preparation bonuses for a covenant's mustered units."""

    quality_steps: int = 0
    strength_bonus: int = 0
    morale_bonus: int = 0
    bonus_units: int = 0


def _select_tier(thresholds, current_progress: int):
    """Return the highest ``min_progress`` row at or below ``current_progress``.

    ``thresholds`` must be ordered by ``-min_progress`` (the model's default).
    Seeded rows always include a ``min_progress=0`` baseline failure tier, so a
    match always exists — this never returns None.

    Args:
        thresholds: iterable of ``WarFundingTierThreshold`` rows, ordered
            by ``-min_progress``.
        current_progress: the project's accumulated progress at deadline.

    Returns:
        The matching ``WarFundingTierThreshold`` row.
    """
    for row in thresholds:
        if row.min_progress <= current_progress:
            return row
    # Unreachable when the baseline min_progress=0 row is present; defensive.
    return thresholds[-1]


def _apply_quality_steps(base_quality: str, steps: int) -> str:
    """Walk the UnitQuality ordering up by ``steps``, clamping at ELITE.

    Args:
        base_quality: A ``UnitQuality`` value string (e.g. ``"trained"``).
        steps: Number of quality levels to upgrade (0 = no change).

    Returns:
        The upgraded quality string, clamped at ``"elite"``.
    """
    if steps <= 0:
        return base_quality
    try:
        idx = _QUALITY_ORDER.index(base_quality)
    except ValueError:
        return base_quality
    new_idx = min(idx + steps, len(_QUALITY_ORDER) - 1)
    return _QUALITY_ORDER[new_idx]


def resolve_war_funding(project: Project) -> None:
    """Grade a RESOLVING WAR_FUNDING project by progress and finalize it.

    Reads ``WarFundingTierThreshold`` rows, selects the tier reached, and calls
    ``resolve_project`` (which dispatches ``complete_war_funding`` before
    setting COMPLETED/FAILED). Registered via ``register_tiered_resolver`` and
    invoked by ``scan_active_projects`` in the same tick the project transitions
    to RESOLVING.
    """
    details = project.war_funding_details
    thresholds = list(details.tier_thresholds.all())
    tier = _select_tier(thresholds, project.current_progress)
    resolve_project(project, outcome_tier=tier.outcome_tier)


@transaction.atomic
def complete_war_funding(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """Kind handler: store the tier on details and update readiness, once each.

    Registered with ``register_kind_handler`` at app-ready; runs from
    ``resolve_project`` before COMPLETED/FAILED is set. A failed outcome
    (``success_level < 0`` or ``None``) grants nothing.

    Idempotent tier-storage via DB-level claim-filter (same pattern as
    ``complete_city_defense``): a second call sees the non-null ``applied_at``
    and no-ops. Uses ``get_or_create`` on ``CovenantMilitaryReadiness`` so it's
    robust if the record was deleted or the project was created outside
    ``start_war_funding_project``.
    """
    from world.battles.models import (  # noqa: PLC0415
        CovenantMilitaryReadiness,
        WarFundingDetails,
        WarFundingTierBonus,
    )

    if outcome_tier is None or outcome_tier.success_level < 0:
        return

    # The claim filter hits the DB, so a second call sees the non-null
    # applied_at and no-ops even though the cached instance is stale.
    claimed = WarFundingDetails.objects.filter(project=project, applied_at__isnull=True).update(
        applied_at=timezone.now()
    )
    if not claimed:
        return

    details = WarFundingDetails.objects.get(project=project)
    details.outcome_tier = outcome_tier
    details.save(update_fields=["outcome_tier"])

    # Look up training_xp; missing row = 0 (content gap, not crash — same
    # try/except pattern as gang_turf._tier_to_reputation_delta).
    try:
        bonus = WarFundingTierBonus.objects.get(outcome_tier=outcome_tier)
        training_xp = bonus.training_xp
    except WarFundingTierBonus.DoesNotExist:
        training_xp = 0

    if training_xp > 0:
        readiness, _ = CovenantMilitaryReadiness.objects.get_or_create(covenant=details.covenant)
        readiness.training_level += training_xp
        readiness.save(update_fields=["training_level"])


def get_war_funding_bonus(covenant: Covenant) -> WarFundingBonus:
    """Return combined war-preparation bonuses for a covenant's mustered units.

    Combines:
    1. The most recent completed WAR_FUNDING project's ``WarFundingTierBonus``
       values (quality_steps, strength_bonus, morale_bonus).
    2. The covenant's ``CovenantMilitaryReadiness`` threshold-gated bonus
       quality steps (looks up the highest ``ReadinessThreshold`` row where
       ``min_training_level <= readiness.training_level``).

    Returns zeros if no project exists, no tier is stored, no award row exists,
    or no readiness record exists — all content gaps, not crashes (same
    try/except pattern as ``get_city_defense_integrity_bonus`` and
    ``gang_turf._tier_to_reputation_delta``).

    Args:
        covenant: The covenant to check for completed war-funding bonuses.

    Returns:
        A ``WarFundingBonus`` dataclass with combined bonuses.
    """
    from world.battles.models import (  # noqa: PLC0415
        CovenantMilitaryReadiness,
        ReadinessThreshold,
        WarFundingDetails,
        WarFundingTierBonus,
    )

    bonus = WarFundingBonus()

    # 1. Most recent completed WAR_FUNDING project's tier bonus.
    details = (
        WarFundingDetails.objects.filter(covenant=covenant, applied_at__isnull=False)
        .select_related("outcome_tier")
        .order_by("-applied_at")
        .first()
    )
    if details is not None and details.outcome_tier_id is not None:
        try:
            tier_bonus = WarFundingTierBonus.objects.get(outcome_tier=details.outcome_tier)
            bonus.quality_steps += tier_bonus.quality_steps
            bonus.strength_bonus += tier_bonus.strength_bonus
            bonus.morale_bonus += tier_bonus.morale_bonus
            bonus.bonus_units += tier_bonus.bonus_units
        except WarFundingTierBonus.DoesNotExist:
            pass

    # 2. Readiness-threshold-gated bonus quality steps.
    try:
        readiness = CovenantMilitaryReadiness.objects.get(covenant=covenant)
    except CovenantMilitaryReadiness.DoesNotExist:
        return bonus

    threshold = (
        ReadinessThreshold.objects.filter(min_training_level__lte=readiness.training_level)
        .order_by("-min_training_level")
        .first()
    )
    if threshold is not None:
        bonus.quality_steps += threshold.bonus_quality_steps

    return bonus


@transaction.atomic
def start_war_funding_project(
    *,
    covenant: Covenant,
    owner_persona: Persona,
    period_days: int = 30,
    tier_thresholds: list[tuple[CheckOutcome, int]] | None = None,
) -> Project:
    """Open a WAR_FUNDING project for a covenant, gated on a leader-rank member.

    Validates ``owner_persona`` holds an active, engaged membership in
    ``covenant`` whose ``rank.can_lead_rituals`` is True (mirrors the battle
    system's command-hierarchy check at ``battles/services.py``). Creates the
    ``Project`` (TIERED_PERIOD, no threshold_target) + ``WarFundingDetails`` +
    seeded ``WarFundingTierThreshold`` rows. Bootstraps
    ``CovenantMilitaryReadiness`` if absent.

    Args:
        covenant: the covenant opening the war-funding drive.
        owner_persona: must be a leader-rank active, engaged member of
            ``covenant``.
        period_days: real-time span until the grading deadline.
        tier_thresholds: optional ``(CheckOutcome, min_progress)`` ladder; if
            omitted, the canonical default ladder is looked up by name.

    Returns:
        The created ``Project`` (with details + thresholds).

    Raises:
        ValueError: if ``owner_persona`` is not a leader-rank active, engaged
            member of ``covenant``.
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.battles.models import (  # noqa: PLC0415
        CovenantMilitaryReadiness,
        WarFundingDetails,
        WarFundingTierThreshold,
    )
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415
    from world.projects.constants import ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    membership = (
        CharacterCovenantRole.objects.filter(
            character_sheet=owner_persona.character_sheet,
            covenant=covenant,
            engaged=True,
            left_at__isnull=True,
        )
        .select_related("rank")
        .first()
    )
    if membership is None or membership.rank is None or not membership.rank.can_lead_rituals:
        msg = "Only leader-rank members of this covenant can open war-funding projects."
        raise ValueError(msg)

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.WAR_FUNDING,
        completion_mode=CompletionMode.TIERED_PERIOD,
        status=ProjectStatus.ACTIVE,
        owner_persona=owner_persona,
        started_at=now,
        time_limit=now + timedelta(days=period_days),
        threshold_target=None,
        description=f"War funding for {covenant.name}",
    )
    details = WarFundingDetails.objects.create(project=project, covenant=covenant)
    for outcome_tier, min_progress in tier_thresholds or _default_thresholds():
        WarFundingTierThreshold.objects.create(
            details=details, outcome_tier=outcome_tier, min_progress=min_progress
        )
    CovenantMilitaryReadiness.objects.get_or_create(covenant=covenant)
    return project


def _default_thresholds() -> list[tuple[CheckOutcome, int]]:
    """Canonical default tier ladder, looked up by CheckOutcome natural key.

    The canonical *bonuses* come from staff-authored ``WarFundingTierBonus``
    rows; the threshold *bands* are a per-project default ladder so a caller
    can omit ``tier_thresholds``. Looked up lazily (no import-time DB query).
    Mirrors the cast-seed names and the seed migration.
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
