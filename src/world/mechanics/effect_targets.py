"""The maneuver effect reader (#4783).

``effect_value`` is the one place a maneuver's number is read: the effect's catalog base
value plus every modifier total a character has on a target scoped to that effect (or to
its kind). Combat and scene maneuvers call it instead of a constant.
"""

from typing import TYPE_CHECKING

from django.db.models import Q

from world.conditions.services import get_condition_modifier_total
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierTarget
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
    if sheet is None:
        return _clamp(effect.kind, effect.base_value)
    targets = ModifierTarget.objects.filter(
        category__name=MANEUVER_EFFECT_CATEGORY_NAME, is_active=True
    ).filter(Q(scope_maneuver_effect_id=effect.pk) | Q(scope_effect_kind=effect.kind))
    total = effect.base_value
    for target in targets:
        total += get_modifier_total(sheet, target) + get_condition_modifier_total(sheet, target)
    return _clamp(effect.kind, total)


def _clamp(kind: str, value: int) -> int:
    """Floor at 0; cap partial protection at 100."""
    value = max(0, value)
    if kind == EffectKind.PARTIAL_PROTECTION:
        return min(value, PARTIAL_PROTECTION_CAP)
    return value
