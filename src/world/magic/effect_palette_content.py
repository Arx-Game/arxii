"""Summon effect bundle + the active-effect CONDITION_APPLIED wiring + reactive
effect bundles (force-field/reflect/blink) (#1584, Tasks 14a & 14b).

Task 14a — idempotently seeds the castable "Summon Spirit" technique so that
casting it fires the ``summon_ally`` effect handler via CONDITION_APPLIED.

Task 14b — idempotently seeds three DAMAGE_PRE_APPLY reactive techniques:
* ``ensure_force_field_content()`` — Aegis Field (absorb_pool, priority 10),
  plus a CONDITION_APPLIED trigger that calls ``init_absorb_buffer`` to seed the
  instance's absorb buffer on application.
* ``ensure_reflect_content()`` — Mirror Ward (reflect_damage, priority 20),
  with a CANCEL_EVENT child step that stops lower-priority interceptors.
* ``ensure_blink_content()`` — Phase Step (blink_dodge, priority 30), with a
  CANCEL_EVENT child step (highest priority; full avoidance stops reflect+absorb).

All ``ensure_*()`` functions are idempotent (get_or_create throughout) and double
as integration-test setup and staff seed data.  Safe to call repeatedly.

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
from world.conditions.constants import (
    BLINK_CONDITION_NAME,
    FORCE_FIELD_CONDITION_NAME,
    REFLECT_CONDITION_NAME,
    SUMMONING_CONDITION_NAME,
)
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

# --- Task 14a: Summon ---

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

# --- Task 14b: Reactive bundles (force-field / reflect / blink) ---

#: Castable technique name for the Aegis Field (force-field) reactive bundle.
FORCE_FIELD_TECHNIQUE_NAME: str = "Aegis Field"

#: Castable technique name for the Mirror Ward (reflect) reactive bundle.
REFLECT_TECHNIQUE_NAME: str = "Mirror Ward"

#: Castable technique name for the Phase Step (blink) reactive bundle.
BLINK_TECHNIQUE_NAME: str = "Phase Step"

# --- Dotted handler paths ---
_ABSORB_POOL_PATH: str = "world.magic.services.effect_handlers.absorb_pool"
_REFLECT_DAMAGE_PATH: str = "world.magic.services.effect_handlers.reflect_damage"
_BLINK_DODGE_PATH: str = "world.magic.services.effect_handlers.blink_dodge"
_INIT_ABSORB_BUFFER_PATH: str = "world.magic.services.effect_handlers.init_absorb_buffer"

# --- Flow names ---
_FORCE_FIELD_FLOW_NAME: str = "force_field_damage_pre_apply"
_FORCE_FIELD_INIT_FLOW_NAME: str = "force_field_init_buffer"
_REFLECT_FLOW_NAME: str = "reflect_damage_pre_apply"
_BLINK_FLOW_NAME: str = "blink_damage_pre_apply"

# --- Trigger names ---
_FORCE_FIELD_DPA_TRIGGER_NAME: str = "force_field_damage_pre_apply"
_FORCE_FIELD_CA_TRIGGER_NAME: str = "force_field_condition_applied"
_REFLECT_DPA_TRIGGER_NAME: str = "reflect_damage_pre_apply"
_BLINK_DPA_TRIGGER_NAME: str = "blink_damage_pre_apply"

# --- Absorb buffer size seeded by the CONDITION_APPLIED init handler ---
_FORCE_FIELD_INIT_BUFFER: int = 20


# ---------------------------------------------------------------------------
# Public entry points
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


# ---------------------------------------------------------------------------
# Task 14b: Reactive bundles (force-field / reflect / blink)
# ---------------------------------------------------------------------------


def _seed_reactive_condition(
    condition_name: str,
    reactive_anima_cost: int,
    upkeep_anima_per_round: int,
    description: str,
) -> ConditionTemplate:
    """Get-or-create a ``ConditionTemplate`` suitable for a DAMAGE_PRE_APPLY reactive.

    Shared boilerplate for the three reactive bundles: Aegis Field, Mirror Ward,
    Phase Step.  Returns the template (created or existing) for further wiring.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    reactive_category, _ = ConditionCategory.objects.get_or_create(
        name="Reactive",
        defaults={
            "description": "Self-defensive reactive conditions.",
            "is_negative": False,
            "display_order": 20,
        },
    )
    template, _created = ConditionTemplate.objects.get_or_create(
        name=condition_name,
        defaults={
            "description": description,
            "category": reactive_category,
            "default_duration_type": DurationType.UNTIL_END_OF_COMBAT,
            "default_duration_value": 1,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
            "reactive_anima_cost": reactive_anima_cost,
            "upkeep_anima_per_round": upkeep_anima_per_round,
        },
    )
    return template


def _seed_call_service_flow(flow_name: str, handler_path: str) -> FlowStepDefinition:
    """Get-or-create a FlowDefinition + root CALL_SERVICE_FUNCTION step.

    Returns the root step so callers can attach CANCEL_EVENT children.
    """
    flow, _created = FlowDefinition.objects.get_or_create(name=flow_name)
    root_step, _created = FlowStepDefinition.objects.get_or_create(
        flow=flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=handler_path,
        defaults={
            "parent_id": None,
            "parameters": {"payload": "@payload"},
        },
    )
    return root_step


def _seed_technique(  # noqa: PLR0913
    technique_name: str,
    gift_name: str,
    style_name: str,
    effect_type_name: str,
    description: str,
    technique_description: str,
    condition_template: ConditionTemplate,
) -> None:
    """Get-or-create a SELF-cast ``Technique`` + ``TechniqueAppliedCondition`` row.

    Shared boilerplate for the three reactive bundles.
    """
    gift, _ = Gift.objects.get_or_create(
        name=gift_name,
        defaults={"description": description},
    )
    style, _ = TechniqueStyle.objects.get_or_create(
        name=style_name,
        defaults={"description": f"A magical style for {style_name.lower()} techniques."},
    )
    effect_type, _ = EffectType.objects.get_or_create(
        name=effect_type_name,
        defaults={
            "description": technique_description,
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
    )
    tech, _created = Technique.objects.get_or_create(
        name=technique_name,
        gift=gift,
        defaults={
            "description": technique_description,
            "style": style,
            "effect_type": effect_type,
            "action_category": ActionCategory.PHYSICAL,
            "intensity": 4,
            "level": 1,
            "control": 4,
            "anima_cost": 2,
            "combo_opening_probing": None,
        },
    )
    TechniqueAppliedCondition.objects.get_or_create(
        technique=tech,
        condition=condition_template,
        target_kind=ConditionTargetKind.SELF,
        defaults={
            "base_severity": 1,
            "minimum_success_level": 1,
        },
    )


def ensure_force_field_content() -> None:
    """Idempotently seed the Aegis Field (force-field) reactive bundle (#1584, Task 14b).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``force_field_damage_pre_apply``) with a single
       ``CALL_SERVICE_FUNCTION`` step pointing at ``absorb_pool``.  No ``CANCEL_EVENT``
       child — mutation-only; damage overflow still lands.
    2. A ``TriggerDefinition`` on ``DAMAGE_PRE_APPLY`` with priority 10 (lowest of the
       three reactive interceptors; blink 30 > reflect 20 > absorb 10).
    3. A second ``FlowDefinition`` (``force_field_init_buffer``) + ``TriggerDefinition``
       on ``CONDITION_APPLIED`` that calls ``init_absorb_buffer`` with
       ``buffer=20`` — seeds ``absorb_remaining`` when the condition is first applied
       (``apply_condition`` does NOT initialise instance fields).
    4. An "Aegis Field" ``ConditionTemplate`` (``FORCE_FIELD_CONDITION_NAME``) with
       ``reactive_anima_cost=1``, ``upkeep_anima_per_round=1``, and both triggers in
       its ``reactive_triggers`` M2M.
    5. An "Aegis Field" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. DAMAGE_PRE_APPLY flow (absorb_pool, no CANCEL_EVENT).
    dpa_root = _seed_call_service_flow(_FORCE_FIELD_FLOW_NAME, _ABSORB_POOL_PATH)
    dpa_flow = dpa_root.flow

    # 2. DAMAGE_PRE_APPLY trigger, priority 10.
    dpa_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_FORCE_FIELD_DPA_TRIGGER_NAME,
        defaults={
            "event_name": EventName.DAMAGE_PRE_APPLY,
            "flow_definition": dpa_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 10,
            "description": (
                "Soaks incoming damage via the force-field absorb buffer "
                "(installed by the Aegis Field condition; DAMAGE_PRE_APPLY, priority 10)."
            ),
        },
    )

    # 3. CONDITION_APPLIED init flow (init_absorb_buffer with static buffer=20).
    ca_flow, _created = FlowDefinition.objects.get_or_create(name=_FORCE_FIELD_INIT_FLOW_NAME)
    FlowStepDefinition.objects.get_or_create(
        flow=ca_flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=_INIT_ABSORB_BUFFER_PATH,
        defaults={
            "parent_id": None,
            "parameters": {"payload": "@payload", "buffer": _FORCE_FIELD_INIT_BUFFER},
        },
    )
    ca_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_FORCE_FIELD_CA_TRIGGER_NAME,
        defaults={
            "event_name": EventName.CONDITION_APPLIED,
            "flow_definition": ca_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 0,
            "description": (
                "Seeds absorb_remaining=20 on the Aegis Field instance when the "
                "condition is applied (CONDITION_APPLIED; force-field init)."
            ),
        },
    )

    # 4. ConditionTemplate: "Aegis Field" with both triggers.
    condition = _seed_reactive_condition(
        FORCE_FIELD_CONDITION_NAME,
        reactive_anima_cost=1,
        upkeep_anima_per_round=1,
        description=(
            "A shimmering force field that absorbs incoming damage into its anima buffer.  "
            "Each round costs 1 anima to sustain; each hit costs 1 anima to intercept.  "
            "When the buffer runs dry the field collapses."
        ),
    )
    condition.reactive_triggers.add(dpa_trigger, ca_trigger)

    # 5. Technique.
    _seed_technique(
        FORCE_FIELD_TECHNIQUE_NAME,
        gift_name="Warding",
        style_name="Warding Stance",
        effect_type_name="Force Field",
        description="Techniques that erect protective barriers.",
        technique_description=(
            "Erect a shimmering force field that absorbs incoming damage.  "
            "The field persists until combat ends or its buffer is exhausted."
        ),
        condition_template=condition,
    )


def ensure_reflect_content() -> None:
    """Idempotently seed the Mirror Ward (reflect) reactive bundle (#1584, Task 14b).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``reflect_damage_pre_apply``) with:
       - root ``CALL_SERVICE_FUNCTION`` step → ``reflect_damage``.
       - a ``CANCEL_EVENT`` child step (parent = root) — stops lower-priority
         interceptors (absorb_pool at priority 10) after the reflect fires.
    2. A ``TriggerDefinition`` on ``DAMAGE_PRE_APPLY`` with priority 20.
    3. A "Mirror Ward" ``ConditionTemplate`` (``REFLECT_CONDITION_NAME``) with
       ``reactive_anima_cost=2``, ``upkeep_anima_per_round=1``.
    4. A "Mirror Ward" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: CALL_SERVICE_FUNCTION root + CANCEL_EVENT child.
    root_step = _seed_call_service_flow(_REFLECT_FLOW_NAME, _REFLECT_DAMAGE_PATH)
    reflect_flow = root_step.flow

    # CANCEL_EVENT child step — get_or_create keyed on (flow, action, parent).
    FlowStepDefinition.objects.get_or_create(
        flow=reflect_flow,
        action=FlowActionChoices.CANCEL_EVENT,
        parent=root_step,
        defaults={"parameters": {}},
    )

    # 2. Trigger: DAMAGE_PRE_APPLY, priority 20.
    reflect_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_REFLECT_DPA_TRIGGER_NAME,
        defaults={
            "event_name": EventName.DAMAGE_PRE_APPLY,
            "flow_definition": reflect_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 20,
            "description": (
                "Bounces incoming damage back to the attacker and cancels "
                "lower-priority interceptors (Aegis Field / absorb_pool)."
            ),
        },
    )

    # 3. ConditionTemplate: "Mirror Ward".
    condition = _seed_reactive_condition(
        REFLECT_CONDITION_NAME,
        reactive_anima_cost=2,
        upkeep_anima_per_round=1,
        description=(
            "A mirrored ward that reflects incoming damage back at the attacker.  "
            "Costs 2 anima per reflection; 1 anima per round to sustain.  "
            "When the ward fires it also cancels any force-field absorption."
        ),
    )
    condition.reactive_triggers.add(reflect_trigger)

    # 4. Technique.
    _seed_technique(
        REFLECT_TECHNIQUE_NAME,
        gift_name="Warding",
        style_name="Warding Stance",
        effect_type_name="Damage Reflection",
        description="Techniques that erect protective barriers.",
        technique_description=(
            "Weave a mirror ward that reflects incoming damage back at your attacker, "
            "cancelling any active force-field absorption."
        ),
        condition_template=condition,
    )


def ensure_blink_content() -> None:
    """Idempotently seed the Phase Step (blink) reactive bundle (#1584, Task 14b).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``blink_damage_pre_apply``) with:
       - root ``CALL_SERVICE_FUNCTION`` step → ``blink_dodge``.
       - a ``CANCEL_EVENT`` child step (parent = root) — stops lower-priority
         interceptors (reflect at 20, absorb at 10) after a successful dodge.
    2. A ``TriggerDefinition`` on ``DAMAGE_PRE_APPLY`` with priority 30 (highest).
    3. A "Phase Step" ``ConditionTemplate`` (``BLINK_CONDITION_NAME``) with
       ``reactive_anima_cost=2``, ``upkeep_anima_per_round=1``.
    4. A "Phase Step" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: CALL_SERVICE_FUNCTION root + CANCEL_EVENT child.
    root_step = _seed_call_service_flow(_BLINK_FLOW_NAME, _BLINK_DODGE_PATH)
    blink_flow = root_step.flow

    # CANCEL_EVENT child step — get_or_create keyed on (flow, action, parent).
    FlowStepDefinition.objects.get_or_create(
        flow=blink_flow,
        action=FlowActionChoices.CANCEL_EVENT,
        parent=root_step,
        defaults={"parameters": {}},
    )

    # 2. Trigger: DAMAGE_PRE_APPLY, priority 30.
    blink_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_BLINK_DPA_TRIGGER_NAME,
        defaults={
            "event_name": EventName.DAMAGE_PRE_APPLY,
            "flow_definition": blink_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 30,
            "description": (
                "Teleports the bearer to avoid incoming damage and cancels "
                "lower-priority interceptors (Mirror Ward, Aegis Field)."
            ),
        },
    )

    # 3. ConditionTemplate: "Phase Step".
    condition = _seed_reactive_condition(
        BLINK_CONDITION_NAME,
        reactive_anima_cost=2,
        upkeep_anima_per_round=1,
        description=(
            "A phase-step attunement that blinks the bearer out of the way of incoming "
            "damage.  Costs 2 anima to activate; 1 anima per round to sustain.  "
            "A successful blink cancels all other reactive interceptors (reflect, absorb)."
        ),
    )
    condition.reactive_triggers.add(blink_trigger)

    # 4. Technique.
    _seed_technique(
        BLINK_TECHNIQUE_NAME,
        gift_name="Evasion",
        style_name="Evasion Stance",
        effect_type_name="Blink Dodge",
        description="Techniques that attune the body to phase-step through incoming attacks.",
        technique_description=(
            "Phase-step out of the way of incoming damage, teleporting to an adjacent "
            "position and negating the hit entirely."
        ),
        condition_template=condition,
    )
