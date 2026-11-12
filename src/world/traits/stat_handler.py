"""
Stat handler for primary character statistics.

Provides a stat-specific interface wrapping the generic TraitHandler,
with methods tailored for the 8 primary stats.
"""

from typing import TYPE_CHECKING

from world.traits.constants import PrimaryStat

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


class StatHandler:
    """
    Handler for character primary statistics.

    Wraps TraitHandler to provide stat-specific semantics while delegating
    storage to the existing traits system. Stats store and show the same value
    (10-50 at character creation, #5091).
    """

    STAT_NAMES = PrimaryStat.get_all_stat_names()

    def __init__(self, character: "ObjectDB") -> None:
        """
        Initialize the stat handler.

        Args:
            character: The character object this handler is bound to
        """
        self.character = character
        self.traits = character.traits

    def get_stat(self, stat_name: str) -> int:
        """
        Get a stat value.

        Args:
            stat_name: Name of the stat (e.g., "strength")

        Returns:
            Stat value (10-50 at character creation)
        """
        return self.traits.get_trait_value(stat_name)

    def set_stat(self, stat_name: str, value: int) -> bool:
        """
        Set stat value with validation.

        Args:
            stat_name: Name of the stat (e.g., "strength")
            value: Value to set (typically 10-50)

        Returns:
            True if successful, False otherwise
        """
        return self.traits.set_trait_value(stat_name, value)

    def get_all_stats(self) -> dict[str, int]:
        """
        Get all 8 primary stats as a dictionary.

        Returns:
            Dict mapping stat names to values
        """
        return {stat: self.get_stat(stat) for stat in self.STAT_NAMES}
