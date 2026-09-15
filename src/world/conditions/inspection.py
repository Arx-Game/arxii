"""Authoring diagnostics for condition mechanics (#3715).

A condition reference proves only that a ``ConditionTemplate`` exists. This
module separates that fact from recognized runtime wiring and deliberately
leaves unrecognized wiring for a human to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Prefetch

from world.conditions.constants import BreakFreeMode
from world.conditions.models import (
    ConditionCapabilityEffect,
    ConditionCheckModifier,
    ConditionDamageOverTime,
    ConditionModifierEffect,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
)


class ConditionMechanicsState(StrEnum):
    """The state of a referenced condition's recognizable mechanics."""

    REFERENCED = "referenced"
    WIRED = "wired"
    MANUAL_VERIFICATION = "manual_verification"


@dataclass(frozen=True)
class ConditionMechanicsDiagnostic:
    """Inspection result for one referenced ``ConditionTemplate``.

    ``referenced`` is always true when this result is returned: the technique
    payload has a foreign key to the condition. ``channels`` names only
    consumers this inspector knows how to recognize. An empty channel list is
    intentionally ``MANUAL_VERIFICATION``, not a claim that the condition is
    inert.
    """

    condition_id: int
    condition_name: str
    state: ConditionMechanicsState
    referenced: bool
    channels: tuple[str, ...]

    @property
    def requires_manual_verification(self) -> bool:
        """Whether staff must check behavior outside the recognized channels."""
        return self.state is ConditionMechanicsState.MANUAL_VERIFICATION

    def as_text(self) -> str:
        """Return concise staff-facing diagnostic text."""
        if self.channels:
            labels = [condition_channel_label(channel) for channel in self.channels]
            return (
                f"{self.condition_name}: referenced condition exists; wired ({', '.join(labels)})"
            )
        return (
            f"{self.condition_name}: referenced condition exists; "
            "requires manual verification (no recognized channel)"
        )


# Stable channel names are suitable for tests and admin text. They intentionally
# describe authored data, rather than making a claim about the eventual effect.
_CHANNEL_LABELS = {
    "capability_effect": "capability effect",
    "modifier_effect": "stat modifier",
    "check_modifier": "check modifier",
    "resistance_modifier": "resistance modifier",
    "damage_over_time": "damage over time",
    "category.alters_behavior": "category alters behavior",
    "category.grants_intangibility": "category grants intangibility",
    "category.conceals_from_perception": "category conceals from perception",
    "combat.affects_turn_order": "turn order",
    "combat.turn_order_modifier": "turn order",
    "combat.draws_aggro": "aggro",
    "combat.aggro_priority": "aggro",
    "combat.break_free": "break free",
    "combat.exploitable_tiers": "exploitable tiers",
    "combat.upkeep_anima": "anima upkeep",
    "combat.reactive_anima": "reactive anima",
    "combat.passive_decay": "passive decay",
    "combat.clash_lock": "clash lock",
    "combat.corruption": "corruption",
    "property": "property",
    "reactive_trigger": "reactive trigger",
    "stage": "stage progression",
    "stage_entry": "stage entry",
    "damage_interaction": "damage interaction",
    "condition_interaction": "condition interaction",
    "treatment_target": "treatment target",
    "achievement_stat_rule": "achievement stat rule",
}


def condition_channel_label(channel: str) -> str:
    """Return the human-facing label for a diagnostic channel."""
    return _CHANNEL_LABELS.get(channel, channel)


def condition_template_prefetches(*, prefix: str = "") -> list[Prefetch]:
    """Prefetch every relation read by ``inspect_condition_template``.

    ``prefix`` is the path from the queryset model to the template. For
    example, ``condition__`` is used by a technique payload queryset. The
    normal Django prefetch cache is used deliberately; condition-owned rows
    must not be copied into identity-mapped ``to_attr`` attributes.
    """
    stage_queryset = ConditionStage.objects.prefetch_related(
        # Normal Django cache is required here; ``to_attr`` is prohibited for
        # identity-mapped condition rows (ADR-0263).
        Prefetch("properties"),  # noqa: PREFETCH_STRING
        Prefetch("on_entry_conditions"),  # noqa: PREFETCH_STRING
    )
    return [
        Prefetch(
            f"{prefix}conditioncapabilityeffect_set",
            queryset=ConditionCapabilityEffect.objects.all(),
        ),
        Prefetch(
            f"{prefix}conditionmodifiereffect_set",
            queryset=ConditionModifierEffect.objects.all(),
        ),
        Prefetch(
            f"{prefix}conditioncheckmodifier_set",
            queryset=ConditionCheckModifier.objects.all(),
        ),
        Prefetch(
            f"{prefix}conditionresistancemodifier_set",
            queryset=ConditionResistanceModifier.objects.all(),
        ),
        Prefetch(
            f"{prefix}conditiondamageovertime_set",
            queryset=ConditionDamageOverTime.objects.all(),
        ),
        Prefetch(f"{prefix}stages", queryset=stage_queryset),
        Prefetch(f"{prefix}properties"),
        Prefetch(f"{prefix}reactive_triggers"),
        Prefetch(f"{prefix}damage_interactions"),
        Prefetch(f"{prefix}interactions_as_primary"),
        Prefetch(f"{prefix}interactions_as_secondary"),
        Prefetch(f"{prefix}treatments"),
        Prefetch(f"{prefix}stat_rules_for"),
    ]


def _related_values(template: ConditionTemplate, relation_name: str) -> list[object]:
    """Read a relation through Django's normal, invalidatable prefetch cache."""
    relation = getattr(template, relation_name)
    return list(relation.all())


def _stage_values(template: ConditionTemplate) -> list[ConditionStage]:
    """Read stages through Django's normal prefetch cache."""
    return list(template.stages.all())


def inspect_condition_template(template: ConditionTemplate) -> ConditionMechanicsDiagnostic:
    """Classify recognizable mechanics on a condition template.

    The inspector is intentionally conservative. Any recognized channel makes
    the condition ``WIRED``. No recognized channel is ``MANUAL_VERIFICATION``
    because custom consumers may exist outside this catalog; it is never called
    inert.
    """
    channels: list[str] = []

    relation_specs = (
        ("conditioncapabilityeffect_set", "capability_effect"),
        ("conditionmodifiereffect_set", "modifier_effect"),
        ("conditioncheckmodifier_set", "check_modifier"),
        ("conditionresistancemodifier_set", "resistance_modifier"),
        ("conditiondamageovertime_set", "damage_over_time"),
        ("properties", "property"),
        ("reactive_triggers", "reactive_trigger"),
        ("damage_interactions", "damage_interaction"),
        ("interactions_as_primary", "condition_interaction"),
        ("interactions_as_secondary", "condition_interaction"),
        ("treatments", "treatment_target"),
        ("stat_rules_for", "achievement_stat_rule"),
    )
    for relation_name, channel in relation_specs:
        if _related_values(template, relation_name) and channel not in channels:
            channels.append(channel)

    category = template.category
    category_flags = (
        (category.alters_behavior, "category.alters_behavior"),
        (category.grants_intangibility, "category.grants_intangibility"),
        (category.conceals_from_perception, "category.conceals_from_perception"),
        # ``is_negative`` is presentation/filter metadata, not a bearer effect.
        # It must not make an otherwise empty condition appear wired.
    )
    for enabled, channel in category_flags:
        if enabled:
            channels.append(channel)

    combat_flags = (
        (template.affects_turn_order, "combat.affects_turn_order"),
        (template.turn_order_modifier != 0, "combat.turn_order_modifier"),
        (template.draws_aggro, "combat.draws_aggro"),
        (template.aggro_priority != 0, "combat.aggro_priority"),
        (template.break_free_mode != BreakFreeMode.NONE, "combat.break_free"),
        (template.exploitable_tiers != 0, "combat.exploitable_tiers"),
        (template.upkeep_anima_per_round != 0, "combat.upkeep_anima"),
        (template.reactive_anima_cost != 0, "combat.reactive_anima"),
        (template.passive_decay_per_day != 0, "combat.passive_decay"),
        (template.is_clash_lock, "combat.clash_lock"),
        (template.corruption_resonance_id is not None, "combat.corruption"),
    )
    for enabled, channel in combat_flags:
        if enabled:
            channels.append(channel)

    stages = _stage_values(template)
    if stages:
        channels.append("stage")
        if any(_stage_values_for_entries(stage) for stage in stages):
            channels.append("stage_entry")

    # Stable order and duplicate removal make admin output deterministic.
    channels = list(dict.fromkeys(channels))
    state = (
        ConditionMechanicsState.WIRED if channels else ConditionMechanicsState.MANUAL_VERIFICATION
    )
    return ConditionMechanicsDiagnostic(
        condition_id=template.pk,
        condition_name=template.name,
        state=state,
        referenced=True,
        channels=tuple(channels),
    )


def _stage_values_for_entries(stage: ConditionStage) -> list[object]:
    """Read stage entry conditions through Django's normal prefetch cache."""
    return list(stage.on_entry_conditions.all())
