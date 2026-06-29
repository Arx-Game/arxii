"""Ransom-as-Project: the crowdfundable demand standing in the cell (#1500).

The Arx 1 ransom was a private debt between two orgs, paid from one treasury.
Arx 2 reframes it as a **Project on the ground in the captive's cell**: a GM
demands a sum, which raises a ``RANSOM`` :class:`~world.projects.models.Project`
linked to the captivity. *Anyone* — family, friends, a rival who wants leverage,
a stranger moved by the story — may ``project/donate`` toward it (the same
contribution surface every project uses, #1574). The instant the threshold is
funded the captive is freed and sent home; no one waits on a cron tick.

This module owns the two ends of that loop: ``demand_ransom_project`` (the GM
surface creates the Project) and ``resolve_ransom_project`` (the projects
framework's kind handler frees the captive on completion). Payment itself needs
no code here — it rides ``world.projects.services.donate_to_project`` and the
instant-completion seam (``register_instant_completion_kind``).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import AlreadyDemandedError, NotHeldError
from world.captivity.ransom import default_ransom_amount
from world.captivity.services import resolve_captivity
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.models import Project

if TYPE_CHECKING:
    from world.captivity.models import Captivity

# A ransom doesn't lapse on a timer — it stands until paid or the captivity ends
# another way. Project.time_limit is required, so we set it far out; the generic
# cron resolver never fires for RANSOM (it's instant-completion only). PLACEHOLDER
# window — a future "the captor loses patience" escalation may shorten it.
_RANSOM_PROJECT_WINDOW = timedelta(days=3650)

# Money advances project progress at one unit per 100 coppers (see
# projects.services.add_contribution), so a demand of N coppers needs N // 100
# progress to clear. At least 1 so a tiny demand is still fundable.
_COPPERS_PER_PROGRESS = 100


def demand_ransom_project(
    captivity: Captivity,
    *,
    amount: int | None = None,
) -> Project:
    """Raise a crowdfundable RANSOM Project for a held captive (#1500).

    Creates an ACTIVE, SINGLE_THRESHOLD ``RANSOM`` project whose threshold is the
    demanded sum (``amount`` coppers, defaulting to ``default_ransom_amount``) and
    links it onto ``captivity.ransom_project``. The captive's primary persona owns
    the project (the framework requires an owner; for a ransom it is simply the
    person the project is *about*). Anyone may then donate toward it.

    Raises ``NotHeldError`` if the captivity is already over, or
    ``AlreadyDemandedError`` if an unfunded RANSOM project is already standing.
    """
    if captivity.status != CaptivityStatus.HELD:
        raise NotHeldError
    existing = captivity.ransom_project
    if existing is not None and existing.status == ProjectStatus.ACTIVE:
        raise AlreadyDemandedError

    value = amount if amount is not None else default_ransom_amount(captivity.captive)
    threshold = max(1, value // _COPPERS_PER_PROGRESS)
    now = timezone.now()
    captive_name = captivity.captive.character.key

    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.RANSOM,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            owner_persona=captivity.captive.primary_persona,
            started_at=now,
            time_limit=now + _RANSOM_PROJECT_WINDOW,
            threshold_target=threshold,
            # PLACEHOLDER player-facing prose — rewrite in the deployment's voice.
            description=(
                f"PLACEHOLDER: A ransom of {value} coppers is demanded for the safe "
                f"return of {captive_name}. Contribute to see them freed."
            ),
        )
        captivity.ransom_project = project
        captivity.save(update_fields=["ransom_project"])
    return project


def resolve_ransom_project(project: Project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Free the captive when their RANSOM project is funded — the kind handler (#1500).

    Registered with ``world.projects.services.register_kind_handler`` at app-ready
    time and fired by ``maybe_complete_immediately`` the instant the threshold is
    met. Resolves the linked captivity as ``RANSOMED`` (which relocates the captive
    home and tears down the cell). Idempotent: a no-op if no held captivity points
    at this project, so a double-fire is harmless. ``outcome_tier`` is unused — a
    funded ransom has no check roll to tier.
    """
    from world.captivity.models import Captivity  # noqa: PLC0415

    captivity = Captivity.objects.filter(ransom_project=project).first()
    if captivity is None or captivity.status != CaptivityStatus.HELD:
        return
    resolve_captivity(captivity, status=CaptivityStatus.RANSOMED)
