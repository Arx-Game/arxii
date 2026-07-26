"""
Constants for the traits system.

Defines enums and constant values used throughout the traits system.
"""

from typing import NamedTuple

from django.db import models

from world.traits.models import TraitCategory, TraitType


class PrimaryStat(models.TextChoices):
    """
    Primary character statistics.

    These are the 12 core stats used in character creation and gameplay,
    organized into 4 categories.

    Categories:
    - Physical: Strength, Agility, Stamina
    - Social: Charm, Presence, Composure
    - Mental: Intellect, Wits, Stability
    - Meta: Luck, Perception, Willpower
    """

    STRENGTH = "strength", "Strength"
    AGILITY = "agility", "Agility"
    STAMINA = "stamina", "Stamina"
    CHARM = "charm", "Charm"
    PRESENCE = "presence", "Presence"
    COMPOSURE = "composure", "Composure"
    INTELLECT = "intellect", "Intellect"
    WITS = "wits", "Wits"
    STABILITY = "stability", "Stability"
    LUCK = "luck", "Luck"
    PERCEPTION = "perception", "Perception"
    WILLPOWER = "willpower", "Willpower"

    @classmethod
    def get_all_stat_names(cls) -> list[str]:
        """Return list of all primary stat names (lowercase values)."""
        return [stat.value for stat in cls]

    @classmethod
    def get_stat_metadata(cls) -> list[tuple[str, str, str]]:
        """
        Return metadata for all primary stats for use in migrations.

        Returns:
            List of tuples: (name, category, description)
        """
        return [
            ("strength", "physical", "Raw physical power and muscle."),
            ("agility", "physical", "Speed, reflexes, and coordination."),
            ("stamina", "physical", "Endurance and resistance to harm."),
            ("charm", "social", "Likability and social magnetism."),
            ("presence", "social", "Force of personality and leadership."),
            (
                "composure",
                "social",
                "Social endurance. Poise under social pressure and resistance to embarrassment.",
            ),
            ("intellect", "mental", "Reasoning and learned knowledge."),
            ("wits", "mental", "Quick thinking and situational awareness."),
            (
                "stability",
                "mental",
                "Mental endurance. Sustained focus and resistance to mental strain.",
            ),
            ("luck", "meta", "Fortune and happenstance. The universe's favor."),
            ("perception", "meta", "Awareness and reading of people and situations."),
            ("willpower", "meta", "Mental fortitude and determination."),
        ]


class TraitDefault(NamedTuple):
    """Code default for a STAT Trait a config prerequisite (#2724) may need to create."""

    trait_type: str
    category: str
    description: str


# Code defaults for the STAT Traits multiple config-prerequisite paths roll checks on
# (fatigue's willpower/endurance checks, dreams' Dream Peril Resolve — see
# world.seeds.config_prerequisites) before the content load populates the `traits.trait`
# fixtures. `Trait.category` has no model default and is a required column
# (world/traits/models.py) — a get_or_create that omits it silently stores "". These
# values match the authored rows in arx2/fixtures/traits/trait.json exactly, so the
# later content-fixture upsert (`load_entries`) is a no-op when the lore repo already
# carries the row. Byte-identical to what was previously the private
# world.fatigue.constants.FATIGUE_TRAIT_DEFAULTS (#2724) — this is now the only copy;
# do not fork a second one.
STAT_TRAIT_DEFAULTS: dict[str, TraitDefault] = {
    "willpower": TraitDefault(
        TraitType.STAT, TraitCategory.META, "Mental fortitude and determination."
    ),
    "stamina": TraitDefault(
        TraitType.STAT, TraitCategory.PHYSICAL, "Endurance and resistance to harm."
    ),
    "composure": TraitDefault(
        TraitType.STAT,
        TraitCategory.SOCIAL,
        "Social endurance. Poise under social pressure and resistance to embarrassment.",
    ),
    "stability": TraitDefault(
        TraitType.STAT,
        TraitCategory.MENTAL,
        "Mental endurance. Sustained focus and resistance to mental strain.",
    ),
}
