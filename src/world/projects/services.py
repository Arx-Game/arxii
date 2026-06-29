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
from world.projects.models import Contribution, ContributionMethod, Project

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome


class ProjectNotActiveError(ValueError):
    """Raised when a contribution targets a project that's not ACTIVE."""


@transaction.atomic
def add_contribution(  # noqa: PLR0913
    *,
    project: Project,
    contributor_persona: Persona,
    kind: str,
    ap_amount: int | None = None,
    money_amount: int | None = None,
    item_instance: ItemInstance | None = None,
    check_outcome: CheckOutcome | None = None,
    contribution_method: ContributionMethod | None = None,
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
        contribution_method=contribution_method,
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


def donate_to_project(project: Project, *, donor_persona: Persona, amount: int) -> Contribution:
    """Debit ``amount`` coppers from the donor's purse and record a MONEY contribution.

    Atomic: the spend and the contribution land together, or neither. ``transfer``
    validates funds — a non-positive ``amount`` or an empty purse raises Django's
    ``ValidationError``; an inactive project raises ``ProjectNotActiveError``. The money
    is sunk (the project consumes it); the contribution advances ``current_progress`` at
    one progress per 100 coppers (see ``add_contribution``).
    """
    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

    # Fail fast before debiting: never take the donor's money for a contribution that
    # would then be rejected (add_contribution also guards this).
    if project.status != ProjectStatus.ACTIVE:
        msg = (
            f"Project #{project.pk} status is {project.status}, not ACTIVE — "
            "cannot accept contributions."
        )
        raise ProjectNotActiveError(msg)

    with transaction.atomic():
        purse = get_or_create_purse(donor_persona.character_sheet)
        transfer(amount=amount, reason="project_donation", from_purse=purse)
        contribution = add_contribution(
            project=project,
            contributor_persona=donor_persona,
            kind=ContributionKind.MONEY,
            money_amount=amount,
        )

    # Post-commit: an instant-completion kind (RANSOM) resolves the moment it's
    # fully funded — frees the captive now rather than on the next cron tick.
    maybe_complete_immediately(project)
    return contribution


class ContributionMethodError(ValueError):
    """Raised when a check-based contribution can't proceed (wrong kind, inactive, or AP)."""


def contribute_check_to_project(
    project: Project,
    *,
    actor: ObjectDB,
    contributor_persona: Persona,
    method: ContributionMethod,
) -> Contribution:
    """Make a check-based contribution: spend AP, roll the check, advance on success (#1574).

    The method must belong to the project's ``kind`` and be active. Atomic: spends
    ``method.ap_cost`` AP (raising ``ContributionMethodError`` if unaffordable), rolls
    ``method.check_type``, records the CHECK contribution, and adds
    ``method.progress_on_success`` when the check succeeds (``success_level >= 0``). The AP
    spend rolls back with the contribution if anything downstream fails.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    if project.status != ProjectStatus.ACTIVE:
        msg = f"Project #{project.pk} is not accepting contributions."
        raise ProjectNotActiveError(msg)
    if not method.is_active or method.kind != project.kind:
        msg = "That contribution method isn't available for this project."
        raise ContributionMethodError(msg)

    with transaction.atomic():
        if method.ap_cost > 0:
            pool = ActionPointPool.get_or_create_for_character(actor)
            if not pool.spend(method.ap_cost):
                msg = "You don't have enough action points for that."
                raise ContributionMethodError(msg)

        result = perform_check(actor, method.check_type)
        if result.outcome is None:
            msg = "The check could not be resolved."
            raise ContributionMethodError(msg)

        contribution = add_contribution(
            project=project,
            contributor_persona=contributor_persona,
            kind=ContributionKind.CHECK,
            check_outcome=result.outcome,
            contribution_method=method,
        )
        if result.success_level >= 0:
            project.current_progress += method.progress_on_success
            project.save(update_fields=["current_progress", "updated_at"])

    # Post-commit: instant-completion kinds resolve the moment their threshold is
    # met (no RANSOM check methods today, but keep the seam uniform across paths).
    maybe_complete_immediately(project)
    return contribution


def set_contribution_story(
    project: Project, *, contributor_persona: Persona, text: str
) -> Contribution | None:
    """Attach the narrative of how a contributor helped to their most recent contribution (#1574).

    Sets ``intent_text`` on the persona's latest contribution to ``project``. Returns the
    updated contribution, or ``None`` if they haven't contributed yet.
    """
    contribution = (
        Contribution.objects.filter(project=project, contributor_persona=contributor_persona)
        .order_by("-occurred_at")
        .first()
    )
    if contribution is None:
        return None
    contribution.intent_text = text
    contribution.save(update_fields=["intent_text"])
    return contribution


def _increment_contribution_stat(persona: Persona) -> None:
    """Increment the projects.total_contributed StatTracker for this persona.

    Lazily creates the StatDefinition row if it does not exist yet, matching the
    pattern used by combat achievement counters. No import-time / app-ready DB
    queries are performed here.
    """
    from world.achievements.models import StatDefinition  # noqa: PLC0415

    stat_def, _ = StatDefinition.objects.get_or_create(
        key="projects.total_contributed",
        defaults={
            "name": "Total Project Contributions",
            "description": "Total contributions made across all projects.",
        },
    )
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
# Instant-completion kinds (#1500)
# ---------------------------------------------------------------------------
# Most kinds resolve on a cron tick (scan_active_projects -> RESOLVING -> a
# generic resolver). A few — RANSOM — must resolve the *instant* their
# threshold is funded: a ransom that's fully paid frees the captive now, not on
# the next 15-minute tick. A kind registered here is checked after every
# progress-advancing contribution; when it crosses its SINGLE_THRESHOLD it runs
# its kind handler immediately and is marked COMPLETED. The handler gets
# ``outcome_tier=None`` (a funded threshold *is* the success — there is no
# check roll to tier).

_INSTANT_COMPLETION_KINDS: set[str] = set()


def register_instant_completion_kind(kind: str) -> None:
    """Mark a ProjectKind as completing immediately on threshold (re-register safe)."""
    _INSTANT_COMPLETION_KINDS.add(kind)


def clear_instant_completion_kinds() -> None:
    """Test-only: clear the instant-completion registry."""
    _INSTANT_COMPLETION_KINDS.clear()


def maybe_complete_immediately(project: Project) -> bool:
    """Resolve an instant-completion project the moment its threshold is funded (#1500).

    A no-op unless ``project.kind`` is registered via
    :func:`register_instant_completion_kind`, the project is still ACTIVE, and its
    SINGLE_THRESHOLD progress has reached ``threshold_target``. When all hold, runs
    the kind handler (``outcome_tier=None``) and marks the project COMPLETED. Returns
    ``True`` if it completed the project. Call this **after** the contribution's
    transaction commits — the handler may have heavy side effects (the RANSOM handler
    relocates the freed captive and tears down their cell).
    """
    if project.kind not in _INSTANT_COMPLETION_KINDS:
        return False
    if project.status != ProjectStatus.ACTIVE:
        return False
    if project.completion_mode != CompletionMode.SINGLE_THRESHOLD:
        return False
    if project.threshold_target is None or project.current_progress < project.threshold_target:
        return False

    get_kind_handler(project.kind)(project, None)
    project.status = ProjectStatus.COMPLETED
    project.save(update_fields=["status", "updated_at"])
    return True


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


def _project_is_completion_ready(project: Project, now: datetime) -> bool:
    """Return True if an ACTIVE project meets its completion condition.

    SINGLE_THRESHOLD: completion = (current_progress >= threshold_target)
                                   OR (now >= time_limit).
    TIERED_PERIOD:    completion = (now >= time_limit).
    """
    if project.completion_mode == CompletionMode.SINGLE_THRESHOLD:
        if project.threshold_target is None:
            return False
        return project.current_progress >= project.threshold_target or now >= project.time_limit
    if project.completion_mode == CompletionMode.TIERED_PERIOD:
        return now >= project.time_limit
    return False


def scan_active_projects() -> int:
    """Cron tick: scan ACTIVE projects, transition completion-ready ones to RESOLVING.

    Returns count of projects transitioned. Resolution itself (handler call +
    outcome_tier set) is done by resolve_project, called separately.
    """
    now = timezone.now()
    transitioned = 0
    active = Project.objects.filter(status=ProjectStatus.ACTIVE)
    for project in active:
        if not _project_is_completion_ready(project, now):
            continue
        # Use save() instead of .objects.filter().update() so the in-memory
        # SharedMemoryModel instance stays in sync — refresh_from_db() does
        # not reliably re-fetch when the identity map already holds the row.
        project.status = ProjectStatus.RESOLVING
        project.save(update_fields=["status", "updated_at"])
        transitioned += 1

    return transitioned
