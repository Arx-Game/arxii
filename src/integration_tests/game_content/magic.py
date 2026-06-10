"""Magic test-infrastructure: seed helpers and MagicContent.

Exports:
- ``seed_magic_dev()`` — master orchestrator for the entire magic cluster.
  Composes all Phase 1 seed helpers into a single idempotent call. This is
  the magic-cluster contribution to Phase 3's ``seed_dev_database()``.
- ``seed_magic_config()`` — Task 1.1 — singletons + IntensityTier + MishapPoolTier
- ``seed_canonical_rituals()`` — Task 1.2 — Rite of Imbuing + Rite of Atonement
- ``seed_thread_pull_catalog()`` — Task 1.3 — ThreadPullCost + ThreadPullEffect catalog
- ``seed_cantrip_starter_catalog()`` — Task 1.8 — 5 styles × 5 archetypes = 25 cantrips
- ``MagicContent`` — static factory helpers for integration-test technique wiring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from actions.models.consequence_pools import ConsequencePool
    from integration_tests.game_content.combat import PenetrationContestResult
    from world.classes.models import Path
    from world.conditions.models import CapabilityType, ConditionStage
    from world.magic.audere import AudereThreshold
    from world.magic.models import (
        Affinity,
        AnimaConfig,
        EffectType,
        IntensityTier,
        MagicalAlterationTemplate,
        MishapPoolTier,
        Resonance,
        Ritual,
        SoulfrayConfig,
        Technique,
        TechniqueCapabilityGrant,
        TechniqueStyle,
    )
    from world.magic.models.cantrips import Cantrip
    from world.magic.models.corruption_config import CorruptionConfig
    from world.magic.models.gain_config import ResonanceGainConfig
    from world.magic.models.threads import ThreadPullCost, ThreadPullEffect
    from world.magic.models.weaving import ThreadWeavingUnlock
    from world.mechanics.models import Property

# Maps action_key → technique name (narrative, not mechanical)
ACTION_TECHNIQUE_MAP: dict[str, str] = {
    "intimidate": "Soul Crush",
    "persuade": "Silver Tongue",
    "deceive": "Veil of Lies",
    "flirt": "Heartstring Pull",
    "perform": "Echoing Song",
    "entrance": "Commanding Presence",
}

_ELEMENTAL_TECHNIQUES: list[tuple[str, list[str], str]] = [
    ("Flame Lance", ["generation", "force", "projection"], "Fire"),
    ("Shadow Step", ["traversal", "perception"], "Shadow"),
    ("Stone Ward", ["barrier", "force"], "Earth"),
    ("Gale Burst", ["manipulation", "projection"], "Air"),
]

_SOCIAL_TECHNIQUE_CAPABILITIES: dict[str, list[str]] = {
    "Soul Crush": ["intimidation", "charm"],
    "Silver Tongue": ["persuasion", "deception"],
    "Veil of Lies": ["deception", "charm"],
    "Heartstring Pull": ["charm", "persuasion"],
    "Echoing Song": ["inspiration", "charm"],
    "Commanding Presence": ["intimidation", "inspiration"],
}

_EFFECT_PROPERTY_DEFINITIONS: list[tuple[str, str]] = [
    ("fire", "Effect carries fire energy"),
    ("shadow", "Effect carries shadow energy"),
    ("earth", "Effect carries earth energy"),
    ("air", "Effect carries air energy"),
]


@dataclass
class MagicContentResult:
    """Returned by MagicContent.create_all()."""

    techniques: dict[str, Technique]  # action_key → Technique
    enhancements: dict[str, ActionEnhancement]  # action_key → ActionEnhancement
    elemental_techniques: dict[str, Technique] = field(default_factory=dict)
    capability_grants: list[TechniqueCapabilityGrant] = field(default_factory=list)


@dataclass
class AlterationContentResult:
    """Returned by MagicContent.create_alteration_content()."""

    tier1_entry: MagicalAlterationTemplate  # AlterationTier.COSMETIC_TOUCH
    tier2_entry: MagicalAlterationTemplate  # AlterationTier.MARKED
    tier3_entry: MagicalAlterationTemplate  # AlterationTier.TOUCHED
    affinity: Affinity
    resonance: Resonance
    soulfray_consequence_pool: ConsequencePool  # pool with MAGICAL_SCARS entry
    soulfray_stage: ConditionStage  # stage whose consequence_pool fires MAGICAL_SCARS


class MagicContent:
    """Creates techniques and ActionEnhancement records for social action integration tests."""

    @staticmethod
    def create_all() -> MagicContentResult:
        """Create 6 techniques and 6 ActionEnhancement records (one per social action).

        Techniques use intensity=2, control=2, anima_cost=12.
        The social safety bonus adds +10 control for unengaged characters, giving
        control_delta=10 and effective_cost = max(12 - 10, 0) = 2 per use.

        Idempotent: uses get_or_create on technique name and on
        (base_action_key, technique) for enhancements, so calling this method
        twice produces exactly 6 techniques and 6 enhancements.

        Safe to call from setUpTestData across multiple test classes.

        Returns:
            MagicContentResult with techniques and enhancements dicts.
        """
        from actions.constants import EnhancementSourceType  # noqa: PLC0415
        from actions.models import ActionEnhancement  # noqa: PLC0415
        from world.magic.factories import GiftFactory  # noqa: PLC0415
        from world.magic.models import EffectType, Technique, TechniqueStyle  # noqa: PLC0415

        gift = GiftFactory(name="Social Arts")

        # Ensure a minimal style and effect_type exist for social techniques.
        # get_or_create so re-runs don't create duplicates.
        style, _ = TechniqueStyle.objects.get_or_create(
            name="Social",
            defaults={"description": "Magic expressed through social interaction."},
        )
        effect_type, _ = EffectType.objects.get_or_create(
            name="Social Influence",
            defaults={
                "description": "Magical enhancement of social action.",
                "base_power": None,
                "base_anima_cost": 2,
                "has_power_scaling": False,
            },
        )

        techniques: dict[str, Technique] = {}
        enhancements: dict[str, ActionEnhancement] = {}

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            technique, _ = Technique.objects.get_or_create(
                name=technique_name,
                defaults={
                    "gift": gift,
                    "style": style,
                    "effect_type": effect_type,
                    "intensity": 2,
                    "control": 2,
                    "anima_cost": 12,
                    "description": f"Social magic technique: {technique_name}.",
                },
            )
            techniques[action_key] = technique

            variant_name = f"Magical {action_key.title()}"
            enhancement, _ = ActionEnhancement.objects.get_or_create(
                base_action_key=action_key,
                technique=technique,
                defaults={
                    "variant_name": variant_name,
                    "is_involuntary": False,
                    "source_type": EnhancementSourceType.TECHNIQUE,
                    "distinction": None,
                    "condition": None,
                },
            )
            enhancements[action_key] = enhancement

        return MagicContentResult(techniques=techniques, enhancements=enhancements)

    @staticmethod
    def grant_techniques_to_character(
        character: ObjectDB,
        techniques: list[Technique],
    ) -> None:
        """Create CharacterTechnique records so the character knows each technique.

        Args:
            character: The ObjectDB character (must have a CharacterSheet already created).
            techniques: Techniques to grant. Duplicate grants are ignored (get_or_create).
        """
        from world.magic.factories import CharacterTechniqueFactory  # noqa: PLC0415

        sheet = character.sheet_data
        for technique in techniques:
            CharacterTechniqueFactory(character=sheet, technique=technique)

    @staticmethod
    def create_elemental_techniques(
        capability_types: dict[str, CapabilityType],
    ) -> tuple[dict[str, Technique], list[TechniqueCapabilityGrant]]:
        """Create 4 elemental techniques with capability grants and effect properties.

        Builds the full Resonance → Gift → Technique → TechniqueCapabilityGrant chain,
        plus a PropertyCategory "Effect" with 4 effect Properties wired via Resonance M2M.

        Args:
            capability_types: name → CapabilityType lookup (must contain all capabilities
                referenced in ``_ELEMENTAL_TECHNIQUES``).

        Returns:
            Tuple of (name → Technique dict, list of all TechniqueCapabilityGrants).
        """
        from world.magic.factories import (  # noqa: PLC0415
            AffinityFactory,
            GiftFactory,
            ResonanceFactory,
            TechniqueCapabilityGrantFactory,
            TechniqueFactory,
        )
        from world.mechanics.factories import (  # noqa: PLC0415
            PropertyCategoryFactory,
            PropertyFactory,
        )

        # Effect properties
        effect_category = PropertyCategoryFactory(name="Effect")
        effect_properties: dict[str, Property] = {}
        for prop_name, prop_desc in _EFFECT_PROPERTY_DEFINITIONS:
            effect_properties[prop_name] = PropertyFactory(
                name=prop_name,
                description=prop_desc,
                category=effect_category,
            )

        # Resonances (one per element, all sharing "Primal" affinity)
        affinity = AffinityFactory(name="Primal")
        resonances: dict[str, object] = {}
        element_names = ["Fire", "Shadow", "Earth", "Air"]
        element_prop_keys = ["fire", "shadow", "earth", "air"]
        for elem_name, prop_key in zip(element_names, element_prop_keys, strict=True):
            resonances[elem_name] = ResonanceFactory(
                name=elem_name,
                affinity=affinity,
                properties=[effect_properties[prop_key]],
            )

        # Gift wired to all resonances
        gift = GiftFactory(name="Elemental Arts")
        gift.resonances.set(resonances.values())

        # Techniques and capability grants
        techniques: dict[str, Technique] = {}
        grants: list[TechniqueCapabilityGrant] = []

        for tech_name, cap_names, _resonance_name in _ELEMENTAL_TECHNIQUES:
            technique = TechniqueFactory(
                name=tech_name,
                gift=gift,
                intensity=3,
                control=3,
                anima_cost=15,
            )
            techniques[tech_name] = technique

            for cap_name in cap_names:
                grant = TechniqueCapabilityGrantFactory(
                    technique=technique,
                    capability=capability_types[cap_name],
                    base_value=5,
                    intensity_multiplier=Decimal("1.0"),
                )
                grants.append(grant)

        return techniques, grants

    @staticmethod
    def wire_social_technique_capabilities(
        techniques: dict[str, Technique],
        capability_types: dict[str, CapabilityType],
    ) -> list[TechniqueCapabilityGrant]:
        """Add TechniqueCapabilityGrants to existing social techniques.

        Args:
            techniques: action_key → Technique dict (from ``create_all()``).
            capability_types: name → CapabilityType lookup.

        Returns:
            List of all created TechniqueCapabilityGrant instances.
        """
        from world.magic.factories import (  # noqa: PLC0415
            TechniqueCapabilityGrantFactory,
        )

        # Build reverse lookup: technique.name → Technique
        name_to_technique: dict[str, Technique] = {t.name: t for t in techniques.values()}

        grants: list[TechniqueCapabilityGrant] = []
        for tech_name, cap_names in _SOCIAL_TECHNIQUE_CAPABILITIES.items():
            technique = name_to_technique[tech_name]
            for cap_name in cap_names:
                grant = TechniqueCapabilityGrantFactory(
                    technique=technique,
                    capability=capability_types[cap_name],
                    base_value=5,
                    intensity_multiplier=Decimal("1.0"),
                )
                grants.append(grant)

        return grants

    @staticmethod
    def create_alteration_content() -> AlterationContentResult:
        """Create library entries at three tiers for alteration pipeline tests.

        Creates:
        - Three staff library MagicalAlterationTemplate entries at tiers
          COSMETIC_TOUCH (1), MARKED (2), and TOUCHED (3), each backed by a
          ConditionTemplate with permanent duration and a ConditionResistanceModifier
          effect row (the one effect type that resolve_pending_alteration authors).
        - A shared Affinity + Resonance so library query filtering by affinity
          works correctly across all three entries.
        - A Soulfray ConditionTemplate with one stage whose consequence_pool contains
          a Consequence with a MAGICAL_SCARS ConsequenceEffect, so end-to-end tests
          can drive the full use_technique → Soulfray → MAGICAL_SCARS → PendingAlteration
          pipeline without mocking.

        Safe to call from setUpTestData. Returns an AlterationContentResult
        dataclass with the three templates, shared affinity/resonance, and the
        soulfray consequence pool + stage for pipeline wiring.

        Returns:
            AlterationContentResult dataclass.
        """
        from actions.factories import (  # noqa: PLC0415
            ConsequencePoolEntryFactory,
            ConsequencePoolFactory,
        )
        from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
        from world.checks.factories import (  # noqa: PLC0415
            CheckTypeFactory,
            ConsequenceEffectFactory,
            ConsequenceFactory,
        )
        from world.conditions.constants import DurationType  # noqa: PLC0415
        from world.conditions.factories import (  # noqa: PLC0415
            ConditionCategoryFactory,
            ConditionCheckModifierFactory,
            ConditionResistanceModifierFactory,
            ConditionStageFactory,
            ConditionTemplateFactory,
        )
        from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415
        from world.magic.constants import AlterationTier  # noqa: PLC0415
        from world.magic.factories import (  # noqa: PLC0415
            AffinityFactory,
            MagicalAlterationTemplateFactory,
            ResonanceFactory,
        )

        alteration_cat = ConditionCategoryFactory(name="Magical Alteration")
        affinity = AffinityFactory(name="Primal (Alteration Test)")
        resonance = ResonanceFactory(name="Ember Touch (Alteration Test)", affinity=affinity)
        check_type = CheckTypeFactory(name="Resilience (Alteration Test)")

        # --- Library entries with full effect rows ---
        # Each entry gets a ConditionResistanceModifier (the one effect that
        # resolve_pending_alteration actually creates on scratch-path resolution).
        tier_data = [
            (AlterationTier.COSMETIC_TOUCH, "Faint Ember Traces"),
            (AlterationTier.MARKED, "Seared Markings"),
            (AlterationTier.TOUCHED, "Flame-Written Flesh"),
        ]
        templates = []
        for tier, cond_name in tier_data:
            from world.conditions.factories import DamageTypeFactory  # noqa: PLC0415

            damage_type = DamageTypeFactory(name=f"Fire (tier {tier} test)")
            condition_template = ConditionTemplateFactory(
                name=cond_name,
                category=alteration_cat,
                description=f"A permanent magical mark from overburn at tier {tier}.",
                default_duration_type=DurationType.PERMANENT,
            )
            # Resistance modifier: fire vulnerability — the effect row type that is
            # authored by resolve_pending_alteration on the scratch path.
            ConditionResistanceModifierFactory(
                condition=condition_template,
                stage=None,
                damage_type=damage_type,
                modifier_value=-5,  # small vulnerability for test purposes
            )
            # Check penalty (social/observer reactivity analogue — for completeness).
            ConditionCheckModifierFactory(
                condition=condition_template,
                stage=None,
                check_type=check_type,
                modifier_value=-5,
                scales_with_severity=False,
            )
            template = MagicalAlterationTemplateFactory(
                condition_template=condition_template,
                tier=tier,
                origin_affinity=affinity,
                origin_resonance=resonance,
                is_library_entry=True,
                is_visible_at_rest=(tier >= AlterationTier.MARKED_PROFOUNDLY),
            )
            templates.append(template)

        # --- Soulfray stage with MAGICAL_SCARS consequence pool ---
        # This wires the full pipeline:
        #   use_technique (low anima) → _handle_soulfray_accumulation
        #     → stage.consequence_pool fires
        #       → Consequence with MAGICAL_SCARS effect
        #         → _apply_magical_scars handler → create_pending_alteration
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
            default_duration_type=DurationType.PERMANENT,
        )

        pool = ConsequencePoolFactory(name="Soulfray Stage 1 Consequences (Alteration Test)")

        # Consequence whose effect fires MAGICAL_SCARS with severity=2 → tier MARKED
        magical_scars_consequence = ConsequenceFactory(label="Mage Scars (alteration test)")
        ConsequenceEffectFactory(
            consequence=magical_scars_consequence,
            effect_type=CheckEffectType.MAGICAL_SCARS,
            condition_severity=2,  # severity 2 → AlterationTier.MARKED
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=magical_scars_consequence)

        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name="Searing (alteration test)",
            consequence_pool=pool,
            severity_threshold=1,  # fires on first severity increment past zero (i.e. second use)
        )

        return AlterationContentResult(
            tier1_entry=templates[0],
            tier2_entry=templates[1],
            tier3_entry=templates[2],
            affinity=affinity,
            resonance=resonance,
            soulfray_consequence_pool=pool,
            soulfray_stage=soulfray_stage,
        )


# ---------------------------------------------------------------------------
# Task 1.11 — seed_canonical_affinities()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 13a — _seed_endure_hallowed_ground_check()
# ---------------------------------------------------------------------------


def _seed_endure_hallowed_ground_check() -> None:
    """Seed the endure_hallowed_ground CheckType + a placeholder ResultChart.

    Phase 2 task 2F replaces the placeholder tuning with real production
    values. For this slice, just enough rows exist so perform_check resolves
    `endure_hallowed_ground` deterministically (the pipeline test uses
    force_check_outcome to bypass the dice).

    CheckOutcome rows are not migration-seeded; this helper creates them via
    get_or_create so repeated calls are idempotent.
    """
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415
    from world.traits.models import CheckOutcome, ResultChart, ResultChartOutcome  # noqa: PLC0415

    # --- Ensure the "Magic" CheckCategory exists (shared with seed_magic_config) ---
    magic_category, _ = CheckCategory.objects.get_or_create(name="Magic")

    # --- CheckType ---
    CheckType.objects.get_or_create(
        name="endure_hallowed_ground",
        defaults={
            "category": magic_category,
            "description": (
                "Endurance check against the spiritual pressure of hallowed ground. "
                "Placeholder — tuning replaced in Phase 2 task 2F."
            ),
            "is_active": True,
        },
    )

    # --- Canonical CheckOutcome rows (not migration-seeded; idempotent) ---
    canonical_outcomes: dict[str, int] = {
        "Critical Success": 2,
        "Success": 1,
        "Failure": -1,
        "Critical Failure": -2,
    }
    outcome_instances: dict[str, CheckOutcome] = {}
    for name, success_level in canonical_outcomes.items():
        outcome, _ = CheckOutcome.objects.get_or_create(
            name=name,
            defaults={
                "success_level": success_level,
                "description": "",
                "display_template": "",
            },
        )
        outcome_instances[name] = outcome

    # --- ResultChart (rank_difference=0, baseline placeholder) ---
    chart, _ = ResultChart.objects.get_or_create(
        rank_difference=0,
        defaults={"name": "Even Match (placeholder)"},
    )

    # --- Four ResultChartOutcome rows ---
    # Natural key is (chart, min_roll). Ranges are placeholder; Phase 2 replaces.
    #   1–15  → Critical Failure
    #   16–50 → Failure
    #   51–85 → Success
    #   86–100 → Critical Success
    outcome_specs: list[tuple[int, int, str]] = [
        (1, 15, "Critical Failure"),
        (16, 50, "Failure"),
        (51, 85, "Success"),
        (86, 100, "Critical Success"),
    ]
    for min_roll, max_roll, outcome_name in outcome_specs:
        ResultChartOutcome.objects.get_or_create(
            chart=chart,
            min_roll=min_roll,
            defaults={
                "max_roll": max_roll,
                "outcome": outcome_instances[outcome_name],
            },
        )


# ---------------------------------------------------------------------------
# Task 13b — _seed_hallowed_reaction_conditions()
# ---------------------------------------------------------------------------

#: SINGLE SOURCE OF TRUTH for the 5 Hallowed-Threshold reaction conditions.
#: ``outcome_tier`` is the CheckOutcome tier this condition is applied on.
#: ``HALLOWED_REACTION_CONDITION_NAMES`` and ``CRIT_FAIL_CONDITION_NAMES`` are
#: DERIVED from this list (see below) so the names live in exactly one place.
#: ``_seed_hallowed_reaction_conditions()`` only reads name/description/
#: player_description/observer_description and ignores ``outcome_tier``.
_HALLOWED_REACTION_SPECS: list[dict[str, str]] = [
    {
        "name": "Tempered Against Light",
        "outcome_tier": "Critical Success",
        "description": (
            "The caster's flesh remembers an old burn; they walk hallowed ground unscathed."
        ),
        "player_description": (
            "You walked into the light and walked out unchanged. Some part of you is being remade."
        ),
        "observer_description": "Their skin barely flickers in the consecrated air.",
    },
    {
        "name": "Singed",
        "outcome_tier": "Success",
        "description": "A faint mark of celestial rejection.",
        "player_description": (
            "Light glances along your skin. A faint mark stings where the spell met sanctified air."
        ),
        "observer_description": "A pale brand glows briefly on their skin.",
    },
    {
        "name": "Burning",
        "outcome_tier": "Failure",
        "description": "Sanctified flame on Abyssal flesh.",
        "player_description": "Your skin burns where it meets the consecrated air.",
        "observer_description": "They smolder, marked by light they cannot bear.",
    },
    {
        "name": "Hallowed Burn",
        "outcome_tier": "Critical Failure",
        "description": "A grievous, self-rebuking mark from sanctified ground.",
        "player_description": (
            "The sanctified ground answers the spell with fire. "
            "You are flung from the working, burning."
        ),
        "observer_description": (
            "They are flung from their spell, burning where the light touched them."
        ),
    },
    {
        "name": "Cast Disrupted",
        "outcome_tier": "Critical Failure",
        "description": "The casting failed mid-working; threads in the caster's hands snap.",
        "player_description": (
            "The threads in your hands snap. Whatever you were weaving has come undone."
        ),
        "observer_description": "The spell goes wide and collapses around them.",
    },
]


def _seed_hallowed_reaction_conditions() -> None:
    """Seed the 5 reaction conditions for the Hallowed Threshold pipeline.

    These conditions are applied on different check outcomes when an
    Abyssal-aligned caster uses a technique in a Celestial-aura room:
      Critical Success -> Tempered Against Light
      Success          -> Singed
      Failure          -> Burning
      Critical Failure -> Hallowed Burn + Cast Disrupted

    Burning may already exist (factory-created in some tests); get_or_create
    reuses an existing row with the same name.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    # Ensure a "Magical" category exists. Reuse if already present.
    category, _ = ConditionCategory.objects.get_or_create(
        name="Magical",
        defaults={
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
    )

    for spec in _HALLOWED_REACTION_SPECS:
        ConditionTemplate.objects.get_or_create(
            name=spec["name"],
            defaults={
                "category": category,
                "description": spec["description"],
                "player_description": spec["player_description"],
                "observer_description": spec["observer_description"],
                "default_duration_type": DurationType.ROUNDS,
                "default_duration_value": 3,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": True,
            },
        )


# ---------------------------------------------------------------------------
# T12 — consequence pool constants and seed helper
# ---------------------------------------------------------------------------

#: The Critical Failure tier — the only tier with >1 spec (two APPLY_CONDITION
#: effects on one Consequence). All other tiers map 1:1 to a single condition.
_CRIT_FAIL_TIER: str = "Critical Failure"


def _derive_tier_condition_names() -> dict[str, str]:
    """CheckOutcome tier name → FIRST condition name at that tier.

    Derived from ``_HALLOWED_REACTION_SPECS`` (the single source of truth).
    Tier insertion order follows spec order; the first spec at each tier wins
    (so Critical Failure → the primary "Hallowed Burn"). The full list of
    crit-fail names lives in ``CRIT_FAIL_CONDITION_NAMES``.
    """
    names: dict[str, str] = {}
    for spec in _HALLOWED_REACTION_SPECS:
        names.setdefault(spec["outcome_tier"], spec["name"])
    return names


#: DERIVED: CheckOutcome tier name → ConditionTemplate name for the OPPOSED
#: backfire consequence pools. Single source of truth is
#: ``_HALLOWED_REACTION_SPECS`` — do not restate condition names anywhere else.
HALLOWED_REACTION_CONDITION_NAMES: dict[str, str] = _derive_tier_condition_names()

#: DERIVED: every condition applied by the Critical Failure tier, in spec order
#: (two APPLY_CONDITION effects on the same Consequence row).
CRIT_FAIL_CONDITION_NAMES: list[str] = [
    spec["name"] for spec in _HALLOWED_REACTION_SPECS if spec["outcome_tier"] == _CRIT_FAIL_TIER
]

#: Pool names for pair #4 (Abyssal→Celestial) and pair #7 (Primal→Celestial).
_ABYSSAL_CELESTIAL_POOL_NAME: str = "OPPOSED Backfire: Abyssal caster in Celestial place"
_PRIMAL_CELESTIAL_POOL_NAME: str = "OPPOSED Backfire: Primal caster in Celestial place"


def _seed_resonance_environment_consequence_pools() -> None:
    """Seed OPPOSED consequence pools for pair #4 (Abyssal→Celestial) and #7 (Primal→Celestial).

    Creates two ConsequencePool rows (one per pairing), each with four
    ConsequencePoolEntry → Consequence rows keyed by CheckOutcome tier,
    with ConsequenceEffect(effect_type=APPLY_CONDITION) wiring:

        Critical Success  → Tempered Against Light (1 effect)
        Success           → Singed                 (1 effect)
        Failure           → Burning                (1 effect)
        Critical Failure  → Hallowed Burn          (2 effects)
                            + Cast Disrupted

    Then sets AffinityInteraction.consequence_pool on both rows and saves.

    Depends on:
    - seed_canonical_affinities()      (Celestial/Primal/Abyssal must exist)
    - _seed_affinity_interactions()    (9 AffinityInteraction rows)
    - _seed_hallowed_reaction_conditions() (all 5 ConditionTemplate rows)
    - _seed_endure_hallowed_ground_check() (CheckOutcome rows)

    Idempotent: get_or_create keyed on stable names at every layer.  Duplicate
    ConsequencePoolEntry rows are prevented by the (pool, consequence) unique
    constraint; duplicate ConsequenceEffect rows are guarded explicitly.
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
    from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import AffinityInteraction  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    # --- Fetch CheckOutcome tiers (created by _seed_endure_hallowed_ground_check) ---
    outcome_map: dict[str, CheckOutcome] = {}
    for name in ("Critical Success", "Success", "Failure", "Critical Failure"):
        outcome_map[name] = CheckOutcome.objects.get(name=name)

    # --- Fetch injury ConditionTemplates (created by _seed_hallowed_reaction_conditions) ---
    # Names come from the single source of truth (_HALLOWED_REACTION_SPECS) and are
    # unique per spec, so no de-dup guard is needed when building this map.
    cond_map: dict[str, ConditionTemplate] = {
        spec["name"]: ConditionTemplate.objects.get(name=spec["name"])
        for spec in _HALLOWED_REACTION_SPECS
    }

    def _build_pool(pool_name: str, description: str) -> ConsequencePool:
        """Create (or fetch) a pool and wire its 4 Consequence + ConsequenceEffect rows."""
        pool, _ = ConsequencePool.objects.get_or_create(
            name=pool_name,
            defaults={"description": description},
        )

        # --- Single-effect outcomes: every tier except Critical Failure ---
        # Derived inline from the single source of truth (no separate map constant).
        for outcome_name, condition_name in HALLOWED_REACTION_CONDITION_NAMES.items():
            if outcome_name == _CRIT_FAIL_TIER:
                continue
            outcome = outcome_map[outcome_name]
            condition = cond_map[condition_name]
            # SOFT NATURAL KEY: there is no DB constraint on (outcome_tier, label).
            # Idempotency relies on ConsequencePool.name being unique=True and the
            # label embedding that unique pool name, so (outcome_tier, label) is
            # effectively pool-scoped-unique. A label-format change across runs
            # would create duplicates (acceptable for seed; do NOT change the model).
            consequence, _ = Consequence.objects.get_or_create(
                outcome_tier=outcome,
                label=f"{pool_name}: {outcome_name}",
                defaults={
                    "mechanical_description": f"Apply {condition_name}.",
                    "weight": 1,
                    "character_loss": False,
                },
            )
            ConsequencePoolEntry.objects.get_or_create(
                pool=pool,
                consequence=consequence,
            )
            # SOFT NATURAL KEY: the (consequence, effect_type, condition_template)
            # triple is functionally unique for this seed but is NOT DB-enforced
            # (pre-existing model-wide gap affecting all ConsequenceEffect callers;
            # out of scope for this seed task — tracked as a separate follow-up).
            ConsequenceEffect.objects.get_or_create(
                consequence=consequence,
                effect_type=CheckEffectType.APPLY_CONDITION,
                condition_template=condition,
                defaults={"execution_order": 0},
            )

        # --- Critical Failure: two APPLY_CONDITION effects on one Consequence ---
        crit_fail_outcome = outcome_map["Critical Failure"]
        crit_fail_label = f"{pool_name}: Critical Failure"
        # SOFT NATURAL KEY (same rationale as above): (outcome_tier, label) is not
        # DB-unique; idempotency relies on the unique pool name embedded in label.
        crit_fail_consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=crit_fail_outcome,
            label=crit_fail_label,
            defaults={
                "mechanical_description": "Apply Hallowed Burn and Cast Disrupted.",
                "weight": 1,
                "character_loss": False,
            },
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=crit_fail_consequence,
        )
        for order, cond_name in enumerate(CRIT_FAIL_CONDITION_NAMES):
            # SOFT NATURAL KEY: (consequence, effect_type, condition_template) is
            # functionally unique here but NOT DB-enforced (pre-existing model-wide
            # gap; out of scope for this seed task — tracked separately).
            ConsequenceEffect.objects.get_or_create(
                consequence=crit_fail_consequence,
                effect_type=CheckEffectType.APPLY_CONDITION,
                condition_template=cond_map[cond_name],
                defaults={"execution_order": order},
            )

        return pool

    # --- Build both pools ---
    abyssal_celestial_pool = _build_pool(
        _ABYSSAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for an Abyssal caster working magic in a Celestial place.",
    )
    primal_celestial_pool = _build_pool(
        _PRIMAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for a Primal caster working magic in a Celestial place.",
    )

    # --- Wire AffinityInteraction.consequence_pool for pair #4 and #7 ---
    abyssal = Affinity.objects.get(name="Abyssal")
    primal = Affinity.objects.get(name="Primal")
    celestial = Affinity.objects.get(name="Celestial")

    pair4 = AffinityInteraction.objects.get(
        source_affinity=abyssal,
        environment_affinity=celestial,
    )
    if pair4.consequence_pool_id != abyssal_celestial_pool.pk:
        pair4.consequence_pool = abyssal_celestial_pool
        pair4.save(update_fields=["consequence_pool"])

    pair7 = AffinityInteraction.objects.get(
        source_affinity=primal,
        environment_affinity=celestial,
    )
    if pair7.consequence_pool_id != primal_celestial_pool.pk:
        pair7.consequence_pool = primal_celestial_pool
        pair7.save(update_fields=["consequence_pool"])


# ---------------------------------------------------------------------------
# T13 — _seed_resonance_alignment_boons()
# ---------------------------------------------------------------------------

#: Authored buff ConditionTemplate specs for the Abyssal/Abyssal ALIGNED boon family.
#: Two bands: LOW (min_magnitude=1) → minor empowerment; HIGH (min_magnitude=40) → deep attuned.
#: Descriptions narrate WHY an abyssal place empowers an abyssal caster.
_ABYSSAL_BOON_SPECS: list[dict[str, str]] = [
    {
        "name": "Abyssal Resonance — Minor Attunement",
        "band": "low",
        "description": (
            "The dissolution that permeates this place recognises the caster's touch. "
            "The boundary between intent and effect thins slightly, smoothing the passage "
            "of abyssal workings."
        ),
        "player_description": (
            "Something in the air here knows you. Your spells feel lighter, the threads "
            "a little more willing than usual."
        ),
        "observer_description": (
            "A subtle ease settles over their gestures — as though the place itself is "
            "helping them."
        ),
    },
    {
        "name": "Abyssal Resonance — Deep Attunement",
        "band": "high",
        "description": (
            "The concentrated dissolution saturating this place and the caster's own "
            "abyssal nature are in alignment so deep that the distinction between them "
            "blurs. The caster's workings are carried on the current of the place's power."
        ),
        "player_description": (
            "The place pours into you. Every thread you reach for is already half-woven "
            "by the dissolution around you. You are not working against the world here — "
            "you are the world working."
        ),
        "observer_description": (
            "The dissolution in the air seems to gather toward them, pulled by the same "
            "source that moves in their hands."
        ),
    },
]

#: min_magnitude thresholds for the low and high Abyssal boon bands.
#: LOW=1: any non-zero magnitude qualifies for the lesser buff.
#: HIGH=40: above the low band; the seeded Abyssal Sanctum room (magnitude=60) qualifies.
_ABYSSAL_BOON_LOW_MIN_MAGNITUDE: int = 1
_ABYSSAL_BOON_HIGH_MIN_MAGNITUDE: int = 40

#: Name for the positive ConditionCategory that owns buff/boon templates.
#: Must NOT match the negative "Magical" category used by injury/reaction conditions.
_MAGICAL_BOON_CATEGORY_NAME: str = "Magical Boon"


def _seed_resonance_alignment_boons() -> None:
    """Seed ALIGNED boon tiers for pair #5 (Abyssal source → Abyssal environment).

    Creates:
    - A "Magical Boon" ConditionCategory with is_negative=False (or reuses if already present).
      This is DISTINCT from the negative "Magical" category used by injury/reaction conditions.
      is_negative is load-bearing: services filter positive vs negative conditions by this flag.
    - Two named buff ConditionTemplate rows (low and high band) with authored
      descriptions narrating why an abyssal place empowers an abyssal caster.
    - Two ResonanceAlignmentBoonTier rows for pair #5 with ascending min_magnitude:
        LOW  band (min_magnitude=1)  → minor attunement template
        HIGH band (min_magnitude=40) → deep attunement template

    IMPORTANT: full_clean() is called before every tier.save() to exercise the
    ALIGNED-valence validation in ResonanceAlignmentBoonTier.clean(). A bare
    objects.create() bypasses clean(), so this explicit call is mandatory.

    Depends on:
    - seed_canonical_affinities()   (Abyssal must exist)
    - _seed_affinity_interactions() (pair #5 AffinityInteraction must exist)

    Idempotent: get_or_create keyed on stable natural keys (template by name;
    tier by (affinity_interaction, min_magnitude) unique constraint).
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import (  # noqa: PLC0415
        AffinityInteraction,
        ResonanceAlignmentBoonTier,
    )

    # --- Positive "Magical Boon" ConditionCategory for buff templates ---
    # MUST be separate from the negative "Magical" category (used by injury conditions).
    # is_negative=False is load-bearing: services/views count and filter positive vs negative
    # conditions by this flag (see conditions/services.py only_negative filter and
    # conditions/views.py positive/negative counting).
    category, _ = ConditionCategory.objects.get_or_create(
        name=_MAGICAL_BOON_CATEGORY_NAME,
        defaults={
            "description": (
                "Positive magical conditions from resonance alignment and aura attunement."
            ),
            "is_negative": False,
            "display_order": 10,
        },
    )

    # --- Seed the two boon ConditionTemplates ---
    # DurationType.PERMANENT + default_duration_value=0: persists until cleared by the
    # movement service on the next move (no inherent expiry timer).
    template_map: dict[str, ConditionTemplate] = {}
    for spec in _ABYSSAL_BOON_SPECS:
        template, _ = ConditionTemplate.objects.get_or_create(
            name=spec["name"],
            defaults={
                "category": category,
                "description": spec["description"],
                "player_description": spec["player_description"],
                "observer_description": spec["observer_description"],
                "default_duration_type": DurationType.PERMANENT,
                "default_duration_value": 0,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": False,
            },
        )
        template_map[spec["band"]] = template

    # --- Fetch pair #5: Abyssal → Abyssal (ALIGNED) ---
    abyssal = Affinity.objects.get(name="Abyssal")
    pair5 = AffinityInteraction.objects.get(
        source_affinity=abyssal,
        environment_affinity=abyssal,
    )

    # --- Seed two boon tiers with full_clean() guard before every save() ---
    # full_clean() is MANDATORY here: ResonanceAlignmentBoonTier.clean() validates
    # ALIGNED valence but there is no save() override — objects.create() bypasses it.
    # Calling full_clean() before save() ensures a non-ALIGNED interaction can never
    # be silently attached, even if this helper is mis-called with wrong data.
    tier_specs: list[tuple[int, str]] = [
        (_ABYSSAL_BOON_LOW_MIN_MAGNITUDE, "low"),
        (_ABYSSAL_BOON_HIGH_MIN_MAGNITUDE, "high"),
    ]
    for min_magnitude, band in tier_specs:
        condition_template = template_map[band]
        # get_or_create keyed on the unique (affinity_interaction, min_magnitude) pair.
        # On the CREATE path: build the instance, full_clean(), then save().
        # On the GET path: no save needed; full_clean is already guaranteed on prior run.
        try:
            ResonanceAlignmentBoonTier.objects.get(
                affinity_interaction=pair5,
                min_magnitude=min_magnitude,
            )
        except ResonanceAlignmentBoonTier.DoesNotExist:
            tier = ResonanceAlignmentBoonTier(
                affinity_interaction=pair5,
                min_magnitude=min_magnitude,
                condition_template=condition_template,
            )
            tier.full_clean()  # CRITICAL: validates ALIGNED valence (clean() not called by save())
            tier.save()


# ---------------------------------------------------------------------------
# Task 13c — _seed_hallowed_achievement_bridge()
# ---------------------------------------------------------------------------

_HALLOWED_ACHIEVEMENT_BRIDGE_SPECS: list[dict[str, object]] = [
    {
        "condition_name": "Tempered Against Light",
        "stat_key": "conditions.tempered_against_light.gained",
        "stat_name": "Tempered Against Light Gained",
        "achievement_name": "Hallowed-Hardened",
        "achievement_description": (
            "Walked into hallowed ground unscathed. The wound your blood "
            "remembers has hardened to a callus."
        ),
        "notification_level": "gamewide",
    },
    {
        "condition_name": "Singed",
        "stat_key": "conditions.singed.gained",
        "stat_name": "Singed Gained",
        "achievement_name": "Touched by Light",
        "achievement_description": "Light glanced your skin. You carry a faint mark.",
        "notification_level": "personal",
    },
    {
        "condition_name": "Hallowed Burn",
        "stat_key": "conditions.hallowed_burn.gained",
        "stat_name": "Hallowed Burn Gained",
        "achievement_name": "Cast Out by the Light",
        "achievement_description": (
            "Broken against the threshold. Sanctified ground answered the spell with fire."
        ),
        "notification_level": "gamewide",
    },
]


def _seed_hallowed_achievement_bridge() -> None:
    """Seed the achievement bridge for the Hallowed Threshold pipeline.

    For Tempered Against Light / Singed / Hallowed Burn (3 of the 4 reaction
    outcomes — Burning is common-failure, not noteworthy enough for an
    achievement), creates:

        StatDefinition → ConditionStatRule → Achievement → AchievementRequirement

    Discoveries fire automatically via the existing achievements engine when
    the first character earns each Achievement.

    Depends on _seed_hallowed_reaction_conditions() having run first to
    create the ConditionTemplate rows we reference.
    """
    from django.utils.text import slugify  # noqa: PLC0415

    from world.achievements.constants import (  # noqa: PLC0415
        ComparisonType,
        ConditionEventType,
    )
    from world.achievements.models import (  # noqa: PLC0415
        Achievement,
        AchievementRequirement,
        ConditionStatRule,
        StatDefinition,
    )
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    for spec in _HALLOWED_ACHIEVEMENT_BRIDGE_SPECS:
        condition = ConditionTemplate.objects.get(name=spec["condition_name"])
        stat, _ = StatDefinition.objects.get_or_create(
            key=spec["stat_key"],
            defaults={
                "name": spec["stat_name"],
                "description": (
                    f"Count of times this character has gained {spec['condition_name']}."
                ),
            },
        )
        ConditionStatRule.objects.get_or_create(
            stat=stat,
            condition=condition,
            event_type=ConditionEventType.GAINED,
            defaults={"increment_amount": 1},
        )
        notification_level = spec["notification_level"]
        achievement, _ = Achievement.objects.get_or_create(
            name=spec["achievement_name"],
            defaults={
                "slug": slugify(spec["achievement_name"]),
                "description": spec["achievement_description"],
                "hidden": True,
                "notification_level": notification_level,
                "is_active": True,
            },
        )
        # Key on (achievement, stat, threshold, comparison) to stay idempotent
        # without requiring a DB-level unique constraint on AchievementRequirement.
        AchievementRequirement.objects.get_or_create(
            achievement=achievement,
            stat=stat,
            threshold=1,
            comparison=ComparisonType.GTE,
        )


# ---------------------------------------------------------------------------
# Task RC4 — _seed_resonance_environment_rooms()
# ---------------------------------------------------------------------------

#: Cascade magnitude for the Low celestial room.
_CELESTIAL_LOW_MAGNITUDE: int = 10

#: Cascade magnitude for the High celestial room.
_CELESTIAL_HIGH_MAGNITUDE: int = 80

#: Cascade magnitude for the Abyssal aligned-pole room.
_ABYSSAL_ALIGNED_MAGNITUDE: int = 60


def _seed_resonance_environment_rooms() -> None:
    """Seed three cascade-resonance rooms for the resonance-environment pipeline.

    Replaces the deleted RoomAuraProfile/RoomResonance approach. Room resonance
    magnitudes now live as LocationValueModifier rows (key_type=RESONANCE),
    created via tag_room_resonance and then magnitude-tuned to the desired level.

    The "Hallowed Rejection" marker ConditionTemplate is also seeded here as
    flavor content for the story.

    Three rooms:
      - "The Hallowed Threshold (Low)"   — Celestial / Light, magnitude=10
      - "The Hallowed Threshold (High)"  — Celestial / Light, magnitude=80
      - "The Resonant Sanctum (Aligned)" — Abyssal / Dissolution, magnitude=60

    Idempotent at every layer:
      - rooms: filter().first() + create_object(nohome=True) when absent
      - RoomProfile: get_or_create
      - LocationValueModifier: tag_room_resonance uses update_or_create keyed on
        (room_profile, resonance, source) then we set .value + .save() to tune
        magnitude — re-runs restore the desired value.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Resonance  # noqa: PLC0415
    from world.magic.services.gain import tag_room_resonance  # noqa: PLC0415

    # ----- Hallowed Rejection marker (flavor condition for the story) -----
    category, _ = ConditionCategory.objects.get_or_create(
        name="Magical",
        defaults={
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name="Hallowed Rejection",
        defaults={
            "category": category,
            "description": (
                "An Abyssal-aligned soul remembers a wound made by sanctified light. "
                "Whenever the bearer casts in a celestial-aura room, the rejection "
                "answers with fire."
            ),
            "player_description": "You bear a scar that hates hallowed ground.",
            "observer_description": "They flinch from sanctified air.",
            "default_duration_type": DurationType.PERMANENT,
            "default_duration_value": 0,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": False,
        },
    )

    # ----- Rooms with cascade resonance -----
    light = Resonance.objects.get(name="Light")
    dissolution = Resonance.objects.get(name="Dissolution")

    room_specs: list[tuple[str, Resonance, int]] = [
        ("The Hallowed Threshold (Low)", light, _CELESTIAL_LOW_MAGNITUDE),
        ("The Hallowed Threshold (High)", light, _CELESTIAL_HIGH_MAGNITUDE),
        ("The Resonant Sanctum (Aligned)", dissolution, _ABYSSAL_ALIGNED_MAGNITUDE),
    ]

    for db_key, resonance, magnitude in room_specs:
        # ObjectDB.db_key is not unique in Evennia — use filter().first() for idempotency.
        existing = ObjectDB.objects.filter(
            db_key=db_key,
            db_typeclass_path="typeclasses.rooms.Room",
        ).first()
        if existing is not None:
            room = existing
        else:
            # Evennia's create_object fires at_object_creation, which auto-creates
            # the RoomProfile OneToOne extension for typeclasses.rooms.Room.
            room = evennia_create.create_object(
                typeclass="typeclasses.rooms.Room",
                key=db_key,
                nohome=True,
            )
        # RoomProfile is auto-created by Room.at_object_creation().
        profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        # Tag the room with the resonance (update_or_create, idempotent).
        # Returns the LocationValueModifier row; tune value to the desired magnitude.
        modifier = tag_room_resonance(profile, resonance)
        if modifier.value != magnitude:
            modifier.value = magnitude
            modifier.save(update_fields=["value"])


# ---------------------------------------------------------------------------
# Task 13f — _seed_hallowed_threshold_story()
# ---------------------------------------------------------------------------


def _seed_hallowed_threshold_story() -> None:
    """Seed the Hallowed Threshold Story DAG.

    Structure:
      Story "The Hallowed Threshold" (CHARACTER scope, no character_sheet — template)
        Chapter "First Trial" (order=1)
          Episode "Stepping Into Light" (order=1, source)
            Beat-Tempered: CONDITION_HELD Tempered Against Light
            Beat-Singed: CONDITION_HELD Singed
            Beat-Burning: CONDITION_HELD Burning
            Beat-Hallowed-Burn: CONDITION_HELD Hallowed Burn
          Episode "Tempered Walk" (order=2, destination)
          Episode "Marked Path" (order=3, destination, shared SUCCESS+FAILURE)
          Episode "Cast Out" (order=4, destination)

      Transitions out of Stepping Into Light (in order):
        1 → Tempered Walk (TRO: Beat-Tempered SUCCESS)
        2 → Cast Out (TRO: Beat-Hallowed-Burn SUCCESS)
        3 → Marked Path (TRO: Beat-Singed SUCCESS)
        4 → Marked Path (TRO: Beat-Burning SUCCESS)

    ZERO EpisodeProgressionRequirement rows — gate is open; routing depends
    purely on which beat the reactive flow satisfies.

    Idempotent via get_or_create throughout. Re-running on a populated DB is a
    no-op; staff edits to existing rows are preserved.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.stories.constants import (  # noqa: PLC0415
        BeatOutcome,
        BeatPredicateType,
        StoryScope,
    )
    from world.stories.models import (  # noqa: PLC0415
        Beat,
        Chapter,
        Episode,
        Story,
        Transition,
        TransitionRequiredOutcome,
    )
    from world.stories.types import StoryPrivacy, StoryStatus  # noqa: PLC0415

    # --- Story (CHARACTER scope, no character_sheet — used as a template;
    #     the pipeline test wires character_sheet at runtime per playthrough) ---
    story, _ = Story.objects.get_or_create(
        title="The Hallowed Threshold",
        defaults={
            "description": (
                "A threshold of sanctified light. Abyssal-aligned casters who attempt "
                "to work magic here will find the ground remembers them."
            ),
            "scope": StoryScope.CHARACTER,
            "character_sheet": None,
            "status": StoryStatus.INACTIVE,
            "privacy": StoryPrivacy.PUBLIC,
        },
    )

    # --- Chapter ---
    chapter, _ = Chapter.objects.get_or_create(
        story=story,
        order=1,
        defaults={"title": "First Trial"},
    )

    # --- Episodes ---
    episodes_by_title: dict[str, Episode] = {}
    for ep_title, ep_order in [
        ("Stepping Into Light", 1),
        ("Tempered Walk", 2),
        ("Marked Path", 3),
        ("Cast Out", 4),
    ]:
        ep, _ = Episode.objects.get_or_create(
            chapter=chapter,
            order=ep_order,
            defaults={"title": ep_title},
        )
        episodes_by_title[ep_title] = ep

    source = episodes_by_title["Stepping Into Light"]

    # --- Beats on source episode ---
    beat_specs: list[tuple[str, str]] = [
        (
            "Tempered Against Light",
            "The light bends around you instead of burning. The wound your blood "
            "remembers has hardened to a callus.",
        ),
        (
            "Singed",
            "Light glances along your skin. A faint mark stings where the spell "
            "met sanctified air.",
        ),
        (
            "Burning",
            "The ground rejects you. Your skin burns where it meets the "
            "consecrated air, and the spell goes wide.",
        ),
        (
            "Hallowed Burn",
            "The sanctified ground answers the spell with fire. You are flung "
            "from the working, burning, and the threads in your hands snap.",
        ),
    ]
    beats_by_condition_name: dict[str, Beat] = {}
    for cond_name, player_resolution_text in beat_specs:
        condition = ConditionTemplate.objects.get(name=cond_name)
        beat, _ = Beat.objects.get_or_create(
            episode=source,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=condition,
            defaults={
                "internal_description": (
                    f"Beat satisfied when character gains the '{cond_name}' condition "
                    "as a result of the hallowed-ground endurance check."
                ),
                "player_resolution_text": player_resolution_text,
            },
        )
        beats_by_condition_name[cond_name] = beat

    # --- Transitions out of source episode ---
    marked_summary = (
        "The light marked you. You carry the burn now — and a question about what you are."
    )
    transition_specs: list[tuple[int, str, str, str]] = [
        (
            1,
            "Tempered Walk",
            "Tempered Against Light",
            "You walked into hallowed ground and walked out unchanged. "
            "Some part of you is being remade.",
        ),
        (
            2,
            "Cast Out",
            "Hallowed Burn",
            "You broke against the threshold. Whatever was watching turned away. "
            "You will not try this again the same way.",
        ),
        (3, "Marked Path", "Singed", marked_summary),
        (4, "Marked Path", "Burning", marked_summary),
    ]
    for order, target_title, beat_cond_name, connection_summary in transition_specs:
        target = episodes_by_title[target_title]
        transition, _ = Transition.objects.get_or_create(
            source_episode=source,
            target_episode=target,
            order=order,
            defaults={"connection_summary": connection_summary},
        )
        beat = beats_by_condition_name[beat_cond_name]
        TransitionRequiredOutcome.objects.get_or_create(
            transition=transition,
            beat=beat,
            defaults={"required_outcome": BeatOutcome.SUCCESS},
        )


def seed_canonical_affinities() -> None:
    """Seed the 3 canonical magic Affinities (Celestial / Primal / Abyssal).

    Idempotent. Re-running on a populated DB is a no-op for these rows.
    Other magic content (resonances, room aura, etc.) can depend on these
    existing — call this before any seed that references Affinity FKs.
    """
    from world.magic.models.affinity import Affinity  # noqa: PLC0415

    for name in ("Celestial", "Primal", "Abyssal"):
        Affinity.objects.get_or_create(name=name)


def seed_canonical_resonances() -> None:
    """Seed canonical Resonances for the magic-story slice.

    Celestial: Light / Sanctity / Radiance
    Abyssal: Dissolution

    Depends on seed_canonical_affinities(). Idempotent via get_or_create.
    The Celestial resonances are used by Hallowed Threshold room cascade rows.
    Dissolution (Abyssal) is used by the Resonant Sanctum room for the
    ALIGNED-pole amplification subtest (an Abyssal caster casting in an Abyssal
    resonance room gets the boon).
    """
    from world.magic.models.affinity import Affinity, Resonance  # noqa: PLC0415

    celestial = Affinity.objects.get(name="Celestial")
    for name in ("Light", "Sanctity", "Radiance"):
        Resonance.objects.get_or_create(
            name=name,
            defaults={"affinity": celestial},
        )

    abyssal = Affinity.objects.get(name="Abyssal")
    Resonance.objects.get_or_create(
        name="Dissolution",
        defaults={"affinity": abyssal},
    )


# Task RC1 — directed RPS affinity interaction matrix
# (source_name, env_name, valence, kind, aggressor, severity_multiplier, caster_dominance_defiles)
# caster_dominance_defiles=True ONLY for the Abyssal-caster OPPOSED pairs (#4 Abyssal->Celestial,
# #6 Abyssal->Primal): a strong-enough Abyssal caster overpowers and defiles those places.
_AFFINITY_INTERACTION_ROWS: list[tuple[str, str, str, str, str, str, bool]] = [
    ("Celestial", "Celestial", "aligned", "amplify", "environment", "1.00", False),
    ("Celestial", "Abyssal", "opposed", "reject", "environment", "1.00", False),
    ("Celestial", "Primal", "opposed", "repel", "environment", "0.30", False),
    ("Abyssal", "Celestial", "opposed", "reject", "environment", "1.00", True),
    ("Abyssal", "Abyssal", "aligned", "amplify", "environment", "1.00", False),
    ("Abyssal", "Primal", "opposed", "corrupt", "caster", "1.00", True),
    ("Primal", "Celestial", "opposed", "reject", "environment", "1.00", False),
    ("Primal", "Abyssal", "opposed", "corrupt", "environment", "1.00", False),
    ("Primal", "Primal", "aligned", "amplify", "environment", "1.00", False),
]


def _seed_affinity_interactions() -> None:
    """Seed the 9 directed AffinityInteraction rows (caster affinity → place affinity).

    Depends on seed_canonical_affinities() (Celestial / Primal / Abyssal must exist).
    Idempotent: get_or_create keyed on (source_affinity, environment_affinity).
    Staff edits to valence/kind/aggressor/severity_multiplier are preserved.

    ``caster_dominance_defiles`` is authored lore (not a staff tuning knob), so it is
    enforced even on pre-existing rows via an explicit set-after-get — this avoids the
    get_or_create "defaults dropped when the row already exists" gotcha, while leaving
    the genuinely-tunable fields untouched.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import AffinityInteraction  # noqa: PLC0415

    canonical_names = ("Celestial", "Primal", "Abyssal")
    affinity_cache: dict[str, Affinity] = {
        obj.name: obj for obj in Affinity.objects.filter(name__in=canonical_names)
    }
    for row in _AFFINITY_INTERACTION_ROWS:
        src_name, env_name, valence, kind, aggressor, mult_str, defiles = row
        obj, created = AffinityInteraction.objects.get_or_create(
            source_affinity=affinity_cache[src_name],
            environment_affinity=affinity_cache[env_name],
            defaults={
                "valence": valence,
                "kind": kind,
                "aggressor": aggressor,
                "severity_multiplier": Decimal(mult_str),
                "caster_dominance_defiles": defiles,
            },
        )
        if not created and obj.caster_dominance_defiles != defiles:
            obj.caster_dominance_defiles = defiles
            obj.save(update_fields=["caster_dominance_defiles"])


def _seed_resonance_environment_config() -> None:
    """Seed (lazy-create) the ResonanceEnvironmentConfig singleton (pk=1).

    Delegates to get_resonance_environment_config() which is idempotent by
    construction — it uses get_or_create(pk=1) internally.
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )

    get_resonance_environment_config()


# ---------------------------------------------------------------------------
# Task 1.1 — seed_magic_config()
# ---------------------------------------------------------------------------

#: Canonical IntensityTier definitions: (name, threshold, control_modifier)
_INTENSITY_TIERS: list[tuple[str, int, int]] = [
    ("Minor", 5, 0),
    ("Moderate", 10, -2),
    ("Major", 15, -5),
]

#: Name for the default mishap consequence pool
_MISHAP_POOL_NAME: str = "Magic Mishap Pool (default)"


@dataclass
class MagicConfigResult:
    """Returned by seed_magic_config().

    All singletons are lazy-created via get_or_create.  Re-running preserves
    any edits to existing rows (idempotent).
    """

    anima_config: AnimaConfig
    soulfray_config: SoulfrayConfig
    resonance_gain_config: ResonanceGainConfig
    corruption_config: CorruptionConfig
    audere_threshold: AudereThreshold
    intensity_tiers: dict[str, IntensityTier]  # name → tier
    mishap_pool_tier: MishapPoolTier


def seed_magic_config() -> MagicConfigResult:
    """Lazy-create the 5 magic config singletons plus IntensityTier and MishapPoolTier rows.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    Existing rows are never modified; staff edits survive repeated calls.

    Creates:
    - AnimaConfig (pk=1)
    - SoulfrayConfig (pk=1, resilience_check_type="Magical Endurance")
    - ResonanceGainConfig (pk=1)
    - CorruptionConfig (pk=1)
    - IntensityTier rows: Minor (threshold=5), Moderate (threshold=10), Major (threshold=15)
    - AudereThreshold (minimum_intensity_tier=Major, minimum_warp_stage=Soulfray "Ripping")
    - MishapPoolTier (min_deficit=1, max_deficit=None) backed by a minimal ConsequencePool

    Returns:
        MagicConfigResult dataclass with all created/fetched instances.
    """
    from actions.models.consequence_pools import ConsequencePool  # noqa: PLC0415
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415
    from world.magic.audere import AudereThreshold  # noqa: PLC0415
    from world.magic.factories import SoulfrayContentFactory  # noqa: PLC0415
    from world.magic.models import (  # noqa: PLC0415
        AnimaConfig,
        IntensityTier,
        MishapPoolTier,
        SoulfrayConfig,
    )
    from world.magic.models.corruption_config import CorruptionConfig  # noqa: PLC0415
    from world.magic.models.gain_config import ResonanceGainConfig  # noqa: PLC0415

    # --- AnimaConfig (has its own get_or_create helper) ---
    anima_config = AnimaConfig.get_singleton()

    # --- SoulfrayConfig (singleton, no get_or_create on factory) ---
    # Use direct ORM rather than CheckTypeFactory: the factory's SubFactory
    # generates a fresh CheckCategory on every call, making (name, category)
    # novel and leaking an orphan CheckType row on each re-run.
    magic_check_category, _ = CheckCategory.objects.get_or_create(name="Magic")
    resilience_check_type, _ = CheckType.objects.get_or_create(
        name="Magical Endurance",
        defaults={"category": magic_check_category},
    )
    soulfray_config, _ = SoulfrayConfig.objects.get_or_create(
        pk=1,
        defaults={
            "soulfray_threshold_ratio": Decimal("0.30"),
            "severity_scale": 10,
            "deficit_scale": 5,
            "resilience_check_type": resilience_check_type,
            "base_check_difficulty": 15,
            "ritual_budget_critical_success": 10,
            "ritual_budget_success": 6,
            "ritual_budget_partial": 3,
            "ritual_budget_failure": 1,
            "ritual_severity_cost_per_point": 1,
        },
    )

    # --- ResonanceGainConfig (pk=1) ---
    resonance_gain_config, _ = ResonanceGainConfig.objects.get_or_create(pk=1, defaults={})

    # --- CorruptionConfig (pk=1) ---
    corruption_config, _ = CorruptionConfig.objects.get_or_create(pk=1, defaults={})

    # --- IntensityTier reference rows ---
    intensity_tiers: dict[str, IntensityTier] = {}
    for tier_name, threshold, control_mod in _INTENSITY_TIERS:
        tier, _ = IntensityTier.objects.get_or_create(
            name=tier_name,
            defaults={
                "threshold": threshold,
                "control_modifier": control_mod,
                "description": f"{tier_name} intensity level.",
            },
        )
        intensity_tiers[tier_name] = tier

    major_tier = intensity_tiers["Major"]

    # --- Soulfray condition + stages (needed for AudereThreshold.minimum_warp_stage) ---
    # SoulfrayContentFactory() is idempotent — uses get_or_create internally.
    soulfray_content = SoulfrayContentFactory()
    ripping_stage = next(s for s in soulfray_content.stages if s.name == "Ripping")

    # --- AudereThreshold (singleton, no get_or_create on factory) ---
    audere_threshold, _ = AudereThreshold.objects.get_or_create(
        pk=1,
        defaults={
            "minimum_intensity_tier": major_tier,
            "minimum_warp_stage": ripping_stage,
            "intensity_bonus": 20,
            "anima_pool_bonus": 30,
            "warp_multiplier": 2,
        },
    )

    # --- MishapPoolTier: one catch-all tier (min_deficit=1, max_deficit=None) ---
    mishap_pool, _ = ConsequencePool.objects.get_or_create(
        name=_MISHAP_POOL_NAME,
        defaults={"description": "Default pool for magic mishaps from control deficit."},
    )
    mishap_pool_tier, _ = MishapPoolTier.objects.get_or_create(
        min_deficit=1,
        max_deficit=None,
        defaults={"consequence_pool": mishap_pool},
    )

    return MagicConfigResult(
        anima_config=anima_config,
        soulfray_config=soulfray_config,
        resonance_gain_config=resonance_gain_config,
        corruption_config=corruption_config,
        audere_threshold=audere_threshold,
        intensity_tiers=intensity_tiers,
        mishap_pool_tier=mishap_pool_tier,
    )


# ---------------------------------------------------------------------------
# Task 1.2 — seed_canonical_rituals()
# ---------------------------------------------------------------------------


@dataclass
class RitualSeedResult:
    """Returned by seed_canonical_rituals().

    Wraps the canonical Rite of Imbuing and Rite of Atonement rituals.
    Both are lazy-created via factory django_get_or_create on name,
    so re-running preserves any edits to existing rows (idempotent).
    """

    rite_of_imbuing: Ritual
    rite_of_atonement: Ritual


def seed_canonical_rituals() -> RitualSeedResult:
    """Lazy-create the two canonical rituals: Imbuing and Atonement.

    Both factories use django_get_or_create(name=...) so re-running on a
    populated DB is a no-op. Existing rows are never modified; staff edits
    survive repeated calls.

    Creates:
    - Ritual: "Rite of Imbuing" (SERVICE dispatch to spend_resonance_for_imbuing)
    - Ritual: "Rite of Atonement" (SERVICE dispatch to atonement service)

    Returns:
        RitualSeedResult dataclass with both ritual instances.
    """
    from world.magic.factories import (  # noqa: PLC0415
        AtonementRitualFactory,
        ImbuingRitualFactory,
    )

    imbuing = ImbuingRitualFactory()
    atonement = AtonementRitualFactory()
    return RitualSeedResult(rite_of_imbuing=imbuing, rite_of_atonement=atonement)


# ---------------------------------------------------------------------------
# Task 1.3 — seed_thread_pull_catalog()
# ---------------------------------------------------------------------------

#: Canonical resonance name for the thread pull catalog.
#: Must not collide with names used by other seed helpers
#: ("Wild Hunt", "Web of Spiders" are claimed by corruption content).
_CATALOG_RESONANCE_NAME: str = "Tideborne"
_CATALOG_AFFINITY_NAME: str = "Primal (Tideborne)"

#: Per-tier pull cost definitions: (tier, resonance_cost, anima_per_thread, label)
_PULL_COST_TIERS: list[tuple[int, int, int, str]] = [
    (1, 1, 1, "soft"),
    (2, 3, 2, "medium"),
    (3, 6, 3, "hard"),
]

#: Canonical capability name for CAPABILITY_GRANT effect.
_CATALOG_CAPABILITY_NAME: str = "endurance"


@dataclass
class ThreadPullCatalogResult:
    """Returned by seed_thread_pull_catalog().

    All rows are lazy-created via get_or_create. Re-running preserves any edits
    to existing rows (idempotent).
    """

    pull_costs: dict[int, ThreadPullCost]  # tier → cost row
    canonical_resonance: Resonance
    pull_effects: dict[str, ThreadPullEffect]  # EffectKind value → effect row


def seed_thread_pull_catalog() -> ThreadPullCatalogResult:
    """Lazy-create ThreadPullCost rows (tiers 1/2/3) and a 4-row ThreadPullEffect catalog.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    Existing rows are never modified; staff edits survive repeated calls.

    Creates:
    - ThreadPullCost rows: tier 1 (soft), tier 2 (medium), tier 3 (hard)
    - Affinity "Primal (Tideborne)" — shared affinity for the catalog resonance
    - Resonance "Tideborne" — canonical reference resonance for the catalog
    - CapabilityType "endurance" — used by the CAPABILITY_GRANT effect
    - ThreadPullEffect rows:
        - FLAT_BONUS (tier=1, min_thread_level=0, flat_bonus_amount=2)
        - INTENSITY_BUMP (tier=2, min_thread_level=0, intensity_bump_amount=1)
        - VITAL_BONUS (tier=0, min_thread_level=0, vital_bonus_amount=5, MAX_HEALTH)
        - CAPABILITY_GRANT (tier=3, min_thread_level=5, capability=endurance)

    Returns:
        ThreadPullCatalogResult dataclass with all created/fetched instances.
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        AffinityFactory,
        ResonanceFactory,
        ThreadPullCostFactory,
    )
    from world.magic.models.threads import ThreadPullEffect  # noqa: PLC0415

    # --- ThreadPullCost rows (tier is the natural key via django_get_or_create) ---
    pull_costs: dict[int, ThreadPullCost] = {}
    for tier, resonance_cost, anima_per_thread, label in _PULL_COST_TIERS:
        cost = ThreadPullCostFactory(
            tier=tier,
            resonance_cost=resonance_cost,
            anima_per_thread=anima_per_thread,
            label=label,
        )
        pull_costs[tier] = cost

    # --- Canonical resonance (both factory calls use django_get_or_create on name) ---
    affinity = AffinityFactory(name=_CATALOG_AFFINITY_NAME)
    resonance = ResonanceFactory(name=_CATALOG_RESONANCE_NAME, affinity=affinity)

    # --- CapabilityType for CAPABILITY_GRANT (get_or_create on name) ---
    capability, _ = CapabilityType.objects.get_or_create(
        name=_CATALOG_CAPABILITY_NAME,
        defaults={"description": "Endurance capability — used by thread pull catalog."},
    )

    # --- ThreadPullEffect rows (natural key: target_kind, resonance, tier, min_thread_level) ---
    # Using direct ORM get_or_create per task spec to avoid non-idempotent factory calls.
    pull_effects: dict[str, ThreadPullEffect] = {}

    flat_bonus_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=1,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.FLAT_BONUS,
            "flat_bonus_amount": 2,
        },
    )
    pull_effects[EffectKind.FLAT_BONUS] = flat_bonus_effect

    intensity_bump_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=2,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.INTENSITY_BUMP,
            "intensity_bump_amount": 1,
        },
    )
    pull_effects[EffectKind.INTENSITY_BUMP] = intensity_bump_effect

    vital_bonus_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=0,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.VITAL_BONUS,
            "vital_bonus_amount": 5,
            "vital_target": VitalBonusTarget.MAX_HEALTH,
        },
    )
    pull_effects[EffectKind.VITAL_BONUS] = vital_bonus_effect

    capability_grant_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=3,
        min_thread_level=5,
        defaults={
            "effect_kind": EffectKind.CAPABILITY_GRANT,
            "capability_grant": capability,
        },
    )
    pull_effects[EffectKind.CAPABILITY_GRANT] = capability_grant_effect

    return ThreadPullCatalogResult(
        pull_costs=pull_costs,
        canonical_resonance=resonance,
        pull_effects=pull_effects,
    )


# ---------------------------------------------------------------------------
# Task 1.8 — seed_cantrip_starter_catalog()
# ---------------------------------------------------------------------------
#
# 5×5 grid: 5 CantripArchetype values × 5 TechniqueStyle names = 25 cantrips.
#
# Style → PROSPECT Path mapping (per CLAUDE.md / magic CLAUDE.md):
#   Manifestation → Path of Steel
#   Subtle        → Path of Whispers
#   Performance   → Path of Voice
#   Prayer        → Path of the Chosen
#   Incantation   → Path of Tomes
#
# Archetype → EffectType mapping:
#   ATTACK  → Ranged Attack  (for Manifestation/Performance/Incantation)
#             Weapon Enhancement (for Subtle/Prayer)
#   DEFENSE → Defense
#   BUFF    → Buff
#   DEBUFF  → Debuff
#   UTILITY → Utility
#
# Each (archetype, style) pair maps to exactly one cantrip with an evocative name.
#

#: 5 canonical PROSPECT paths, each with minimal required fields.
#: (name, description)
_PROSPECT_PATHS: list[tuple[str, str]] = [
    ("Path of Steel", "Warriors who temper themselves through hardship and direct action."),
    ("Path of Whispers", "Those who move unseen, trading in secrets and subtle influence."),
    ("Path of Voice", "Performers whose magic resonates through song, story, and presence."),
    ("Path of the Chosen", "Devotees bound to a higher power whose prayers shape reality."),
    ("Path of Tomes", "Scholars who unlock magic through careful study and written lore."),
]

#: 5 canonical TechniqueStyle definitions (name, description) and their linked path name.
_TECHNIQUE_STYLES: list[tuple[str, str, str]] = [
    (
        "Manifestation",
        "Magic made tangible — raw elemental force given shape and weight.",
        "Path of Steel",
    ),
    (
        "Subtle",
        "Magic woven into the fabric of things — invisible until it strikes.",
        "Path of Whispers",
    ),
    (
        "Performance",
        "Magic amplified through art — voice, gesture, and presence as conduit.",
        "Path of Voice",
    ),
    (
        "Prayer",
        "Magic granted by devotion — the higher power answers through the faithful.",
        "Path of the Chosen",
    ),
    (
        "Incantation",
        "Magic encoded in language — formulae, glyphs, and spoken true names.",
        "Path of Tomes",
    ),
]

#: 6 canonical EffectType definitions (name, description, base_power, base_anima_cost).
_EFFECT_TYPES: list[tuple[str, str, int | None, int]] = [
    ("Weapon Enhancement", "Imbues a held weapon with magical force.", 10, 3),
    ("Ranged Attack", "Projects destructive energy at a distant target.", 10, 3),
    ("Buff", "Enhances the caster or an ally with a temporary magical boon.", None, 2),
    ("Debuff", "Weakens or hampers a target with a magical affliction.", None, 2),
    ("Defense", "Interposes magical protection between the caster and harm.", 8, 3),
    ("Utility", "Produces a practical magical effect with no direct combat role.", None, 2),
]

# Mapping: (archetype_value, style_name) → (cantrip_name, description, effect_type_name)
# 25 entries covering all 5×5 combinations.
_CANTRIP_GRID: list[tuple[str, str, str, str, str]] = [
    # (archetype, style, cantrip_name, description, effect_type)
    # --- ATTACK ---
    (
        "attack",
        "Manifestation",
        "Burning Strike",
        "A lance of raw fire conjured from personal will and hurled at the enemy.",
        "Ranged Attack",
    ),
    (
        "attack",
        "Subtle",
        "Shadow Blade",
        "A blade wreathed in shadow strikes from an unexpected angle.",
        "Weapon Enhancement",
    ),
    (
        "attack",
        "Performance",
        "Shattering Chorus",
        "A keening note tears through armor and resolve alike.",
        "Ranged Attack",
    ),
    (
        "attack",
        "Prayer",
        "Smiting Light",
        "Holy radiance descends on the unworthy, burning like judgment.",
        "Weapon Enhancement",
    ),
    (
        "attack",
        "Incantation",
        "Force Sigil",
        "A rune of impact is inscribed mid-air, detonating on contact.",
        "Ranged Attack",
    ),
    # --- DEFENSE ---
    (
        "defense",
        "Manifestation",
        "Iron Skin",
        "The caster's flesh hardens momentarily into something like cooled metal.",
        "Defense",
    ),
    (
        "defense",
        "Subtle",
        "Blur Step",
        "Subtle distortions make the caster hard to track — blows glance aside.",
        "Defense",
    ),
    (
        "defense",
        "Performance",
        "Resonant Ward",
        "A harmonious tone creates a shimmering barrier that absorbs incoming force.",
        "Defense",
    ),
    (
        "defense",
        "Prayer",
        "Sacred Ward",
        "The devout invoke their patron's shelter; harm slides off like rain.",
        "Defense",
    ),
    (
        "defense",
        "Incantation",
        "Arcane Barrier",
        "An inscribed ward springs up and deflects the next magical blow.",
        "Defense",
    ),
    # --- BUFF ---
    (
        "buff",
        "Manifestation",
        "Surge",
        "Raw vitality floods the target's limbs, sharpening reflexes for a moment.",
        "Buff",
    ),
    (
        "buff",
        "Subtle",
        "Unseen Edge",
        "Whispered magic gifts the target preternatural awareness of threats.",
        "Buff",
    ),
    (
        "buff",
        "Performance",
        "Inspiring Refrain",
        "A rousing melody lifts allies' spirits and sharpens their focus.",
        "Buff",
    ),
    (
        "buff",
        "Prayer",
        "Blessing of Strength",
        "A murmured prayer calls down divine favor onto a willing recipient.",
        "Buff",
    ),
    (
        "buff",
        "Incantation",
        "Empowering Glyph",
        "A brief formula inscribed on the target's skin grants temporary potency.",
        "Buff",
    ),
    # --- DEBUFF ---
    (
        "debuff",
        "Manifestation",
        "Leaden Aura",
        "Palpable magical weight presses down on the target, slowing movement.",
        "Debuff",
    ),
    (
        "debuff",
        "Subtle",
        "Doubt's Touch",
        "A whisper in the mind erodes the target's certainty at a critical moment.",
        "Debuff",
    ),
    (
        "debuff",
        "Performance",
        "Discordant Note",
        "A jarring sound disrupts the target's concentration and coordination.",
        "Debuff",
    ),
    (
        "debuff",
        "Prayer",
        "Mark of Penitence",
        "The caster's deity marks the target, making all blows against them more telling.",
        "Debuff",
    ),
    (
        "debuff",
        "Incantation",
        "Unraveling Hex",
        "A compact curse formula frays the target's magical and physical defenses.",
        "Debuff",
    ),
    # --- UTILITY ---
    (
        "utility",
        "Manifestation",
        "Mending Touch",
        "Elemental force knits broken objects or calms a raging fire with a touch.",
        "Utility",
    ),
    (
        "utility",
        "Subtle",
        "Silent Passage",
        "The caster's presence dampens sound and scent — ideal for moving unseen.",
        "Utility",
    ),
    (
        "utility",
        "Performance",
        "Lullaby",
        "A soft melody coaxes fatigue into the listener, easing them toward sleep.",
        "Utility",
    ),
    (
        "utility",
        "Prayer",
        "Gentle Mending",
        "A prayer of restoration closes minor wounds and soothes pain.",
        "Utility",
    ),
    (
        "utility",
        "Incantation",
        "Light Script",
        "A luminous glyph provides clean magical light until dismissed.",
        "Utility",
    ),
]


@dataclass
class CantripStarterCatalogResult:
    """Returned by seed_cantrip_starter_catalog().

    Covers the 5×5 grid of archetypes × styles.  All rows are lazy-created via
    get_or_create so re-running on a populated DB is a no-op; staff edits survive.
    """

    styles: dict[str, TechniqueStyle]  # style_name → TechniqueStyle
    effect_types: dict[str, EffectType]  # effect_type_name → EffectType
    cantrips: dict[str, Cantrip]  # cantrip_name → Cantrip
    paths: dict[str, Path]  # path_name → Path (the 5 PROSPECT paths)


def seed_cantrip_starter_catalog() -> CantripStarterCatalogResult:
    """Lazy-create the cantrip starter catalog: 5 styles × 5 archetypes = 25 cantrips.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    Existing rows are never modified; staff edits survive repeated calls.

    5×5 archetype × style grid
    ─────────────────────────────────────────────────────────────────────────
    Style         Path              Archetype coverage
    ─────────────────────────────────────────────────────────────────────────
    Manifestation Path of Steel     attack, defense, buff, debuff, utility
    Subtle        Path of Whispers  attack, defense, buff, debuff, utility
    Performance   Path of Voice     attack, defense, buff, debuff, utility
    Prayer        Path of Chosen    attack, defense, buff, debuff, utility
    Incantation   Path of Tomes     attack, defense, buff, debuff, utility
    ─────────────────────────────────────────────────────────────────────────

    Creates:
    - 5 Path rows (PROSPECT stage) — one per style, idempotent on name
    - 5 TechniqueStyle rows — wired to their corresponding Path via allowed_paths M2M
    - 6 EffectType rows — Weapon Enhancement, Ranged Attack, Buff, Debuff, Defense, Utility
    - 25 Cantrip rows — one per (archetype, style) pair, idempotent on name

    Returns:
        CantripStarterCatalogResult with all created/fetched instances.
    """
    from world.classes.models import Path, PathStage  # noqa: PLC0415
    from world.magic.constants import CantripArchetype  # noqa: PLC0415
    from world.magic.models import EffectType, TechniqueStyle  # noqa: PLC0415
    from world.magic.models.cantrips import Cantrip  # noqa: PLC0415

    # --- PROSPECT Paths (idempotent on name) ---
    paths: dict[str, Path] = {}
    for path_name, path_description in _PROSPECT_PATHS:
        path, _ = Path.objects.get_or_create(
            name=path_name,
            defaults={
                "description": path_description,
                "stage": PathStage.PROSPECT,
                "minimum_level": 1,
                "is_active": True,
                "sort_order": 0,
            },
        )
        paths[path_name] = path

    # --- TechniqueStyle rows + M2M wiring (idempotent on name) ---
    styles: dict[str, TechniqueStyle] = {}
    for style_name, style_description, linked_path_name in _TECHNIQUE_STYLES:
        style, _ = TechniqueStyle.objects.get_or_create(
            name=style_name,
            defaults={"description": style_description},
        )
        # Wire the path into allowed_paths if not already linked (M2M add is idempotent)
        linked_path = paths[linked_path_name]
        style.allowed_paths.add(linked_path)
        styles[style_name] = style

    # --- EffectType rows (idempotent on name) ---
    effect_types: dict[str, EffectType] = {}
    for et_name, et_description, base_power, base_anima_cost in _EFFECT_TYPES:
        has_scaling = base_power is not None
        et, _ = EffectType.objects.get_or_create(
            name=et_name,
            defaults={
                "description": et_description,
                "base_power": base_power,
                "base_anima_cost": base_anima_cost,
                "has_power_scaling": has_scaling,
            },
        )
        effect_types[et_name] = et

    # --- Cantrip rows (idempotent on name) ---
    # Validate all archetype values exist in CantripArchetype
    valid_archetypes = {choice.value for choice in CantripArchetype}
    cantrips: dict[str, Cantrip] = {}
    for sort_idx, (archetype_value, style_name, cantrip_name, description, et_name) in enumerate(
        _CANTRIP_GRID
    ):
        if archetype_value not in valid_archetypes:
            msg = f"Invalid archetype '{archetype_value}' in _CANTRIP_GRID"
            raise ValueError(msg)
        cantrip, _ = Cantrip.objects.get_or_create(
            name=cantrip_name,
            defaults={
                "description": description,
                "archetype": archetype_value,
                "effect_type": effect_types[et_name],
                "style": styles[style_name],
                "base_intensity": 1,
                "base_control": 1,
                "base_anima_cost": 5,
                "requires_facet": False,
                "is_active": True,
                "sort_order": sort_idx,
            },
        )
        cantrips[cantrip_name] = cantrip

    return CantripStarterCatalogResult(
        styles=styles,
        effect_types=effect_types,
        cantrips=cantrips,
        paths=paths,
    )


# ---------------------------------------------------------------------------
# Task 1.9 — seed_magic_dev()
# ---------------------------------------------------------------------------


@dataclass
class FacetThreadUnlockResult:
    """Returned by seed_facet_thread_unlock()."""

    unlock: ThreadWeavingUnlock


@dataclass
class MagicDevSeedResult:
    """Returned by seed_magic_dev().

    Composes all Phase 1 seed results into one dataclass.
    ``author_reference_corruption_content()`` returns None so it is not
    represented here; callers can query Wild Hunt / Web of Spiders rows directly.
    ``penetration`` holds the penetration CheckType, factor ladder, and
    check-scoped ModifierTarget seeded by seed_penetration_contest() (#767).
    """

    config: MagicConfigResult
    rituals: RitualSeedResult
    thread_pull_catalog: ThreadPullCatalogResult
    cantrip_catalog: CantripStarterCatalogResult
    magic_content: MagicContentResult
    facet_thread_unlock: FacetThreadUnlockResult
    penetration: PenetrationContestResult


def seed_facet_thread_unlock() -> FacetThreadUnlockResult:
    """Lazy-create the single global ThreadWeavingUnlock for FACET kind.

    No specific facet is pinned — the unlock applies to weaving any Facet
    thread. Idempotency is guaranteed by ``get_or_create`` semantics keyed on
    ``target_kind=FACET``. The model has no DB-level uniqueness for FACET
    unlocks, but only one global unlock is ever needed (no per-facet variant).
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.weaving import ThreadWeavingUnlock  # noqa: PLC0415

    unlock, _ = ThreadWeavingUnlock.objects.get_or_create(
        target_kind=TargetKind.FACET,
        defaults={"xp_cost": 50},  # baseline cost; staff may tune
    )
    return FacetThreadUnlockResult(unlock=unlock)


def seed_starter_magic_story() -> None:
    """Seed the entire magic-story pipeline slice content set.

    Composes the per-phase helpers in dependency order:

      1. seed_canonical_affinities() — the 3 magic Affinities
      2. seed_canonical_resonances() — Celestial (Light/Sanctity/Radiance) + Abyssal (Dissolution)
     RC1. _seed_affinity_interactions() — 9 directed AffinityInteraction rows (needs affinities)
     RC1. _seed_resonance_environment_config() — ResonanceEnvironmentConfig singleton
      B. _seed_hallowed_reaction_conditions() — 5 OPPOSED reaction conditions
      C. _seed_hallowed_achievement_bridge() — stats, rules, achievements
                                                (needs reaction conditions)
      A. _seed_endure_hallowed_ground_check() — CheckType + ResultChart
     RC4. _seed_resonance_environment_rooms() — 3 cascade rooms (needs resonances)
      F. _seed_hallowed_threshold_story() — Story + Chapter + Episodes + Beats + Transitions + TROs

    All sub-helpers are idempotent (get_or_create at every layer), so the
    orchestrator itself is idempotent. Re-running on an edited DB preserves
    edits (per project seed rule: never update_or_create).
    """
    seed_canonical_affinities()
    seed_canonical_resonances()
    _seed_affinity_interactions()
    _seed_resonance_environment_config()
    _seed_hallowed_reaction_conditions()
    _seed_hallowed_achievement_bridge()
    _seed_endure_hallowed_ground_check()
    _seed_resonance_environment_consequence_pools()  # T12: OPPOSED backfire pools
    _seed_resonance_alignment_boons()  # T13: ALIGNED boon tiers + named buffs
    _seed_resonance_environment_rooms()
    _seed_hallowed_threshold_story()


def seed_magic_dev() -> MagicDevSeedResult:
    """Seed the entire magic cluster in one idempotent call.

    Composes all Phase 1 seed helpers:

    1. ``seed_magic_config()`` — AnimaConfig, SoulfrayConfig, ResonanceGainConfig,
       CorruptionConfig, AudereThreshold, IntensityTier × 3, MishapPoolTier
    2. ``seed_canonical_rituals()`` — Rite of Imbuing, Rite of Atonement
    3. ``seed_thread_pull_catalog()`` — ThreadPullCost × 3, ThreadPullEffect × 4,
       canonical Tideborne resonance
    4. ``seed_cantrip_starter_catalog()`` — 5 TechniqueStyle, 6 EffectType,
       25 Cantrip, 5 PROSPECT Path rows
    5. ``author_reference_corruption_content()`` — Wild Hunt (Primal) + Web of
       Spiders (Abyssal) Corruption ConditionTemplates + CORRUPTION_TWIST entries
    6. ``MagicContent.create_all()`` — 6 social action Techniques + 6
       ActionEnhancements
    7. ``seed_facet_thread_unlock()`` — single global FACET ThreadWeavingUnlock
    8. ``seed_starter_magic_story()`` — magic-story pipeline slice (Affinities,
       Resonances, Hallowed Rejection conditions + triggers, Hallowed Threshold story)
    9. ``seed_penetration_contest()`` — penetration CheckType + factor ladder +
       check-scoped ModifierTarget (#767)

    All writes are idempotent (get_or_create throughout). Re-running on a
    populated database is a no-op; staff edits to existing rows are preserved.

    Returns:
        MagicDevSeedResult composing all sub-results.
    """
    from integration_tests.game_content.combat import seed_penetration_contest  # noqa: PLC0415
    from world.magic.factories import author_reference_corruption_content  # noqa: PLC0415

    config = seed_magic_config()
    rituals = seed_canonical_rituals()
    thread_pull_catalog = seed_thread_pull_catalog()
    cantrip_catalog = seed_cantrip_starter_catalog()
    author_reference_corruption_content()
    magic_content = MagicContent.create_all()
    facet_thread_unlock = seed_facet_thread_unlock()
    seed_starter_magic_story()
    penetration = seed_penetration_contest()

    return MagicDevSeedResult(
        config=config,
        rituals=rituals,
        thread_pull_catalog=thread_pull_catalog,
        cantrip_catalog=cantrip_catalog,
        magic_content=magic_content,
        facet_thread_unlock=facet_thread_unlock,
        penetration=penetration,
    )
