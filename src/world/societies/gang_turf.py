"""GANG_TURF project kind: ongoing gang territorial pressure graded over a period (#1891).

The first ``TIERED_PERIOD`` kind. A gang org opens a turf project; members
contribute over a period; at the deadline accumulated progress is graded into a
``CheckOutcome`` tier via ``GangTurfTierThreshold`` rows, and the tier applies
a data-driven reputation delta to the owning gang org through the existing
``bump_organization_reputation`` seam.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind
from world.projects.services import resolve_project
from world.societies.models import (
    GangTurfDetails,
    GangTurfReputationAward,
    GangTurfTierThreshold,
)
from world.societies.renown import bump_organization_reputation

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.societies.models import Organization
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


def _select_tier(thresholds, current_progress: int):
    """Return the highest ``min_progress`` row at or below ``current_progress``.

    ``thresholds`` must be ordered by ``-min_progress`` (the model's default).
    Seeded rows always include a ``min_progress=0`` baseline failure tier, so a
    match always exists — this never returns None.

    Args:
        thresholds: iterable of ``GangTurfTierThreshold`` rows, ordered
            by ``-min_progress``.
        current_progress: the project's accumulated progress at deadline.

    Returns:
        The matching ``GangTurfTierThreshold`` row.
    """
    for row in thresholds:
        if row.min_progress <= current_progress:
            return row
    # Unreachable when the baseline min_progress=0 row is seeded; defensive.
    return thresholds[-1]


def _tier_to_reputation_delta(outcome_tier: CheckOutcome) -> int:
    """Return the configured reputation delta for ``outcome_tier``, or 0.

    A missing ``GangTurfReputationAward`` row is a content gap, not a crash —
    aligns with the repo's "prefer try/except for specific expected exceptions"
    guidance. Only called for success tiers (failure tiers no-op in the handler).

    Args:
        outcome_tier: the graded ``CheckOutcome``.

    Returns:
        The configured reputation delta, or 0 if no award row exists.
    """
    try:
        return GangTurfReputationAward.objects.get(outcome_tier=outcome_tier).reputation_delta
    except GangTurfReputationAward.DoesNotExist:
        return 0


def resolve_gang_turf(project: Project) -> None:
    """Grade a RESOLVING GANG_TURF project by progress and finalize it.

    Reads ``GangTurfTierThreshold`` rows, selects the tier reached, and calls
    ``resolve_project`` (which dispatches ``complete_gang_turf`` before setting
    COMPLETED/FAILED). Registered via ``register_tiered_resolver`` and invoked by
    ``scan_active_projects`` in the same tick the project transitions to RESOLVING.
    """
    details = project.gang_turf_details
    thresholds = list(details.tier_thresholds.all())
    tier = _select_tier(thresholds, project.current_progress)
    resolve_project(project, outcome_tier=tier.outcome_tier)


@transaction.atomic
def complete_gang_turf(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """Kind handler: apply the tier's reputation delta to the owning gang org.

    Registered with ``register_kind_handler`` at app-ready; runs from
    ``resolve_project`` before COMPLETED/FAILED is set. A failed outcome
    (``success_level < 0`` or ``None``) grants nothing — no reputation gain.
    """
    if outcome_tier is None or outcome_tier.success_level < 0:
        return
    details = project.gang_turf_details
    delta = _tier_to_reputation_delta(outcome_tier)
    if delta > 0:
        bump_organization_reputation(project.owner_persona, details.organization, delta)


@transaction.atomic
def start_gang_turf_project(
    *,
    organization: Organization,
    owner_persona: Persona,
    target_area: Area | None = None,
    period_days: int = 30,
    tier_thresholds: list[tuple[CheckOutcome, int]] | None = None,
) -> Project:
    """Open a GANG_TURF project for a gang org, gated on a leader-rank member.

    Validates ``owner_persona`` holds an active membership of ``organization``
    whose ``rank.can_lead_rituals`` is True (advances #708). Creates the
    ``Project`` (TIERED_PERIOD, no threshold_target) + ``GangTurfDetails`` +
    seeded ``GangTurfTierThreshold`` rows. Default tier ladder if none supplied.

    Args:
        organization: the gang org exerting pressure.
        owner_persona: must be a leader-rank active member of ``organization``.
        target_area: optional IC-flavor area under pressure (not a control field).
        period_days: real-time span until the grading deadline.
        tier_thresholds: optional ``(CheckOutcome, min_progress)`` ladder; if
            omitted, the canonical default ladder is looked up by name.

    Returns:
        The created ``Project`` (with details + thresholds).

    Raises:
        ValueError: if ``owner_persona`` is not a leader-rank active member.
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.projects.models import Project  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    membership = (
        OrganizationMembership.objects.filter(
            organization=organization,
            persona=owner_persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
        )
        .select_related("rank")
        .first()
    )
    if membership is None or membership.rank is None or not membership.rank.can_lead_rituals:
        msg = "Only leader-rank members of this gang can open turf projects."
        raise ValueError(msg)

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.GANG_TURF,
        completion_mode=CompletionMode.TIERED_PERIOD,
        owner_persona=owner_persona,
        started_at=now,
        time_limit=now + timedelta(days=period_days),
        threshold_target=None,
        description=f"Gang turf pressure by {organization.name}",
    )
    details = GangTurfDetails.objects.create(
        project=project, organization=organization, target_area=target_area
    )
    for outcome_tier, min_progress in tier_thresholds or _default_thresholds():
        GangTurfTierThreshold.objects.create(
            details=details, outcome_tier=outcome_tier, min_progress=min_progress
        )
    return project


def _default_thresholds() -> list[tuple[CheckOutcome, int]]:
    """Canonical default tier ladder, looked up by CheckOutcome natural key.

    The canonical award *deltas* come from the seed migration; the threshold
    *bands* are a per-project default ladder so a caller can omit
    ``tier_thresholds``. Looked up lazily (no import-time DB query). Mirrors the
    cast-seed names (world/magic/seeds_cast.py) and the seed migration.
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
