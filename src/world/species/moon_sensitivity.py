"""Lycan moon-control checks (#2845): the pull, the roll, and the loss.

A moon-bound character (holds a distinction carrying the ``moon-bound``
DistinctionTag — Lycans innately, ADR-0179 anchoring) under a strong felt
moon pull rolls a control check each reconcile window. Failure forces the
battle-form shift (`trigger_transformation`, the built involuntary seam) and
applies the shared **Berserk** condition — the same row the fury engine
applies, so the not-in-control derivation, the revert block, and the Restore
to Sense break-out all compose with zero moon-specific state.

Mastery axes (ruled 2026-07-31): character level (tier), thread level on the
species gift, and raw willpower/composure growth. At ``MOON_EXEMPT_LEVEL``+
the check fires only while impaired — condition-driven willpower a full tier
below base (drink, drugs, despair-class conditions).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.species.moon_constants import (
    MOON_BERSERK_DURATION_ROUNDS,
    MOON_BERSERK_SEVERITY,
    MOON_BOUND_TAG,
    MOON_CONTROL_BASE_DIFFICULTY,
    MOON_CONTROL_CHECK_NAME,
    MOON_CONTROL_COMPOSURE_WEIGHT,
    MOON_CONTROL_DIFFICULTY_PER_PULL,
    MOON_CONTROL_RELIEF_PER_LEVEL,
    MOON_CONTROL_WILLPOWER_WEIGHT,
    MOON_EXEMPT_LEVEL,
    MOON_IMPAIRMENT_WILLPOWER_DROP,
    MOON_PULL_CHECK_THRESHOLD,
    MOON_THREAD_RELIEF_CAP,
    MOON_THREAD_RELIEF_PER_LEVEL,
    WOLFS_FURY_GIFT_NAME,
)
from world.species.moon_pull import felt_moon_pull, moon_clarity_instance_value

CANI_UNEASE_MESSAGE = (
    "|wThe moonlight prickles along your spine — something old in your blood "
    "stirs and will not settle while the moon watches.|n"
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType

logger = logging.getLogger(__name__)

BERSERK_CONDITION_NAME = "Berserk"


def is_moon_bound(sheet: CharacterSheet) -> bool:
    """Whether *sheet* holds any distinction tagged ``moon-bound``."""
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    return CharacterDistinction.objects.filter(
        character=sheet, distinction__tags__slug=MOON_BOUND_TAG
    ).exists()


def reconcile_moon_pull(character) -> None:
    """One moon-bound character's control-check window (#2845).

    No-ops for the unbound, the already-Berserk, and anyone below the pull
    threshold. Failure = forced battle-form shift + shared Berserk.
    """
    sheet = character.character_sheet
    if sheet is None or not is_moon_bound(sheet):
        return
    if _active_berserk_instance(character) is not None:
        _rampage_window(character)
        return
    exposure = felt_moon_pull(character, character.location)
    if exposure.pull < MOON_PULL_CHECK_THRESHOLD:
        return
    level = sheet.current_level
    if level >= MOON_EXEMPT_LEVEL and not _is_impaired(sheet):
        return
    if _control_holds(character, sheet, exposure.pull, level):
        return
    _lose_control(character, sheet)


def reconcile_moon_pull_safely(character) -> None:
    """Best-effort moon reconcile for cron call sites (#2845)."""
    from world.species.services import run_reconcile_safely  # noqa: PLC0415

    run_reconcile_safely(character, reconcile_moon_pull, "moon-pull")


def _control_holds(character, sheet: CharacterSheet, pull: int, level: int) -> bool:
    """Roll the moon control check. Fail-open when the check type is missing."""
    from world.checks.services import perform_check  # noqa: PLC0415

    check_type = _ensure_moon_control_check_type()
    if check_type is None:
        logger.warning("moon_control check type unavailable; control holds by default.")
        return True
    difficulty = max(
        0,
        MOON_CONTROL_BASE_DIFFICULTY
        + pull * MOON_CONTROL_DIFFICULTY_PER_PULL
        - level * MOON_CONTROL_RELIEF_PER_LEVEL
        - _thread_relief(sheet),
    )
    result = perform_check(character, check_type, difficulty)
    return result.success_level > 0


def _thread_relief(sheet: CharacterSheet) -> int:
    """Mastery relief from the character's thread on the species gift."""
    from world.magic.models import Thread  # noqa: PLC0415

    thread = Thread.objects.filter(
        owner=sheet,
        target_gift__name=WOLFS_FURY_GIFT_NAME,
        retired_at__isnull=True,
    ).first()
    if thread is None:
        return 0
    return min(MOON_THREAD_RELIEF_CAP, thread.level * MOON_THREAD_RELIEF_PER_LEVEL)


def _is_impaired(sheet: CharacterSheet) -> bool:
    """Condition-driven willpower a full tier (or more) below base (ruled 2026-07-31)."""
    from world.conditions.services import get_condition_modifier_total  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    target = ModifierTarget.objects.filter(target_trait__name__iexact="willpower").first()
    if target is None:
        return False
    return get_condition_modifier_total(sheet, target) <= -MOON_IMPAIRMENT_WILLPOWER_DROP


def _lose_control(character, sheet: CharacterSheet) -> None:
    """Failure consequences: forced shift into the battle form, then Berserk."""
    _force_battle_form_shift(character, sheet)
    _apply_berserk(character)
    character.msg(
        "|rThe moon's pull crests and something older than you answers it — "
        "the beast takes the reins.|n"
    )
    location = character.location
    if location is not None:
        location.msg_contents(
            f"|r{character.key} convulses under the moonlight — and what rises is "
            "not entirely them anymore.|n",
            exclude=[character],
        )


def _force_battle_form_shift(character, sheet: CharacterSheet) -> None:
    """Shift into the battle form via the built involuntary seam, moon-scaled.

    Skips silently when no battle form is provisioned (Berserk still lands) or
    when an alternate self is already active (a voluntary shift preempts the
    forced one — the rage simply takes over the shape they already wear).
    """
    from world.forms.models import ActiveAlternateSelf, AlternateSelf  # noqa: PLC0415
    from world.forms.services.transformation import trigger_transformation  # noqa: PLC0415

    if ActiveAlternateSelf.objects.filter(character=sheet).exists():
        return
    alt = AlternateSelf.objects.filter(character=sheet, combat_profile__isnull=False).first()
    if alt is None:
        from world.species.moon_provisioning import ensure_lycan_battle_form  # noqa: PLC0415

        alt = ensure_lycan_battle_form(sheet)
    clarity = moon_clarity_instance_value(character, character.location)
    trigger_transformation(sheet, alt, cause="moon", instance_value=clarity)


def _apply_berserk(character) -> None:
    """Apply the shared Berserk condition (the same row fury applies)."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=BERSERK_CONDITION_NAME).first()
    if template is None:
        logger.warning("Berserk template missing; moon control loss applied no condition.")
        return
    apply_condition(
        character,
        template,
        severity=MOON_BERSERK_SEVERITY,
        duration_rounds=MOON_BERSERK_DURATION_ROUNDS,
        source_character=character,
    )


def _rampage_window(character) -> None:
    """One out-of-combat rampage window while the moon-swept character rages."""
    from world.combat.berserk_compulsion import berserk_rampage_window  # noqa: PLC0415

    berserk_rampage_window(character)


def _active_berserk_instance(character):
    """The character's active Berserk ConditionInstance, if any."""
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    for instance in get_active_conditions(character):
        if instance.condition.name == BERSERK_CONDITION_NAME:
            return instance
    return None


def _ensure_moon_control_check_type() -> CheckType | None:
    """Lazy-ensure the ``moon_control`` CheckType (willpower + composure).

    Config row named by a code literal (ADR-0171) — also registered in
    ``world.seeds.config_prerequisites`` so it exists after a press.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.services import ensure_stat_trait  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Species",
        defaults={"description": "Species instinct-control checks", "display_order": 97},
    )
    check_type, _ = CheckType.objects.get_or_create(
        name=MOON_CONTROL_CHECK_NAME,
        defaults={
            "category": category,
            "description": "Holding the self against the moon's pull (#2845).",
        },
    )
    for trait_name, weight in (
        ("willpower", MOON_CONTROL_WILLPOWER_WEIGHT),
        ("composure", MOON_CONTROL_COMPOSURE_WEIGHT),
    ):
        trait = ensure_stat_trait(trait_name)
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=trait, defaults={"weight": weight}
        )
    return check_type


def reconcile_cani_unease(character) -> None:
    """Apply/remove the Cani Moonlit Unease with the open night moon (#2845).

    Ruled 2026-07-31: the Cani umbrella (wolves, hounds, all canine-touched)
    carries the unease — khati subspecies stay umbrella families, so no
    wolf-specific subspecies exists or should. Mechanically inert flavor state
    in v1 (PLACEHOLDER); the message fires once, on application.
    """
    from world.conditions.services import (  # noqa: PLC0415
        apply_condition,
        get_active_conditions,
        remove_condition,
    )
    from world.species.factories import ensure_moonlit_unease_condition  # noqa: PLC0415
    from world.species.moon_constants import MOONLIT_UNEASE_NAME  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None or not _is_cani(sheet):
        return
    exposure = felt_moon_pull(character, character.location)
    active = None
    for instance in get_active_conditions(character):
        if instance.condition.name == MOONLIT_UNEASE_NAME:
            active = instance
            break
    if exposure.pull > 0 and active is None:
        template = ensure_moonlit_unease_condition()
        apply_condition(character, template, severity=1, source_character=character)
        character.msg(CANI_UNEASE_MESSAGE)
    elif exposure.pull <= 0 and active is not None:
        remove_condition(character, active.condition)


def _is_cani(sheet: CharacterSheet) -> bool:
    """Whether the sheet's species is (or descends from) the Cani umbrella."""
    from world.species.moon_constants import CANI_SPECIES_NAME  # noqa: PLC0415

    species = sheet.species
    while species is not None:
        if species.name == CANI_SPECIES_NAME:
            return True
        species = species.parent
    return False


def reconcile_cani_unease_safely(character) -> None:
    """Best-effort unease reconcile for the cron sweep (#2845)."""
    from world.species.services import run_reconcile_safely  # noqa: PLC0415

    run_reconcile_safely(character, reconcile_cani_unease, "cani-unease")
