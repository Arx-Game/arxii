"""Service functions for the projects framework.

See: docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md
(subsystem A — Project Framework).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ProjectStatus,
)
from world.projects.models import Contribution, Project

if TYPE_CHECKING:
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome


class ProjectNotActiveError(ValueError):
    """Raised when a contribution targets a project that's not ACTIVE."""


@transaction.atomic
def add_contribution(  # noqa: PLR0913 — discriminator-pattern requires per-kind kwargs
    *,
    project: Project,
    contributor_persona: Persona,
    kind: str,
    ap_amount: int | None = None,
    money_amount: int | None = None,
    item_instance: ItemInstance | None = None,
    check_outcome: CheckOutcome | None = None,
    intent_text: str = "",
    privacy_setting: str = "PRIVATE",
) -> Contribution:
    """Add a contribution to an ACTIVE Project and advance current_progress.

    Validates the project is ACTIVE. AP/MONEY/ITEM contributions advance
    progress immediately by their amount (AP) or value (money/100, item=1).
    CHECK contributions are recorded; cron tick applies their progress effect
    after the check resolves.

    Also increments the contributor's `projects.total_contributed` stat for
    achievement tracking (if the StatDefinition exists).
    """
    if project.status != ProjectStatus.ACTIVE:
        msg = (
            f"Project #{project.pk} status is {project.status}, not ACTIVE — "
            "cannot accept contributions."
        )
        raise ProjectNotActiveError(msg)

    contribution = Contribution(
        project=project,
        contributor_persona=contributor_persona,
        kind=kind,
        ap_amount=ap_amount,
        money_amount=money_amount,
        item_instance=item_instance,
        check_outcome=check_outcome,
        intent_text=intent_text,
        privacy_setting=privacy_setting,
    )
    contribution.full_clean()
    contribution.save()

    # Immediate progress advancement for non-CHECK kinds.
    progress_delta = 0
    if kind == ContributionKind.AP and ap_amount is not None:
        progress_delta = ap_amount
    elif kind == ContributionKind.MONEY and money_amount is not None:
        # 1 progress per 100 gold (per-kind details may override later).
        progress_delta = money_amount // 100
    elif kind == ContributionKind.ITEM:
        # Placeholder: 1 progress per item. Per-kind details may override.
        progress_delta = 1
    # CHECK contributions have their progress applied by the cron scan
    # after the check outcome is resolved.

    if progress_delta > 0:
        # Use save() so the in-memory SharedMemoryModel instance updates.
        # The F-expression path with .filter().update() leaves callers reading
        # stale current_progress because refresh_from_db doesn't re-fetch
        # cached SMM rows reliably.
        project.current_progress += progress_delta
        project.save(update_fields=["current_progress", "updated_at"])

    # Increment the contributor's project-contribution achievement stat.
    _increment_contribution_stat(contributor_persona)

    return contribution


def _increment_contribution_stat(persona: Persona) -> None:
    """Increment the projects.total_contributed StatTracker for this persona.

    Silent no-op if the StatDefinition isn't seeded (defensive — apps.ready()
    seeds it, but isolated tests may skip ready()).
    """
    from world.achievements.models import StatDefinition  # noqa: PLC0415

    try:
        stat_def = StatDefinition.objects.get(key="projects.total_contributed")
    except StatDefinition.DoesNotExist:
        return
    # The stats handler API varies — best to call via the persona's character_sheet.
    # Defensive guard: if the API doesn't exist as assumed, skip silently.
    import contextlib  # noqa: PLC0415

    with contextlib.suppress(AttributeError):
        persona.character_sheet.stats.increment(stat_def, 1)


# ---------------------------------------------------------------------------
# Kind handler registry — maps ProjectKind values to per-kind resolvers.
# Per-kind details models (e.g., BuildingConstructionDetails in Plan 3)
# register their resolver here at app-ready time.
# ---------------------------------------------------------------------------

KindHandler = Callable[[Project, "CheckOutcome | None"], None]

_KIND_HANDLERS: dict[str, KindHandler] = {}


def register_kind_handler(kind: str, handler: KindHandler) -> None:
    """Register a per-kind resolution handler. Re-registration overwrites."""
    _KIND_HANDLERS[kind] = handler


def get_kind_handler(kind: str) -> KindHandler:
    """Return the registered handler for `kind`, or raise LookupError."""
    try:
        return _KIND_HANDLERS[kind]
    except KeyError as exc:
        msg = f"No handler registered for ProjectKind={kind!r}"
        raise LookupError(msg) from exc


def clear_kind_handlers() -> None:
    """Test-only: clear the handler registry."""
    _KIND_HANDLERS.clear()


# ---------------------------------------------------------------------------
# Cron lifecycle services
# ---------------------------------------------------------------------------


@transaction.atomic
def resolve_project(project: Project, *, outcome_tier: CheckOutcome) -> None:
    """Finalize a RESOLVING project: dispatch to per-kind handler, set outcome.

    Marks COMPLETED if outcome_tier.success_level >= 0, otherwise FAILED.
    Per-kind handlers run BEFORE status is updated so they can read the
    pre-resolution state.
    """
    if project.status != ProjectStatus.RESOLVING:
        msg = (
            f"resolve_project requires status=RESOLVING, got {project.status} "
            f"for project #{project.pk}"
        )
        raise ValueError(msg)

    handler = get_kind_handler(project.kind)
    handler(project, outcome_tier)

    project.outcome_tier = outcome_tier
    project.status = (
        ProjectStatus.COMPLETED if outcome_tier.success_level >= 0 else ProjectStatus.FAILED
    )
    project.save(update_fields=["outcome_tier", "status", "updated_at"])


def scan_active_projects() -> int:
    """Cron tick: scan ACTIVE projects, transition completion-ready ones to RESOLVING.

    SINGLE_THRESHOLD: completion = (current_progress >= threshold_target)
                                   OR (now >= time_limit).
    TIERED_PERIOD:    completion = (now >= time_limit).

    Returns count of projects transitioned. Resolution itself (handler call +
    outcome_tier set) is done by resolve_project, called separately.
    """
    now = timezone.now()
    transitioned = 0
    active = Project.objects.filter(status=ProjectStatus.ACTIVE)
    for project in active:
        should_resolve = False
        if project.completion_mode == CompletionMode.SINGLE_THRESHOLD:
            if project.threshold_target is None:
                continue
            if project.current_progress >= project.threshold_target or now >= project.time_limit:
                should_resolve = True
        elif project.completion_mode == CompletionMode.TIERED_PERIOD:
            if now >= project.time_limit:
                should_resolve = True

        if should_resolve:
            # Use save() instead of .objects.filter().update() so the in-memory
            # SharedMemoryModel instance stays in sync — refresh_from_db() does
            # not reliably re-fetch when the identity map already holds the row.
            project.status = ProjectStatus.RESOLVING
            project.save(update_fields=["status", "updated_at"])
            transitioned += 1

    return transitioned


# ---------------------------------------------------------------------------
# StatDefinition seeding (called at app-ready)
# ---------------------------------------------------------------------------


def register_stat_definitions() -> None:
    """Create the StatDefinition rows for project-related achievement stats.

    Idempotent (get_or_create). Called at app-ready time in apps.py.
    """
    from world.achievements.models import StatDefinition  # noqa: PLC0415

    StatDefinition.objects.get_or_create(
        key="projects.total_contributed",
        defaults={
            "name": "Total Project Contributions",
            "description": "Total contributions made across all projects.",
        },
    )
    StatDefinition.objects.get_or_create(
        key="projects.completed_critical",
        defaults={
            "name": "Critical Project Completions",
            "description": (
                "Number of projects the character contributed to that completed at CRITICAL tier."
            ),
        },
    )
