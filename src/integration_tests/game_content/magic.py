"""MagicContent — technique and ActionEnhancement records for social action tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from world.conditions.models import CapabilityType
    from world.magic.models import Technique, TechniqueCapabilityGrant
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
