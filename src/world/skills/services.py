"""Service functions for the skills training system."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Max, Sum

from world.action_points.models import ActionPointConfig, ActionPointPool
from world.classes.models import CharacterClassLevel
from world.progression.constants import DP_BASE_LEVEL
from world.progression.models.rewards import DevelopmentTransaction
from world.progression.types import DevelopmentSource, ProgressionReason
from world.relationships.helpers import get_relationship_tier
from world.relationships.services import standing_tie_ap
from world.roster.models import RosterEntry
from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    Skill,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)
from world.skills.types import SkillTrainingResult
from world.traits.models import CharacterTraitChange, CharacterTraitValue, TraitChangeSource

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona
    from world.traits.models import Trait

logger = logging.getLogger(__name__)

_UNSET = object()

# XP boundaries: skill values where advancement is blocked until XP purchase.
# Values ending in 9 within each decade represent mastery gates.
_XP_BOUNDARY_DIGIT = 9
_XP_BOUNDARY_MIN = 19
_XP_BOUNDARY_MAX = 49

# A skill's shown value is its stored value / 10 (the "3.0" a plateau message names).
# Band caps (#4585) are authored on that shown scale and converted at the comparison.
_SKILL_SHOWN_DIVISOR = 10


def _get_path_level(character: ObjectDB) -> int:
    """Get the character's highest class level.

    Looks up all CharacterClassLevel rows for the character and returns the
    maximum ``level`` value. Defaults to 1 if the character has no class levels.

    Args:
        character: The character whose path level to look up.

    Returns:
        The highest class level, or 1 if none exist.
    """
    levels = CharacterClassLevel.objects.filter(character_id=character.pk)
    if not levels:
        return 1
    return max(entry.level for entry in levels)


def _bulk_path_levels(character_pks: set[int]) -> dict[int, int]:
    """Batch-fetch path levels for multiple characters in a single query.

    Args:
        character_pks: Set of character primary keys to look up.

    Returns:
        Dict mapping character PK to highest class level (default 1).
    """
    qs = (
        CharacterClassLevel.objects.filter(character_id__in=character_pks)
        .values("character_id")
        .annotate(max_level=Max("level"))
    )
    levels = {row["character_id"]: row["max_level"] for row in qs}
    return {pk: levels.get(pk, 1) for pk in character_pks}


def _get_skill_value(character: ObjectDB, skill: Skill) -> int:
    """Look up a character's value for a given skill.

    Args:
        character: The character to look up.
        skill: The skill to query.

    Returns:
        The raw skill value, or 0 if the character has no value for this skill.
    """
    try:
        return CharacterSkillValue.objects.get(character_id=character.pk, skill=skill).value
    except CharacterSkillValue.DoesNotExist:
        return 0


def _get_spec_value(character: ObjectDB, specialization: Specialization) -> int:
    """Look up a character's value for a given specialization.

    Args:
        character: The character to look up.
        specialization: The specialization to query.

    Returns:
        The raw specialization value, or 0 if the character has no value for it.
    """
    try:
        return CharacterSpecializationValue.objects.get(
            character_id=character.pk, specialization=specialization
        ).value
    except CharacterSpecializationValue.DoesNotExist:
        return 0


def get_specialization_value(character: ObjectDB, specialization: Specialization) -> int:
    """A character's raw value for a specialization, 0 if unowned (#1688).

    The public read the check engine uses to fold a specialization into a roll. Public wrapper
    over ``_get_spec_value`` so callers outside the skills cron don't reach a private helper.
    """
    return _get_spec_value(character, specialization)


def has_specialization(
    character: ObjectDB, specialization: Specialization, *, minimum_rank: int = 1
) -> bool:
    """Whether a character owns a specialization at ``minimum_rank`` or better (#1688).

    A rank is ten points of stored value (rank 1 = value 10 — the same rung
    boundaries XP unlocks cross). Gates surfacing of spec-only options
    (e.g. the gossip option only appears at Gossip rank ≥ 1).
    """
    return _get_spec_value(character, specialization) >= minimum_rank * 10


def _get_teaching_skill() -> Skill | None:
    """Look up the Teaching skill from the skill config.

    Returns:
        The Teaching Skill instance, or None if not configured.
    """
    budget = SkillPointBudget.get_active_budget()
    return budget.teaching_skill


def _get_teaching_value(
    mentor_character: ObjectDB,
    teaching_skill: Skill | None = _UNSET,  # type: ignore[assignment]
) -> int:
    """Look up the mentor's Teaching skill value.

    Args:
        mentor_character: The mentor character to look up.
        teaching_skill: Pre-fetched Teaching skill instance for batch use.
            Pass ``_UNSET`` (default) to look it up automatically.

    Returns:
        The mentor's Teaching skill value, or 0 if the Teaching skill does not
        exist or the mentor has no value for it.
    """
    if teaching_skill is _UNSET:
        teaching_skill = _get_teaching_skill()
    if teaching_skill is None:
        return 0
    return _get_skill_value(mentor_character, teaching_skill)


def calculate_training_development(
    allocation: TrainingAllocation,
    *,
    _teaching_skill: Skill | None = _UNSET,  # type: ignore[assignment]
    _path_levels: dict[int, int] | None = None,
) -> int:
    """Calculate development points earned from a training allocation.

    Formula::

        base_gain = 5 * AP_spent * path_level

        If mentor:
            mentor_skill_total = mentor_skill + teaching (+ parent if spec)
            student_skill_total = student_skill (+ parent if spec)
            ratio = mentor_skill_total / student_skill_total
            effective_AP = AP_spent + teaching
            mentor_bonus = effective_AP * ratio * (relationship_tier + 1)

        dev_points = base_gain + mentor_bonus

    Args:
        allocation: The TrainingAllocation record to calculate for.
        _teaching_skill: Pre-fetched Teaching skill for batch use (internal).
        _path_levels: Pre-built {character_pk: level} dict for batch use (internal).

    Returns:
        Development points as an integer (truncated).
    """
    character = allocation.character
    ap_spent = allocation.ap_amount

    if _path_levels is not None:
        path_level = _path_levels.get(character.pk, 1)
    else:
        path_level = _get_path_level(character)
    base_gain = 5 * ap_spent * path_level

    if not allocation.mentor:
        return int(base_gain)

    mentor_character = allocation.mentor.character_sheet
    teaching = _get_teaching_value(mentor_character, teaching_skill=_teaching_skill)

    if allocation.specialization:
        # Specialization training: include parent skill in totals
        spec = allocation.specialization
        parent_skill = spec.parent_skill

        student_parent = _get_skill_value(character, parent_skill)
        student_spec = _get_spec_value(character, spec)
        student_total = student_parent + student_spec

        mentor_parent = _get_skill_value(mentor_character, parent_skill)
        mentor_spec = _get_spec_value(mentor_character, spec)
        mentor_total = mentor_parent + mentor_spec + teaching
    else:
        # Skill training
        skill = allocation.skill
        student_total = _get_skill_value(character, skill)
        mentor_total = _get_skill_value(mentor_character, skill) + teaching

    # Prevent division by zero
    if student_total == 0:
        student_total = 1

    ratio = mentor_total / student_total
    effective_ap = ap_spent + teaching
    relationship_tier = get_relationship_tier(character, mentor_character)
    mentor_bonus = effective_ap * ratio * (relationship_tier + 1)

    return int(base_gain + mentor_bonus)


def total_allocated_training_ap(character_id: int, exclude_pk: int | None = None) -> int:
    """Get total AP currently allocated across all training for a character.

    Public because ties spend from the same weekly purse and must count this total in
    their own budget check (``world.relationships.services.standing_weekly_ap``, #3957
    final review). Takes the id rather than the character: ``TrainingAllocation.character``
    is the ``CharacterSheet``, which shares ``ObjectDB``'s pk, so a caller holding either
    passes ``.pk`` and no row is fetched to ask the question.

    Args:
        character_id: pk of the character (or their sheet) whose allocations to sum.
        exclude_pk: Optional allocation PK to exclude from the total (used when
            validating an update).

    Returns:
        Total AP allocated, or 0 if none.
    """
    qs = TrainingAllocation.objects.filter(character_id=character_id)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(total=Sum("ap_amount"))["total"] or 0


def create_training_allocation(
    character: ObjectDB,
    ap_amount: int,
    *,
    skill: Skill | None = None,
    specialization: Specialization | None = None,
    mentor: Persona | None = None,
) -> TrainingAllocation:
    """Create a new training allocation for a character.

    Args:
        character: The character to create the allocation for.
        ap_amount: Action points to allocate.
        skill: The skill to train (mutually exclusive with specialization).
        specialization: The specialization to train (mutually exclusive with skill).
        mentor: Optional mentor persona for the training.

    Returns:
        The created TrainingAllocation instance.

    Raises:
        ValueError: If ap_amount is <= 0, or the character's standing allocations —
            training AND ties, which share one weekly purse (#3957) — would exceed the
            weekly AP budget.
    """
    if ap_amount <= 0:
        msg = "AP amount must be greater than 0."
        raise ValueError(msg)

    budget = ActionPointConfig.get_weekly_regen()
    current_total = total_allocated_training_ap(character.pk) + standing_tie_ap(character.pk)
    if current_total + ap_amount > budget:
        msg = (
            f"Total allocated AP ({current_total + ap_amount}) would exceed "
            f"weekly budget ({budget})."
        )
        raise ValueError(msg)

    return TrainingAllocation.objects.create(
        character=character.sheet_data,
        skill=skill,
        specialization=specialization,
        mentor=mentor,
        ap_amount=ap_amount,
    )


def update_training_allocation(
    allocation: TrainingAllocation,
    *,
    ap_amount: int | None = None,
    mentor: Persona | None = _UNSET,  # type: ignore[assignment]
) -> TrainingAllocation:
    """Update an existing training allocation.

    Args:
        allocation: The allocation to update.
        ap_amount: New AP amount (if provided).
        mentor: New mentor persona, or None to remove mentor. Pass the sentinel
            ``_UNSET`` (default) to leave unchanged.

    Returns:
        The updated TrainingAllocation instance.

    Raises:
        ValueError: If ap_amount is <= 0, or the character's standing allocations —
            training AND ties, which share one weekly purse (#3957) — would exceed the
            weekly AP budget.
    """
    if ap_amount is not None:
        if ap_amount <= 0:
            msg = "AP amount must be greater than 0."
            raise ValueError(msg)

        budget = ActionPointConfig.get_weekly_regen()
        current_total = total_allocated_training_ap(
            allocation.character_id, exclude_pk=allocation.pk
        ) + standing_tie_ap(allocation.character_id)
        if current_total + ap_amount > budget:
            msg = (
                f"Total allocated AP ({current_total + ap_amount}) would exceed "
                f"weekly budget ({budget})."
            )
            raise ValueError(msg)
        allocation.ap_amount = ap_amount

    if mentor is not _UNSET:
        allocation.mentor = mentor

    allocation.save()
    return allocation


def remove_training_allocation(allocation: TrainingAllocation) -> None:
    """Delete a training allocation.

    Args:
        allocation: The allocation to remove.
    """
    allocation.delete()


def set_skill_trait(sheet: CharacterSheet, skill: Skill, value: int, source: str) -> None:
    """The skill's ``CharacterTraitValue`` the check engine reads (#2894), stamped (#3055).

    A skill's rating lives in two stores: ``CharacterSkillValue`` (what the sheet shows)
    and this trait row (what a check reads). Every writer of a skill's value keeps them
    equal (#4496): character creation and staff edit through ``set_skill_values``,
    weekly training, the XP breakthrough and a level-up from use through here and
    :func:`set_skill_sheet_value`. A row that changes, or is new, gets a
    ``CharacterTraitChange`` with ``source``.
    """
    row = CharacterTraitValue.objects.filter(character=sheet, trait=skill.trait).first()
    old = row.value if row else 0
    if row is None:
        CharacterTraitValue.objects.create(character=sheet, trait=skill.trait, value=value)
    elif row.value != value:
        row.value = value
        row.save(update_fields=["value"])
    else:
        return
    CharacterTraitChange.objects.create(
        character_sheet=sheet, trait=skill.trait, old_value=old, new_value=value, source=source
    )


def set_skill_sheet_value(sheet: CharacterSheet, skill: Skill, value: int) -> None:
    """The skill's ``CharacterSkillValue`` the sheet shows, the mirror of ``set_skill_trait``.

    Creates the row when the sheet has none. Only ``value`` moves; the row's
    ``development_points`` and ``rust_points`` are the training counters and stay as
    they are (the use-development counter, ``DevelopmentPoints``, is a separate one).
    """
    row, created = CharacterSkillValue.objects.get_or_create(
        character=sheet,
        skill=skill,
        defaults={"value": value, "development_points": 0, "rust_points": 0},
    )
    if not created and row.value != value:
        row.value = value
        row.save(update_fields=["value"])


def reconcile_skill_stores(sheet: CharacterSheet, skill: Skill) -> int:
    """Bring a skill's two stores up to the higher of the two, and return that rating.

    Skills only rise in play, so when the stores disagree (weekly training and an XP
    breakthrough once wrote only the sheet row, a level-up from use only the trait row,
    #4496) the higher value is the one the character earned. Every post-creation
    writer calls this before it adds its own progress, so no write can lower a
    character's skill. Returns 0, writing nothing, when the character has neither row.
    """
    sheet_row = CharacterSkillValue.objects.filter(character=sheet, skill=skill).first()
    trait_row = CharacterTraitValue.objects.filter(character=sheet, trait=skill.trait).first()
    if sheet_row is None and trait_row is None:
        return 0
    rating = max(
        sheet_row.value if sheet_row else 0,
        trait_row.value if trait_row else 0,
    )
    set_skill_sheet_value(sheet, skill, rating)
    set_skill_trait(sheet, skill, rating, TraitChangeSource.DEVELOPMENT_LEVEL_UP)
    return rating


def _development_cost(current_value: int) -> int:
    """Calculate the development point cost to reach the next skill level.

    Cost formula: ``max((current_value - 9) * 100, 1)``.

    Examples: 10->11 costs 100, 11->12 costs 200, 15->16 costs 600.

    Args:
        current_value: The current skill or specialization value.

    Returns:
        Development points required to advance one level (minimum 1).
    """
    return max((current_value - 9) * 100, 1)


def _is_at_xp_boundary(value: int) -> bool:
    """Check whether a skill value is at an XP boundary.

    XP boundaries are values ending in 9 within each decade (19, 29, 39, 49).
    At these boundaries, further training development is blocked until XP is
    spent to break through.

    Args:
        value: The current skill value to check.

    Returns:
        True if the value is at an XP boundary.
    """
    return value % 10 == _XP_BOUNDARY_DIGIT and _XP_BOUNDARY_MIN <= value <= _XP_BOUNDARY_MAX


def is_skill_at_xp_boundary(value: int) -> bool:
    """Public wrapper for :func:`_is_at_xp_boundary` (#2115).

    Lets other apps (e.g. character-sheet serialization) check boundary state
    without reaching into a private helper.
    """
    return _is_at_xp_boundary(value)


def stored_skill_cap(sheet: CharacterSheet) -> int | None:
    """The highest stored value the sheet's level band lets a skill reach (#4585).

    ``MaturationStatCap.skill_cap`` (shown units) times ten, or ``None`` when the band
    has no row or its skill cap is blank. Applies to skills and their specializations.
    """
    from world.progression.services.maturation import skill_cap_for  # noqa: PLC0415

    cap = skill_cap_for(sheet)
    return None if cap is None else cap * _SKILL_SHOWN_DIVISOR


def skill_cap_message(name: str, stored_cap: int) -> str:
    """Message shown when development stops at the band's skill cap (#4585)."""
    return (
        f"{name} is at {stored_cap / _SKILL_SHOWN_DIVISOR:.1f}, the cap for your current "
        "level band. Development maintains it but cannot raise it further."
    )


def _boundary_message(skill: Skill, next_rating: int) -> str:
    """Plateau message shown when dev points dissipate at an XP boundary (#2115)."""
    return (
        f"{skill.name} is at threshold {next_rating / 10:.1f} — training maintains, "
        "does not advance until the breakthrough is unlocked."
    )


def _apply_development_to_skill(skill_value: CharacterSkillValue, dev_points: int) -> str | None:
    """Apply development points to a skill and keep the check engine's copy equal (#4496).

    Starts from the higher of the skill's two stores (``reconcile_skill_stores``), runs
    :func:`_develop_skill_value`, then writes the resulting rating to the trait row a
    check reads. Returns the plateau message ``_develop_skill_value`` returns.
    """
    sheet = skill_value.character
    skill = skill_value.skill
    skill_value.value = max(skill_value.value, reconcile_skill_stores(sheet, skill))
    message = _develop_skill_value(skill_value, dev_points)
    set_skill_trait(sheet, skill, skill_value.value, TraitChangeSource.DEVELOPMENT_LEVEL_UP)
    return message


def points_to_next_boundary(skill_value: CharacterSkillValue) -> int | None:
    """Development the skill can take before it parks at its next XP boundary.

    Counts unpaid rust first (rust is paid before any level), then the cost of each
    level from the current value up to the next boundary (19, 29, 39, 49), less the
    ``development_points`` already banked toward the current level. A skill already
    sitting at a boundary can take only its rust, since anything more dissipates. The
    band's skill cap (#4585) is a stop like a boundary: the count ends there, and a skill
    at its cap takes only its rust. Returns ``None`` above 49 with no cap set, where no
    stop lies ahead. A caller that must not lose any development to dissipation clamps
    what it applies to this number.
    """
    value = skill_value.value
    cap = stored_skill_cap(skill_value.character)
    if _is_at_xp_boundary(value) or (cap is not None and value >= cap):
        return skill_value.rust_points
    boundary = next(
        (
            v
            for v in range(max(value, _XP_BOUNDARY_MIN), _XP_BOUNDARY_MAX + 1)
            if _is_at_xp_boundary(v)
        ),
        None,
    )
    if cap is not None:
        boundary = cap if boundary is None else min(boundary, cap)
    if boundary is None:
        return None
    level_cost = sum(_development_cost(v) for v in range(value, boundary))
    return skill_value.rust_points + max(level_cost - skill_value.development_points, 0)


def train_skill(
    sheet: CharacterSheet,
    skill: Skill,
    dev_points: int,
    *,
    description: str,
    stop_at_boundary: bool = False,
) -> SkillTrainingResult:
    """Develop a skill from training and record the audit transaction.

    The one writer for development from training: weekly training and an Academy course
    both come through here. Creates the sheet's ``CharacterSkillValue`` at the base level
    when it has none, applies ``dev_points`` through :func:`_apply_development_to_skill`
    (which keeps the sheet row and the check engine's trait row equal), and writes one
    ``DevelopmentTransaction`` for the points applied, with any plateau message appended
    to ``description``. With ``stop_at_boundary`` the points are clamped to
    :func:`points_to_next_boundary`, so none dissipates at a boundary; the excess is
    simply not applied and the caller keeps it.
    """
    skill_value, _created = CharacterSkillValue.objects.get_or_create(
        character=sheet,
        skill=skill,
        defaults={"value": DP_BASE_LEVEL, "development_points": 0, "rust_points": 0},
    )
    skill_value.value = max(skill_value.value, reconcile_skill_stores(sheet, skill))
    old_value = skill_value.value
    points_applied = dev_points
    if stop_at_boundary:
        room = points_to_next_boundary(skill_value)
        if room is not None:
            points_applied = min(dev_points, room)
    plateau_message = _apply_development_to_skill(skill_value, points_applied)
    _record_training_transaction(sheet, skill.trait, points_applied, description, plateau_message)
    return SkillTrainingResult(
        old_value=old_value,
        new_value=skill_value.value,
        points_applied=points_applied,
        plateau_message=plateau_message,
    )


def _record_training_transaction(
    sheet: CharacterSheet,
    trait: Trait,
    amount: int,
    description: str,
    plateau_message: str | None,
) -> None:
    """Write the ``DevelopmentTransaction`` audit row for a training award."""
    if plateau_message:
        description = f"{description} — {plateau_message}"
    DevelopmentTransaction.objects.create(
        character_sheet=sheet,
        trait=trait,
        source=DevelopmentSource.TRAINING,
        amount=amount,
        reason=ProgressionReason.SYSTEM_AWARD,
        description=description,
    )


def _develop_skill_value(skill_value: CharacterSkillValue, dev_points: int) -> str | None:
    """Apply development points to a skill, handling rust payoff, level-ups, and plateau.

    Dev points pay off rust first, always — even while the skill is parked at an
    XP boundary (19, 29, 39, 49), so training/use can still "blow the rust off" a
    gated skill (#2115). Any surplus beyond the rust payoff dissipates at a
    boundary: development points are deliberately ephemeral (the 2026-07-09
    ephemerality ruling) — never banked, never silently discarded. The same
    dissipation (with the same visible message) applies to overflow from a
    level-up that lands exactly on a boundary. The band's skill cap (#4585) is a
    wall of the same kind: development stops at it, surplus dissipates, and the
    message names the cap. Mutates ``skill_value`` in place and saves it.

    Args:
        skill_value: The CharacterSkillValue to develop.
        dev_points: Development points to apply.

    Returns:
        A plateau message when points dissipated at a boundary or the band's cap
        this call, else ``None``.
    """
    cap = stored_skill_cap(skill_value.character)
    # Pay off rust first — always, even when parked at a boundary.
    remaining = dev_points
    if skill_value.rust_points > 0:
        rust_paid = min(remaining, skill_value.rust_points)
        skill_value.rust_points -= rust_paid
        remaining -= rust_paid

    if cap is not None and skill_value.value >= cap:
        message = skill_cap_message(skill_value.skill.name, cap) if remaining else None
        skill_value.development_points = 0
        skill_value.save()
        return message

    if _is_at_xp_boundary(skill_value.value):
        message = _boundary_message(skill_value.skill, skill_value.value + 1) if remaining else None
        skill_value.development_points = 0
        skill_value.save()
        return message

    # Apply remaining to development
    remaining += skill_value.development_points

    message = None
    cost = _development_cost(skill_value.value)
    while remaining >= cost:
        remaining -= cost
        skill_value.value += 1
        if cap is not None and skill_value.value >= cap:
            if remaining > 0:
                message = skill_cap_message(skill_value.skill.name, cap)
            remaining = 0
            break
        if _is_at_xp_boundary(skill_value.value):
            if remaining > 0:
                message = _boundary_message(skill_value.skill, skill_value.value + 1)
            remaining = 0
            break
        cost = _development_cost(skill_value.value)

    skill_value.development_points = remaining
    skill_value.save()
    return message


def purchase_skill_breakthrough(character: ObjectDB, skill: Skill) -> tuple[bool, str]:
    """Spend XP to break through a skill's XP-boundary plateau (#2115).

    Wires the pre-existing but never-called ``TraitRatingUnlock`` model through
    the same ``purchase_unlock`` seam as class-level/thread unlocks
    (``spend_xp_on_unlock``'s pattern). The purchase does not itself grant a
    level (ADR-0053: XP buys the unlock that gates, never the grant) — it just
    clears the gate. Because dev points earned while gated dissipate rather than
    bank (the 2026-07-09 ephemerality ruling), there is nothing to retroactively
    apply: training simply resumes accruing from zero once the gate is clear.

    Args:
        character: The character purchasing the breakthrough.
        skill: The gated skill.

    Returns:
        ``(success, message)`` — mirrors ``spend_xp_on_unlock``'s contract.
    """
    from world.progression.exceptions import (  # noqa: PLC0415
        InsufficientXPError,
        NoAccountForCharacterError,
    )
    from world.progression.models import TraitRatingUnlock  # noqa: PLC0415
    from world.progression.services.xp_ledger import spend_xp_for_character  # noqa: PLC0415

    reconcile_skill_stores(character.sheet_data, skill)
    try:
        skill_value = CharacterSkillValue.objects.get(character_id=character.pk, skill=skill)
    except CharacterSkillValue.DoesNotExist:
        return False, f"{skill.name} has no recorded value for this character."

    if not _is_at_xp_boundary(skill_value.value):
        return False, f"{skill.name} is not at a breakthrough boundary."

    target_rating = skill_value.value + 1
    cap = stored_skill_cap(character.sheet_data)
    if cap is not None and target_rating > cap:
        return False, skill_cap_message(skill.name, cap)
    try:
        unlock = TraitRatingUnlock.objects.get(trait=skill.trait, target_rating=target_rating)
    except TraitRatingUnlock.DoesNotExist:
        return (
            False,
            f"No breakthrough authored for {skill.name} at this level — contact staff.",
        )

    xp_cost = unlock.get_xp_cost_for_character(character)

    with transaction.atomic():
        # Re-read under lock: another purchase (or training) may have moved the value
        # between the read above and this transaction, so re-check the boundary still
        # holds before spending XP (double-spend guard). Write through the locked
        # instance so the identity map isn't left holding the stale, unlocked one.
        skill_value = CharacterSkillValue.objects.select_for_update().get(pk=skill_value.pk)
        if skill_value.value + 1 != target_rating:
            return False, f"{skill.name} is not at a breakthrough boundary."

        try:
            spend_xp_for_character(
                character.sheet_data,
                xp_cost,
                f"Breakthrough: {skill.name} to {target_rating / 10:.1f}",
            )
        except InsufficientXPError as exc:
            return False, f"Insufficient XP (need {exc.required}, have {exc.available})."
        except NoAccountForCharacterError as exc:
            return False, exc.user_message

        skill_value.value = target_rating
        skill_value.development_points = 0
        skill_value.save()
        set_skill_trait(
            skill_value.character, skill, target_rating, TraitChangeSource.XP_BREAKTHROUGH
        )

    return (
        True,
        f"Breakthrough! {skill.name} rises to {target_rating / 10:.1f} — training resumes.",
    )


@dataclass(frozen=True)
class SkillBreakthroughProspect:
    """A skill parked at an XP boundary, with its breakthrough cost if authored (#2115)."""

    skill: Skill
    next_rating: int
    xp_cost: int | None
    authored: bool


def skills_at_boundary(character: ObjectDB) -> list[SkillBreakthroughProspect]:
    """Return the character's skills currently parked at an XP boundary (#2115).

    Feeds the ``progression unlock`` listing and the sheet skills section's
    ``at_boundary`` flag — so a player sees why a skill stalled, and what the
    breakthrough costs, before burning a session wondering.

    Args:
        character: The character whose skills to check.

    Returns:
        One :class:`SkillBreakthroughProspect` per gated skill; ``authored`` is
        False (and ``xp_cost`` is None) when staff hasn't authored a
        ``TraitRatingUnlock`` for that boundary yet.
    """
    from world.progression.models import TraitRatingUnlock  # noqa: PLC0415

    gated = [
        sv
        for sv in CharacterSkillValue.objects.filter(character_id=character.pk).select_related(
            "skill__trait"
        )
        if _is_at_xp_boundary(sv.value)
    ]
    if not gated:
        return []

    trait_ids = [sv.skill.trait_id for sv in gated]
    target_ratings = [sv.value + 1 for sv in gated]
    unlocks = {
        (u.trait_id, u.target_rating): u
        for u in TraitRatingUnlock.objects.filter(
            trait_id__in=trait_ids, target_rating__in=target_ratings
        )
    }

    prospects: list[SkillBreakthroughProspect] = []
    for sv in gated:
        next_rating = sv.value + 1
        unlock = unlocks.get((sv.skill.trait_id, next_rating))
        prospects.append(
            SkillBreakthroughProspect(
                skill=sv.skill,
                next_rating=next_rating,
                xp_cost=unlock.get_xp_cost_for_character(character) if unlock else None,
                authored=unlock is not None,
            )
        )
    return prospects


def _apply_development_to_specialization(
    spec_value: CharacterSpecializationValue, dev_points: int
) -> str | None:
    """Apply development points to a specialization, handling level-ups.

    Specializations have no XP boundaries, but the band's skill cap (#4585) binds
    them as it binds their parent skill: development stops at it and the surplus
    dissipates. Mutates the ``spec_value`` instance in place and saves it.

    Args:
        spec_value: The CharacterSpecializationValue to develop.
        dev_points: Development points to apply.

    Returns:
        A message naming the cap when points dissipated there, else ``None``.
    """
    cap = stored_skill_cap(spec_value.character)
    name = spec_value.specialization.name
    if cap is not None and spec_value.value >= cap:
        spec_value.development_points = 0
        spec_value.save()
        return skill_cap_message(name, cap) if dev_points > 0 else None

    spec_value.development_points += dev_points

    message = None
    cost = _development_cost(spec_value.value)
    while spec_value.development_points >= cost:
        spec_value.development_points -= cost
        spec_value.value += 1
        if cap is not None and spec_value.value >= cap:
            if spec_value.development_points > 0:
                message = skill_cap_message(name, cap)
            spec_value.development_points = 0
            break
        cost = _development_cost(spec_value.value)

    spec_value.save()
    return message


@transaction.atomic
def process_weekly_training() -> dict[int, set[int]]:
    """Process all training allocations for the weekly tick.

    Iterates every ``TrainingAllocation``, calculates development points,
    applies them to the relevant skill or specialization, consumes AP
    from the character's action point pool, and records a
    ``DevelopmentTransaction`` audit trail entry for each allocation.

    Returns:
        A dict mapping character PKs to sets of trained Skill PKs. For
        specialization training the parent skill PK is included (used by
        the rust system to prevent rust on actively trained skills).
    """
    trained_skills: dict[int, set[int]] = defaultdict(set)

    # Pre-fetch the Teaching skill once for all mentor calculations.
    teaching_skill = _get_teaching_skill()

    active_characters = (
        RosterEntry.objects.active_rosters().exclude_dormant().values("character_sheet")
    )
    allocations = list(
        TrainingAllocation.objects.filter(
            character__in=active_characters,
        ).select_related(
            "character",
            "skill",
            "skill__trait",
            "specialization",
            "specialization__parent_skill",
            "specialization__parent_skill__trait",
            "mentor",
            "mentor__character_sheet__character",
        )
    )

    # Batch-fetch path levels for all involved characters (1 query).
    character_pks = {a.character_id for a in allocations}
    path_levels = _bulk_path_levels(character_pks)

    for allocation in allocations:
        character = allocation.character
        dev_points = calculate_training_development(
            allocation, _teaching_skill=teaching_skill, _path_levels=path_levels
        )

        description = f"Weekly training: {allocation}"
        if allocation.skill:
            train_skill(character, allocation.skill, dev_points, description=description)
            trained_skills[character.pk].add(allocation.skill.pk)
        elif allocation.specialization:
            spec_value, _created = CharacterSpecializationValue.objects.get_or_create(
                character=character,
                specialization=allocation.specialization,
                defaults={"value": 10, "development_points": 0},
            )
            cap_message = _apply_development_to_specialization(spec_value, dev_points)
            trained_skills[character.pk].add(allocation.specialization.parent_skill_id)
            _record_training_transaction(
                character,
                allocation.specialization.parent_skill.trait,
                dev_points,
                description,
                cap_message,
            )
        else:
            continue  # pragma: no cover — XOR constraint prevents this

        # Consume AP. Training still processes if pool is missing or has
        # insufficient AP — allocations represent reserved budget, and the
        # weekly AP regen is assumed to have run before training processing.
        try:
            pool = ActionPointPool.objects.get(character_id=character.pk)
            if not pool.spend(allocation.ap_amount):
                logger.warning(
                    "Insufficient AP for %s: wanted %d, pool has %d",
                    str(character),
                    allocation.ap_amount,
                    pool.current,
                )
        except ActionPointPool.DoesNotExist:
            logger.warning(
                "No AP pool for %s during training processing",
                str(character),
            )

    return dict(trained_skills)


def run_weekly_skill_cron() -> None:
    """Run the full weekly skill development cycle.

    1. Process all training allocations (award dev points, consume AP).
    2. Apply rust to all untrained skills.
    """
    trained_skills = process_weekly_training()
    apply_weekly_rust(trained_skills)


def apply_weekly_rust(trained_skills: dict[int, set[int]]) -> None:
    """Apply weekly rust to all untrained skills.

    Skills that were actively trained or used this week (present in
    ``trained_skills``) are exempt. All other skills accumulate rust
    equal to ``character_level + 5``, capped at the current level's
    development cost.

    Args:
        trained_skills: Dict from ``process_weekly_training()`` mapping
            character PKs to sets of Skill PKs that were active this week.
    """
    active_characters = (
        RosterEntry.objects.active_rosters().exclude_dormant().values("character_sheet")
    )
    all_skill_values = list(
        CharacterSkillValue.objects.filter(
            character__in=active_characters,
        ).select_related("character")
    )

    # Batch-fetch path levels for all characters with skill values (1 query).
    character_pks = {sv.character_id for sv in all_skill_values}
    path_levels = _bulk_path_levels(character_pks)

    for sv in all_skill_values:
        active_skills = trained_skills.get(sv.character_id, set())
        if sv.skill_id in active_skills:
            continue

        char_level = path_levels.get(sv.character_id, 1)
        rust_amount = char_level + 5
        max_rust = _development_cost(sv.value)
        sv.rust_points = min(sv.rust_points + rust_amount, max_rust)
        sv.save()
