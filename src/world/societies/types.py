"""Type definitions for the societies system."""

from enum import Enum

# Reputation tier thresholds (upper bounds, inclusive)
# Each tier covers: (previous_threshold + 1) to this_threshold
TIER_REVILED_MAX = -750
TIER_DESPISED_MAX = -500
TIER_DISLIKED_MAX = -250
TIER_DISFAVORED_MAX = -100
TIER_UNKNOWN_MAX = 99
TIER_FAVORED_MAX = 249
TIER_LIKED_MAX = 499
TIER_HONORED_MAX = 749
# REVERED is anything above TIER_HONORED_MAX


class ReputationTier(Enum):
    """
    Named reputation tiers shown to players.

    The internal reputation value ranges from -1000 to +1000 but players
    see these descriptive tier names instead of raw numbers.
    """

    REVILED = "reviled"
    DESPISED = "despised"
    DISLIKED = "disliked"
    DISFAVORED = "disfavored"
    UNKNOWN = "unknown"
    FAVORED = "favored"
    LIKED = "liked"
    HONORED = "honored"
    REVERED = "revered"

    @classmethod
    def from_value(cls, value: int) -> "ReputationTier":
        """
        Get the reputation tier for a given numeric value.

        Args:
            value: The reputation value (-1000 to 1000)

        Returns:
            The corresponding ReputationTier enum member
        """
        # Ordered list of (threshold, tier) pairs for cleaner lookup
        tier_thresholds = [
            (TIER_REVILED_MAX, cls.REVILED),
            (TIER_DESPISED_MAX, cls.DESPISED),
            (TIER_DISLIKED_MAX, cls.DISLIKED),
            (TIER_DISFAVORED_MAX, cls.DISFAVORED),
            (TIER_UNKNOWN_MAX, cls.UNKNOWN),
            (TIER_FAVORED_MAX, cls.FAVORED),
            (TIER_LIKED_MAX, cls.LIKED),
            (TIER_HONORED_MAX, cls.HONORED),
        ]

        for threshold, tier in tier_thresholds:
            if value <= threshold:
                return tier

        return cls.REVERED

    @property
    def display_name(self) -> str:
        """Return a human-readable display name for this tier."""
        return self.value.capitalize()

    @property
    def range_description(self) -> str:
        """Return a description of the value range for this tier."""
        ranges = {
            ReputationTier.REVILED: "-1000 to -750",
            ReputationTier.DESPISED: "-749 to -500",
            ReputationTier.DISLIKED: "-499 to -250",
            ReputationTier.DISFAVORED: "-249 to -100",
            ReputationTier.UNKNOWN: "-99 to +99",
            ReputationTier.FAVORED: "+100 to +249",
            ReputationTier.LIKED: "+250 to +499",
            ReputationTier.HONORED: "+500 to +749",
            ReputationTier.REVERED: "+750 to +1000",
        }
        return ranges[self]
