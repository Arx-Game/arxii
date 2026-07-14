"""RESEARCH project kind (#1146) — collaborative investigation toward a clue's target.

Plugs the Investigation & Discovery clue (#1144) into the projects framework as a new
``ProjectKind``: players set up a research project targeting a clue, contributors spend
AP to make Research rolls that add (floored) progress, a weekly cron can deal bad-luck
setbacks (never below zero), and on success the clue's target is granted to everyone who
helped. Magnitudes (progress per tier, setback severity, thresholds, the bad-luck odds)
are placeholder data deferred to a later author pass per #1143.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from world.clues.constants import ClueTargetKind
from world.clues.models import ResearchProjectDetails
from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ProjectKind,
    ProjectStatus,
)
from world.projects.models import Project
from world.projects.services import add_contribution

if TYPE_CHECKING:
    from world.clues.models import Clue
    from world.roster.models import RosterEntry
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome

# Placeholder magnitudes — tuned in a later author pass (#1143).
_DEFAULT_THRESHOLD = 10
_DEFAULT_DURATION = timedelta(days=30)


def start_research_project(
    clue: Clue,
    owner_persona: Persona,
    *,
    threshold_target: int = _DEFAULT_THRESHOLD,
    duration: timedelta | None = None,
) -> Project:
    """Set up a collaborative research project targeting ``clue`` (status ACTIVE)."""
    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.RESEARCH,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        status=ProjectStatus.ACTIVE,
        owner_persona=owner_persona,
        started_at=now,
        time_limit=now + (duration or _DEFAULT_DURATION),
        threshold_target=threshold_target,
    )
    ResearchProjectDetails.objects.create(project=project, clue=clue)
    return project


def contribute_research(
    project: Project,
    contributor_persona: Persona,
    check_outcome: CheckOutcome,
    *,
    intent_text: str = "",
) -> int:
    """Record a contributor's Research roll and add its (floored) progress.

    The contribution *is* the check — AP is its cost, charged by the caller before this.
    A successful roll adds progress scaled by the outcome; a failed roll adds nothing and
    **never** detracts (floored at 0), so helping is always weakly positive and no one is
    punished for being let in to help. Returns the progress added.
    """
    add_contribution(
        project=project,
        contributor_persona=contributor_persona,
        kind=ContributionKind.CHECK,
        check_outcome=check_outcome,
        intent_text=intent_text,
    )
    delta = max(0, check_outcome.success_level)  # placeholder mapping; floored at 0
    if delta > 0:
        project.current_progress += delta
        project.save(update_fields=["current_progress", "updated_at"])
    return delta


def apply_research_setback(project: Project, amount: int) -> int:
    """Shave research progress by a bad-luck setback, floored at 0.

    Returns the amount actually removed (0 if already at the floor). This is the *only*
    source of negative progress — contributor rolls never detract (see
    :func:`contribute_research`).
    """
    removed = min(amount, project.current_progress)
    if removed > 0:
        project.current_progress -= removed
        project.save(update_fields=["current_progress", "updated_at"])
    return removed


def apply_research_setbacks(amount: int = 1) -> int:
    """Weekly cron sweep: deal a bad-luck setback to ACTIVE research projects.

    Returns the number of projects actually set back. WHICH projects get hit (the
    bad-luck roll) and HOW MUCH are placeholder magnitudes deferred to a later pass
    (#1143); for now every active research project takes a small placeholder setback.
    """
    count = 0
    active = Project.objects.filter(kind=ProjectKind.RESEARCH, status=ProjectStatus.ACTIVE)
    for project in active:
        if apply_research_setback(project, amount) > 0:
            count += 1
    return count


@transaction.atomic
def resolve_research(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """RESEARCH kind handler (#1146): grant the clue's target to contributors on success.

    Registered with the projects framework at app-ready; runs from ``resolve_project``
    *before* the COMPLETED/FAILED status is set. A failed outcome grants nothing. On
    success every distinct contributor learns the clue's target. CODEX targets are wired
    now (the contributors learn the entry, firing the codex KNOWN reactivity); other
    target kinds (mission/secret) are a documented extension point.
    """
    if outcome_tier is None or outcome_tier.success_level < 0:
        return
    clue = project.research_details.clue
    if clue.target_kind == ClueTargetKind.SECRET:
        _resolve_secret_research(project, clue)
        return
    if clue.target_kind != ClueTargetKind.CODEX:
        return  # mission target grants — extension point (#1143)
    entry = clue.target_codex_entry
    if entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    for roster_entry in _distinct_contributor_roster_entries(project):
        knowledge, _ = CharacterCodexKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            entry=entry,
            defaults={"status": CodexKnowledgeStatus.UNCOVERED},
        )
        # Push past the threshold so the entry lands KNOWN (and fires the stories hook).
        knowledge.add_progress(entry.learn_threshold)


def _resolve_secret_research(project: Project, clue: Clue) -> None:
    """SECRET-target research payoff (#1825): grant the fact; nullify a proven frame.

    Every contributor learns the secret. When the secret is an ACCUSATION, completing
    the investigation is the proof of fabrication — fire the justice-side nullification
    (compensating reputation, heat zeroed, claim retracted, the author-unmask trail).
    """
    from world.secrets.constants import SecretProvenance  # noqa: PLC0415
    from world.secrets.services import grant_secret_knowledge  # noqa: PLC0415

    secret = clue.target_secret
    if secret is None:
        return
    for roster_entry in _distinct_contributor_roster_entries(project):
        grant_secret_knowledge(roster_entry=roster_entry, secret=secret)
    if secret.provenance == SecretProvenance.ACCUSATION:
        from world.justice.nullification import nullify_accusation  # noqa: PLC0415

        nullify_accusation(secret)


def _distinct_contributor_roster_entries(project: Project) -> list[RosterEntry]:
    """The roster entries of everyone who contributed (distinct, order-preserved).

    Skips personas with no character sheet or no roster entry (off-roster contributors).
    """
    seen: set[int] = set()
    result: list[RosterEntry] = []
    contributions = project.contributions.select_related(
        "contributor_persona__character_sheet__roster_entry"
    )
    for contribution in contributions:
        sheet = contribution.contributor_persona.character_sheet
        if sheet is None:
            continue
        try:
            roster_entry = sheet.roster_entry
        except ObjectDoesNotExist:
            continue
        if roster_entry.pk not in seen:
            seen.add(roster_entry.pk)
            result.append(roster_entry)
    return result
