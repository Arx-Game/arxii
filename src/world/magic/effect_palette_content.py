"""Summon effect bundle + the active-effect CONDITION_APPLIED wiring (#1584, Task 14a).

Idempotently seeds the content a castable "Summon Spirit" technique needs so that
casting it actually fires the ``summon_ally`` effect handler:

* A ``ThreatPool`` ("Summoned Spirit") with one ``ThreatPoolEntry`` carrying
  ``base_damage`` + ``damage_type`` so the summon can attack.
* A ``FlowDefinition`` with a single ``CALL_SERVICE_FUNCTION`` step pointing at the
  ``summon_ally_on_condition`` adapter, passing ``@payload`` alongside the static
  ``threat_pool_id`` (the pool's pk), ``bond_rounds`` and ``max_health`` params.
* A ``TriggerDefinition`` subscribed to ``CONDITION_APPLIED`` with a SELF filter
  (only fires when the applied condition's bearer is the caster).
* A "Summoning" ``ConditionTemplate`` with that trigger in its ``reactive_triggers``
  M2M. When the SELF technique applies it on cast, ``_install_reactive_side_effects``
  makes it live, so the ``CONDITION_APPLIED`` emit fires the summon flow.
* A "Summon Spirit" ``Technique`` with a
  ``TechniqueAppliedCondition(target_kind=SELF, condition=Summoning)``.

This is the active-effect wiring exemplar (cast -> CONDITION_APPLIED -> flow ->
service handler) that the rest of the effect palette reuses. ``ensure_summon_content()``
is idempotent (all writes via ``get_or_create``) and doubles as integration-test
setup and staff seed data. Safe to call repeatedly.

The full cast -> trigger -> summon path is exercised by the Task 15 PG E2E
(``apply_condition`` uses PG-only DISTINCT ON); this module's own tests stay SQLite-safe.
"""

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowDefinition, FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.combat.constants import ActionCategory
from world.conditions.constants import SUMMONING_CONDITION_NAME
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

#: Name of the ThreatPool the summoned ally draws its attacks from.
SUMMON_POOL_NAME: str = "Summoned Spirit"

#: Name of the castable summon technique.
SUMMON_TECHNIQUE_NAME: str = "Summon Spirit"

#: Dotted path to the CONDITION_APPLIED -> summon_ally adapter.
_SUMMON_HANDLER_PATH: str = "world.magic.services.effect_handlers.summon_ally_on_condition"

#: Name of the FlowDefinition that summons an ally when the Summoning condition lands.
_SUMMON_FLOW_NAME: str = "summon_on_condition"

#: Name of the TriggerDefinition firing on CONDITION_APPLIED for the caster.
_SUMMON_TRIGGER_NAME: str = "summon_on_condition_applied"

#: Rounds the summoned ally's bond persists before it is dismissed.
_SUMMON_BOND_ROUNDS: int = 5

#: Explicit max_health for the summon (manual mode → no scaling formula → SQLite-safe).
_SUMMON_MAX_HEALTH: int = 30

#: Filter: trigger fires only when the applied condition's bearer is the caster.
_SELF_TARGET_FILTER: dict[str, object] = {"path": "target", "op": "==", "value": "self"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ensure_summon_content() -> None:
    """Idempotently seed the Summon Spirit bundle + active CONDITION_APPLIED wiring.

    Creates (get_or_create), in dependency order:

    1. A ``ThreatPool`` ("Summoned Spirit") with one ``ThreatPoolEntry`` (base_damage,
       damage_type) so the summon can attack. The pool is created FIRST so its pk can
       be embedded as a static parameter in the flow step.
    2. A ``FlowDefinition`` with a single ``CALL_SERVICE_FUNCTION`` step whose
       ``parameters`` carry ``{"payload": "@payload", "threat_pool_id": <pool.pk>,
       "bond_rounds": 5, "max_health": 30}`` — the static literals resolve alongside
       ``@payload``.
    3. A ``TriggerDefinition`` on ``CONDITION_APPLIED`` with ``base_filter_condition``
       = the SELF filter (fires only when the bearer is the caster).
    4. A "Summoning" ``ConditionTemplate`` with the trigger wired into its
       ``reactive_triggers`` M2M.
    5. A "Summon Spirit" ``Technique`` with a ``TechniqueAppliedCondition`` whose
       ``target_kind=SELF`` points at the Summoning template.
    """
    # Lazy import — combat models pull in services that lazy-import magic.
    from world.combat.models import ThreatPool, ThreatPoolEntry  # noqa: PLC0415
    from world.conditions.models import DamageType  # noqa: PLC0415

    # 1. ThreatPool + one attacking entry (created first so its pk seeds the flow step).
    pool, _created = ThreatPool.objects.get_or_create(
        name=SUMMON_POOL_NAME,
        defaults={"description": "Attacks available to a summoned spirit ally."},
    )
    force_damage, _ = DamageType.objects.get_or_create(name="Force")
    ThreatPoolEntry.objects.get_or_create(
        pool=pool,
        name="Spirit Strike",
        defaults={
            "description": "A summoned spirit's basic attack.",
            "attack_category": ActionCategory.PHYSICAL,
            "base_damage": 6,
            "damage_type": force_damage,
        },
    )

    # 2. Flow: one CALL_SERVICE_FUNCTION step → the summon adapter, with the pool pk static.
    flow, _created = FlowDefinition.objects.get_or_create(name=_SUMMON_FLOW_NAME)
    FlowStepDefinition.objects.get_or_create(
        flow=flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=_SUMMON_HANDLER_PATH,
        defaults={
            "parent_id": None,
            "parameters": {
                "payload": "@payload",
                "threat_pool_id": pool.pk,
                "bond_rounds": _SUMMON_BOND_ROUNDS,
                "max_health": _SUMMON_MAX_HEALTH,
            },
        },
    )

    # 3. Trigger: fires on CONDITION_APPLIED, only when the bearer is the caster.
    trigger_def, _created = TriggerDefinition.objects.get_or_create(
        name=_SUMMON_TRIGGER_NAME,
        defaults={
            "event_name": EventName.CONDITION_APPLIED,
            "flow_definition": flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "description": (
                "Summons an ALLY combatant when the Summoning condition is applied to "
                "the caster (installed by the Summon Spirit technique on cast)."
            ),
        },
    )

    # 4. ConditionTemplate: "Summoning" with the reactive trigger installed on apply.
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
    summoning_template, _created = ConditionTemplate.objects.get_or_create(
        name=SUMMONING_CONDITION_NAME,
        defaults={
            "description": (
                "A transient marker applied to a caster as they summon a spirit ally; "
                "its reactive trigger creates the ally combatant on application."
            ),
            "category": condition_category,
            "default_duration_type": DurationType.UNTIL_USED,
            "default_duration_value": 1,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": False,
        },
    )
    # Wire the trigger into the condition's M2M (idempotent: add is a no-op if present).
    summoning_template.reactive_triggers.add(trigger_def)

    # 5. Summon Spirit Technique with a SELF TechniqueAppliedCondition.
    #    Technique requires gift, style, and effect_type — seed minimal rows.
    summon_gift, _ = Gift.objects.get_or_create(
        name="Summoning",
        defaults={"description": "Techniques that call spirit allies into being."},
    )
    summon_style, _ = TechniqueStyle.objects.get_or_create(
        name="Conjuration",
        defaults={"description": "A magical style focused on summoning entities."},
    )
    summon_effect_type, _ = EffectType.objects.get_or_create(
        name="Summon",
        defaults={
            "description": "Calls an allied combatant into the encounter.",
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
    )
    summon_tech, _created = Technique.objects.get_or_create(
        name=SUMMON_TECHNIQUE_NAME,
        gift=summon_gift,
        defaults={
            "description": ("Call a spirit ally into the encounter to fight alongside you."),
            "style": summon_style,
            "effect_type": summon_effect_type,
            "action_category": ActionCategory.PHYSICAL,
            "intensity": 4,
            "level": 1,
            "control": 4,
            "anima_cost": 0,
            "combo_opening_probing": None,
        },
    )
    TechniqueAppliedCondition.objects.get_or_create(
        technique=summon_tech,
        condition=summoning_template,
        target_kind=ConditionTargetKind.SELF,
        defaults={
            "base_severity": 1,
            "minimum_success_level": 1,
        },
    )
