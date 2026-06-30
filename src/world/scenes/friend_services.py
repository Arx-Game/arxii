"""Service functions for the OOC friends list (#1727).

A trusted-RP-partner list (Block's positive twin), entirely separate from the IC relationship
tracker. Friendships are **per tenure on both sides** — re-roster-safe and alt-private. Consumed by
the login/logoff watch alerts and the ``FRIENDS_WHITELIST`` consent mode (#1698).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.models import Friendship

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from evennia_extensions.models import PlayerData
    from world.roster.models import RosterTenure


def add_friend(*, friender_tenure: RosterTenure, friend_tenure: RosterTenure) -> Friendship:
    """Mark ``friend_tenure`` as a friend of ``friender_tenure`` (idempotent)."""
    friendship, _ = Friendship.objects.get_or_create(
        friender_tenure=friender_tenure, friend_tenure=friend_tenure
    )
    return friendship


def add_friend_all_characters(*, player_data: PlayerData, friend_tenure: RosterTenure) -> int:
    """Fan out a friend designation across **all the player's current characters** (#1727).

    The opt-in "friend from all my characters" — one ``Friendship`` row per active tenure the player
    holds (idempotent), each independently removable. Returns the number of the player's tenures.
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    tenures = list(
        RosterTenure.objects.filter(player_data=player_data, end_date__isnull=True).exclude(
            pk=friend_tenure.pk
        )
    )
    for tenure in tenures:
        Friendship.objects.get_or_create(friender_tenure=tenure, friend_tenure=friend_tenure)
    return len(tenures)


def remove_friend(*, friender_tenure: RosterTenure, friend_tenure: RosterTenure) -> None:
    """Drop this friend designation from one character (the friender's others stay)."""
    matches = Friendship.objects.filter(
        friender_tenure=friender_tenure, friend_tenure=friend_tenure
    )
    matches.delete()


def is_friend(*, owner_tenure: RosterTenure, friend_tenure: RosterTenure) -> bool:
    """Has ``owner_tenure`` friended ``friend_tenure``? — the #1698 FRIENDS_WHITELIST predicate."""
    return Friendship.objects.filter(
        friender_tenure=owner_tenure, friend_tenure=friend_tenure
    ).exists()


def friended_tenures_for(friender_tenure: RosterTenure) -> QuerySet[RosterTenure]:
    """The tenures this character has friended — the friender's list + watch-alert source."""
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(friendships_received__friender_tenure=friender_tenure)
