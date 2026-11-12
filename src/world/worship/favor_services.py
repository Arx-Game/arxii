"""Favor modifiers and the earning rate (#4333, design 1a and 1b).

Every being has one ``ModifierTarget`` in each of two categories,
``favor_invocation`` and ``favor_earning`` (``ModifierTarget.target_being``), and
each category has one "any being" target (``target_being`` null). Any modifier
source authored against those targets (a distinction effect, a condition effect,
a crafting recipe modifier, a covenant role bonus) reaches a character through
``favor_modifier_total``, the one reader.

Each category also has one patron target (``ModifierTarget.targets_patron``, #4341):
"the character's own patron", resolved when read. It reaches a character only for a
being she is the Chosen of (``chosen_patronage_of``), so the Chosen earning bonus and
invocation ease live as effects of the designated Chosen distinction
(``ChosenFavorConfig.chosen_distinction``) on these targets, and a pact holder never
picks them up.

Targets are created explicitly, never by a signal: by the Deity Editor's
``save_being``, by the backfill data migration ``0224_being_favor_targets``, and by
the seeds. The patron targets (``ensure_patron_modifier_targets``) come with every
being's targets and when the Chosen favor admin opens. A missing target reads as 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.mechanics.constants import (
    FAVOR_EARNING_CATEGORY_NAME,
    FAVOR_INVOCATION_CATEGORY_NAME,
)
from world.worship.constants import FAVOR_EARNING_BASE_PERCENT

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import ModifierCategory, ModifierTarget
    from world.worship.models import DevotionStanding, WorshippedBeing

#: (category name, label used in target names, category description).
_FAVOR_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    (
        FAVOR_INVOCATION_CATEGORY_NAME,
        "favor invocation",
        "Difficulty points eased on the invocation check for a being (#4333).",
    ),
    (
        FAVOR_EARNING_CATEGORY_NAME,
        "favor earning",
        "Percentage points added to the earning rate with a being (#4333).",
    ),
)
ANY_BEING_TARGET_PREFIX = "Any being"
PATRON_TARGET_PREFIX = "Your patron"
_TARGET_NAME_MAX_LENGTH = 100  # ModifierTarget.name


def _being_target_name(being: WorshippedBeing, label: str) -> str:
    """ "<being> <label>", the being's name shortened to fit the target name column."""
    suffix = f" {label}"
    return f"{being.name[: _TARGET_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _favor_category(name: str, description: str) -> ModifierCategory:
    from world.mechanics.models import ModifierCategory  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(
        name=name, defaults={"description": description}
    )
    return category


def ensure_being_modifier_targets(being: WorshippedBeing) -> list[ModifierTarget]:
    """Get-or-create ``being``'s two favor targets and the two "any being" targets.

    Idempotent. Returns the being's own targets, invocation first. A target that
    already exists keeps its name, so a renamed being keeps working; only the
    (category, being) pair identifies it.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    ensure_patron_modifier_targets()
    targets: list[ModifierTarget] = []
    for category_name, label, description in _FAVOR_CATEGORIES:
        category = _favor_category(category_name, description)
        ModifierTarget.objects.get_or_create(
            category=category,
            name=f"{ANY_BEING_TARGET_PREFIX} {label}",
            defaults={"target_being": None},
        )
        target = ModifierTarget.objects.filter(category=category, target_being=being).first()
        if target is None:
            # A target that already carries the being's name but lost its link
            # (a rolled-back release) is linked again rather than duplicated.
            target, _ = ModifierTarget.objects.get_or_create(
                category=category,
                name=_being_target_name(being, label),
                defaults={"target_being": being},
            )
            if target.target_being_id != being.pk:
                target.target_being = being
                target.save(update_fields=["target_being"])
        targets.append(target)
    return targets


def ensure_patron_modifier_targets() -> list[ModifierTarget]:
    """Get-or-create the two patron targets (#4341), invocation first. Idempotent."""
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    targets: list[ModifierTarget] = []
    for category_name, label, description in _FAVOR_CATEGORIES:
        category = _favor_category(category_name, description)
        target = ModifierTarget.objects.filter(category=category, targets_patron=True).first()
        if target is None:
            target, _ = ModifierTarget.objects.get_or_create(
                category=category,
                name=f"{PATRON_TARGET_PREFIX} {label}",
                defaults={"targets_patron": True, "target_being": None},
            )
            if not target.targets_patron:
                # A same-named row staff made by hand before the flag existed.
                target.targets_patron = True
                target.target_being = None
                target.save(update_fields=["targets_patron", "target_being"])
        targets.append(target)
    return targets


def _target_total(sheet: CharacterSheet, targets) -> int:
    from world.conditions.services import get_condition_modifier_total  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    return sum(
        get_modifier_total(sheet, target) + get_condition_modifier_total(sheet, target)
        for target in targets.select_related("category")
    )


def patron_modifier_total(sheet: CharacterSheet, being: WorshippedBeing, category_name: str) -> int:
    """The character's patron-target total of one favor category for ``being`` (#4341).

    0 unless she is ``being``'s Chosen (``chosen_patronage_of``): the patron target means
    her own patron, and a pact holder's patron is not one. Displays show this part as the
    Chosen line; ``favor_modifier_total`` already includes it.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    if chosen_patronage_of(sheet, being) is None:
        return 0
    targets = ModifierTarget.objects.filter(
        category__name=category_name, is_active=True, targets_patron=True
    )
    return _target_total(sheet, targets)


def favor_modifier_total(sheet: CharacterSheet, being: WorshippedBeing, category_name: str) -> int:
    """The character's total of one favor category for ``being``, from every source.

    Sums, over every target in the category whose ``target_being`` is ``being`` or
    null (any being), ``get_modifier_total`` (eager ``CharacterModifier`` rows such
    as distinctions, crafted items, the equipment walk with covenant roles counted
    once) and ``get_condition_modifier_total`` (active conditions). The patron target
    is not an any-being target: it is added through ``patron_modifier_total`` only for
    a being she is the Chosen of (#4341).
    """
    return general_favor_modifier_total(sheet, being, category_name) + patron_modifier_total(
        sheet, being, category_name
    )


def general_favor_modifier_total(
    sheet: CharacterSheet, being: WorshippedBeing, category_name: str
) -> int:
    """``favor_modifier_total`` without the patron target: the being's own targets and
    the any-being one. Displays that show the patron part as its own Chosen line read
    this for the rest, so nothing is counted twice."""
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    targets = (
        ModifierTarget.objects.filter(category__name=category_name, is_active=True)
        .filter(Q(target_being=being) | Q(target_being__isnull=True))
        .exclude(targets_patron=True)
    )
    return _target_total(sheet, targets)


def chosen_distinction_patron_value(category_name: str) -> int:
    """What the designated Chosen distinction adds at rank 1 on one favor category's patron
    target (#4341), for the admin previews that show a Chosen column. 0 when no
    distinction is designated or it has no effect there."""
    from world.distinctions.models import DistinctionEffect  # noqa: PLC0415
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    distinction_id = get_chosen_favor_config().chosen_distinction_id
    if distinction_id is None:
        return 0
    effects = DistinctionEffect.objects.filter(
        distinction_id=distinction_id,
        target__category__name=category_name,
        target__targets_patron=True,
        target__is_active=True,
    )
    return sum(effect.get_value_at_rank(1) for effect in effects)


def chosen_standing_q() -> Q:
    """A standing that makes its character the being's Chosen (#4341): a patronage whose
    valence is set and is not PACT (devotional or antagonistic), not released."""
    from world.worship.models import PatronageValence  # noqa: PLC0415

    return Q(valence__isnull=False, released_at__isnull=True) & ~Q(valence=PatronageValence.PACT)


def active_patronage_of(sheet: CharacterSheet, being: WorshippedBeing) -> DevotionStanding | None:
    """The character's active patronage of ``being`` of any valence, a pact's included,
    or None. Chosen readers use ``chosen_patronage_of``."""
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    return DevotionStanding.objects.filter(
        character_sheet=sheet,
        being=being,
        valence__isnull=False,
        released_at__isnull=True,
    ).first()


def chosen_patronage_of(sheet: CharacterSheet, being: WorshippedBeing) -> DevotionStanding | None:
    """The character's Chosen patronage of ``being`` (she is its Chosen), or None (#4341).

    A PACT patronage is not one: a pact holder gets none of the Chosen bonuses.
    """
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    return (
        DevotionStanding.objects.filter(character_sheet=sheet, being=being)
        .filter(chosen_standing_q())
        .first()
    )


def chosen_patronages_for(sheet: CharacterSheet) -> list[DevotionStanding]:
    """The character's Chosen patronages (#4341), highest favor first."""
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    return list(
        DevotionStanding.objects.filter(character_sheet=sheet)
        .filter(chosen_standing_q())
        .select_related("being")
        .order_by("-favor")
    )


def earning_rate(sheet: CharacterSheet, being: WorshippedBeing) -> int:
    """The percentage applied to all favor ``sheet`` earns with ``being`` (design 1a).

    100, plus the character's favor earning total for it (the Chosen bonus is a modifier
    on the patron target from the Chosen distinction, #4341), plus what the worn pieces
    carrying a facet the being favors add (#4520). Never below 0.
    """
    from world.worship.worn_services import worn_meaning  # noqa: PLC0415

    rate = FAVOR_EARNING_BASE_PERCENT
    rate += favor_modifier_total(sheet, being, FAVOR_EARNING_CATEGORY_NAME)
    rate += worn_meaning(sheet, being).earning_percent
    return max(rate, 0)
