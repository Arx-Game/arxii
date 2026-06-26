"""Toggle services for interaction favorites + emoji reactions (#1341).

The sole mutators extracted from the inline ``InteractionFavoriteViewSet`` /
``InteractionReactionViewSet`` so web (viewsets) and telnet (Actions) converge
on one path. Both are idempotent toggles: delete if present, else create.
Mirrors how ``react_to_window`` is the sole mutator for reaction windows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.roster.models import RosterEntry
    from world.scenes.models import Interaction, InteractionFavorite, InteractionReaction


def toggle_interaction_favorite(
    *,
    interaction: Interaction,
    roster_entry: RosterEntry,
) -> tuple[bool, InteractionFavorite | None]:
    """Toggle a private bookmark for ``roster_entry`` on ``interaction``.

    Returns ``(created, favorite)``. ``created=False`` means an existing
    favorite was removed (``favorite`` is then ``None``).
    """
    from world.scenes.models import InteractionFavorite  # noqa: PLC0415

    deleted, _ = InteractionFavorite.objects.filter(
        interaction=interaction,
        roster_entry=roster_entry,
    ).delete()
    if deleted:
        return False, None
    favorite = InteractionFavorite.objects.create(
        interaction=interaction,
        timestamp=interaction.timestamp,
        roster_entry=roster_entry,
    )
    return True, favorite


def toggle_interaction_reaction(
    *,
    interaction: Interaction,
    account: AccountDB,
    emoji: str,
) -> tuple[bool, InteractionReaction | None]:
    """Toggle an emoji ``reaction`` by ``account`` on ``interaction``.

    Returns ``(created, reaction)``. ``created=False`` means an existing
    reaction was removed.
    """
    from world.scenes.models import InteractionReaction  # noqa: PLC0415

    deleted, _ = InteractionReaction.objects.filter(
        interaction=interaction,
        account=account,
        emoji=emoji,
    ).delete()
    if deleted:
        return False, None
    reaction = InteractionReaction.objects.create(
        interaction=interaction,
        timestamp=interaction.timestamp,
        account=account,
        emoji=emoji,
    )
    return True, reaction
