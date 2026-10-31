"""The maneuver effect reader (#4783).

``effect_value`` is the one place a maneuver's number is read: the effect's catalog base
value plus every modifier total a character has on a target scoped to that effect (or to
its kind). Combat and scene maneuvers call it instead of a constant.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db.models import Q

from world.conditions.services import get_condition_modifier_total
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ManeuverEffect, ModifierTarget
from world.mechanics.services import get_modifier_total

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

PARTIAL_PROTECTION_CAP = 100


def effect_value(sheet: "CharacterSheet | None", key: str) -> int:
    """The value of maneuver effect ``key`` for ``sheet``: base plus its modifiers.

    A target counts when it is active, sits in the maneuver effect category and is scoped to
    this effect, or to this effect's kind. A target with neither scope matches nothing. Each
    target contributes its modifier total (distinctions, gear, vow scaling) and its
    active-condition total. The result is never below 0, and partial protection never
    above 100 (a stop of more than all of the damage means nothing). With no sheet there
    are no modifiers, so the base value comes back.
    """
    effect = get_maneuver_effect(key)
    return _clamp(effect.kind, effect.base_value + effect_modifier_total(sheet, key))


def effect_modifier_total(sheet: "CharacterSheet | None", key: str) -> int:
    """The unclamped sum of every modifier on maneuver effect ``key`` for ``sheet``.

    The same targets ``effect_value`` counts, without the base value and without the floor
    or cap, so a caller that scales the base itself (a lance doubling a charge) can clamp
    once, on its own total. With no sheet there are no modifiers: 0.
    """
    if sheet is None:
        return 0
    return _modifier_total(sheet, _matching_targets(get_maneuver_effect(key)))


def effect_values(sheets: Iterable["CharacterSheet"], key: str) -> dict[int, int]:
    """``effect_value`` for several sheets at once, keyed by sheet pk.

    The catalog row and its matching targets are read once for the whole batch; only each
    sheet's own modifier totals are read per sheet. For a maneuver several characters
    perform together (every ally covering one fleer).
    """
    effect = get_maneuver_effect(key)
    targets = _matching_targets(effect)
    return {
        sheet.pk: _clamp(effect.kind, effect.base_value + _modifier_total(sheet, targets))
        for sheet in sheets
    }


def _matching_targets(effect: ManeuverEffect) -> list[ModifierTarget]:
    """The active maneuver-effect targets scoped to ``effect`` or to its kind."""
    return list(
        ModifierTarget.objects.filter(
            category__name=MANEUVER_EFFECT_CATEGORY_NAME, is_active=True
        ).filter(Q(scope_maneuver_effect_id=effect.pk) | Q(scope_effect_kind=effect.kind))
    )


def _modifier_total(sheet: "CharacterSheet", targets: list[ModifierTarget]) -> int:
    """``sheet``'s modifier and active-condition totals summed over ``targets``."""
    return sum(
        get_modifier_total(sheet, target) + get_condition_modifier_total(sheet, target)
        for target in targets
    )


def _clamp(kind: str, value: int) -> int:
    """Floor at 0; cap partial protection at 100."""
    value = max(0, value)
    if kind == EffectKind.PARTIAL_PROTECTION:
        return min(value, PARTIAL_PROTECTION_CAP)
    return value
