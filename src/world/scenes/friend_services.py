"""Service functions for the OOC friends list (#1727).

A trusted-RP-partner list (Block's positive twin), entirely separate from the IC relationship
tracker. Friendships are **per tenure on both sides** — re-roster-safe and alt-private. Consumed by
the login/logoff watch alerts and the ``FRIENDS_WHITELIST`` consent mode (#1698).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.scenes.models import Friendship, Rivalry

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import PlayerData
    from world.roster.models import RosterTenure

# Neutral and constant on purpose (#2996 Decision 2, mirrors journals.types.JournalError
# .UNAVAILABLE) — a rejection here can't leak that a block is involved: "not available to
# friend right now" has many innocent causes (no active tenure, moderation, ...). Never says
# "blocked."
_FRIEND_UNAVAILABLE = "That character is not available to add as a friend right now."


def _raise_if_account_blocked(
    *, friender_tenure: RosterTenure, friend_tenure: RosterTenure
) -> None:
    """Reject the add with a neutral failure when an account-level Block sits between them (#2996).

    Fail-open when either side has no ``player_data`` (can't prove a block, so don't manufacture
    one) — mirrors every other #2996 seam's policy.
    """
    from world.scenes.block_services import account_block_active  # noqa: PLC0415

    friender_player = friender_tenure.player_data
    friend_player = friend_tenure.player_data
    if friender_player is None or friend_player is None:
        return
    if account_block_active(player_a=friender_player, player_b=friend_player):
        raise ValidationError(_FRIEND_UNAVAILABLE)


def add_friend(*, friender_tenure: RosterTenure, friend_tenure: RosterTenure) -> Friendship:
    """Mark ``friend_tenure`` as a friend of ``friender_tenure`` (idempotent).

    Rejects with a shared neutral failure when an account-level Block sits between the two
    players, either direction (#2996 Decision 2) — checked before the write, so no ``Friendship``
    row is ever created for a blocked pair.
    """
    _raise_if_account_blocked(friender_tenure=friender_tenure, friend_tenure=friend_tenure)
    friendship, _ = Friendship.objects.get_or_create(
        friender_tenure=friender_tenure, friend_tenure=friend_tenure
    )
    return friendship


def add_friend_all_characters(*, player_data: PlayerData, friend_tenure: RosterTenure) -> int:
    """Fan out a friend designation across **all the player's current characters** (#1727).

    The opt-in "friend from all my characters" — one ``Friendship`` row per active tenure the player
    holds (idempotent), each independently removable. Returns the number of the player's tenures.

    Loops through ``add_friend`` per tenure (#2996) rather than writing ``Friendship`` rows
    directly — the fan-out gets the same account-block gate as the single-add path for free,
    with no separate check to keep in sync. The block test is player-level (not tenure-level),
    so it resolves identically for every one of the player's tenures — a blocked pair fails on
    the very first tenure, before any row is written.
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    tenures = list(
        RosterTenure.objects.filter(player_data=player_data, end_date__isnull=True).exclude(
            pk=friend_tenure.pk
        )
    )
    for tenure in tenures:
        add_friend(friender_tenure=tenure, friend_tenure=friend_tenure)
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


def is_rival(*, owner_tenure: RosterTenure, rival_tenure: RosterTenure) -> bool:
    """Is there a **mutual** rivalry between the two tenures? — the #2170 RIVALS predicate.

    Double opt-in: both directions must be declared, so RIVALS-mode antagonism only flows
    between characters who have *each* named the other a rival — no one is dragged in one-sidedly.
    """
    return (
        Rivalry.objects.filter(rivaler_tenure=owner_tenure, rival_tenure=rival_tenure).exists()
        and Rivalry.objects.filter(rivaler_tenure=rival_tenure, rival_tenure=owner_tenure).exists()
    )


def declare_rival(*, rivaler_tenure: RosterTenure, rival_tenure: RosterTenure) -> Rivalry:
    """Declare ``rival_tenure`` a rival of ``rivaler_tenure`` (one-way, idempotent).

    Only a *mutual* declaration (both sides) satisfies the RIVALS consent gate — this records
    one side's intent.
    """
    rivalry, _ = Rivalry.objects.get_or_create(
        rivaler_tenure=rivaler_tenure, rival_tenure=rival_tenure
    )
    return rivalry


def undeclare_rival(*, rivaler_tenure: RosterTenure, rival_tenure: RosterTenure) -> bool:
    """Withdraw a rival declaration (rivaler → rival). Returns True if a row was removed."""
    deleted, _ = Rivalry.objects.filter(
        rivaler_tenure=rivaler_tenure, rival_tenure=rival_tenure
    ).delete()
    return deleted > 0


def rivaled_tenures_for(rivaler_tenure: RosterTenure) -> QuerySet[RosterTenure]:
    """The tenures this character has declared rivals (their own side — may not be mutual yet)."""
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(rivalries_received__rivaler_tenure=rivaler_tenure)


def friended_tenures_for(friender_tenure: RosterTenure) -> QuerySet[RosterTenure]:
    """The tenures this character has friended — the friender's list + watch-alert source."""
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(friendships_received__friender_tenure=friender_tenure)


def notify_friends_of_status(character: ObjectDB, *, online: bool) -> None:
    """Alert online frienders that this character has come online / gone offline — the watch list.

    A friend watches a specific **character** (its current tenure). On puppet/unpuppet we notify the
    *players* who friended that tenure — OOC, to their account (``msg`` to an offline account is a
    harmless no-op, so offline frienders simply don't see it). Only **active** friender tenures
    count (a friender who re-rostered away no longer watches). Best-effort: a notification failure
    must never break login/logout.
    """
    from evennia.utils.logger import log_trace  # noqa: PLC0415

    from world.roster.models import RosterTenure  # noqa: PLC0415

    try:
        entry = character.sheet_data.roster_entry
        tenure = entry.current_tenure if entry is not None else None
        if tenure is None:
            return
        verb = "has come online" if online else "has gone offline"
        message = f"|w[Friends]|n {character.key} {verb}."
        friender_tenures = (
            RosterTenure.objects.filter(
                friendships_made__friend_tenure=tenure, end_date__isnull=True
            )
            .select_related("player_data__account")
            .distinct()
        )
        seen: set[int] = set()
        for friender in friender_tenures:
            account = friender.player_data.account
            if account is None or account.pk in seen:
                continue
            seen.add(account.pk)
            account.msg(message)
    except Exception:  # noqa: BLE001 — best-effort watch alert; never break the login hook (#1164)
        log_trace(f"friend watch-alert failed for {character}")
