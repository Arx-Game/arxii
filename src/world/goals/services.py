"""
Goals Service Functions

Service layer for goal bonus calculations with percentage modifiers.
"""

from typing import TYPE_CHECKING

from world.goals.models import CharacterGoal
from world.goals.types import GoalBonusBreakdown
from world.mechanics.constants import (
    GOAL_CATEGORY_NAME,
    GOAL_PERCENT_CATEGORY_NAME,
    GOAL_POINTS_CATEGORY_NAME,
)
from world.mechanics.models import CharacterModifier, ModifierTarget

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.goals.models import GoalJournal
    from world.goals.types import GoalInputData

# Base goal points available to distribute at character creation
DEFAULT_GOAL_POINTS = 30

# Maximum total points a character can allocate across all goals
MAX_GOAL_POINTS = 30


def get_goal_bonus(
    character: "CharacterSheet",
    domain: "ModifierTarget",
) -> int:
    """
    Get the goal bonus for a specific domain, applying percentage modifiers.

    Base bonus = CharacterGoal.points for that domain.
    Final bonus = base * (1 + percentage_modifiers/100).

    Percentage modifiers come from:
    - goal_percent/all: applies to all goal bonuses
    - goal_percent/<domain>: applies to specific domain only

    Args:
        character: CharacterSheet instance
        domain: ModifierTarget instance for the goal domain

    Returns:
        Final goal bonus as integer (truncated)
    """
    # Get base goal points for this domain
    try:
        goal = CharacterGoal.objects.get(
            character=character,
            domain=domain,
        )
        base_points = goal.points
    except CharacterGoal.DoesNotExist:
        base_points = 0

    if base_points == 0:
        return 0

    # Get percentage modifiers
    total_percent = _get_goal_percent_modifier(character, domain)

    # Apply percentage: final = base * (1 + percent/100)
    multiplier = 1 + (total_percent / 100)
    return int(base_points * multiplier)


def _get_goal_percent_modifier(
    character: "CharacterSheet",
    domain: "ModifierTarget",
) -> int:
    """
    Get total percentage modifier for a goal domain.

    Combines:
    - goal_percent/all modifiers (apply to all goals)
    - goal_percent/<domain_name> modifiers (domain-specific)

    Args:
        character: CharacterSheet instance
        domain: ModifierTarget instance for the goal domain

    Returns:
        Total percentage modifier (e.g., 150 means +150%)
    """
    total_percent = 0

    # Get "all" goal percent modifier
    all_modifiers = CharacterModifier.objects.filter(
        character=character,
        target__category__name=GOAL_PERCENT_CATEGORY_NAME,
        target__name="all",
    )
    total_percent += sum(m.value for m in all_modifiers)

    # Get domain-specific percent modifier (iexact because domain names are
    # capitalized e.g. "Needs" while percent modifier targets are lowercase)
    domain_modifiers = CharacterModifier.objects.filter(
        character=character,
        target__category__name=GOAL_PERCENT_CATEGORY_NAME,
        target__name__iexact=domain.name,
    )
    total_percent += sum(m.value for m in domain_modifiers)

    return total_percent


def get_total_goal_points(character: "CharacterSheet") -> int:
    """
    Get the total goal points available for a character to distribute.

    Base is DEFAULT_GOAL_POINTS (30), plus any goal_points/total_points
    modifiers from distinctions.

    Args:
        character: CharacterSheet instance

    Returns:
        Total goal points available (base + modifiers)
    """
    base_points = DEFAULT_GOAL_POINTS

    # Get goal_points/total_points modifiers
    bonus_modifiers = CharacterModifier.objects.filter(
        character=character,
        target__category__name=GOAL_POINTS_CATEGORY_NAME,
        target__name="total_points",
    )
    bonus = sum(m.value for m in bonus_modifiers)

    return base_points + bonus


def set_character_goals(
    *,
    character: "CharacterSheet",
    goals: list["GoalInputData"],
) -> list[CharacterGoal]:
    """Replace a character's goal allocations, enforcing the weekly revision limit.

    Validates total points (<= MAX_GOAL_POINTS) and rejects duplicate domains.
    First-time setup (no existing goals) skips the revision gate. Mirrors the
    former inline ``CharacterGoalViewSet.update_all`` logic; raises ``GoalError``
    on revision-too-soon / over-cap / duplicate-domain.

    Args:
        character: The character sheet whose goals are being set.
        goals: Validated goal allocations — each a ``GoalInputData`` dict
            with ``domain`` (ModifierTarget pk or instance), ``points``, ``notes``.

    Returns:
        The new ``CharacterGoal`` rows (re-fetch with domain prefetched).
    """
    from django.db import transaction  # noqa: PLC0415

    from world.goals.models import GoalRevision  # noqa: PLC0415
    from world.goals.types import GoalError  # noqa: PLC0415

    revision, _created = GoalRevision.objects.get_or_create(character=character)
    has_existing_goals = CharacterGoal.objects.filter(character=character).exists()

    if has_existing_goals and not revision.can_revise():
        raise GoalError(GoalError.REVISION_TOO_SOON)

    # Resolve domains + validate cap/duplicates in one pass.
    resolved: list[tuple[ModifierTarget, int, str]] = []
    total_points = 0
    seen_domain_ids: set[int] = set()
    for goal_data in goals:
        domain = goal_data["domain"]
        if isinstance(domain, int):
            domain = ModifierTarget.objects.get(pk=domain)
        if domain.pk in seen_domain_ids:
            raise GoalError(GoalError.DUPLICATE_DOMAIN)
        seen_domain_ids.add(domain.pk)
        points = goal_data.get("points", 0)
        notes = goal_data.get("notes", "")
        if points > 0 or notes:
            resolved.append((domain, points, notes))
        total_points += points

    if total_points > MAX_GOAL_POINTS:
        raise GoalError(GoalError.OVER_POINT_CAP)

    with transaction.atomic():
        CharacterGoal.objects.filter(character=character).delete()
        for domain, points, notes in resolved:
            CharacterGoal.objects.create(
                character=character,
                domain=domain,
                points=points,
                notes=notes,
            )
        if has_existing_goals:
            revision.mark_revised()

    return list(CharacterGoal.objects.filter(character=character).select_related("domain"))


def log_goal_progress(
    *,
    character: "CharacterSheet",
    domain: "ModifierTarget | None",
    title: str,
    content: str,
    is_public: bool = False,
) -> "GoalJournal":
    """Create a goal-progress journal entry (records 1 XP on the row).

    Records ``xp_awarded=1`` on the ``GoalJournal`` row; actually granting the
    XP to the character's account is a pre-existing TODO (the former inline
    ``GoalJournalCreateSerializer.create`` had the same gap). Mirrors the
    former inline ``GoalJournalViewSet.create``. ``domain`` may be ``None`` for
    unattributed reflections.
    """
    from world.goals.models import GoalJournal  # noqa: PLC0415

    return GoalJournal.objects.create(
        character=character,
        domain=domain,
        title=title,
        content=content,
        is_public=is_public,
        xp_awarded=1,
    )


def get_goal_bonuses_breakdown(
    character: "CharacterSheet",
) -> dict[str, GoalBonusBreakdown]:
    """
    Get breakdown of all goal bonuses for a character.

    Returns:
        Dict mapping domain name to:
        - base_points: Raw points allocated
        - percent_modifier: Total percentage modifier
        - final_bonus: Calculated bonus after percentage
    """
    # Get all goal domains
    goal_domains = ModifierTarget.objects.filter(
        category__name=GOAL_CATEGORY_NAME,
        is_active=True,
    )

    # Prefetch all character goals in one query
    character_goals = CharacterGoal.objects.filter(
        character=character,
        domain__category__name=GOAL_CATEGORY_NAME,
    ).select_related("domain")
    goals_by_domain = {goal.domain.name: goal.points for goal in character_goals}

    breakdown = {}
    for domain in goal_domains:
        base_points = goals_by_domain.get(domain.name, 0)
        percent_modifier = _get_goal_percent_modifier(character, domain)
        multiplier = 1 + (percent_modifier / 100) if base_points > 0 else 1
        final_bonus = int(base_points * multiplier) if base_points > 0 else 0

        breakdown[domain.name] = GoalBonusBreakdown(
            base_points=base_points,
            percent_modifier=percent_modifier,
            final_bonus=final_bonus,
        )

    return breakdown


# Per-cron-day application budget (#940): base 1, raised by distinctions via
# the goal_points/applications_per_day modifier target.
DEFAULT_APPLICATIONS_PER_DAY = 1
APPLICATIONS_PER_DAY_TARGET = "applications_per_day"


def get_daily_application_budget(character: "CharacterSheet") -> int:
    """How many goal applications this character gets per cron day."""
    modifiers = CharacterModifier.objects.filter(
        character=character,
        target__category__name=GOAL_POINTS_CATEGORY_NAME,
        target__name=APPLICATIONS_PER_DAY_TARGET,
    )
    return DEFAULT_APPLICATIONS_PER_DAY + sum(m.value for m in modifiers)


def apply_goal(goal: CharacterGoal, *, context: str = "") -> int:
    """Owner-claimed goal application (#940): spend one daily use, get the bonus.

    The owner decides the goal applies; the system only enforces the
    per-cron-day budget (1 + distinction modifiers). Returns the bonus for
    the caller to feed into ``perform_check``'s ``extra_modifiers``.
    The "cron day" boundary is the server date — adequate until the #932
    scheduler grows an authoritative day tick.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.goals.models import GoalApplication  # noqa: PLC0415

    sheet = goal.character
    used_today = GoalApplication.objects.filter(
        goal__character=goal.character,
        created_at__date=timezone.now().date(),
    ).count()
    if used_today >= get_daily_application_budget(sheet):
        msg = "You have already drawn on your goals today."
        raise ValidationError(msg)

    bonus = get_goal_bonus(sheet, goal.domain)
    GoalApplication.objects.create(goal=goal, bonus_granted=bonus, context=context)
    return bonus
