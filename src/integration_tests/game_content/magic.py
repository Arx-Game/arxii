"""Magic test-infrastructure: MagicContent (technique content) and seed_magic_config()."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from actions.models.consequence_pools import ConsequencePool
    from world.conditions.models import CapabilityType, ConditionStage
    from world.magic.audere import AudereThreshold
    from world.magic.models import (
        Affinity,
        AnimaConfig,
        IntensityTier,
        MagicalAlterationTemplate,
        MishapPoolTier,
        Resonance,
        SoulfrayConfig,
        Technique,
        TechniqueCapabilityGrant,
    )
    from world.magic.models.corruption_config import CorruptionConfig
    from world.magic.models.gain_config import ResonanceGainConfig
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

        Safe to call from setUpTestData across multiple test classes.

        Returns:
            MagicContentResult with techniques and enhancements dicts.
        """
        from actions.constants import EnhancementSourceType  # noqa: PLC0415
        from actions.factories import ActionEnhancementFactory  # noqa: PLC0415
        from world.magic.factories import GiftFactory, TechniqueFactory  # noqa: PLC0415

        gift = GiftFactory(name="Social Arts")
        techniques: dict[str, Technique] = {}
        enhancements: dict[str, ActionEnhancement] = {}

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            technique = TechniqueFactory(
                name=technique_name,
                gift=gift,
                intensity=2,
                control=2,
                anima_cost=12,
            )
            techniques[action_key] = technique

            enhancement = ActionEnhancementFactory(
                base_action_key=action_key,
                variant_name=f"Magical {action_key.title()}",
                source_type=EnhancementSourceType.TECHNIQUE,
                technique=technique,
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
            "soulfray_threshold_ratio": "0.30",
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
