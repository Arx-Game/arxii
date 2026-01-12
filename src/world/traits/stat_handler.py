"""
Stat handler for primary character statistics.

Provides a stat-specific interface wrapping the generic TraitHandler,
with methods tailored for the 8 primary stats.
"""

from world.traits.constants import PrimaryStat


class StatHandler:
    """
    Handler for character primary statistics.

    Wraps TraitHandler to provide stat-specific semantics while delegating
    storage to the existing traits system. Stats are stored internally as
    values 10-50 (multiply display 1-5 by 10) to align with the traits system.
    """

    STAT_NAMES = PrimaryStat.get_all_stat_names()

    def __init__(self, character):
        """
        Initialize the stat handler.

        Args:
            character: The character object this handler is bound to
        """
        self.character = character
        self.traits = character.traits

    def get_stat(self, stat_name: str) -> int:
        """
        Get internal stat value.

        Args:
            stat_name: Name of the stat (e.g., "strength")

        Returns:
            Internal stat value (10-50 scale for CG range 1-5)
        """
        return self.traits.get_trait_value(stat_name)

    def get_stat_display(self, stat_name: str) -> int:
        """
        Get display value for a stat.

        Args:
            stat_name: Name of the stat (e.g., "strength")

        Returns:
            Display value (1-5 integer scale) using integer division
        """
        return self.get_stat(stat_name) // 10

    def set_stat(self, stat_name: str, value: int) -> bool:
        """
        Set stat value with validation.

        Args:
            stat_name: Name of the stat (e.g., "strength")
            value: Internal value to set (typically 10-50)

        Returns:
            True if successful, False otherwise
        """
        return self.traits.set_trait_value(stat_name, value)

    def get_all_stats(self) -> dict[str, int]:
        """
        Get all 8 primary stats as a dictionary.

        Returns:
            Dict mapping stat names to internal values
        """
        return {stat: self.get_stat(stat) for stat in self.STAT_NAMES}

    def get_all_stats_display(self) -> dict[str, dict]:
        """
        Get all stats with display formatting for API/UI.

        Returns:
            Dict mapping stat names to dicts containing:
                - value: Internal value (10-50 range)
                - display: Display value (1-5 integer)
                - modifiers: List of temporary modifiers (empty for now)
        """
        result = {}
        for stat in self.STAT_NAMES:
            value = self.get_stat(stat)
            result[stat] = {
                "value": value,
                "display": value // 10,  # Integer division, rounds down
                "modifiers": [],  # Future: temporary modifiers
            }
        return result
