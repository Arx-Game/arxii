"""MagicContent — technique and ActionEnhancement records for social action tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from world.magic.models import Technique

# Maps action_key → technique name (narrative, not mechanical)
ACTION_TECHNIQUE_MAP: dict[str, str] = {
    "intimidate": "Soul Crush",
    "persuade": "Silver Tongue",
    "deceive": "Veil of Lies",
    "flirt": "Heartstring Pull",
    "perform": "Echoing Song",
    "entrance": "Commanding Presence",
}


@dataclass
class MagicContentResult:
    """Returned by MagicContent.create_all()."""

    techniques: dict[str, Technique]  # action_key → Technique
    enhancements: dict[str, ActionEnhancement]  # action_key → ActionEnhancement


class MagicContent:
    """Creates techniques and ActionEnhancement records for social action integration tests."""

    @staticmethod
    def create_all() -> MagicContentResult:
        """Create 6 techniques and 6 ActionEnhancement records (one per social action).

        Techniques use intensity=2, control=2, anima_cost=2 — no control deficit,
        predictable anima deduction of 2 per use.

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
                anima_cost=2,
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
