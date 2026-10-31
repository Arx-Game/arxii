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
from world.mechanics.types import TechniqueEffectContext

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique

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


def effect_modifier_total(
    sheet: "CharacterSheet | None", key: str, *, kind_wide: bool = True
) -> int:
    """The unclamped sum of every modifier on maneuver effect ``key`` for ``sheet``.

    With ``kind_wide=False`` only targets scoped to this effect itself count; a target
    that names just the kind of effect (it already reaches techniques) is left out.

    The same targets ``effect_value`` counts, without the base value and without the floor
    or cap, so a caller that scales the base itself (a lance doubling a charge) can clamp
    once, on its own total. With no sheet there are no modifiers: 0.
    """
    if sheet is None:
        return 0
    return _modifier_total(sheet, _matching_targets(get_maneuver_effect(key), kind_wide=kind_wide))


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


def _matching_targets(effect: ManeuverEffect, *, kind_wide: bool = True) -> list[ModifierTarget]:
    """The active maneuver-effect targets scoped to ``effect`` or (``kind_wide``) its kind.

    A target with any technique scope belongs to the technique reader and never matches
    a maneuver, though it names a kind (#4822).
    """
    scope = Q(scope_maneuver_effect_id=effect.pk)
    if kind_wide:
        scope |= Q(scope_effect_kind=effect.kind)
    return list(
        ModifierTarget.objects.filter(
            category__name=MANEUVER_EFFECT_CATEGORY_NAME,
            is_active=True,
            scope_technique__isnull=True,
            scope_gift__isnull=True,
            scope_technique_function="",
            scope_damage_type__isnull=True,
            scope_resonance__isnull=True,
        ).filter(scope)
    )


def technique_effect_context(
    sheet: "CharacterSheet",
    technique: "Technique",
    *,
    damage_type_id: int | None = None,
) -> TechniqueEffectContext:
    """Describe ``technique`` as cast by ``sheet`` for the technique-scoped targets."""
    from world.magic.specialization.services import gift_resonances_for  # noqa: PLC0415

    gift = technique.gift
    gift_ids = {gift.pk}
    if gift.parent_id is not None:
        gift_ids.add(gift.parent_id)
    return TechniqueEffectContext(
        technique_id=technique.pk,
        gift_ids=frozenset(gift_ids),
        functions=frozenset(tag.function for tag in technique.cached_function_tags),
        resonance_ids=frozenset(r.pk for r in gift_resonances_for(sheet.character, gift)),
        damage_type_id=damage_type_id,
    )


def technique_effect_targets(kind: str) -> list[ModifierTarget]:
    """Active maneuver-effect targets for ``kind`` that name no one maneuver effect.

    Kind-only targets (no technique scope) and technique-scoped ones both come back;
    ``technique_effect_total`` narrows them to a cast. One query.
    """
    return list(
        ModifierTarget.objects.filter(
            category__name=MANEUVER_EFFECT_CATEGORY_NAME,
            is_active=True,
            scope_effect_kind=kind,
            scope_maneuver_effect__isnull=True,
        )
    )


def technique_effect_total(
    sheet: "CharacterSheet | None",
    context: TechniqueEffectContext,
    targets: list[ModifierTarget],
) -> int:
    """The unclamped sum of ``sheet``'s modifiers over the ``targets`` that fit ``context``.

    A target fits when every technique scope it sets matches the cast. No sheet, no
    modifiers: 0.
    """
    if sheet is None:
        return 0
    return _modifier_total(sheet, [t for t in targets if _fits(t, context)])


def _fits(target: ModifierTarget, context: TechniqueEffectContext) -> bool:
    """Whether every technique scope ``target`` sets matches ``context``."""
    checks = (
        (target.scope_technique_id, context.technique_id == target.scope_technique_id),
        (target.scope_gift_id, target.scope_gift_id in context.gift_ids),
        (
            target.scope_technique_function,
            target.scope_technique_function in context.functions,
        ),
        (target.scope_damage_type_id, context.damage_type_id == target.scope_damage_type_id),
        (target.scope_resonance_id, target.scope_resonance_id in context.resonance_ids),
    )
    return all(matches for scope, matches in checks if scope)


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
