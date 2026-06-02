"""Cached handlers for conditions.

ConditionHandler — generic per-object handler for active ConditionInstance rows.
  Installed as a ``cached_property`` on ``ObjectParent`` so every typeclassed
  object (Character, Room, Exit, Object) exposes ``obj.conditions``.
  Uses the same "active" filter semantics as ``get_active_conditions`` —
  suppression-aware (suppressed_until expiry is respected), no resolved_at gate.
  Caches the active list on first access; subsequent reads and all filter
  methods are query-free.  Mutation services call ``invalidate()`` after writes.

CharacterConditionHandler — Character-specific subclass of ConditionHandler.
  Adds ``resistance_modifier(damage_type)`` with a prefetch of
  ConditionResistanceModifier rows.  Installed on ``Character`` via its own
  ``cached_property``, shadowing the base handler on ObjectParent.

ConditionTemplateReactiveHandler — per-template handler for reactive infrastructure.
  Wraps the template's reactive_triggers M2M and ConditionStatRule rows (from
  achievements), both cached as @cached_property. Services in apply_condition (T10)
  go through template.reactive_handler instead of touching related managers directly,
  preserving the SharedMemoryModel identity-map cache.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.db.models import Prefetch, Q
from django.utils import timezone
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


class ConditionHandler:
    """Generic cached handler for active ConditionInstance rows on any ObjectDB target.

    Installed as ``cached_property`` on ``ObjectParent`` so every typeclassed
    object (Character, Room, Exit, Object) exposes ``obj.conditions``.

    The "active" definition matches ``get_active_conditions`` exactly:
    - Not suppressed (``is_suppressed=False``), OR suppression has expired
      (``suppressed_until`` is non-null and in the past).
    - No filter on ``resolved_at`` — consistent with get_active_conditions.

    Usage::

        instances = obj.conditions.active()          # cached list[ConditionInstance]
        obj.conditions.instances_for_templates({t1}) # Python filter, 0 queries
        obj.conditions.has_template(t)               # Python check, 0 queries
        obj.conditions.invalidate()                  # drop cache; next .active() re-queries
    """

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    @staticmethod
    def _canonical_active_qs(owner: Any) -> Any:
        """Return the canonical active-condition queryset for *owner*.

        Extracted so subclasses can call this and layer extra prefetches on top,
        keeping the filter predicate in exactly one place (parity with
        ``get_active_conditions``).  Suppression-aware; no resolved_at gate.
        """
        # Keep in sync with get_active_conditions in services.py
        return ConditionInstance.objects.filter(
            Q(is_suppressed=False)
            | Q(suppressed_until__isnull=False, suppressed_until__lt=timezone.now()),
            target=owner,
        ).select_related(
            "condition",
            "condition__category",
            "current_stage",
        )

    @cached_property
    def _active(self) -> list[ConditionInstance]:
        return list(self._canonical_active_qs(self._owner))

    def active(self) -> list[ConditionInstance]:
        """Return all currently-active condition instances on this object.

        First call executes one DB query; all subsequent calls return the
        cached list without touching the database.
        """
        return self._active

    def instances_for_templates(
        self,
        templates: Any,
    ) -> list[ConditionInstance]:
        """Return active instances whose template is in *templates*.

        Filters the cached list in Python — zero DB queries after warmup.

        Args:
            templates: Iterable of ConditionTemplate instances to filter by.
        """
        template_pks = {t.pk for t in templates}
        return [inst for inst in self._active if inst.condition_id in template_pks]

    def has_template(self, template: ConditionTemplate) -> bool:
        """Return True if *template* is among the active conditions.

        Zero DB queries after warmup.
        """
        return any(inst.condition_id == template.pk for inst in self._active)

    def invalidate(self) -> None:
        """Drop the internal cache so the next ``active()`` call re-queries the DB.

        Called by condition mutation services (apply_condition, remove_condition,
        bulk_apply_conditions, process_round_end, etc.).
        """
        self.__dict__.pop("_active", None)


class CharacterConditionHandler(ConditionHandler):
    """Character-specific extension of ConditionHandler.

    Adds ``resistance_modifier(damage_type)`` which requires prefetching
    ConditionResistanceModifier rows.  Installed on ``Character`` via its own
    ``cached_property``, shadowing the base ConditionHandler from ObjectParent.

    The active-row filter is inherited from ``ConditionHandler._canonical_active_qs``
    so the predicate is defined in exactly one place (parity with
    ``get_active_conditions`` is structural, not coincidental).
    """

    def __init__(self, character: Character) -> None:
        super().__init__(character)
        self.character = character

    @cached_property
    def _active(self) -> list[ConditionInstance]:
        return list(
            self._canonical_active_qs(self.character).prefetch_related(
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
        from world.achievements.models import ConditionStatRule  # noqa: PLC0415

        rules_by_event: dict[str, list[ConditionStatRule]] = defaultdict(list)
        rules = ConditionStatRule.objects.filter(
            condition=self._template,
        ).select_related("stat")
        for rule in rules:
            rules_by_event[rule.event_type].append(rule)
        return dict(rules_by_event)

    def stat_rules_for_event(self, event_type: str) -> list[ConditionStatRule]:
        return self._stat_rules_by_event.get(event_type, [])
