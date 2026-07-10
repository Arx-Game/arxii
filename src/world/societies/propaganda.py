"""Propaganda campaigns — the money→prestige project kind (#1621).

The only sanctioned way a project yields fame: fund a PROPAGANDA project to its
threshold and ``resolve_propaganda_project`` fires ``fire_renown_award`` for the
sponsor (``Project.owner_persona``) with the campaign's authored config. Every
other kind stays renown-free (the #1574 resolution — fame is for deeds, and
per-contribution renown would both be grindable and leak private activity).

Ownership mirrors how ``world.captivity`` owns RANSOM: kind constant in
projects, details model + handler + registration here in societies, instant
completion via the #1500 seam. Donations are a sink — an under-funded campaign
that hits its deadline resolves with **no award and no refunds**.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.models import Project
from world.societies.models import PropagandaCampaignTier, PropagandaDetails
from world.societies.renown import fire_renown_award

if TYPE_CHECKING:
    from world.checks.constants import CheckOutcome
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)

# PLACEHOLDER campaign window pending tuning; the deadline only bounds how long
# an under-funded campaign lingers (funding to threshold completes instantly).
_CAMPAIGN_WINDOW = timedelta(days=30)

_COPPERS_PER_PROGRESS = 100  # donate_to_project's exchange rate (projects/services.py)


class PropagandaError(Exception):
    """Base for propaganda-campaign failures; carries a user_message."""

    user_message = "Could not launch that campaign."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class InactiveCampaignTierError(PropagandaError):
    """The chosen campaign tier is not active."""

    user_message = "That campaign scale is not currently offered."


def launch_propaganda_campaign(
    *,
    owner_persona: Persona,
    tier: PropagandaCampaignTier,
    campaign_name: str,
    description: str = "",
) -> Project:
    """Create an ACTIVE PROPAGANDA project + its details copied from ``tier``.

    The tier's renown config is snapshotted onto the campaign's
    ``PropagandaDetails`` so later tier edits never mutate live campaigns.
    Anyone may then fund it via the ordinary ``project/donate`` surface.
    """
    if not tier.is_active:
        raise InactiveCampaignTierError
    now = timezone.now()
    threshold = max(1, tier.threshold_coppers // _COPPERS_PER_PROGRESS)
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.PROPAGANDA,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            owner_persona=owner_persona,
            started_at=now,
            time_limit=now + _CAMPAIGN_WINDOW,
            threshold_target=threshold,
            description=description
            or (
                # PLACEHOLDER player-facing prose — rewrite in the deployment's voice.
                f"PLACEHOLDER: {campaign_name} — a propaganda campaign singing the "
                f"praises of {owner_persona.name}. Coin fuels the crier's voice."
            ),
        )
        details = PropagandaDetails.objects.create(
            project=project,
            campaign_name=campaign_name,
            source_tier=tier,
            magnitude=tier.magnitude,
            risk=tier.risk,
            reach=tier.reach,
        )
        details.archetypes.set(tier.archetypes.all())
    return project


def resolve_propaganda_project(project: Project, outcome_tier: CheckOutcome | None) -> None:  # noqa: ARG001 — KindHandler signature
    """PROPAGANDA kind handler: fire the sponsor's renown award, exactly once.

    Fires only when the threshold was actually reached — a deadline resolution
    of an under-funded campaign awards nothing (and refunds nothing; the sink
    keeps what it swallowed). ``renown_fired`` guards re-fires.
    """
    details = PropagandaDetails.objects.filter(project=project).first()
    if details is None:
        logger.warning("PROPAGANDA project %s has no PropagandaDetails; no award.", project.pk)
        return
    if details.renown_fired:
        return
    if project.threshold_target is None or project.current_progress < project.threshold_target:
        logger.info(
            "PROPAGANDA project %s resolved under-funded (%s/%s); no award.",
            project.pk,
            project.current_progress,
            project.threshold_target,
        )
        return
    fire_renown_award(
        persona=project.owner_persona,
        title=details.campaign_name,
        **details.as_renown_award_kwargs(),
    )
    details.renown_fired = True
    details.save(update_fields=["renown_fired"])
