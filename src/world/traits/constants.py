"""
Constants for the traits system.

Defines enums and constant values used throughout the traits system.
"""

from django.db import models


class PrimaryStat(models.TextChoices):
    """
    Primary character statistics.

    These are the 8 core stats used in character creation and gameplay.
    Values are stored internally as multiples of 10 (10-50 scale during CG,
    higher post-creation) but displayed as integers (1-5 during CG, higher post-creation).

    Categories:
    - Physical: Strength, Agility, Stamina
    - Social: Charm, Presence
    - Mental: Intellect, Wits, Willpower
    """

    STRENGTH = "strength", "Strength"
    AGILITY = "agility", "Agility"
    STAMINA = "stamina", "Stamina"
    CHARM = "charm", "Charm"
    PRESENCE = "presence", "Presence"
    INTELLECT = "intellect", "Intellect"
    WITS = "wits", "Wits"
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
            ("intellect", "mental", "Reasoning and learned knowledge."),
            ("wits", "mental", "Quick thinking and situational awareness."),
            ("willpower", "mental", "Mental fortitude and determination."),
        ]
