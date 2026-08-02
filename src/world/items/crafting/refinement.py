"""Refinement projects — the guaranteed long road (#2878).

An item's owner (or their atelier) pours AP and coin into a piece until it
wraps over into +1: a chosen Accent raised (or newly added), or the base
quality rung. Built ON the projects accumulator (ADR-0010: this module is
the specific consumer; ``projects`` stays generic):

* deterministic — **no per-cycle rolls** (Apostate's ruling: roll-to-see-
  failure gacha is unsatisfying; checks live at initial crafting only);
* self-scaling — the threshold is ``item value × target rung`` in coppers
  (via the projects app's 1-progress-per-100-coppers), so higher rungs are
  a longer, costlier road and alaricite costs alaricite money;
* master-gated — the contribution that crosses the threshold requires a
  contributor whose thread-capped ceiling reaches the goal rung
  (``RefinementAwaitsMaster`` otherwise): apprentices can carry the work to
  the brink, but crossing into divine needs a master on the project.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.crafting.constants import (
    ACCENT_REFINEMENT_COST_BASE,
    BASE_MAX_ACCENT_LEVEL,
    BASE_MAX_QUALITY_RUNG,
    REFINEMENT_PACE_MULTIPLIER,
    REFINEMENT_TIME_LIMIT_DAYS,
    REFINEMENT_VALUE_PER_PROGRESS,
)
from world.items.crafting.models import ItemAccent, ItemRefinementDetails
from world.items.exceptions import (
    InvalidAccentTarget,
    RefinementAwaitsMaster,
    RefinementNotPossible,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.mechanics.models import ModifierTarget
    from world.projects.models import Project
    from world.scenes.models import Persona
    from world.traits.models import CheckOutcome, Trait

import logging

logger = logging.getLogger(__name__)


def _refinement_skill_trait(item_instance: ItemInstance) -> Trait | None:
    """The crafting skill governing this piece: its first crafted recipe's trait."""
    crafted = item_instance.crafted_recipes.select_related("recipe__skill_trait").first()
    return crafted.recipe.skill_trait if crafted is not None else None


def _goal_rung(item_instance: ItemInstance, accent_target: ModifierTarget | None) -> int:
    """The rung the project is reaching for: current + 1 (1 for a new Accent)."""
    if accent_target is not None:
        existing = ItemAccent.objects.filter(
            item_instance=item_instance, target=accent_target
        ).first()
        return existing.level.level + 1 if existing is not None else 1
    quality = item_instance.quality_tier
    if quality is None:
        raise RefinementNotPossible
    return quality.sort_order + 1


def _goal_exists(item_instance: ItemInstance, accent_target: ModifierTarget | None) -> bool:
    """True when the ladder actually has a rung above the current one."""
    from world.items.models import AccentLevel, QualityTier  # noqa: PLC0415

    rung = _goal_rung(item_instance, accent_target)
    if accent_target is not None:
        return AccentLevel.objects.filter(level__gte=rung).exists()
    return QualityTier.objects.filter(sort_order__gte=rung).exists()


def _contributor_cap(item_instance: ItemInstance, sheet: CharacterSheet, accent_goal: bool) -> int:
    """One contributor's thread-capped ceiling for this piece's skill."""
    from world.items.crafting.quality import thread_count_for_skill  # noqa: PLC0415

    skill = _refinement_skill_trait(item_instance)
    character = sheet.character
    threads = thread_count_for_skill(character, skill) if character is not None else 0
    base = BASE_MAX_ACCENT_LEVEL if accent_goal else BASE_MAX_QUALITY_RUNG
    return base + threads


def _max_project_cap(
    project: Project,
    details: ItemRefinementDetails,
    extra_sheet: CharacterSheet | None = None,
) -> int:
    """The highest thread-capped ceiling among everyone on the project."""
    sheets = {
        c.contributor_persona.character_sheet
        for c in project.contributions.select_related("contributor_persona__character_sheet")
    }
    sheets.add(project.owner_persona.character_sheet)
    if extra_sheet is not None:
        sheets.add(extra_sheet)
    accent_goal = details.accent_target_id is not None
    return max(
        (_contributor_cap(details.item_instance, sheet, accent_goal) for sheet in sheets),
        default=0,
    )


def refinement_threshold(item_instance: ItemInstance, goal_rung: int) -> int:
    """Progress to wrap: value × rung × pace ÷ 100, doubled per accent.

    Each accent on the piece doubles the road (#2886, Apostate's ruling): a
    heavily accented piece is a finished statement — reworking it approaches
    commissioning anew. PLACEHOLDER curve.
    """
    base = max(
        1,
        (item_instance.template.value * goal_rung * REFINEMENT_PACE_MULTIPLIER)
        // REFINEMENT_VALUE_PER_PROGRESS,
    )
    return base * (ACCENT_REFINEMENT_COST_BASE ** item_instance.accents.count())


def start_item_refinement(
    *,
    item_instance: ItemInstance,
    initiator_persona: Persona,
    accent_target: ModifierTarget | None = None,
) -> Project:
    """Open a refinement project on ``item_instance`` toward one +1 goal.

    Raises ``InvalidAccentTarget`` for a non-styleable axis,
    ``RefinementNotPossible`` when the piece has no quality to raise, the
    ladder has no higher rung, or an active project already covers this goal.
    """
    from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    if accent_target is not None and (
        not accent_target.is_styleable or not accent_target.is_active
    ):
        raise InvalidAccentTarget
    if accent_target is not None:
        from world.items.crafting.models import AccentExclusion  # noqa: PLC0415

        existing = set(
            ItemAccent.objects.filter(item_instance=item_instance).values_list(
                "target_id", flat=True
            )
        )
        if AccentExclusion.conflict_exists([*existing, accent_target.pk]) is not None:
            raise InvalidAccentTarget
    if not _goal_exists(item_instance, accent_target):
        raise RefinementNotPossible
    duplicate = ItemRefinementDetails.objects.filter(
        item_instance=item_instance,
        accent_target=accent_target,
        project__status=ProjectStatus.ACTIVE,
    ).exists()
    if duplicate:
        raise RefinementNotPossible

    rung = _goal_rung(item_instance, accent_target)
    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.ITEM_REFINEMENT,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        status=ProjectStatus.ACTIVE,
        owner_persona=initiator_persona,
        started_at=now,
        time_limit=now + timedelta(days=REFINEMENT_TIME_LIMIT_DAYS),
        threshold_target=refinement_threshold(item_instance, rung),
        description=f"Refinement of {item_instance.display_name}",
    )
    ItemRefinementDetails.objects.create(
        project=project,
        item_instance=item_instance,
        accent_target=accent_target,
    )
    return project


def _assert_crossing_allowed(
    project: Project, added_progress: int, contributor_sheet: CharacterSheet
) -> None:
    """The master gate: the threshold-crossing contribution needs a capped hand."""
    if project.threshold_target is None:
        return
    if project.current_progress + added_progress < project.threshold_target:
        return
    details = ItemRefinementDetails.objects.get(project=project)
    goal = _goal_rung(details.item_instance, details.accent_target)
    if goal > _max_project_cap(project, details, extra_sheet=contributor_sheet):
        raise RefinementAwaitsMaster


def donate_to_item_refinement(project: Project, *, donor_persona: Persona, amount: int) -> None:
    """Coin into the work: debits the purse, advances progress, may complete.

    Deterministic — the only gate is the master gate on the crossing
    contribution.
    """
    from world.projects.services import donate_to_project  # noqa: PLC0415

    _assert_crossing_allowed(project, amount // 100, donor_persona.character_sheet)
    donate_to_project(project, donor_persona=donor_persona, amount=amount)


def contribute_ap_to_item_refinement(
    project: Project, *, contributor_persona: Persona, ap_amount: int
) -> None:
    """AP into the work: spends the pool, advances progress 1:1, may complete."""
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.projects.constants import ContributionKind  # noqa: PLC0415
    from world.projects.services import (  # noqa: PLC0415
        add_contribution,
        maybe_complete_immediately,
    )

    _assert_crossing_allowed(project, ap_amount, contributor_persona.character_sheet)
    character = contributor_persona.character_sheet.character
    pool = ActionPointPool.get_or_create_for_character(character)
    if not pool.spend(ap_amount):
        raise RefinementNotPossible
    add_contribution(
        project=project,
        contributor_persona=contributor_persona,
        kind=ContributionKind.AP,
        ap_amount=ap_amount,
    )
    maybe_complete_immediately(project)


def resolve_item_refinement(
    project: Project,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """Instant-completion handler: apply the +1, clamped to the project's cap.

    Deterministic — ``outcome_tier`` is always None (a funded threshold IS the
    success). Defensive clamp: contributions normally can't cross the
    threshold past the cap (``RefinementAwaitsMaster``), but if a generic
    donation slipped through, apply the best reachable rung and log.
    """
    from world.items.models import AccentLevel, QualityTier  # noqa: PLC0415

    details = ItemRefinementDetails.objects.get(project=project)
    item = details.item_instance
    goal = _goal_rung(item, details.accent_target)
    cap = _max_project_cap(project, details)
    if goal > cap:
        logger.warning(
            "Refinement project #%s funded past the contributor cap (goal %s > cap %s) — "
            "applying nothing; the piece keeps its current rung.",
            project.pk,
            goal,
            cap,
        )
        return

    if details.accent_target is not None:
        level = AccentLevel.objects.filter(level__lte=goal).order_by("-level").first()
        if level is None:
            return
        ItemAccent.objects.update_or_create(
            item_instance=item,
            target=details.accent_target,
            defaults={"level": level},
        )
        return

    tier = QualityTier.objects.filter(sort_order__lte=goal).order_by("-sort_order").first()
    if tier is None or (item.quality_tier is not None and tier.pk == item.quality_tier.pk):
        return
    item.quality_tier = tier
    item.save(update_fields=["quality_tier"])
    # The crafted-recipe snapshot scales facet/modifier math — keep it in step.
    # Instance saves, not queryset .update(): a raw UPDATE bypasses the
    # SharedMemoryModel identity map and leaves cached rows stale.
    for crafted in item.crafted_recipes.all():
        crafted.quality_tier = tier
        crafted.save(update_fields=["quality_tier"])
