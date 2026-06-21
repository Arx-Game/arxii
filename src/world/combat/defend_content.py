"""DEFEND stance content seed (#1273, Task 6).

Idempotently seeds the content the DEFEND passive stance needs:

* A ``FlowDefinition`` with a single ``MODIFY_PAYLOAD`` step that multiplies
  ``DamagePreApplyPayload.amount`` by 0.5 (halves incoming damage).
* A ``TriggerDefinition`` subscribed to ``DAMAGE_PRE_APPLY`` with a SELF filter
  (only fires when the payload's target is the bearer — the protected ally).
* A "Shielded" ``ConditionTemplate`` with the trigger in its ``reactive_triggers``
  M2M. When applied to an ally, ``_install_reactive_side_effects`` converts the
  M2M rows into live ``Trigger`` rows on the ally's ``trigger_handler`` so the
  next ``emit_event(DAMAGE_PRE_APPLY, ...)`` dispatch sees them.
* A DEFEND passive ``Technique`` with a
  ``TechniqueAppliedCondition(target_kind=ALLY, condition=Shielded)``.

``ensure_defend_content()`` is idempotent (all writes via ``get_or_create``) and
doubles as integration-test setup and staff seed data. Safe to call repeatedly.
"""

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowDefinition, FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.combat.constants import ActionCategory
from world.conditions.models import ConditionTemplate
from world.magic.models.gifts import Gift
from world.magic.models.techniques import (
    ConditionTargetKind,
    EffectType,
    Technique,
    TechniqueAppliedCondition,
    TechniqueStyle,
)

# ---------------------------------------------------------------------------
# Identity keys (module-level constants for stable naming)
# ---------------------------------------------------------------------------

#: Name of the reactive condition installed on allies by the DEFEND passive.
SHIELDED_CONDITION_NAME: str = "Shielded"

#: Name of the DEFEND passive technique.
DEFEND_PASSIVE_NAME: str = "Defend"

#: Name of the FlowDefinition that halves incoming damage.
_SHIELDED_FLOW_NAME: str = "shielded_halve_damage"

#: Name of the TriggerDefinition that fires on DAMAGE_PRE_APPLY for the bearer.
_SHIELDED_TRIGGER_NAME: str = "shielded_damage_pre_apply"

#: Filter: trigger fires only when payload.target == trigger.obj (the shielded ally).
_SELF_TARGET_FILTER: dict[str, object] = {"path": "target", "op": "==", "value": "self"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ensure_defend_content() -> None:
    """Idempotently seed the DEFEND passive stance content (#1273).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (name ``shielded_halve_damage``) with a single
       ``MODIFY_PAYLOAD`` step ``{"field": "amount", "op": "multiply", "value": 0.5}``.
    2. A ``TriggerDefinition`` (name ``shielded_damage_pre_apply``) on
       ``DAMAGE_PRE_APPLY`` with ``base_filter_condition=_SELF_TARGET_FILTER``
       (``{"path": "target", "op": "==", "value": "self"}``), which restricts
       firing to events where ``payload.target`` is the trigger's bearer (the
       protected ally). Without this filter it would fire for any target
       in the room — the SELF filter ensures per-ally specificity.
    3. A "Shielded" ``ConditionTemplate`` with ``reactive_triggers`` wired to the
       trigger above.
    4. A ``Technique`` named "Defend" (PHYSICAL, intensity=4) with a
       ``TechniqueAppliedCondition`` row whose ``target_kind=ALLY`` points at the
       Shielded template.

    Adding further mitigation effects later is pure data: additional
    ``TechniqueAppliedCondition`` rows on the DEFEND technique, or additional
    ``reactive_triggers`` on the Shielded template, require zero engine changes.
    """
    # 1. Flow: multiply payload.amount by 0.5
    flow, _created = FlowDefinition.objects.get_or_create(name=_SHIELDED_FLOW_NAME)
    FlowStepDefinition.objects.get_or_create(
        flow=flow,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        defaults={
            "parent_id": None,
            "parameters": {"field": "amount", "op": "multiply", "value": 0.5},
        },
    )

    # 2. Trigger: fires on DAMAGE_PRE_APPLY, but only when payload.target is the bearer.
    trigger_def, _created = TriggerDefinition.objects.get_or_create(
        name=_SHIELDED_TRIGGER_NAME,
        defaults={
            "event_name": EventName.DAMAGE_PRE_APPLY,
            "flow_definition": flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "description": (
                "Halves incoming damage when the bearer is the damage target "
                "(installed by the Shielded condition; fired by the DEFEND passive)."
            ),
        },
    )

    # 3. ConditionTemplate: "Shielded" with reactive trigger installed on apply.
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    condition_category, _ = ConditionCategory.objects.get_or_create(
        name="Defensive",
        defaults={
            "description": "Protective conditions granted by allies.",
            "is_negative": False,
            "display_order": 10,
        },
    )
    shielded_template, _created = ConditionTemplate.objects.get_or_create(
        name=SHIELDED_CONDITION_NAME,
        defaults={
            "description": (
                "A protective ward cast by an ally's DEFEND stance. "
                "Halves incoming damage while the condition persists."
            ),
            "category": condition_category,
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
        },
    )
    # Wire the trigger into the condition's M2M (idempotent: add is a no-op if present).
    shielded_template.reactive_triggers.add(trigger_def)

    # 4. DEFEND passive Technique with an ALLY TechniqueAppliedCondition.
    #    Technique requires gift, style, and effect_type — seed minimal rows.
    defend_gift, _ = Gift.objects.get_or_create(
        name=DEFEND_PASSIVE_NAME,
        defaults={"description": "Combat stances and protective techniques."},
    )
    defend_style, _ = TechniqueStyle.objects.get_or_create(
        name="Defensive Stance",
        defaults={"description": "A fighting style focused on protecting allies."},
    )
    defend_effect_type, _ = EffectType.objects.get_or_create(
        name="Defensive Aura",
        defaults={
            "description": "Creates a protective aura around allies.",
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
    )
    defend_tech, _created = Technique.objects.get_or_create(
        name=DEFEND_PASSIVE_NAME,
        gift=defend_gift,
        defaults={
            "description": (
                "Take a defensive stance that shields active allies, "
                "halving the damage they receive this round."
            ),
            "style": defend_style,
            "effect_type": defend_effect_type,
            "action_category": ActionCategory.PHYSICAL,
            "intensity": 4,
            "level": 1,
            "control": 4,
            "anima_cost": 0,
            "combo_opening_probing": None,
        },
    )
    TechniqueAppliedCondition.objects.get_or_create(
        technique=defend_tech,
        condition=shielded_template,
        target_kind=ConditionTargetKind.ALLY,
        defaults={
            "base_severity": 1,
            "minimum_success_level": 1,
        },
    )
