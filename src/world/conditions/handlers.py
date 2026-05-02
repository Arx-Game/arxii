"""Per-character handler for active ConditionInstance rows.

Wires onto the ``Character`` typeclass alongside ``character.combat_pulls``.
Mirrors the shape of CharacterCombatPullHandler — caches the active list
on first read; consumers walk the in-memory list. Mutation services
(apply_condition, bulk_apply_conditions, process_round_start/end, etc.)
must call ``invalidate()`` after writing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django.utils.functional import cached_property

from world.conditions.models import (
    ConditionInstance,
    ConditionResistanceModifier,
)

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.conditions.models import DamageType


class CharacterConditionHandler:
    """Handler for a character's active ConditionInstance rows."""

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _active(self) -> list[ConditionInstance]:
        return list(
            ConditionInstance.objects.filter(
                target=self.character,
                is_suppressed=False,
                resolved_at__isnull=True,
            )
            .select_related("condition", "current_stage")
            .prefetch_related(
                Prefetch(
                    "condition__conditionresistancemodifier_set",
                    queryset=ConditionResistanceModifier.objects.select_related("damage_type"),
                    to_attr="template_resistance_modifiers_cached",
                ),
                Prefetch(
                    "current_stage__conditionresistancemodifier_set",
                    queryset=ConditionResistanceModifier.objects.select_related("damage_type"),
                    to_attr="stage_resistance_modifiers_cached",
                ),
            )
        )

    def active(self) -> list[ConditionInstance]:
        """Return all currently-active condition instances on this character."""
        return self._active

    def resistance_modifier(self, damage_type: DamageType | None) -> int:
        """Sum ConditionResistanceModifier values across active instances
        whose damage_type matches (specific) or is null (all-types).

        Walks the cached active list — no DB query past the first access.
        Negative return = vulnerability; positive = resistance.
        """
        if damage_type is None:
            return 0
        total = 0
        for instance in self._active:
            for mod in instance.condition.template_resistance_modifiers_cached:
                if mod.damage_type_id in (damage_type.pk, None):
                    total += mod.modifier_value
            if instance.current_stage_id:
                for mod in instance.current_stage.stage_resistance_modifiers_cached:
                    if mod.damage_type_id in (damage_type.pk, None):
                        total += mod.modifier_value
        return total

    def invalidate(self) -> None:
        """Clear the cached active list. Called by condition mutation services."""
        self.__dict__.pop("_active", None)
