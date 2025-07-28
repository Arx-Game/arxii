"""
Selector functions for roster system queries.

Selectors are pure functions that return querysets based on business logic.
They encapsulate complex filtering and permission logic for roster data.
"""

from typing import TYPE_CHECKING, Dict

from django.db.models import Count, QuerySet

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerData
    from world.roster.models import Roster

from world.roster.models import RosterEntry, RosterType


def get_visible_roster_entries_for_player(
    player_data: "PlayerData", roster_queryset: QuerySet = None
) -> QuerySet["RosterEntry"]:
    """
    Get roster entries that are visible to the given player.

    Filters out characters the player cannot apply for due to:
    - Trust level requirements
    - Roster permissions
    - Special restrictions
    - Availability issues

    Args:
        player_data: PlayerData instance for the requesting player
        roster_queryset: Optional queryset to filter (defaults to all roster entries)

    Returns:
        QuerySet of RosterEntry objects the player can see
    """
    if roster_queryset is None:
        roster_queryset = RosterEntry.objects.all()

    # Start with basic filtering
    queryset = roster_queryset.select_related("roster", "character")

    # Apply trust-based filters
    queryset = _apply_trust_based_filters(queryset, player_data)

    # Apply roster-specific filters
    queryset = _apply_roster_filters(queryset, player_data)

    # Apply availability filters
    queryset = _apply_availability_filters(queryset, player_data)

    return queryset


def get_roster_counts_for_player(player_data: "PlayerData") -> Dict[str, int]:
    """
    Get count of available characters by roster type for display.

    Args:
        player_data: PlayerData instance for the requesting player

    Returns:
        Dict mapping roster names to available character counts
    """
    visible_entries = get_visible_roster_entries_for_player(player_data)

    counts = (
        visible_entries.values("roster__name")
        .annotate(count=Count("id"))
        .order_by("roster__name")
    )

    return {item["roster__name"]: item["count"] for item in counts}


def get_available_rosters_for_player(player_data: "PlayerData") -> QuerySet["Roster"]:
    """
    Get rosters that have characters available for the given player.

    Args:
        player_data: PlayerData instance for the requesting player

    Returns:
        QuerySet of Roster objects with available characters
    """
    from world.roster.models import Roster

    # Get rosters that have visible entries for this player
    visible_entry_roster_ids = get_visible_roster_entries_for_player(
        player_data
    ).values_list("roster_id", flat=True)

    return Roster.objects.filter(id__in=visible_entry_roster_ids).distinct()


def _apply_trust_based_filters(
    queryset: QuerySet, player_data: "PlayerData"
) -> QuerySet:
    """Apply trust level and permission-based filters."""

    # For now, implement basic logic. This will be expanded when trust system is built
    restricted_rosters = []

    # Restricted characters require staff approval - hide from general players
    if not _player_can_access_restricted_characters(player_data):
        restricted_rosters.append(RosterType.RESTRICTED)

    # Filter out rosters player can't access
    if restricted_rosters:
        queryset = queryset.exclude_roster_types(restricted_rosters)

    return queryset


def _apply_roster_filters(queryset: QuerySet, player_data: "PlayerData") -> QuerySet:
    """Apply roster-specific visibility rules."""

    # Only show active rosters unless player is staff
    if not player_data.account.is_staff:
        queryset = queryset.active_rosters()

    # Exclude frozen characters
    queryset = queryset.exclude_frozen()

    return queryset


def _apply_availability_filters(
    queryset: QuerySet, player_data: "PlayerData"
) -> QuerySet:
    """Filter based on character availability."""

    # Only show characters without current players
    queryset = queryset.available_characters()

    # Exclude characters player already has access to or pending applications for
    queryset = queryset.exclude_characters_for_player(player_data)

    return queryset


def _player_can_access_restricted_characters(player_data: "PlayerData") -> bool:
    """
    Check if player can access restricted characters.

    This is where complex trust evaluation will live.
    For now, just check staff status.
    """
    # TODO: Implement proper trust evaluation system
    # This will include:
    # - Player trust ratings for IC conflict handling
    # - Story involvement restrictions
    # - Character-specific requirements
    # - GM approval scopes

    return player_data.account.is_staff


class TrustEvaluator:
    """
    Evaluates player trust levels for character applications.
    This will be expanded significantly when the trust system is implemented.
    """

    @classmethod
    def evaluate_player_for_character(
        cls, player_data: "PlayerData", character
    ) -> Dict:
        """
        Evaluate if a player has the trust level needed for a character.

        Returns:
            dict: {
                'eligible': bool,
                'trust_level': str,
                'requirements': list,
                'warnings': list,
                'auto_approvable': bool
            }
        """
        # TODO: Implement comprehensive trust evaluation
        # This will consider:
        # - Player history with IC conflict
        # - Ability to make conflicts fun for others
        # - Past character performance
        # - Story involvement track record
        # - GM feedback and ratings

        # Placeholder implementation
        roster_entry = getattr(character, "roster_entry", None)
        if not roster_entry:
            return {
                "eligible": False,
                "trust_level": "none",
                "requirements": ["Character not on roster"],
                "warnings": [],
                "auto_approvable": False,
            }

        is_restricted = roster_entry.roster.name == RosterType.RESTRICTED
        is_staff = player_data.account.is_staff

        return {
            "eligible": not is_restricted or is_staff,
            "trust_level": "staff" if is_staff else "basic",
            "requirements": (
                ["Staff approval required"] if is_restricted and not is_staff else []
            ),
            "warnings": (
                ["Character requires careful IC conflict handling"]
                if is_restricted
                else []
            ),
            "auto_approvable": not is_restricted,
        }
