"""ChallengeContent — capabilities, properties, applications, and starter challenges.

Creates the full Capabilities & Challenges content suite:
  - 19 CapabilityTypes (physical, magical, social, mental)
  - 5 PropertyCategories with ~27 Properties
  - ~44 Applications linking capabilities to properties
  - 5 non-social CheckTypes with trait weights
  - 11 TraitCapabilityDerivation records
  - 3 bonus ConditionTemplates for critical success effects
  - 5 ChallengeCategories with 6 starter ChallengeTemplates
  - ConsequencePools with 4 tiers per challenge + ConsequenceEffects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.conditions.models import CapabilityType, ConditionTemplate
    from world.mechanics.models import (
        Application,
        ChallengeCategory,
        ChallengeTemplate,
        Property,
        PropertyCategory,
        TraitCapabilityDerivation,
    )
    from world.traits.models import CheckOutcome

# ---------------------------------------------------------------------------
# Data constants
# ---------------------------------------------------------------------------

# 19 CapabilityTypes: (name, description)
CAPABILITY_TYPES: list[tuple[str, str]] = [
    # Physical / Magical (12)
    ("generation", "Creating energy, matter, or elemental forces from nothing."),
    ("force", "Applying raw physical or magical power to overcome resistance."),
    ("projection", "Launching directed attacks or energy at range."),
    ("manipulation", "Controlling and redirecting existing forces or objects."),
    ("barrier", "Creating protective shields, wards, or containment."),
    ("traversal", "Moving through or across difficult terrain and obstacles."),
    ("movement", "Enhancing personal speed, agility, or positional advantage."),
    ("precision", "Fine motor control and accuracy for delicate tasks."),
    ("suppression", "Nullifying, dispelling, or containing magical effects."),
    ("transmutation", "Changing the nature or form of materials and energy."),
    ("communication", "Conveying information across barriers or distances."),
    ("perception", "Sensing hidden or distant things beyond normal limits."),
    # Social (5)
    ("intimidation", "Coercing through force of presence, threats, or physical dominance."),
    ("persuasion", "Convincing through reasoned argument, charm, and social grace."),
    ("deception", "Misleading through misdirection, half-truths, or outright lies."),
    ("charm", "Winning favour through personal magnetism and likability."),
    ("inspiration", "Rousing courage, morale, or action in others."),
    # Mental (2)
    ("analysis", "Understanding systems, patterns, and hidden structures."),
    ("exploitation", "Finding and leveraging weaknesses in defences."),
]

# 5 PropertyCategories with properties: (category_name, [(prop_name, description), ...])
PROPERTY_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Elemental",
        [
            ("flammable", "Susceptible to fire or combustion."),
            ("frozen", "Covered in or composed of ice."),
            ("electrified", "Charged with electrical energy."),
            ("flooded", "Submerged or saturated with water."),
            ("shadowy", "Shrouded in supernatural darkness."),
            ("radiant", "Emitting or infused with holy or pure light."),
            ("arcane", "Infused with raw magical energy."),
        ],
    ),
    (
        "Physical",
        [
            ("locked", "Secured by a mechanical or magical lock."),
            ("breakable", "Can be destroyed by sufficient force."),
            ("heavy", "Massive or weighty, requiring great strength."),
            ("armored", "Protected by physical defences."),
            ("solid", "Dense and resistant to penetration."),
            ("mechanical", "Operates through gears, levers, or mechanisms."),
            ("enclosed", "Sealed or confined with limited exit."),
        ],
    ),
    (
        "Environmental",
        [
            ("dark", "Lacking light, visibility impaired."),
            ("underwater", "Submerged beneath a body of water."),
            ("elevated", "Raised above ground level, requiring climbing."),
            ("hazardous", "Actively dangerous to those nearby."),
            ("gaseous", "Filled with gas, vapour, or airborne particles."),
        ],
    ),
    (
        "Creature",
        [
            ("abyssal", "Originating from demonic or abyssal planes."),
            ("celestial", "Of divine or heavenly origin."),
            ("undead", "Animated by necromantic forces."),
            ("bestial", "Animal-like in nature and behaviour."),
            ("spectral", "Ghostly, incorporeal, or spirit-like."),
        ],
    ),
    (
        "Social",
        [
            ("fearful", "Prone to fear and anxiety."),
            ("trusting", "Open and credulous, slow to suspect deception."),
            ("proud", "Motivated by ego and self-image."),
            ("reasonable", "Receptive to logical argument and evidence."),
            ("demoralized", "Low in morale, lacking confidence."),
        ],
    ),
]

# ~44 Applications: (app_name, capability_name, property_name)
APPLICATION_DEFS: list[tuple[str, str, str]] = [
    # generation
    ("Ignite", "generation", "flammable"),
    ("Illuminate", "generation", "dark"),
    ("Evaporate", "generation", "flooded"),
    # force
    ("Break", "force", "breakable"),
    ("Lift", "force", "heavy"),
    ("Breach", "force", "armored"),
    ("Drain", "force", "flooded"),
    # projection
    ("Blast", "projection", "solid"),
    ("Strike", "projection", "armored"),
    # manipulation
    ("Channel", "manipulation", "flooded"),
    ("Direct", "manipulation", "gaseous"),
    ("Control", "manipulation", "mechanical"),
    # barrier
    ("Shield", "barrier", "hazardous"),
    ("Contain", "barrier", "flooded"),
    ("Ward", "barrier", "arcane"),
    ("Block", "barrier", "armored"),
    # traversal
    ("Navigate", "traversal", "dark"),
    ("Cross", "traversal", "hazardous"),
    ("Escape", "traversal", "enclosed"),
    ("Ascend", "traversal", "elevated"),
    ("Swim", "traversal", "underwater"),
    # perception
    ("Scout", "perception", "dark"),
    ("Detect", "perception", "arcane"),
    ("Analyze", "perception", "spectral"),
    ("Spot", "perception", "enclosed"),
    # suppression
    ("Cleanse", "suppression", "arcane"),
    ("Purify", "suppression", "abyssal"),
    ("Dispel", "suppression", "shadowy"),
    ("Exorcise", "suppression", "undead"),
    # precision
    ("Pick", "precision", "locked"),
    ("Disarm", "precision", "mechanical"),
    # analysis
    ("Solve", "analysis", "mechanical"),
    ("Decipher", "analysis", "arcane"),
    ("Assess", "analysis", "armored"),
    # exploitation
    ("Exploit", "exploitation", "armored"),
    ("Shatter", "exploitation", "breakable"),
    # intimidation
    ("Cow", "intimidation", "proud"),
    ("Threaten", "intimidation", "fearful"),
    # persuasion
    ("Convince", "persuasion", "reasonable"),
    ("Sway", "persuasion", "trusting"),
    # deception
    ("Mislead", "deception", "trusting"),
    ("Bluff", "deception", "proud"),
    # charm
    ("Befriend", "charm", "reasonable"),
    ("Seduce", "charm", "proud"),
    # inspiration
    ("Rally", "inspiration", "demoralized"),
    ("Embolden", "inspiration", "fearful"),
]

# 5 Challenge CheckTypes: (name, primary_trait, primary_weight, secondary_trait, secondary_weight)
CHALLENGE_CHECK_TYPES: list[tuple[str, str, str, str, str]] = [
    ("physical_challenge", "strength", "1.00", "agility", "0.50"),
    ("magical_challenge", "willpower", "1.00", "intellect", "0.50"),
    ("precision_challenge", "agility", "1.00", "perception", "0.50"),
    ("mental_challenge", "intellect", "1.00", "wits", "0.50"),
    ("perception_challenge", "perception", "1.00", "wits", "0.50"),
]

# 11 TraitCapabilityDerivations: (trait_name, capability_name)
TRAIT_DERIVATIONS: list[tuple[str, str]] = [
    ("strength", "force"),
    ("agility", "precision"),
    ("agility", "traversal"),
    ("charm", "charm"),
    ("charm", "persuasion"),
    ("charm", "deception"),
    ("presence", "intimidation"),
    ("presence", "inspiration"),
    ("intellect", "analysis"),
    ("wits", "exploitation"),
    ("perception", "perception"),
]

# 3 Bonus conditions for critical success effects: (name, description)
BONUS_CONDITIONS: list[tuple[str, str]] = [
    ("Emboldened", "A surge of confidence from overcoming a challenge."),
    ("Enlightened", "Heightened clarity from unravelling a mystery."),
    ("Resolute", "Steeled determination from a triumphant social encounter."),
]

# 5 ChallengeCategories
CHALLENGE_CATEGORIES: list[str] = [
    "Environmental",
    "Physical",
    "Magical",
    "Combat",
    "Social",
]

# 6 Starter challenges: (name, challenge_type, severity, category_name, props, approaches)
# approaches: [(display_name, application_name, check_type_name)]
# For the Social challenge, check_type_name refers to Social CheckType names from Pass 1.
CHALLENGE_DEFS: list[tuple[str, str, int, str, list[str], list[tuple[str, str, str]]]] = [
    (
        "Locked Door",
        "inhibitor",
        2,
        "Physical",
        ["locked", "solid", "breakable"],
        [
            ("Pick the Lock", "Pick", "precision_challenge"),
            ("Break Down", "Break", "physical_challenge"),
            ("Analyze Mechanism", "Solve", "mental_challenge"),
        ],
    ),
    (
        "Magical Ward",
        "inhibitor",
        3,
        "Magical",
        ["arcane", "radiant"],
        [
            ("Dispel Ward", "Cleanse", "magical_challenge"),
            ("Decipher Runes", "Decipher", "mental_challenge"),
            ("Counter-Ward", "Ward", "magical_challenge"),
        ],
    ),
    (
        "Flooded Chamber",
        "threat",
        2,
        "Environmental",
        ["flooded", "hazardous", "enclosed"],
        [
            ("Boil Away", "Evaporate", "magical_challenge"),
            ("Force Drain", "Drain", "physical_challenge"),
            ("Channel Water", "Channel", "magical_challenge"),
            ("Find Escape", "Escape", "precision_challenge"),
        ],
    ),
    (
        "Armored Guardian",
        "inhibitor",
        4,
        "Combat",
        ["armored", "breakable", "bestial"],
        [
            ("Breach Armor", "Breach", "physical_challenge"),
            ("Find Weakness", "Assess", "mental_challenge"),
            ("Exploit Opening", "Exploit", "mental_challenge"),
        ],
    ),
    (
        "Darkness",
        "inhibitor",
        1,
        "Environmental",
        ["dark"],
        [
            ("Create Light", "Illuminate", "magical_challenge"),
            ("Scout Ahead", "Scout", "perception_challenge"),
            ("Navigate Blind", "Navigate", "precision_challenge"),
        ],
    ),
    (
        "Proud Noble",
        "inhibitor",
        2,
        "Social",
        ["proud", "reasonable"],
        [
            ("Cow", "Cow", "Intimidation"),
            ("Convince", "Convince", "Persuasion"),
            ("Bluff", "Bluff", "Deception"),
            ("Seduce", "Seduce", "Seduction"),
        ],
    ),
]

# Maps challenge name → bonus condition name for critical success effects.
CHALLENGE_BONUS_CONDITIONS: dict[str, str] = {
    "Locked Door": "Emboldened",
    "Magical Ward": "Enlightened",
    "Flooded Chamber": "Emboldened",
    "Armored Guardian": "Emboldened",
    "Darkness": "Enlightened",
    "Proud Noble": "Resolute",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ChallengeContentResult:
    """Returned by ChallengeContent.create_all()."""

    capability_types: dict[str, CapabilityType] = field(default_factory=dict)
    property_categories: dict[str, PropertyCategory] = field(default_factory=dict)
    properties: dict[str, Property] = field(default_factory=dict)
    applications: list[Application] = field(default_factory=list)
    challenge_check_types: dict[str, CheckType] = field(default_factory=dict)
    trait_derivations: list[TraitCapabilityDerivation] = field(default_factory=list)
    bonus_conditions: dict[str, ConditionTemplate] = field(default_factory=dict)
    challenge_categories: dict[str, ChallengeCategory] = field(default_factory=dict)
    challenges: dict[str, ChallengeTemplate] = field(default_factory=dict)
    outcomes: dict[str, CheckOutcome] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Builder class
# ---------------------------------------------------------------------------


class ChallengeContent:
    """Creates the complete Capabilities & Challenges content suite for integration tests."""

    @staticmethod
    def create_capability_types() -> dict[str, CapabilityType]:
        """Create 19 CapabilityTypes (physical, magical, social, mental).

        Returns:
            Dict mapping capability name to CapabilityType instance.
        """
        from world.conditions.factories import CapabilityTypeFactory  # noqa: PLC0415

        result: dict[str, CapabilityType] = {}
        for name, description in CAPABILITY_TYPES:
            result[name] = CapabilityTypeFactory(name=name, description=description)
        return result

    @staticmethod
    def create_properties() -> tuple[dict[str, PropertyCategory], dict[str, Property]]:
        """Create 5 PropertyCategories and ~27 Properties.

        Returns:
            Tuple of (categories dict, properties dict) keyed by name.
        """
        from world.mechanics.factories import (  # noqa: PLC0415
            PropertyCategoryFactory,
            PropertyFactory,
        )

        categories: dict[str, PropertyCategory] = {}
        properties: dict[str, Property] = {}

        for order, (cat_name, prop_defs) in enumerate(PROPERTY_CATEGORIES):
            category = PropertyCategoryFactory(
                name=cat_name,
                description=f"Properties related to {cat_name.lower()} characteristics.",
                display_order=order,
            )
            categories[cat_name] = category

            for prop_name, prop_desc in prop_defs:
                properties[prop_name] = PropertyFactory(
                    name=prop_name,
                    description=prop_desc,
                    category=category,
                )

        return categories, properties

    @staticmethod
    def create_applications(
        capability_types: dict[str, CapabilityType],
        properties: dict[str, Property],
    ) -> list[Application]:
        """Create ~44 Applications linking capabilities to target properties.

        Args:
            capability_types: Dict from create_capability_types().
            properties: Dict from create_properties().

        Returns:
            List of Application instances.
        """
        from world.mechanics.factories import ApplicationFactory  # noqa: PLC0415

        applications: list[Application] = []
        for app_name, cap_name, prop_name in APPLICATION_DEFS:
            app = ApplicationFactory(
                name=app_name,
                capability=capability_types[cap_name],
                target_property=properties[prop_name],
                description=f"{app_name} using {cap_name} on {prop_name} targets.",
            )
            applications.append(app)
        return applications

    @staticmethod
    def create_challenge_check_types() -> dict[str, CheckType]:
        """Create 5 non-social CheckTypes with trait weights for challenge resolution.

        Returns:
            Dict mapping check type name to CheckType instance.
        """
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory  # noqa: PLC0415
        from world.checks.models import CheckTypeTrait  # noqa: PLC0415
        from world.traits.factories import StatTraitFactory  # noqa: PLC0415

        challenge_cat = CheckCategoryFactory(
            name="Challenge",
            description="Check types used for challenge resolution.",
            display_order=20,
        )

        check_types: dict[str, CheckType] = {}
        for (
            ct_name,
            primary_trait,
            primary_w,
            secondary_trait,
            secondary_w,
        ) in CHALLENGE_CHECK_TYPES:
            ct = CheckTypeFactory(
                name=ct_name,
                category=challenge_cat,
                description=f"Challenge check weighted toward {primary_trait}.",
            )
            check_types[ct_name] = ct

            for trait_name, weight in [(primary_trait, primary_w), (secondary_trait, secondary_w)]:
                trait = StatTraitFactory(name=trait_name)
                CheckTypeTrait.objects.get_or_create(
                    check_type=ct,
                    trait=trait,
                    defaults={"weight": Decimal(weight)},
                )

        return check_types

    @staticmethod
    def create_trait_derivations(
        capability_types: dict[str, CapabilityType],
    ) -> list[TraitCapabilityDerivation]:
        """Create 11 TraitCapabilityDerivation records (all base_value=0, multiplier=0.50).

        Args:
            capability_types: Dict from create_capability_types().

        Returns:
            List of TraitCapabilityDerivation instances.
        """
        from world.mechanics.factories import TraitCapabilityDerivationFactory  # noqa: PLC0415
        from world.traits.factories import StatTraitFactory  # noqa: PLC0415

        derivations: list[TraitCapabilityDerivation] = []
        for trait_name, cap_name in TRAIT_DERIVATIONS:
            trait = StatTraitFactory(name=trait_name)
            deriv = TraitCapabilityDerivationFactory(
                trait=trait,
                capability=capability_types[cap_name],
                base_value=0,
                trait_multiplier=Decimal("0.50"),
            )
            derivations.append(deriv)
        return derivations

    @staticmethod
    def _create_bonus_conditions() -> dict[str, ConditionTemplate]:
        """Create 3 bonus ConditionTemplates for critical success effects.

        Returns:
            Dict mapping condition name to ConditionTemplate instance.
        """
        from world.conditions.factories import (  # noqa: PLC0415
            ConditionCategoryFactory,
            ConditionTemplateFactory,
        )

        bonus_cat = ConditionCategoryFactory(name="Bonus", is_negative=False)
        conditions: dict[str, ConditionTemplate] = {}
        for name, description in BONUS_CONDITIONS:
            conditions[name] = ConditionTemplateFactory(
                name=name,
                category=bonus_cat,
                description=description,
            )
        return conditions

    @staticmethod
    def create_challenges(
        properties: dict[str, Property],
        applications: list[Application],
        challenge_check_types: dict[str, CheckType],
        outcomes: dict[str, CheckOutcome],
    ) -> tuple[dict[str, ChallengeCategory], dict[str, ChallengeTemplate]]:
        """Create 5 ChallengeCategories and 6 starter ChallengeTemplates with consequences.

        Each challenge gets:
          - ChallengeTemplateProperty records for its properties
          - A ConsequencePool with 4 Consequences (failure/partial/success/critical)
          - ChallengeTemplateConsequence through-model records with resolution types
          - ChallengeApproach records linking applications to check types
          - ConsequenceEffect on critical tier applying a bonus condition

        Args:
            properties: Dict from create_properties().
            applications: List from create_applications().
            challenge_check_types: Dict from create_challenge_check_types().
            outcomes: Dict with "failure", "partial", "success", "critical" CheckOutcome instances.

        Returns:
            Tuple of (categories dict, challenges dict) keyed by name.
        """
        from actions.factories import (  # noqa: PLC0415
            ConsequencePoolEntryFactory,
            ConsequencePoolFactory,
        )
        from world.checks.constants import EffectTarget, EffectType  # noqa: PLC0415
        from world.checks.factories import ConsequenceFactory  # noqa: PLC0415
        from world.checks.models import CheckType, ConsequenceEffect  # noqa: PLC0415
        from world.mechanics.constants import ChallengeType, ResolutionType  # noqa: PLC0415
        from world.mechanics.factories import (  # noqa: PLC0415
            ChallengeApproachFactory,
            ChallengeCategoryFactory,
            ChallengeTemplateConsequenceFactory,
            ChallengeTemplateFactory,
            ChallengeTemplatePropertyFactory,
        )

        # --- Build application lookup by name ---
        app_by_name: dict[str, Application] = {a.name: a for a in applications}

        # --- Bonus conditions ---
        bonus_conditions = ChallengeContent._create_bonus_conditions()

        # --- Categories ---
        categories: dict[str, ChallengeCategory] = {}
        for order, cat_name in enumerate(CHALLENGE_CATEGORIES):
            categories[cat_name] = ChallengeCategoryFactory(
                name=cat_name,
                description=f"{cat_name} challenges.",
                display_order=order,
            )

        # --- Social check types (from Pass 1) for the Proud Noble challenge ---
        social_check_types: dict[str, CheckType] = {}
        social_cts = CheckType.objects.filter(category__name="Social")
        for ct in social_cts:
            social_check_types[ct.name] = ct

        # --- Consequence tier configs ---
        # (outcome_key, resolution_type, duration_rounds)
        consequence_tiers: list[tuple[str, str, int | None]] = [
            ("failure", ResolutionType.PERSONAL, None),
            ("partial", ResolutionType.TEMPORARY, 3),
            ("success", ResolutionType.DESTROY, None),
            ("critical", ResolutionType.DESTROY, None),
        ]

        # --- Challenges ---
        challenges: dict[str, ChallengeTemplate] = {}

        for ch_name, ch_type, severity, cat_name, prop_names, approaches in CHALLENGE_DEFS:
            challenge_type = (
                ChallengeType.THREAT if ch_type == "threat" else ChallengeType.INHIBITOR
            )
            template = ChallengeTemplateFactory(
                name=ch_name,
                severity=severity,
                category=categories[cat_name],
                challenge_type=challenge_type,
                goal=f"Overcome the {ch_name.lower()}.",
            )
            challenges[ch_name] = template

            # --- Properties ---
            for prop_name in prop_names:
                ChallengeTemplatePropertyFactory(
                    challenge_template=template,
                    property=properties[prop_name],
                )

            # --- Consequence pool ---
            pool = ConsequencePoolFactory(name=f"{ch_name} Pool")

            bonus_cond_name = CHALLENGE_BONUS_CONDITIONS.get(ch_name)
            bonus_cond = bonus_conditions.get(bonus_cond_name) if bonus_cond_name else None

            for outcome_key, resolution_type, duration_rounds in consequence_tiers:
                outcome = outcomes[outcome_key]
                consequence = ConsequenceFactory(
                    outcome_tier=outcome,
                    label=f"{ch_name} {outcome_key.title()}",
                    weight=1,
                    character_loss=False,
                )

                ChallengeTemplateConsequenceFactory(
                    challenge_template=template,
                    consequence=consequence,
                    resolution_type=resolution_type,
                    resolution_duration_rounds=duration_rounds,
                )

                ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

                # Critical success: apply bonus condition
                if outcome_key == "critical" and bonus_cond is not None:
                    ConsequenceEffect.objects.create(
                        consequence=consequence,
                        effect_type=EffectType.APPLY_CONDITION,
                        target=EffectTarget.SELF,
                        condition_template=bonus_cond,
                        condition_severity=1,
                        execution_order=0,
                    )

            # --- Approaches ---
            for display_name, app_name, ct_name in approaches:
                # Look up check type: first in challenge check types, then social
                ct = challenge_check_types.get(ct_name) or social_check_types.get(ct_name)
                if ct is None:
                    msg = (
                        f"CheckType '{ct_name}' not found for approach '{display_name}' "
                        f"on challenge '{ch_name}'."
                    )
                    raise ValueError(msg)

                ChallengeApproachFactory(
                    challenge_template=template,
                    application=app_by_name[app_name],
                    check_type=ct,
                    display_name=display_name,
                    custom_description=f"{display_name} approach to {ch_name.lower()}.",
                )

        return categories, challenges

    @staticmethod
    def create_all(outcomes: dict[str, CheckOutcome]) -> ChallengeContentResult:
        """Orchestrate creation of the entire Capabilities & Challenges content suite.

        Args:
            outcomes: Dict with "failure", "partial", "success", "critical" CheckOutcome
                instances (typically from SocialContent or CheckSystemSetupFactory).

        Returns:
            ChallengeContentResult with all created content.
        """
        capability_types = ChallengeContent.create_capability_types()
        property_categories, properties = ChallengeContent.create_properties()
        applications = ChallengeContent.create_applications(capability_types, properties)
        challenge_check_types = ChallengeContent.create_challenge_check_types()
        trait_derivations = ChallengeContent.create_trait_derivations(capability_types)
        challenge_categories, challenges = ChallengeContent.create_challenges(
            properties, applications, challenge_check_types, outcomes
        )

        # Collect bonus conditions created during challenge setup
        bonus_conditions: dict[str, ConditionTemplate] = {}
        from world.conditions.models import ConditionTemplate as ConditionModel  # noqa: PLC0415

        for cond_name in set(CHALLENGE_BONUS_CONDITIONS.values()):
            cond = ConditionModel.objects.filter(name=cond_name).first()
            if cond is not None:
                bonus_conditions[cond_name] = cond

        return ChallengeContentResult(
            capability_types=capability_types,
            property_categories=property_categories,
            properties=properties,
            applications=applications,
            challenge_check_types=challenge_check_types,
            trait_derivations=trait_derivations,
            bonus_conditions=bonus_conditions,
            challenge_categories=challenge_categories,
            challenges=challenges,
            outcomes=outcomes,
        )
