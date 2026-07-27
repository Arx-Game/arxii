"""Aging services (#2756): birthday tick, old-age decline, and the death sweep.

Three IC-cadence cron entry points (registered in world.game_clock.tasks):

* ``run_birthday_tick`` — advances ``matured_years`` for every birthday that
  fell inside the elapsed IC window (AFK-safe range query; time skips simply
  process the whole elapsed range).
* ``run_decline_checks`` — the old-age stamina check. Difficulty derives from
  biological age (never accumulated ticks), so freezing stops the curve,
  withering deepens it, and clock re-anchors land correctly.
* ``run_death_sweep`` — resolves stamped dying windows through ``_mark_dead``
  (estates settlement opens there, giving the deathbed its scene first).
"""

import calendar
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import LifecycleState
from world.checks.services import perform_check
from world.conditions.services import apply_condition, get_condition_instance
from world.progression.services.maturation import (
    available_points,
    milestone_count,
    sync_maturation_spends,
)
from world.vitals.constants import (
    AGING_CHECK_TYPE_NAME,
    FRAILTY_CONDITION_NAME,
    CharacterLifeState,
)
from world.vitals.models import CharacterVitals
from world.vitals.services import (
    _mark_dead,
    frailty_floor_reached,
    get_vitals_consequence_config,
    recompute_max_health,
)

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate
    from world.vitals.models import VitalsConsequenceConfig

logger = logging.getLogger(__name__)

# PLACEHOLDER copy — player-visible; admin/lore pass pending (Apostate rewrite).
MILESTONE_MESSAGE = (
    "|wPLACEHOLDER|n Another year settles into your bones — and with it, a "
    "Maturation Point. Spend it from your character sheet."
)
DYING_WINDOW_MESSAGE = (
    "|rPLACEHOLDER|n Age has finally caught you: your body is failing. The "
    "time that remains is yours to settle your affairs."
)


def _birthday_occurrences(month: int, day: int, ic_start: datetime, ic_end: datetime) -> int:
    """How many times the (month, day) birthday fell in (ic_start, ic_end].

    Feb 29 birthdays clamp to that year's last day of February. The loop spans
    at most the elapsed years + 1 — a 20-year time skip is 21 iterations.
    """
    count = 0
    for year in range(ic_start.year, ic_end.year + 1):
        clamped_day = min(day, calendar.monthrange(year, month)[1])
        candidate = datetime(year, month, clamped_day, tzinfo=ic_start.tzinfo)
        if ic_start < candidate <= ic_end:
            count += 1
    return count


def _aging_sheets() -> "list[CharacterSheet]":
    """Alive, non-paused sheets of species that age (null species = mortal)."""
    from django.db.models import Q  # noqa: PLC0415

    return list(
        CharacterSheet.objects.filter(
            lifecycle_state=LifecycleState.ALIVE,
            aging_paused=False,
        ).filter(Q(species__isnull=True) | Q(species__eternal_youth=False))
    )


def run_birthday_tick(*, ic_start: datetime, ic_end: datetime) -> int:
    """Advance matured_years for birthdays inside the window; return sheets aged."""
    aged = 0
    for sheet in _aging_sheets():
        if sheet.birthday_month is None or sheet.birthday_day is None:
            continue
        occurrences = _birthday_occurrences(
            sheet.birthday_month, sheet.birthday_day, ic_start, ic_end
        )
        if occurrences == 0:
            continue
        old_milestones = milestone_count(sheet.matured_years)
        sheet.matured_years += occurrences
        sheet.save(update_fields=["matured_years"])
        sync_maturation_spends(sheet)
        aged += 1
        if milestone_count(sheet.matured_years) > old_milestones and available_points(sheet) > 0:
            character = sheet.character
            if character is not None:
                character.msg(MILESTONE_MESSAGE)
    return aged


def _aging_check_type() -> "CheckType | None":
    """Look up (or sample) the stamina-legged Aging Resistance CheckType.

    Content-repo-owned rows (#2698): looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. Returns None when unauthored — decline
    checks are skipped with a log, mirroring the Bleeding Out seeding-gap
    behavior.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415
    from world.vitals.services import _ensure_survival_category  # noqa: PLC0415

    # An authored row wins outright — only the sample-creation path needs the
    # Survival category to exist first.
    check = CheckType.objects.filter(name=AGING_CHECK_TYPE_NAME, is_active=True).first()
    if check is not None:
        return check
    category = _ensure_survival_category()
    if category is None:
        return None
    check = authored_or_sample(
        CheckType,
        {"category": category, "description": "Resist the toll of old age."},
        name=AGING_CHECK_TYPE_NAME,
    )
    if check is None:
        return None
    stamina = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
        name="stamina",
    )
    if stamina is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": Decimal("1.00")}, check_type=check, trait=stamina
        )
    return check


def _frailty_template() -> "ConditionTemplate | None":
    """The Frailty ConditionTemplate, or None when unauthored (skip + log)."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    return ConditionTemplate.objects.filter(name=FRAILTY_CONDITION_NAME).first()


def _deepen_frailty(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — condition services operate on the puppet object
    template: "ConditionTemplate",
    severity_delta: int,
) -> None:  # noqa: OBJECTDB_PARAM
    """Grow (or first-apply) the character's Frailty by ``severity_delta``."""
    instance = get_condition_instance(character, template)
    if instance is None:
        apply_condition(
            character,
            template,
            severity=severity_delta,
            source_description="the toll of old age",
        )
        return
    instance.severity += severity_delta
    instance.save(update_fields=["severity"])


def run_decline_checks(*, ic_now: datetime) -> int:
    """Run the IC-monthly aging check for every declining character.

    Difficulty = config.aging_difficulty_per_year x years past the species
    decline_start_age, computed from biological age. Failure deepens Frailty
    by ``frailty_fail_severity``, partial success by
    ``frailty_partial_severity``; the deepened Frailty is folded into max
    health, and crossing the aging floor stamps the dying-window deadline.
    Returns the number of characters checked.
    """
    check_type = _aging_check_type()
    if check_type is None:
        logger.warning("Aging check type unauthored; decline checks skipped.")
        return 0
    template = _frailty_template()
    if template is None:
        logger.warning("Frailty condition unauthored; decline checks skipped.")
        return 0

    config = get_vitals_consequence_config()
    checked = 0
    for sheet in _aging_sheets():
        species = sheet.species
        start = species.decline_start_age if species else 60
        if start is None or sheet.biological_age <= start:
            continue
        character = sheet.character
        if character is None:
            continue
        difficulty = config.aging_difficulty_per_year * (sheet.biological_age - start)
        result = perform_check(character, check_type, target_difficulty=difficulty)
        checked += 1
        if result.outcome is None:
            continue
        level = int(result.outcome.success_level)
        if level <= -1:
            delta = config.frailty_fail_severity
        elif level == 0:
            delta = config.frailty_partial_severity
        else:
            continue
        _deepen_frailty(character, template, delta)
        recompute_max_health(sheet)
        _maybe_open_dying_window(sheet, ic_now=ic_now, config=config)
    return checked


def _maybe_open_dying_window(
    sheet: CharacterSheet, *, ic_now: datetime, config: "VitalsConsequenceConfig"
) -> None:
    """Stamp the dying-window deadline once the aging floor is crossed."""
    if not frailty_floor_reached(sheet):
        return
    vitals = sheet.vitals_or_none
    if vitals is None or vitals.aging_death_ic_deadline is not None:
        return
    vitals.aging_death_ic_deadline = ic_now + timedelta(days=config.aging_death_window_ic_days)
    vitals.save(update_fields=["aging_death_ic_deadline"])
    character = sheet.character
    if character is not None:
        character.msg(DYING_WINDOW_MESSAGE)
    logger.warning(
        "Dying window opened for %s: old-age death resolves at IC %s.",
        sheet,
        vitals.aging_death_ic_deadline,
    )


def run_death_sweep(*, ic_now: datetime) -> int:
    """Resolve dying windows whose IC deadline has passed. Returns deaths."""
    due = CharacterVitals.objects.filter(
        aging_death_ic_deadline__lte=ic_now,
        life_state=CharacterLifeState.ALIVE,
    )
    deaths = 0
    for vitals in due:
        _mark_dead(vitals.character_sheet)
        deaths += 1
    return deaths
