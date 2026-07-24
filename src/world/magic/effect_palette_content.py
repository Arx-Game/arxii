"""Summon + reactive + simple effect bundles for the castable effect palette (#1584).

Tasks 14a, 14b, 14c — idempotent ``ensure_*_content()`` builders.

Task 14a — "Summon Spirit" technique → CONDITION_APPLIED → ``summon_ally``.

Task 14b — Three DAMAGE_PRE_APPLY reactive techniques. All mutation-only: each handler
sets ``payload.amount = 0`` on success and lower-priority interceptors guard on
``payload.amount <= 0`` (no CANCEL_EVENT — it would fire on the anima-cost fizzle path
too; see #1584 Task 16):
* ``ensure_force_field_content()`` — Aegis Field (absorb_pool, priority 10).
* ``ensure_reflect_content()`` — Mirror Ward (reflect_damage, priority 20).
* ``ensure_blink_content()`` — Phase Step (blink_dodge, priority 30).

#2208 — each of the three ``ensure_*_content()`` builders above also seeds an ally-single
and an ally-party Technique variant (e.g. Aegis Field -> Aegis Ward / Aegis Communion),
all reusing the SAME ConditionTemplate instance the self variant creates — no new
ConditionTemplates, triggers, or flows. Party variants pay 2x the single variant's
``anima_cost``; the payer-pays-for-upkeep rule lives in ``_try_spend_reactive`` /
``drain_reactive_upkeep`` (Tasks 1-2), not in this content module.

Task 14c — Five simple effect techniques + the unified entry point:
* ``ensure_teleport_content()``   — Phase Jump (SELF): CONDITION_APPLIED → move_position.
* ``ensure_obstacle_content()``   — Barricade (SELF): CONDITION_APPLIED → create_obstacle.
* ``ensure_incorporeal_content()`` — Ghostform (SELF): intangibility gate only (no handler).
* ``ensure_sink_content()``        — Earthmeld (SELF, 1 round): intangibility gate only.
* ``ensure_telekinesis_content()`` — Force Grip (ENEMY): CONDITION_APPLIED → move_position.
* ``ensure_effect_palette_content()`` — calls every builder; the single entry point for
  tests and seed data.

All ``ensure_*()`` functions are idempotent (get_or_create throughout) and double
as integration-test setup and staff seed data.  Safe to call repeatedly.

Note — destination/position placeholder params: teleport, obstacle, and telekinesis
flow steps carry ``destination_position_id=0`` / ``position_a_id=0`` / ``position_b_id=0``
as placeholders.  Runtime destination selection (cast-time target picker) is deferred to
a follow-up; the Task 15/16 E2Es use real seeded Positions passed in test setup.

The full cast → CONDITION_APPLIED → trigger → handler paths are exercised by the
Task 15/16 PG E2Es (``apply_condition`` uses PG-only DISTINCT ON); this module's
own tests stay SQLite-safe.
"""

from actions.constants import ActionTargetType
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowDefinition, FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.areas.positioning.constants import RampartSignature
from world.combat.constants import ActionCategory
from world.conditions.constants import (
    BLINK_CONDITION_NAME,
    FORCE_FIELD_CONDITION_NAME,
    INCORPOREAL_CONDITION_NAME,
    OBSTACLE_CONDITION_NAME,
    REFLECT_CONDITION_NAME,
    SINK_CONDITION_NAME,
    SUMMONING_CONDITION_NAME,
    TELEKINESIS_CONDITION_NAME,
    TELEPORT_CONDITION_NAME,
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
from world.magic.seeds_cast import get_standalone_cast_template

# ---------------------------------------------------------------------------
# Identity keys (module-level constants for stable naming)
# ---------------------------------------------------------------------------

#: Flow-step parameter placeholder substituted with the live event payload at runtime.
PAYLOAD_PLACEHOLDER: str = "@payload"

#: Shared TechniqueStyle name for the space-bending translocation techniques.
TRANSLOCATION_STANCE_STYLE_NAME: str = "Translocation Stance"

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

# --- #2208: Ally + party ward technique variants (reuse the templates above) ---

#: Ally-single variant of Aegis Field (target_kind=ALLY, target_type=SINGLE).
FORCE_FIELD_ALLY_TECHNIQUE_NAME: str = "Aegis Ward"

#: Ally-party variant of Aegis Field (target_kind=ALLY, target_type=FILTERED_GROUP).
FORCE_FIELD_PARTY_TECHNIQUE_NAME: str = "Aegis Communion"

#: Ally-single variant of Mirror Ward (target_kind=ALLY, target_type=SINGLE).
REFLECT_ALLY_TECHNIQUE_NAME: str = "Mirror Vigil"

#: Ally-party variant of Mirror Ward (target_kind=ALLY, target_type=FILTERED_GROUP).
REFLECT_PARTY_TECHNIQUE_NAME: str = "Mirror Communion"

#: Ally-single variant of Phase Step (target_kind=ALLY, target_type=SINGLE).
BLINK_ALLY_TECHNIQUE_NAME: str = "Phase Guard"

#: Ally-party variant of Phase Step (target_kind=ALLY, target_type=FILTERED_GROUP).
BLINK_PARTY_TECHNIQUE_NAME: str = "Phase Communion"

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

# --- Shared gift/style/effect-type/description literals (duplicated across bundles) ---

_WARDING_GIFT: str = "Warding"
_WARDING_STANCE_STYLE: str = "Warding Stance"
_FORCE_FIELD_EFFECT_TYPE: str = "Force Field"
_BARRIER_DESCRIPTION: str = "Techniques that erect protective barriers."

_EVASION_GIFT: str = "Evasion"
_EVASION_STANCE_STYLE: str = "Evasion Stance"
_BLINK_DODGE_EFFECT_TYPE: str = "Blink Dodge"
_PHASE_STEP_DESCRIPTION: str = (
    "Techniques that attune the body to phase-step through incoming attacks."
)
_DAMAGE_REFLECTION_EFFECT_TYPE: str = "Damage Reflection"

# ---------------------------------------------------------------------------
# Task 14c: Simple effect bundles (teleport / obstacle / incorporeal / sink / telekinesis)
# ---------------------------------------------------------------------------

#: Castable technique name for the Phase Jump (teleport) bundle.
TELEPORT_TECHNIQUE_NAME: str = "Phase Jump"

#: Castable technique name for the Barricade (obstacle) bundle.
OBSTACLE_TECHNIQUE_NAME: str = "Barricade"

#: Castable technique name for the Ghostform (incorporeal) bundle.
INCORPOREAL_TECHNIQUE_NAME: str = "Ghostform"

#: Castable technique name for the Earthmeld (sink into earth) bundle.
SINK_TECHNIQUE_NAME: str = "Earthmeld"

#: Castable technique name for the Force Grip (telekinesis) bundle.
TELEKINESIS_TECHNIQUE_NAME: str = "Force Grip"

# --- Dotted adapter handler paths ---
_MOVE_POSITION_ADAPTER_PATH: str = "world.magic.services.effect_handlers.move_position_on_condition"
_CREATE_OBSTACLE_ADAPTER_PATH: str = (
    "world.magic.services.effect_handlers.create_obstacle_on_condition"
)
_FORCE_MOVE_ADAPTER_PATH: str = (
    "world.magic.services.effect_handlers.force_move_target_on_condition"
)

# --- Flow names ---
_TELEPORT_FLOW_NAME: str = "teleport_on_condition_applied"
_OBSTACLE_FLOW_NAME: str = "obstacle_on_condition_applied"
_TELEKINESIS_FLOW_NAME: str = "telekinesis_on_condition_applied"

# --- Trigger names ---
_TELEPORT_TRIGGER_NAME: str = "teleport_condition_applied"
_OBSTACLE_TRIGGER_NAME: str = "obstacle_condition_applied"
_TELEKINESIS_TRIGGER_NAME: str = "telekinesis_condition_applied"

#: Placeholder Position pk seeded into the flow step's static params for teleport /
#: obstacle / telekinesis.  Runtime destination selection (cast-time target picker) is
#: a follow-up; the Task 15/16 E2Es pass a real Position via test setup.
_PLACEHOLDER_POSITION_ID: int = 0

# ---------------------------------------------------------------------------
# #2209: Rampart (living barrier) bundle
# ---------------------------------------------------------------------------

#: Gift shared by all four "Raise Rampart" techniques.
RAMPART_GIFT_NAME: str = "Wardcraft"

#: TechniqueStyle shared by all four "Raise Rampart" techniques.
RAMPART_STYLE_NAME: str = "Elemental Bulwark Stance"

#: Name of the Thorn rampart's GRASPING signature_condition. Applied not through
#: this bundle's own CONDITION_APPLIED trigger but at the shared forced-move
#: landing seam (world.mechanics.effect_handlers._apply_grasping_if_covered).
RAMPART_ENTANGLED_CONDITION_NAME: str = "Entangled"

#: Dotted path to the CONDITION_APPLIED -> raise_rampart_on_condition adapter.
_RAISE_RAMPART_ADAPTER_PATH: str = "world.magic.services.effect_handlers.raise_rampart_on_condition"

#: Mid-tier integrity seeded for every Raise Rampart technique (#2209).
_RAMPART_INTEGRITY: int = 24

#: One row per element: (element_name, signature_behavior, signature_value,
#: signature_damage_type_name, signature_condition_name, resistances).
#: resistances is a tuple of (damage_type_name, value) pairs, small ints (2-6).
_RAMPART_ELEMENTS: tuple[tuple[str, str, int, str | None, str | None, tuple], ...] = (
    ("Stone", RampartSignature.SEAL_EDGES, 0, None, None, (("Force", 6), ("Acid", 3))),
    ("Wind", RampartSignature.MISSILE_WARD, 4, None, None, (("Lightning", 3), ("Poison", 4))),
    ("Fire", RampartSignature.MELEE_RETALIATION, 4, "Fire", None, (("Cold", 5),)),
    (
        "Thorn",
        RampartSignature.GRASPING,
        0,
        None,
        RAMPART_ENTANGLED_CONDITION_NAME,
        (("Poison", 4), ("Acid", 2)),
    ),
)


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
       ``parameters`` carry ``{"payload": "@payload", "threat_pool_name": "<pool name>",
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
                "payload": PAYLOAD_PLACEHOLDER,
                "threat_pool_name": pool.name,
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
            "action_template": get_standalone_cast_template(),
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


def _seed_call_service_flow(
    flow_name: str,
    handler_path: str,
    extra_params: dict[str, object] | None = None,
) -> FlowStepDefinition:
    """Get-or-create a FlowDefinition + root CALL_SERVICE_FUNCTION step.

    Returns the root step (the reactive bundles are mutation-only single-step flows;
    the root is returned for symmetry and any future child-step needs).

    ``extra_params`` are merged into the step's ``parameters`` dict alongside the
    mandatory ``{"payload": "@payload"}`` entry.  Useful for active-effect adapters
    that need static ids (e.g. ``destination_position_id``) alongside the payload.
    """
    flow, _created = FlowDefinition.objects.get_or_create(name=flow_name)
    params: dict[str, object] = {"payload": PAYLOAD_PLACEHOLDER}
    if extra_params:
        params.update(extra_params)
    root_step, _created = FlowStepDefinition.objects.get_or_create(
        flow=flow,
        action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        variable_name=handler_path,
        defaults={
            "parent_id": None,
            "parameters": params,
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
    target_kind: str = ConditionTargetKind.SELF,
    target_type: str = ActionTargetType.SINGLE,
    anima_cost: int = 2,
) -> None:
    """Get-or-create a ``Technique`` + ``TechniqueAppliedCondition`` row.

    Shared boilerplate for all effect bundles.  Defaults to ``target_kind=SELF``
    (reactive / self-buff / teleport / incorporeal); pass ``target_kind=ENEMY``
    for techniques applied to opponents (e.g. telekinesis Force Grip), or
    ``target_kind=ALLY`` for the #2208 ward variants. ``target_type`` is the
    per-technique cardinality (``SINGLE`` default preserved; pass
    ``FILTERED_GROUP`` for the #2208 party variants). ``anima_cost`` defaults to
    the original hardcoded 2; party variants pass 2x the single variant's cost.
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
            "anima_cost": anima_cost,
            "target_type": target_type,
            "combo_opening_probing": None,
            "action_template": get_standalone_cast_template(),
        },
    )
    TechniqueAppliedCondition.objects.get_or_create(
        technique=tech,
        condition=condition_template,
        target_kind=target_kind,
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
            "parameters": {"payload": PAYLOAD_PLACEHOLDER, "buffer": _FORCE_FIELD_INIT_BUFFER},
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

    # 5. Technique (self).
    _seed_technique(
        FORCE_FIELD_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_FORCE_FIELD_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Erect a shimmering force field that absorbs incoming damage.  "
            "The field persists until combat ends or its buffer is exhausted."
        ),
        condition_template=condition,
    )

    # 6. Ally + party variants (#2208) — reuse the SAME "Aegis Field" ConditionTemplate;
    # no new ConditionTemplates/triggers/flows. Same Gift/Style/EffectType as the self
    # variant, so acquisition wiring is identical (zero new gate code).
    _seed_technique(
        FORCE_FIELD_ALLY_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_FORCE_FIELD_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Erect a shimmering force field around an ally that absorbs incoming damage.  "
            "The field persists until combat ends or its buffer is exhausted."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.SINGLE,
        anima_cost=2,
    )
    _seed_technique(
        FORCE_FIELD_PARTY_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_FORCE_FIELD_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Erect a shimmering force field around a whole party of allies that absorbs "
            "incoming damage.  Each field persists independently until combat ends or its "
            "own buffer is exhausted."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.FILTERED_GROUP,
        anima_cost=4,
    )


def ensure_reflect_content() -> None:
    """Idempotently seed the Mirror Ward (reflect) reactive bundle (#1584, Task 14b).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``reflect_damage_pre_apply``) with a single root
       ``CALL_SERVICE_FUNCTION`` step → ``reflect_damage`` (mutation-only, NO
       ``CANCEL_EVENT``). ``reflect_damage`` sets ``payload.amount = 0`` on success;
       the lower-priority absorb_pool (10) then no-ops via its ``amount <= 0`` guard.
    2. A ``TriggerDefinition`` on ``DAMAGE_PRE_APPLY`` with priority 20.
    3. A "Mirror Ward" ``ConditionTemplate`` (``REFLECT_CONDITION_NAME``) with
       ``reactive_anima_cost=2``, ``upkeep_anima_per_round=1``.
    4. A "Mirror Ward" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: a single CALL_SERVICE_FUNCTION step (mutation-only, NO CANCEL_EVENT).
    # reflect_damage sets payload.amount=0 on success; the emitter's `amount <= 0`
    # check zeroes damage, and lower-priority interceptors guard on the same. A
    # CANCEL_EVENT child would fire UNCONDITIONALLY — even on the anima-cost fizzle
    # path where reflect_damage returns early — wrongly cancelling an unaffordable
    # reflect so the attack never lands (#1584 Task 16 caught this).
    root_step = _seed_call_service_flow(_REFLECT_FLOW_NAME, _REFLECT_DAMAGE_PATH)
    reflect_flow = root_step.flow

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

    # 4. Technique (self).
    _seed_technique(
        REFLECT_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_DAMAGE_REFLECTION_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Weave a mirror ward that reflects incoming damage back at your attacker, "
            "cancelling any active force-field absorption."
        ),
        condition_template=condition,
    )

    # 5. Ally + party variants (#2208) — reuse the SAME "Mirror Ward" ConditionTemplate;
    # no new ConditionTemplates/triggers/flows. Same Gift/Style/EffectType as the self
    # variant, so acquisition wiring is identical (zero new gate code).
    _seed_technique(
        REFLECT_ALLY_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_DAMAGE_REFLECTION_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Weave a mirror ward onto an ally that reflects incoming damage back at "
            "their attacker, cancelling any active force-field absorption on that ally."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.SINGLE,
        anima_cost=2,
    )
    _seed_technique(
        REFLECT_PARTY_TECHNIQUE_NAME,
        gift_name=_WARDING_GIFT,
        style_name=_WARDING_STANCE_STYLE,
        effect_type_name=_DAMAGE_REFLECTION_EFFECT_TYPE,
        description=_BARRIER_DESCRIPTION,
        technique_description=(
            "Weave a mirror ward onto a whole party of allies that reflects incoming "
            "damage back at each attacker, cancelling any active force-field absorption "
            "on the warded allies."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.FILTERED_GROUP,
        anima_cost=4,
    )


def ensure_blink_content() -> None:
    """Idempotently seed the Phase Step (blink) reactive bundle (#1584, Task 14b).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``blink_damage_pre_apply``) with a single root
       ``CALL_SERVICE_FUNCTION`` step → ``blink_dodge`` (mutation-only, NO
       ``CANCEL_EVENT``). A successful dodge sets ``payload.amount = 0``; the
       lower-priority reflect (20) and absorb (10) then no-op via their guards.
    2. A ``TriggerDefinition`` on ``DAMAGE_PRE_APPLY`` with priority 30 (highest).
    3. A "Phase Step" ``ConditionTemplate`` (``BLINK_CONDITION_NAME``) with
       ``reactive_anima_cost=2``, ``upkeep_anima_per_round=1``.
    4. A "Phase Step" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: a single CALL_SERVICE_FUNCTION step (mutation-only, NO CANCEL_EVENT).
    # blink_dodge sets payload.amount=0 only when the bearer can pay the anima cost;
    # the emitter's `amount <= 0` check then zeroes damage. A CANCEL_EVENT child would
    # fire UNCONDITIONALLY — even when blink_dodge returns early on the fizzle path —
    # so an unaffordable blink would still cancel the attack (#1584 Task 16 caught this).
    root_step = _seed_call_service_flow(_BLINK_FLOW_NAME, _BLINK_DODGE_PATH)
    blink_flow = root_step.flow

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

    # 4. Technique (self).
    _seed_technique(
        BLINK_TECHNIQUE_NAME,
        gift_name=_EVASION_GIFT,
        style_name=_EVASION_STANCE_STYLE,
        effect_type_name=_BLINK_DODGE_EFFECT_TYPE,
        description=_PHASE_STEP_DESCRIPTION,
        technique_description=(
            "Phase-step out of the way of incoming damage, teleporting to an adjacent "
            "position and negating the hit entirely."
        ),
        condition_template=condition,
    )

    # 5. Ally + party variants (#2208) — reuse the SAME "Phase Step" ConditionTemplate;
    # no new ConditionTemplates/triggers/flows. Same Gift/Style/EffectType as the self
    # variant, so acquisition wiring is identical (zero new gate code).
    _seed_technique(
        BLINK_ALLY_TECHNIQUE_NAME,
        gift_name=_EVASION_GIFT,
        style_name=_EVASION_STANCE_STYLE,
        effect_type_name=_BLINK_DODGE_EFFECT_TYPE,
        description=_PHASE_STEP_DESCRIPTION,
        technique_description=(
            "Attune an ally's body to phase-step out of the way of incoming damage, "
            "teleporting them to an adjacent position and negating the hit entirely."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.SINGLE,
        anima_cost=2,
    )
    _seed_technique(
        BLINK_PARTY_TECHNIQUE_NAME,
        gift_name=_EVASION_GIFT,
        style_name=_EVASION_STANCE_STYLE,
        effect_type_name=_BLINK_DODGE_EFFECT_TYPE,
        description=_PHASE_STEP_DESCRIPTION,
        technique_description=(
            "Attune a whole party of allies to phase-step out of the way of incoming "
            "damage, teleporting each to an adjacent position and negating the hit "
            "entirely."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ALLY,
        target_type=ActionTargetType.FILTERED_GROUP,
        anima_cost=4,
    )


# ---------------------------------------------------------------------------
# Task 14c: Simple effect bundles
# ---------------------------------------------------------------------------


def _seed_active_condition(
    condition_name: str,
    category_name: str,
    category_is_negative: bool,
    category_display_order: int,
    description: str,
) -> ConditionTemplate:
    """Get-or-create a one-shot marker ``ConditionTemplate`` for active CONDITION_APPLIED effects.

    The returned template is meant to be applied on cast (SELF or ENEMY) and
    immediately trigger a reactive flow via ``reactive_triggers``.  Duration is
    ``UNTIL_USED`` so the marker expires after the trigger fires.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    category, _ = ConditionCategory.objects.get_or_create(
        name=category_name,
        defaults={
            "description": f"Conditions related to {category_name.lower()} effects.",
            "is_negative": category_is_negative,
            "display_order": category_display_order,
        },
    )
    template, _ = ConditionTemplate.objects.get_or_create(
        name=condition_name,
        defaults={
            "description": description,
            "category": category,
            "default_duration_type": DurationType.UNTIL_USED,
            "default_duration_value": 1,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": False,
        },
    )
    return template


def _seed_intangibility_condition(
    condition_name: str,
    description: str,
    default_duration_type: str,
    default_duration_value: int,
) -> ConditionTemplate:
    """Get-or-create a ``ConditionTemplate`` whose category has ``grants_intangibility=True``.

    Used by Ghostform (incorporeal) and Earthmeld (sink into earth).  These conditions
    carry no reactive triggers — the Task 8 targeting gate reads ``grants_intangibility``
    to make the bearer untargetable while the condition is active.
    """
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    intangible_cat, _ = ConditionCategory.objects.get_or_create(
        name="Incorporeal",
        defaults={
            "description": (
                "Conditions that render the bearer untargetable by phasing them out of "
                "the physical plane (incorporeal flight, earthbound sink, etc.)."
            ),
            "is_negative": False,
            "display_order": 30,
            "grants_intangibility": True,
        },
    )
    template, _ = ConditionTemplate.objects.get_or_create(
        name=condition_name,
        defaults={
            "description": description,
            "category": intangible_cat,
            "default_duration_type": default_duration_type,
            "default_duration_value": default_duration_value,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
        },
    )
    return template


def ensure_teleport_content() -> None:
    """Idempotently seed the Phase Jump (teleport) active-effect bundle (#1584, Task 14c).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``teleport_on_condition_applied``) with a single
       ``CALL_SERVICE_FUNCTION`` step pointing at ``move_position_on_condition``,
       passing ``{"payload": "@payload", "destination_position_id": 0}`` (placeholder;
       runtime destination selection is a follow-up — see note in module docstring).
    2. A ``TriggerDefinition`` on ``CONDITION_APPLIED`` with a SELF filter (fires only
       when the applied condition's bearer is the caster).
    3. A "Phase Jump" ``ConditionTemplate`` (``TELEPORT_CONDITION_NAME``) in the
       "Movement" category, duration ``UNTIL_USED``.  The marker expires after the
       trigger fires.
    4. A "Phase Jump" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: single CALL_SERVICE_FUNCTION step with static destination placeholder.
    root_step = _seed_call_service_flow(
        _TELEPORT_FLOW_NAME,
        _MOVE_POSITION_ADAPTER_PATH,
        extra_params={"destination_position_id": _PLACEHOLDER_POSITION_ID},
    )
    teleport_flow = root_step.flow

    # 2. Trigger: CONDITION_APPLIED, SELF filter.
    teleport_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_TELEPORT_TRIGGER_NAME,
        defaults={
            "event_name": EventName.CONDITION_APPLIED,
            "flow_definition": teleport_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 0,
            "description": (
                "Relocates the caster to a new position when the Phase Jump condition "
                "is applied (CONDITION_APPLIED; active teleport effect)."
            ),
        },
    )

    # 3. ConditionTemplate: "Phase Jump" marker in the Movement category.
    condition = _seed_active_condition(
        TELEPORT_CONDITION_NAME,
        category_name="Movement",
        category_is_negative=False,
        category_display_order=40,
        description=(
            "A transient teleportation marker applied when the caster invokes Phase Jump.  "
            "The CONDITION_APPLIED trigger immediately relocates the caster to the target "
            "position, then the marker expires."
        ),
    )
    condition.reactive_triggers.add(teleport_trigger)

    # 4. Technique.
    _seed_technique(
        TELEPORT_TECHNIQUE_NAME,
        gift_name="Translocation",
        style_name=TRANSLOCATION_STANCE_STYLE_NAME,
        effect_type_name="Teleport",
        description="Techniques that bend space to move the caster instantly.",
        technique_description=(
            "Phase through space in a heartbeat, instantly relocating to a target position "
            "within the encounter."
        ),
        condition_template=condition,
    )


def ensure_obstacle_content() -> None:
    """Idempotently seed the Barricade (obstacle) active-effect bundle (#1584, Task 14c).

    Creates (get_or_create):

    1. A ``FlowDefinition`` (``obstacle_on_condition_applied``) with a single
       ``CALL_SERVICE_FUNCTION`` step pointing at ``create_obstacle_on_condition``,
       passing ``{"payload": "@payload", "position_a_id": 0, "position_b_id": 0}``
       (placeholder positions; runtime target selection is a follow-up).
    2. A ``TriggerDefinition`` on ``CONDITION_APPLIED`` with a SELF filter.
    3. A "Barricade" ``ConditionTemplate`` (``OBSTACLE_CONDITION_NAME``) in the
       "Movement" category, duration ``UNTIL_USED``.
    4. A "Barricade" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    # 1. Flow: single CALL_SERVICE_FUNCTION step with static position placeholders.
    root_step = _seed_call_service_flow(
        _OBSTACLE_FLOW_NAME,
        _CREATE_OBSTACLE_ADAPTER_PATH,
        extra_params={
            "position_a_id": _PLACEHOLDER_POSITION_ID,
            "position_b_id": _PLACEHOLDER_POSITION_ID,
        },
    )
    obstacle_flow = root_step.flow

    # 2. Trigger: CONDITION_APPLIED, SELF filter.
    obstacle_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_OBSTACLE_TRIGGER_NAME,
        defaults={
            "event_name": EventName.CONDITION_APPLIED,
            "flow_definition": obstacle_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 0,
            "description": (
                "Creates an impassable barrier between two positions when the Barricade "
                "condition is applied (CONDITION_APPLIED; active obstacle effect)."
            ),
        },
    )

    # 3. ConditionTemplate: "Barricade" marker in the Movement category.
    condition = _seed_active_condition(
        OBSTACLE_CONDITION_NAME,
        category_name="Movement",
        category_is_negative=False,
        category_display_order=40,
        description=(
            "A transient barrier marker applied when the caster invokes Barricade.  "
            "The CONDITION_APPLIED trigger seals the edge between two positions, "
            "then the marker expires."
        ),
    )
    condition.reactive_triggers.add(obstacle_trigger)

    # 4. Technique.
    _seed_technique(
        OBSTACLE_TECHNIQUE_NAME,
        gift_name="Translocation",
        style_name=TRANSLOCATION_STANCE_STYLE_NAME,
        effect_type_name="Obstacle",
        description="Techniques that reshape the battlefield with barriers and blockades.",
        technique_description=(
            "Erect an impassable magical barrier between two positions in the encounter, "
            "forcing enemies to find another route."
        ),
        condition_template=condition,
    )


def ensure_incorporeal_content() -> None:
    """Idempotently seed the Ghostform (incorporeal) bundle (#1584, Task 14c).

    No handler or trigger is wired — the Task 8 targeting gate reads
    ``ConditionCategory.grants_intangibility`` to make the bearer untargetable while
    Ghostform is active.  Creates (get_or_create):

    1. An "Incorporeal" ``ConditionCategory`` with ``grants_intangibility=True``.
    2. A "Ghostform" ``ConditionTemplate`` (``INCORPOREAL_CONDITION_NAME``) lasting
       until end of combat (sustained incorporeal form).
    3. A "Ghostform" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415

    condition = _seed_intangibility_condition(
        INCORPOREAL_CONDITION_NAME,
        description=(
            "The caster's body becomes insubstantial, phasing through physical matter "
            "and rendering them untargetable by mundane attacks.  Lasts until the end "
            "of combat or until dispelled."
        ),
        default_duration_type=DurationType.UNTIL_END_OF_COMBAT,
        default_duration_value=1,
    )

    _seed_technique(
        INCORPOREAL_TECHNIQUE_NAME,
        gift_name="Translocation",
        style_name=TRANSLOCATION_STANCE_STYLE_NAME,
        effect_type_name="Incorporeal Form",
        description="Techniques that phase the caster out of the physical plane.",
        technique_description=(
            "Render yourself incorporeal for the duration of the encounter, passing "
            "through physical barriers and becoming untargetable by mundane weapons."
        ),
        condition_template=condition,
    )


def ensure_sink_content() -> None:
    """Idempotently seed the Earthmeld (sink into earth) bundle (#1584, Task 14c).

    Like Ghostform but lasts only 1 round — a burst of intangibility for defensive
    timing.  No handler or trigger; the Task 8 targeting gate does the work via
    ``ConditionCategory.grants_intangibility``.  Creates (get_or_create):

    1. An "Incorporeal" ``ConditionCategory`` with ``grants_intangibility=True``
       (shared with Ghostform).
    2. An "Earthmeld" ``ConditionTemplate`` (``SINK_CONDITION_NAME``) lasting
       1 round (shorter than Ghostform's until-end-of-combat).
    3. An "Earthmeld" ``Technique`` with a SELF ``TechniqueAppliedCondition``.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415

    condition = _seed_intangibility_condition(
        SINK_CONDITION_NAME,
        description=(
            "The caster sinks into the earth momentarily, becoming untargetable for "
            "one round before surfacing.  A brief but potent defensive maneuver."
        ),
        default_duration_type=DurationType.ROUNDS,
        default_duration_value=1,
    )

    _seed_technique(
        SINK_TECHNIQUE_NAME,
        gift_name="Translocation",
        style_name=TRANSLOCATION_STANCE_STYLE_NAME,
        effect_type_name="Earth Sink",
        description="Techniques that merge the caster with the earth for a fleeting moment.",
        technique_description=(
            "Sink into the earth for one round, becoming untargetable.  "
            "A burst defensive technique with the shortest possible window of intangibility."
        ),
        condition_template=condition,
    )


def ensure_telekinesis_content() -> None:
    """Idempotently seed the Force Grip (telekinesis) active-effect bundle (#1584, Task 14c).

    Applies the "Force Grip" condition to an **enemy** target; the CONDITION_APPLIED
    trigger repositions that enemy via ``move_position_on_condition``.  Damage is
    deferred as a follow-up (MVP = reposition only).  Creates (get_or_create):

    1. A ``FlowDefinition`` (``telekinesis_on_condition_applied``) with a single
       ``CALL_SERVICE_FUNCTION`` step → ``move_position_on_condition``.
    2. A ``TriggerDefinition`` on ``CONDITION_APPLIED`` with a SELF filter (fires on
       the enemy's bearer, which is the enemy objectdb for an ENEMY condition).
    3. A "Force Grip" ``ConditionTemplate`` (``TELEKINESIS_CONDITION_NAME``) in the
       "Control" category, duration ``UNTIL_USED``.
    4. A "Force Grip" ``Technique`` with an **ENEMY** ``TechniqueAppliedCondition``.
    """
    # 1. Flow: single CALL_SERVICE_FUNCTION step with static destination placeholder.
    root_step = _seed_call_service_flow(
        _TELEKINESIS_FLOW_NAME,
        _FORCE_MOVE_ADAPTER_PATH,
        extra_params={"destination_position_id": _PLACEHOLDER_POSITION_ID},
    )
    telekinesis_flow = root_step.flow

    # 2. Trigger: CONDITION_APPLIED, SELF filter (payload.target = the repositioned enemy).
    telekinesis_trigger, _created = TriggerDefinition.objects.get_or_create(
        name=_TELEKINESIS_TRIGGER_NAME,
        defaults={
            "event_name": EventName.CONDITION_APPLIED,
            "flow_definition": telekinesis_flow,
            "base_filter_condition": _SELF_TARGET_FILTER,
            "priority": 0,
            "description": (
                "Repositions an enemy when the Force Grip condition is applied to them "
                "(CONDITION_APPLIED; active telekinesis effect, ENEMY target)."
            ),
        },
    )

    # 3. ConditionTemplate: "Force Grip" marker in the Control category.
    condition = _seed_active_condition(
        TELEKINESIS_CONDITION_NAME,
        category_name="Control",
        category_is_negative=True,  # applied to enemies
        category_display_order=50,
        description=(
            "An invisible telekinetic grip applied to an enemy.  The CONDITION_APPLIED "
            "trigger immediately flings the target to a new position, then the marker "
            "expires.  Damage follow-up is a future enhancement."
        ),
    )
    condition.reactive_triggers.add(telekinesis_trigger)

    # 4. Technique — ENEMY target kind.
    _seed_technique(
        TELEKINESIS_TECHNIQUE_NAME,
        gift_name="Translocation",
        style_name=TRANSLOCATION_STANCE_STYLE_NAME,
        effect_type_name="Telekinesis",
        description="Techniques that move objects and enemies with invisible force.",
        technique_description=(
            "Seize an enemy in an invisible telekinetic grip and hurl them to another "
            "position.  MVP: reposition only; damage is a future follow-up."
        ),
        condition_template=condition,
        target_kind=ConditionTargetKind.ENEMY,
    )


def ensure_rampart_content() -> None:
    """Idempotently seed the "Raise Rampart" bundle: 4 elemental profiles + techniques (#2209).

    For each of Stone/Wind/Fire/Thorn, creates (get_or_create):

    1. A ``RampartElementProfile`` named after the element, with its authored
       ``signature_behavior``/``signature_value`` and a couple of small
       ``RampartElementResistance`` rows (2-6).
    2. A ``FlowDefinition`` with a single ``CALL_SERVICE_FUNCTION`` step pointing at
       ``raise_rampart_on_condition``, carrying the profile's name and a mid-tier
       ``integrity`` (24) as static params alongside the placeholder ``position_id``
       (runtime destination selection is the cast-time ``cast_destination``, same
       mechanism Barricade/teleport use).
    3. A ``TriggerDefinition`` on ``CONDITION_APPLIED`` with a SELF filter.
    4. A "<Element> Rampart" marker ``ConditionTemplate`` in the "Fortification"
       category, duration ``UNTIL_USED``.
    5. A "Raise Rampart (<Element>)" ``Technique`` with a SELF ``TechniqueAppliedCondition``.

    Thorn's GRASPING signature additionally seeds the "Entangled" ``ConditionTemplate``
    (``RAMPART_ENTANGLED_CONDITION_NAME``) in a "Restrained" category — applied not
    through this bundle's own trigger but at the shared forced-move landing seam
    (``world.mechanics.effect_handlers._apply_grasping_if_covered``).
    """
    from world.areas.positioning.models import (  # noqa: PLC0415
        RampartElementProfile,
        RampartElementResistance,
    )
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, DamageType  # noqa: PLC0415

    for (
        element_name,
        signature_behavior,
        signature_value,
        signature_damage_type_name,
        signature_condition_name,
        resistances,
    ) in _RAMPART_ELEMENTS:
        signature_damage_type = None
        if signature_damage_type_name is not None:
            signature_damage_type, _created = DamageType.objects.get_or_create(
                name=signature_damage_type_name
            )

        signature_condition = None
        if signature_condition_name is not None:
            restrained_cat, _created = ConditionCategory.objects.get_or_create(
                name="Restrained",
                defaults={
                    "description": "Conditions that bind or immobilize the bearer.",
                    "is_negative": True,
                    "display_order": 45,
                },
            )
            signature_condition, _created = ConditionTemplate.objects.get_or_create(
                name=signature_condition_name,
                defaults={
                    "description": (
                        "Bound by grasping growth after being forced onto a Thorn "
                        "rampart's position."
                    ),
                    "category": restrained_cat,
                    "default_duration_type": DurationType.ROUNDS,
                    "default_duration_value": 2,
                    "is_stackable": False,
                    "max_stacks": 1,
                    "has_progression": False,
                    "can_be_dispelled": True,
                },
            )

        # 1. RampartElementProfile + resistances.
        profile, _created = RampartElementProfile.objects.get_or_create(
            name=element_name,
            defaults={
                "description": f"A living barrier woven from {element_name.lower()}.",
                "signature_behavior": signature_behavior,
                "signature_value": signature_value,
                "signature_damage_type": signature_damage_type,
                "signature_condition": signature_condition,
            },
        )
        for damage_type_name, value in resistances:
            damage_type, _created = DamageType.objects.get_or_create(name=damage_type_name)
            RampartElementResistance.objects.get_or_create(
                profile=profile,
                damage_type=damage_type,
                defaults={"value": value},
            )

        # 2. Flow: single CALL_SERVICE_FUNCTION step with static position placeholder.
        root_step = _seed_call_service_flow(
            f"rampart_{element_name.lower()}_on_condition_applied",
            _RAISE_RAMPART_ADAPTER_PATH,
            extra_params={
                "position_id": _PLACEHOLDER_POSITION_ID,
                "element_profile_name": profile.name,
                "integrity": _RAMPART_INTEGRITY,
            },
        )
        rampart_flow = root_step.flow

        # 3. Trigger: CONDITION_APPLIED, SELF filter.
        rampart_trigger, _created = TriggerDefinition.objects.get_or_create(
            name=f"rampart_{element_name.lower()}_condition_applied",
            defaults={
                "event_name": EventName.CONDITION_APPLIED,
                "flow_definition": rampart_flow,
                "base_filter_condition": _SELF_TARGET_FILTER,
                "priority": 0,
                "description": (
                    f"Raises a {element_name} rampart at the cast destination when the "
                    f"{element_name} Rampart condition is applied."
                ),
            },
        )

        # 4. ConditionTemplate: "<Element> Rampart" marker in the Fortification category.
        condition = _seed_active_condition(
            f"{element_name} Rampart",
            category_name="Fortification",
            category_is_negative=False,
            category_display_order=41,
            description=(
                f"A transient marker applied when the caster invokes Raise Rampart "
                f"({element_name}). The CONDITION_APPLIED trigger raises the living "
                "barrier, then the marker expires."
            ),
        )
        condition.reactive_triggers.add(rampart_trigger)

        # 5. Technique.
        _seed_technique(
            f"Raise Rampart ({element_name})",
            gift_name=RAMPART_GIFT_NAME,
            style_name=RAMPART_STYLE_NAME,
            effect_type_name="Fortification",
            description="Techniques that raise living barriers on the battlefield.",
            technique_description=(
                f"Weave a {element_name.lower()}-aspected living barrier at the target "
                "position, chipping down as it absorbs strikes."
            ),
            condition_template=condition,
        )


# ---------------------------------------------------------------------------
# Unified entry point — Task 14c
# ---------------------------------------------------------------------------


def ensure_effect_palette_content() -> None:
    """Idempotently seed the complete castable effect palette (#1584).

    Calls every ``ensure_*_content()`` builder in dependency order.  Safe to
    call repeatedly (all builders are idempotent via ``get_or_create``).

    Bundles seeded:
    - **Task 14a** — Summon Spirit (CONDITION_APPLIED → summon_ally).
    - **Task 14b** — Aegis Field (absorb_pool), Mirror Ward (reflect_damage),
      Phase Step (blink_dodge).
    - **Task 14c** — Phase Jump (teleport), Barricade (obstacle), Ghostform
      (incorporeal), Earthmeld (sink), Force Grip (telekinesis).
    - **#2209** — Raise Rampart (Stone/Wind/Fire/Thorn).

    This is the single function that integration-test setup (Tasks 15/16 E2Es)
    and the staff seed loader call.
    """
    # 14a
    ensure_summon_content()
    # 14b
    ensure_force_field_content()
    ensure_reflect_content()
    ensure_blink_content()
    # 14c
    ensure_teleport_content()
    ensure_obstacle_content()
    ensure_incorporeal_content()
    ensure_sink_content()
    ensure_telekinesis_content()
    # #2209
    ensure_rampart_content()
