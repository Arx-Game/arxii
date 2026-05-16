"""Cached handlers for conditions.

CharacterConditionHandler — per-character handler for active ConditionInstance rows.
  Wires onto the ``Character`` typeclass alongside ``character.combat_pulls``.
  Mirrors the shape of CharacterCombatPullHandler — caches the active list
  on first read; consumers walk the in-memory list. Mutation services
  (apply_condition, bulk_apply_conditions, process_round_start/end, etc.)
  must call ``invalidate()`` after writing.

ConditionTemplateReactiveHandler — per-template handler for reactive infrastructure.
  Wraps the template's reactive_triggers M2M and ConditionStatRule rows (from
  achievements), both cached as @cached_property. Services in apply_condition (T10)
  go through template.reactive_handler instead of touching related managers directly,
  preserving the SharedMemoryModel identity-map cache.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from django.utils.functional import cached_property

from world.conditions.models import (
    ConditionInstance,
    ConditionResistanceModifier,
)

if TYPE_CHECKING:
    from flows.models.triggers import TriggerDefinition
    from typeclasses.characters import Character
    from world.achievements.models import ConditionStatRule
    from world.conditions.models import ConditionTemplate, DamageType


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


class ConditionTemplateReactiveHandler:
    """Cached accessor for reactive infrastructure on a ConditionTemplate.

    Wraps:
    - The template's reactive_triggers M2M, evaluated once and stored.
    - The achievements.ConditionStatRule rows that reference this template,
      bucketed by event_type, evaluated once and stored.

    Both attributes are @cached_property; the handler instance itself is
    cached on ConditionTemplate via @cached_property. ConditionTemplate is
    a SharedMemoryModel so the same handler instance is reused across
    apply_condition calls for the lifetime of the model instance.

    Cache invalidation: not required for the initial slice — content is
    seeded at startup and not mutated at runtime. When authored content
    evolves at runtime (admin add/edit), server restart or explicit handler
    eviction is required. Follow-up work.
    """

    def __init__(self, template: ConditionTemplate) -> None:
        self._template = template

    @cached_property
    def reactive_trigger_definitions(self) -> list[TriggerDefinition]:
        return list(self._template.reactive_triggers.all())

    @cached_property
    def _stat_rules_by_event(self) -> dict[str, list[ConditionStatRule]]:
        from world.achievements.models import ConditionStatRule  # noqa: PLC0415 — cross-app cycle

        rules_by_event: dict[str, list[ConditionStatRule]] = defaultdict(list)
        rules = ConditionStatRule.objects.filter(
            condition=self._template,
        ).select_related("stat")
        for rule in rules:
            rules_by_event[rule.event_type].append(rule)
        return dict(rules_by_event)

    def stat_rules_for_event(self, event_type: str) -> list[ConditionStatRule]:
        return self._stat_rules_by_event.get(event_type, [])
