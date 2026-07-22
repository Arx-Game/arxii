"""Production seed content for the survivability pipeline (#2287).

Everything here is idempotent (get_or_create / fill-only-when-null) so the
cluster can re-run safely without clobbering staff edits. This cluster is what
makes knockout/death actually fire on a fresh database: the pipeline in
``world.vitals.services`` deliberately no-ops any tier whose pool is missing,
and until #2287 the pool content existed only in test factories.

Seeded content:

- Foundational ``CapabilityType`` rows (awareness / movement / limb_use) —
  ``can_act`` degrades to always-True without the awareness row.
- The ``Unconscious`` condition + capability-zeroing effects.
- The ``Bleeding Out`` staged condition (template + 3 stages).
- The three mechanical wound conditions (Lingering Ache / Crippling Wound /
  Bleeding Wound, #2644) + one TreatmentTemplate each for the bounded HP mend.
- The knockout / default-death / default-wound consequence pools, wired onto
  the ``VitalsConsequenceConfig`` singleton (only when currently null). The
  wound pool's partial/failure outcomes apply Lingering Ache / Crippling
  Wound (#2644 — closes the prior effect-free gap).
- The bleed-out terminal / abandonment / surrounded pools (reuses the
  ensure-style creators in ``world.vitals.factories``).
- The ``death`` KudosSourceCategory (death-kudos earning channel).
- The liminal dream room unconscious characters perceive (#2287; the dream
  realm proper replaces this later — see #2290).
- A PLACEHOLDER condolence paragraph on the config singleton.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.vitals.constants import (
    BLEED_OUT_STAGE_SPECS,
    DREAM_ROOM_KEY,
    DREAM_ROOM_TAG,
    DREAM_ROOM_TAG_CATEGORY,
    POOL_DEFAULT_DEATH,
    POOL_DEFAULT_WOUND,
    POOL_KNOCKOUT,
    SLEEPING_CONDITION_NAME,
    WOUND_BLEEDING_NAME,
    WOUND_CRIPPLING_NAME,
    WOUND_LINGERING_ACHE_NAME,
)
from world.vitals.factories import (
    _ensure_peril_category,
    _get_or_create_outcome,
    _seed_pool_consequences,
    create_abandonment_pools,
    create_bleed_out_terminal_pool,
    ensure_surrounded_content,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.checks.models import Consequence
    from world.conditions.models import ConditionCategory, ConditionTemplate

_OUTCOME_FAILURE = "Failure"
_OUTCOME_PARTIAL = "Partial Success"
_OUTCOME_SUCCESS = "Success"

# PLACEHOLDER — Apostate rewrites (admin-editable on VitalsConsequenceConfig).
_DEFAULT_CONDOLENCE_BODY = (
    "PLACEHOLDER: Your character has died. We are very sorry — a permanent "
    "death is a hard moment, especially for a character you have played and "
    "loved for a long time. If you feel this death was in any way unfair or "
    "unjustified, you can reach out to staff about it. Otherwise, you are "
    "free to write your character's exit in final poses while the scene "
    "remains open, and when you are ready to let go, use the retire command "
    "to lay them to rest."
)

# PLACEHOLDER — Apostate rewrites (room desc is world data, editable in-game).
_DREAM_ROOM_DESC = (
    "PLACEHOLDER: A shoreless gray hush, neither waking nor gone. Shapes "
    "drift at the edge of sight like thoughts half-remembered. Somewhere far "
    "above, muffled and slow, the waking world goes on without you."
)


def ensure_foundational_capabilities() -> None:
    """Ensure the foundational CapabilityType rows exist with baseline >= 1.

    ``can_act`` treats a missing awareness CapabilityType as "capability
    system unseeded" and returns True for everyone — so this row is what
    makes Unconscious actually stop a character from acting in production.
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    specs = [
        (FoundationalCapability.AWARENESS, "Basic consciousness; unconscious zeroes it."),
        (FoundationalCapability.MOVEMENT, "Locomotion; immobilized/rooted zeroes it."),
        (FoundationalCapability.LIMB_USE, "Using arms and hands; bound reduces it."),
    ]
    for name, description in specs:
        capability, created = CapabilityType.objects.get_or_create(
            name=name,
            defaults={"innate_baseline": 1, "description": description},
        )
        if not created and capability.innate_baseline < 1:
            # Foundational rows are code-owned: a zero baseline here means every
            # character is permanently incapacitated, so correct it on re-seed.
            capability.innate_baseline = 1
            capability.save(update_fields=["innate_baseline"])


def ensure_unconscious_condition() -> ConditionTemplate:
    """Ensure the Unconscious condition + its capability-zeroing effects."""
    from world.conditions.constants import (  # noqa: PLC0415
        UNCONSCIOUS_CONDITION_NAME,
        DurationType,
        FoundationalCapability,
    )
    from world.conditions.models import (  # noqa: PLC0415
        CapabilityType,
        ConditionCapabilityEffect,
        ConditionTemplate,
    )

    ensure_foundational_capabilities()
    category = _ensure_peril_category()

    template, _ = ConditionTemplate.objects.get_or_create(
        name=UNCONSCIOUS_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "Completely incapacitated. Cannot take any actions, defenseless.",
            "player_description": (
                "You are unconscious, adrift somewhere between waking and dream."
            ),
            "observer_description": "lies unconscious, completely unresponsive.",
            "default_duration_type": DurationType.UNTIL_CURED,
            "default_duration_value": 0,
            "is_visible_to_others": True,
        },
    )

    for capability_name in (FoundationalCapability.AWARENESS, FoundationalCapability.MOVEMENT):
        capability = CapabilityType.objects.get(name=capability_name)
        ConditionCapabilityEffect.objects.get_or_create(
            condition=template,
            stage=None,
            capability=capability,
            defaults={"value": -100},
        )
    return template


def ensure_sleeping_condition() -> ConditionTemplate:
    """Ensure the Sleeping condition for voluntary dream entry (#2290).

    Mirrors Unconscious's capability-zeroing (awareness, movement, limb_use → 0)
    but is voluntarily applied by SleepAction and has no guaranteed-wake
    deadline — the character wakes when they choose (via ``wake``), unless
    dream-engaged (an active scene round in the dream room stamps a deadline).
    """
    from world.conditions.constants import (  # noqa: PLC0415
        DurationType,
        FoundationalCapability,
    )
    from world.conditions.models import (  # noqa: PLC0415
        CapabilityType,
        ConditionCapabilityEffect,
        ConditionTemplate,
    )

    ensure_foundational_capabilities()
    category = _ensure_peril_category()

    template, _ = ConditionTemplate.objects.get_or_create(
        name=SLEEPING_CONDITION_NAME,
        defaults={
            "category": category,
            "description": ("Asleep and dreaming. Cannot take any actions in the waking world."),
            "player_description": (
                "You drift in dreams, your body resting somewhere in the waking world."
            ),
            "observer_description": "lies asleep, lost in dreams.",
            "default_duration_type": DurationType.UNTIL_CURED,
            "default_duration_value": 0,
            "is_visible_to_others": True,
        },
    )

    for capability_name in (
        FoundationalCapability.AWARENESS,
        FoundationalCapability.MOVEMENT,
        FoundationalCapability.LIMB_USE,
    ):
        capability = CapabilityType.objects.get(name=capability_name)
        ConditionCapabilityEffect.objects.get_or_create(
            condition=template,
            stage=None,
            capability=capability,
            defaults={"value": -100},
        )
    return template


def ensure_bleeding_out_condition() -> ConditionTemplate:
    """Ensure the Bleeding Out staged condition (template + 3 stages).

    The death tier applies this condition instead of killing outright
    (ADR-0040/ADR-0049); ``advance_bleed_out`` walks the stages each round and
    the terminal stage resolves through the guarded ``bleed_out_terminal``
    pool. Stage resists use Mortal Resolve (willpower), matching the death
    check the tier itself rolls.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
        DurationType,
    )
    from world.conditions.models import ConditionStage, ConditionTemplate  # noqa: PLC0415
    from world.vitals.services import _ensure_death_check_type  # noqa: PLC0415

    check_type = _ensure_death_check_type()
    category = _ensure_peril_category()

    template, _ = ConditionTemplate.objects.get_or_create(
        name=BLEED_OUT_CONDITION_NAME,
        defaults={
            "category": category,
            "has_progression": True,
            "description": "Dying: life is draining away without intervention.",
            "player_description": (
                "PLACEHOLDER: You are dying. The world narrows; every breath is a fight."
            ),
            "observer_description": "PLACEHOLDER: is bleeding out, life visibly fading.",
            "default_duration_type": DurationType.UNTIL_CURED,
            "default_duration_value": 0,
            "is_visible_to_others": True,
        },
    )

    for order, name, difficulty, rounds_to_next in BLEED_OUT_STAGE_SPECS:
        ConditionStage.objects.get_or_create(
            condition=template,
            stage_order=order,
            defaults={
                "name": name,
                "description": f"PLACEHOLDER: {name} — the dying deepens.",
                "resist_check_type": check_type,
                "resist_difficulty": difficulty,
                "rounds_to_next": rounds_to_next,
            },
        )
    return template


def _ensure_wound_category() -> ConditionCategory:
    """Return the ConditionCategory grouping the three mechanical wound conditions."""
    from world.conditions.models import ConditionCategory  # noqa: PLC0415

    obj, _ = ConditionCategory.objects.get_or_create(
        name="Wound",
        defaults={
            "description": (
                "Permanent-wound conditions from grievous damage — cleansable "
                "(severity decay/dispel) and treatable (bounded HP mend), #2644."
            ),
            "is_negative": True,
        },
    )
    return obj


def ensure_wound_conditions() -> tuple[ConditionTemplate, ConditionTemplate, ConditionTemplate]:
    """Ensure the three mechanical wound ConditionTemplates (#2644).

    Mechanics vocabulary, not lore content (mirrors ensure_bleeding_out_condition) —
    severity is stamped by the wound-pool outcome tier that applies each one.
    Returns (lingering_ache, crippling_wound, bleeding_wound).

    - Lingering Ache (partial-tier default): modest Endurance check penalty.
    - Crippling Wound (failure-tier default): modest limb_use capability penalty.
    - Bleeding Wound (authored, available for future per-DamageType wound-pool
      routing via DamageType.wound_pool — not wired into the default pool; see
      ensure_default_wound_pool's docstring for the documented single-default
      choice, ADR-0155): modest severity-scaled physical DoT.

    All three: is_stackable=False (severity refreshes/raises on re-wounding via
    _handle_refresh, matching how _record_wound_details accumulates damage_taken
    onto the same WoundDetails row), can_be_dispelled=True (default — cleansing
    stays unrestricted), UNTIL_CURED duration (a wound doesn't time out).
    """
    from world.conditions.constants import (  # noqa: PLC0415
        DamageTickTiming,
        DurationType,
        FoundationalCapability,
    )
    from world.conditions.models import (  # noqa: PLC0415
        CapabilityType,
        ConditionCapabilityEffect,
        ConditionCheckModifier,
        ConditionDamageOverTime,
        ConditionTemplate,
        DamageType,
    )
    from world.vitals.services import _ensure_endurance_check_type  # noqa: PLC0415

    ensure_foundational_capabilities()
    category = _ensure_wound_category()
    common_defaults = {
        "category": category,
        "default_duration_type": DurationType.UNTIL_CURED,
        "default_duration_value": 0,
        "is_visible_to_others": True,
    }

    lingering_ache, _ = ConditionTemplate.objects.get_or_create(
        name=WOUND_LINGERING_ACHE_NAME,
        defaults={
            **common_defaults,
            "description": "A wound that never fully healed; it aches with exertion.",
            "player_description": "An old wound aches, sapping your stamina.",
            "observer_description": "moves with a faint, guarded stiffness.",
        },
    )
    endurance_check = _ensure_endurance_check_type()
    ConditionCheckModifier.objects.get_or_create(
        condition=lingering_ache,
        stage=None,
        check_type=endurance_check,
        defaults={"modifier_value": -5, "scales_with_severity": False},
    )

    crippling_wound, _ = ConditionTemplate.objects.get_or_create(
        name=WOUND_CRIPPLING_NAME,
        defaults={
            **common_defaults,
            "description": "A grievous wound that never set right; the limb answers poorly.",
            "player_description": "The wound left you crippled — the limb won't fully answer.",
            "observer_description": "favors a limb that no longer moves quite right.",
        },
    )
    limb_use = CapabilityType.objects.get(name=FoundationalCapability.LIMB_USE)
    ConditionCapabilityEffect.objects.get_or_create(
        condition=crippling_wound,
        stage=None,
        capability=limb_use,
        defaults={"value": -15},
    )

    bleeding_wound, _ = ConditionTemplate.objects.get_or_create(
        name=WOUND_BLEEDING_NAME,
        defaults={
            **common_defaults,
            "description": "An open wound that won't stop bleeding without care.",
            "player_description": "Your wound won't stop bleeding.",
            "observer_description": "is bleeding steadily from an open wound.",
        },
    )
    physical_damage, _ = DamageType.objects.get_or_create(name="Physical")
    ConditionDamageOverTime.objects.get_or_create(
        condition=bleeding_wound,
        stage=None,
        damage_type=physical_damage,
        defaults={
            "base_damage": 1,
            "scales_with_severity": True,
            "scales_with_stacks": False,
            "tick_timing": DamageTickTiming.END_OF_ROUND,
            "is_long_term": False,
        },
    )

    return lingering_ache, crippling_wound, bleeding_wound


def _ensure_apply_condition_effect(
    consequence: Consequence,
    template: ConditionTemplate,
    *,
    severity: int = 1,
) -> None:
    """Idempotently wire an APPLY_CONDITION effect onto a consequence."""
    from world.checks.constants import EffectTarget, EffectType  # noqa: PLC0415
    from world.checks.models import ConsequenceEffect  # noqa: PLC0415

    ConsequenceEffect.objects.get_or_create(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        execution_order=0,
        defaults={
            "target": EffectTarget.SELF,
            "condition_template": template,
            "condition_severity": severity,
        },
    )


def ensure_knockout_pool() -> ConsequencePool:
    """Ensure the global knockout pool: failed low-health checks apply Unconscious."""
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    unconscious = ensure_unconscious_condition()

    pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_KNOCKOUT,
        defaults={
            "description": (
                "Global knockout pool: rolled when a hit lands at or below the "
                "knockout health threshold. Failure/partial apply Unconscious."
            )
        },
    )
    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "shrug_it_off", 2, False),
            (partial, "knocked_out", 2, False),
            (failure, "knocked_out_cold", 2, False),
        ],
    )
    for label in ("knocked_out", "knocked_out_cold"):
        consequence = Consequence.objects.get(label=label)
        _ensure_apply_condition_effect(consequence, unconscious)
    return pool


def ensure_default_death_pool() -> ConsequencePool:
    """Ensure the default death pool: a failed death check applies Bleeding Out."""
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    bleeding_out = ensure_bleeding_out_condition()

    pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_DEFAULT_DEATH,
        defaults={
            "description": (
                "Default death pool: rolled when health drops to zero or below. "
                "Failure applies Bleeding Out (dying), never instant death "
                "(ADR-0040/ADR-0049)."
            )
        },
    )
    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "defiant_survival", 2, False),
            (partial, "grievous_but_stable", 2, False),
            (failure, "mortal_blow", 2, False),
        ],
    )
    consequence = Consequence.objects.get(label="mortal_blow")
    _ensure_apply_condition_effect(consequence, bleeding_out)
    return pool


def ensure_default_wound_pool() -> ConsequencePool:
    """Ensure the default permanent-wound pool (#2644 — closes the audit's central gap).

    Three-outcome graded shape unchanged; outcomes now carry real APPLY_CONDITION
    effects: best (shaken_off) stays effect-free by design (a wound you shook off
    IS effect-free); partial (lasting_ache) applies Lingering Ache; worst
    (lasting_scar) applies Crippling Wound.

    Bleeding Wound is authored (ensure_wound_conditions) but deliberately NOT
    wired into this pool's worst tier — documented judgment call: the pool
    machinery has no simple per-damage-type branch at the single-pool level
    (that lives one layer up, via DamageType.wound_pool routing to a DIFFERENT
    pool entirely), and authoring a second worst-tier ConsequencePoolEntry would
    need weighted alternation, not a real pick. Crippling Wound was chosen as
    the single authored default because it's the more universally-applicable
    mechanical flavor (any damage type can cripple; not every damage type
    plausibly bleeds, e.g. blunt/force). A future DamageType-specific wound
    pool (e.g. for slashing/piercing types) can route to Bleeding Wound with no
    schema change — the condition already exists. See ADR-0155.

    update_or_create on the pool row (not get_or_create) so a stale
    pre-#2644 description on an already-seeded database is corrected on
    re-run; the ConsequenceEffect rows below use get_or_create as their own
    idempotent upsert — a prior run's effect-free consequence rows simply
    gain the effect they were missing, no delete-and-recreate.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    lingering_ache, crippling_wound, _bleeding_wound = ensure_wound_conditions()

    pool, _ = ConsequencePool.objects.update_or_create(
        name=POOL_DEFAULT_WOUND,
        defaults={
            "description": (
                "Default permanent-wound pool: success (shaken_off) is effect-free, "
                "partial applies Lingering Ache, failure applies Crippling Wound (#2644)."
            )
        },
    )
    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "shaken_off", 2, False),
            (partial, "lasting_ache", 2, False),
            (failure, "lasting_scar", 2, False),
        ],
    )
    consequence = Consequence.objects.get(label="lasting_ache")
    _ensure_apply_condition_effect(consequence, lingering_ache, severity=1)
    consequence = Consequence.objects.get(label="lasting_scar")
    _ensure_apply_condition_effect(consequence, crippling_wound, severity=2)
    return pool


def ensure_wound_treatment_content() -> None:
    """Seed one TreatmentTemplate per wound condition (#2644 — bounded HP mend).

    **Check type — documented judgment call.** No Medicine/first-aid CheckType
    exists anywhere in the codebase's seeded content (checked every production
    seed file); authoring a new stat+skill composition (a Medicine Skill/Trait
    plus its CheckType) is a bigger content-authoring lift than this mechanics-
    vocabulary pass calls for. Reuses the vitals-owned ``Endurance`` CheckType
    (Stamina resist check, already seeded by ``_ensure_endurance_check_type``)
    per the spec's fallback clause ("reuse an existing broadly-applicable [check
    type] and document") — a proper Medicine composition is a future authoring
    pass; ``TreatmentTemplate.check_type`` just gets repointed, no schema change.

    Modest ``anima_cost`` (no bond thread requirement — unlike the Soulfray/
    Mage-Scar aftermath treatments, tending a physical wound doesn't require an
    established magical bond). ``once_per_wound_per_helper=True`` +
    ``once_per_scene_per_helper=False``: the double-bounded-mend gate is
    scene-independent — each healer gets exactly one tending per wound, ever,
    not one per scene (#2644 spec).
    """
    from world.conditions.constants import TreatmentTargetKind  # noqa: PLC0415
    from world.conditions.models import TreatmentTemplate  # noqa: PLC0415
    from world.vitals.services import _ensure_endurance_check_type  # noqa: PLC0415

    lingering_ache, crippling_wound, bleeding_wound = ensure_wound_conditions()
    check_type = _ensure_endurance_check_type()

    specs = [
        ("treat_lingering_ache", "Tend Lingering Ache", lingering_ache),
        ("treat_crippling_wound", "Tend Crippling Wound", crippling_wound),
        ("treat_bleeding_wound", "Tend Bleeding Wound", bleeding_wound),
    ]
    for key, name, wound_template in specs:
        TreatmentTemplate.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "description": f"Tend a {wound_template.name.lower()} — real relief, bounded mend.",
                "target_condition": wound_template,
                "target_kind": TreatmentTargetKind.PRIMARY,
                "check_type": check_type,
                "target_difficulty": 15,
                "requires_bond": False,
                "resonance_cost": 0,
                "anima_cost": 5,
                "once_per_scene_per_helper": False,
                "once_per_wound_per_helper": True,
                "scene_required": True,
                "backlash_severity_on_failure": 0,
                "reduction_on_crit": 2,
                "reduction_on_success": 1,
                "reduction_on_partial": 1,
                "reduction_on_failure": 0,
                "mend_on_crit": 8,
                "mend_on_success": 5,
                "mend_on_partial": 2,
            },
        )


def ensure_death_kudos_category() -> None:
    """Ensure the death-kudos KudosSourceCategory (#2287 death-kudos channel)."""
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.get_or_create(
        name="death",
        defaults={
            "display_name": "Graceful Death",
            "description": (
                "Honoring a player who handled their character's death well. "
                "Scaled grants are capped at the character's lifetime XP spend."
            ),
            "default_amount": 1,
            "staff_only": False,
        },
    )


def ensure_dream_room() -> ObjectDB:
    """Ensure the liminal dream room unconscious characters perceive.

    A single PLACEHOLDER room, looked up by system tag; the dream realm
    proper (#2290) replaces this. World data, editable in-game.
    """
    from evennia.utils import create as evennia_create  # noqa: PLC0415
    from evennia.utils.search import search_tag  # noqa: PLC0415

    existing = search_tag(key=DREAM_ROOM_TAG, category=DREAM_ROOM_TAG_CATEGORY)
    if existing:
        return existing[0]
    room = evennia_create.create_object(
        typeclass="typeclasses.rooms.Room",
        key=DREAM_ROOM_KEY,
        nohome=True,
    )
    room.db.desc = _DREAM_ROOM_DESC
    room.tags.add(DREAM_ROOM_TAG, category=DREAM_ROOM_TAG_CATEGORY)
    return room


def _wire_consequence_config() -> None:
    """Fill null pool FKs + empty condolence text on the config singleton.

    Fill-only-when-null so staff overrides survive re-seeding.
    """
    from world.vitals.models import VitalsConsequenceConfig  # noqa: PLC0415

    config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
    update_fields: list[str] = []
    if config.knockout_pool_id is None:
        config.knockout_pool = ensure_knockout_pool()
        update_fields.append("knockout_pool")
    else:
        ensure_knockout_pool()
    if config.default_death_pool_id is None:
        config.default_death_pool = ensure_default_death_pool()
        update_fields.append("default_death_pool")
    else:
        ensure_default_death_pool()
    if config.default_wound_pool_id is None:
        config.default_wound_pool = ensure_default_wound_pool()
        update_fields.append("default_wound_pool")
    else:
        ensure_default_wound_pool()
    if not config.death_condolence_body:
        config.death_condolence_body = _DEFAULT_CONDOLENCE_BODY
        update_fields.append("death_condolence_body")
    if update_fields:
        config.save(update_fields=update_fields)


def seed_survivability_content() -> None:
    """Seed everything the survivability pipeline needs to fire in production."""
    ensure_foundational_capabilities()
    ensure_unconscious_condition()
    ensure_sleeping_condition()
    ensure_bleeding_out_condition()
    ensure_wound_conditions()
    create_bleed_out_terminal_pool()
    create_abandonment_pools()
    ensure_surrounded_content()
    _wire_consequence_config()
    ensure_death_kudos_category()
    ensure_dream_room()
    ensure_wound_treatment_content()
