"""Block resolution + lifecycle (#1278, slice 1).

The coded enforcement primitive the rest of the system will call: "is there an active block
between these two (player, persona) sides?" Block is mutual — it hides each side from the other —
and keyed on PlayerData (account), so it follows the *person* across re-rosters.

Slice 1 added resolution + lifecycle; slice 2 wired the **profile gate**
(``sheet_blocked_for_viewer``); slice 3 wired the **scene target picker**
(``actions.player_interface._block_excluded_persona_ids``); slice 4 wired **feed visibility**
(``hidden_persona_ids_for_viewer`` → the interaction feed excludes the blocked party's content).
The Mute sibling, the awareness/flag + generic "Character Has You Blocked" surface, and the cron
job remain follow-up slices.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from world.scenes.models import Block

if TYPE_CHECKING:
    from datetime import datetime

    from evennia_extensions.models import PlayerData
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import BlockContactFlag, Persona


def _active_blocks() -> QuerySet[Block]:
    """Blocks not past their lift grace window (#1278)."""
    return Block.objects.filter(
        Q(pending_removal_at__isnull=True) | Q(pending_removal_at__gt=timezone.now())
    )


def coded_block_active(
    *,
    player_a: PlayerData,
    persona_a: Persona | None,
    player_b: PlayerData,
    persona_b: Persona | None,
) -> bool:
    """True if an active coded block sits between these two (player, persona) sides (#1278).

    Symmetric: a block hides each side from the other, so the order of the arguments does not
    matter. A block matches when the **exact blocked persona** is involved (the default
    persona→persona case) or, for an ``account_level`` block, when any of the blocker's faces
    meets the blocked persona. Keyed on PlayerData, so a character now played by a *different*
    person does not match (the block follows the original player).

    This is the coded-enforcement check only. The blocked player's *other* identities are handled
    by the separate awareness/flag layer (a later slice) — never here, to preserve the
    anti-derivation invariant.
    """
    candidates = _active_blocks().filter(
        Q(owner=player_a, blocked_player=player_b) | Q(owner=player_b, blocked_player=player_a)
    )

    for block in candidates:
        # Orient the provided sides against this row: which one is the blocked player?
        if block.blocked_player_id == player_b.pk:
            blocked_face, blocker_face = persona_b, persona_a
        else:
            blocked_face, blocker_face = persona_a, persona_b

        # When the row names an exact blocked face, that face must be the one involved.
        if block.blocked_persona_id is not None and (
            blocked_face is None or blocked_face.pk != block.blocked_persona_id
        ):
            continue
        # The blocker's face must match too — unless the block covers all their characters.
        if (
            not block.account_level
            and block.blocker_persona_id is not None
            and (blocker_face is None or blocker_face.pk != block.blocker_persona_id)
        ):
            continue
        return True
    return False


def lift_block(block: Block, *, finalize_at: datetime) -> Block:
    """Begin lifting a block — it stays active until ``finalize_at`` (the next cron tick) (#1278).

    Deliberately delayed: an immediately-cleared block lets someone lift it, get a last word in,
    and re-block. ``finalize_expired_blocks`` removes it once the grace period elapses. Pass the
    timestamp in (the runtime forbids ``timezone.now()`` defaults in importable module code paths
    that must stay deterministic — callers compute the cron tick).
    """
    block.pending_removal_at = finalize_at
    block.save(update_fields=["pending_removal_at"])
    return block


def finalize_expired_blocks(*, now: datetime) -> int:
    """Delete blocks whose lift grace period has elapsed (cron entry point) (#1278).

    Returns the number removed. ``now`` is passed in so the caller (the cron job) controls the
    clock.
    """
    expired = Block.objects.filter(pending_removal_at__isnull=False, pending_removal_at__lte=now)
    count = expired.count()
    expired.delete()
    return count


def sheet_blocked_for_viewer(*, viewer_account: Any, sheet: CharacterSheet) -> bool:
    """True if an active block hides this character's *sheet* from this viewer (#1278).

    The no-persona-pair surface (viewing a profile / OOC sheet): the viewer isn't presenting a
    face toward the sheet, so resolution is keyed on the *sheet's* personas rather than a pair.
    Both modes Apostate ratified are applied here:

    - **Persona-scoped (either direction):** the sheet hosts the exact blocked face (the viewer
      blocked this character) or the exact blocker face (this character blocked the viewer). Only
      *this* sheet is hidden — never the player's other characters — so the block cannot be used
      to derive their alts (the anti-derivation invariant).
    - **Account-level:** this sheet's current player has an ``account_level`` block against the
      viewer, so *all* of their characters are hidden — the blocker's conscious choice to expose
      that those characters share a player.

    One indexed ``exists()`` query (the sheet's current player is read from the prefetched tenure).
    Staff bypass blocks (handled by the caller). Returns False for an anonymous viewer.
    """
    if viewer_account is None or not getattr(viewer_account, "is_authenticated", False):  # noqa: GETATTR_LITERAL
        return False

    # Persona-scoped, either direction — keyed on the viewer's account and only this sheet's faces.
    conditions = Q(owner__account=viewer_account, blocked_persona__character_sheet_id=sheet.pk) | Q(
        blocked_player__account=viewer_account, blocker_persona__character_sheet_id=sheet.pk
    )

    # Account-level block by this sheet's current player (read from the prefetched tenure).
    roster_entry = sheet.roster_entry
    current = roster_entry.current_tenure if roster_entry is not None else None
    if current is not None:
        conditions |= Q(
            owner=current.player_data,
            blocked_player__account=viewer_account,
            account_level=True,
        )

    return _active_blocks().filter(conditions).exists()


def member_blocked_viewer(*, viewer_account: Any, member_sheet: CharacterSheet) -> bool:
    """True if the member's player has an active block against the viewer (#2086).

    The one-directional check for membership-list display: "this member blocked you."
    Unlike ``sheet_blocked_for_viewer`` (which is symmetric — either direction hides
    the sheet), this checks only the *member blocked the viewer* direction, because
    the placeholder should only appear for the blocked player, not for the blocker
    (who already knows the persona they blocked).

    Staff bypass: returns False for staff (they see real names everywhere).
    """
    if viewer_account is None or not getattr(viewer_account, "is_authenticated", False):  # noqa: GETATTR_LITERAL
        return False
    if getattr(viewer_account, "is_staff", False):  # noqa: GETATTR_LITERAL
        return False

    roster_entry = member_sheet.roster_entry
    current = roster_entry.current_tenure if roster_entry is not None else None
    if current is None:
        return False
    member_player = current.player_data

    # The member's player blocked the viewer's account — persona-scoped (the
    # member's face is the blocker) or account-level (all their faces block).
    return (
        _active_blocks()
        .filter(Q(owner=member_player, blocked_player__account=viewer_account))
        .exists()
    )


def hidden_persona_ids_for_viewer(*, viewer_account: Any) -> set[int]:
    """Persona ids whose content is hidden from this viewer by an active block (#1278).

    For the scene feed / presence (no persona pair): a blocked viewer sees nothing the blocked
    party says or does. Persona-scoped blocks hide the exact blocked/blocker face; an
    ``account_level`` block hides *all* of the blocker's currently-played faces. Mutual.

    At most two queries — the viewer's active blocks, plus (only when an account-level block is
    present) the owners' current personas. Empty for an anonymous viewer; staff bypass is the
    caller's concern.
    """
    if viewer_account is None or not getattr(viewer_account, "is_authenticated", False):  # noqa: GETATTR_LITERAL
        return set()

    blocks = list(
        _active_blocks().filter(
            Q(owner__account=viewer_account) | Q(blocked_player__account=viewer_account)
        )
    )
    if not blocks:
        return set()

    hidden: set[int] = set()
    account_level_owner_ids: set[int] = set()
    # PlayerData's pk is its account_id, so owner_id/blocked_player_id == the account pk.
    viewer_pk = viewer_account.pk
    for block in blocks:
        if block.owner_id == viewer_pk:
            # Viewer is the blocker → hide the exact face they blocked.
            if block.blocked_persona_id is not None:
                hidden.add(block.blocked_persona_id)
        elif block.account_level:
            account_level_owner_ids.add(block.owner_id)
        elif block.blocker_persona_id is not None:
            hidden.add(block.blocker_persona_id)

    if account_level_owner_ids:
        from world.scenes.models import Persona  # noqa: PLC0415

        hidden.update(
            Persona.objects.filter(
                character_sheet__roster_entry__tenures__player_data_id__in=account_level_owner_ids,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
            ).values_list("pk", flat=True)
        )
    return hidden


def _sheet_player(sheet: CharacterSheet) -> PlayerData | None:
    """The PlayerData currently playing this character sheet, or None (#1278)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        roster_entry = sheet.roster_entry
    except ObjectDoesNotExist:
        return None
    if roster_entry is None:
        return None
    current = roster_entry.current_tenure
    return current.player_data if current is not None else None


def _persona_player(persona: Persona) -> PlayerData | None:
    """The PlayerData currently playing this persona's character, or None (#1278)."""
    return _sheet_player(persona.character_sheet)


def org_join_blocked(*, joining_sheet: CharacterSheet, member_sheets: Any) -> bool:
    """True if an active block sits between the joining player and any member's player (#1278).

    The org/covenant gate: you can't join an org that holds a member who has blocked you (or whom
    you've blocked). Player-level — the block applies regardless of which face, since joining an org
    is an account-relevant, deliberate act; the joiner is told only generically (no name), so no
    identity is derivable. One query.
    """
    joining_player = _sheet_player(joining_sheet)
    if joining_player is None:
        return False
    member_player_ids = {
        player.pk for sheet in member_sheets if (player := _sheet_player(sheet)) is not None
    }
    member_player_ids.discard(joining_player.pk)
    if not member_player_ids:
        return False
    return (
        _active_blocks()
        .filter(
            (Q(owner=joining_player) & Q(blocked_player_id__in=member_player_ids))
            | (Q(blocked_player=joining_player) & Q(owner_id__in=member_player_ids))
        )
        .exists()
    )


def create_block(
    *,
    blocker_account: Any,
    blocker_persona: Persona,
    blocked_persona: Persona,
    reason: str,
) -> Block:
    """Block ``blocked_persona`` for the requesting account, persona→persona (#1278).

    ``reason`` is required (it's forwarded to staff). Idempotent per
    (owner, blocked_player, blocker_persona, blocked_persona) — re-blocking the same pair returns
    the existing row. Raises ValidationError if the target persona has no current player.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415

    blocker_player, _ = PlayerData.objects.get_or_create(account=blocker_account)
    blocked_player = _persona_player(blocked_persona)
    if blocked_player is None:
        msg = "That character has no current player to block."
        raise ValidationError(msg)
    if blocked_player.pk == blocker_player.pk:
        msg = "You cannot block your own character."
        raise ValidationError(msg)

    block, created = Block.objects.get_or_create(
        owner=blocker_player,
        blocked_player=blocked_player,
        blocker_persona=blocker_persona,
        blocked_persona=blocked_persona,
        defaults={"reason": reason, "account_level": False, "pending_removal_at": None},
    )
    # ``defaults`` only apply on INSERT (the django_get_or_create gotcha). On a re-block (the row
    # already exists — the real path being a re-block within the unblock grace window) refresh the
    # staff-facing ``reason`` to the latest one rather than silently keeping the stale one (#1326).
    # (``account_level`` staleness on re-block is a deliberate player-intent question — left as-is.)
    update_fields: list[str] = []
    if not created and block.reason != reason:
        block.reason = reason
        update_fields.append("reason")
    # Re-blocking a pair mid-grace cancels the pending removal (it's active again).
    if block.pending_removal_at is not None:
        block.pending_removal_at = None
        update_fields.append("pending_removal_at")
    if update_fields:
        block.save(update_fields=update_fields)
    return block


# How long a lifted block stays active before the cron clears it — matches the hourly
# scenes.block_finalize task, so an unblock takes effect within one cron cycle (#1278).
_UNBLOCK_GRACE = timedelta(hours=1)


def request_unblock(block: Block) -> Block:
    """Begin unblocking — the block stays active until the next cron clears it (#1278).

    Deliberately delayed (lift → snipe → re-block guard); ``scenes.block_finalize`` removes it.
    """
    return lift_block(block, finalize_at=timezone.now() + _UNBLOCK_GRACE)


def share_block_account_wide(block: Block) -> Block:
    """Escalate a block so ALL the blocker's characters block the target (#1278).

    The conscious opt-in: the target may now infer those characters share a player. Persona-scoped
    on the target side is preserved (only the exact blocked face), per the anti-derivation rule.
    """
    if not block.account_level:
        block.account_level = True
        block.save(update_fields=["account_level"])
    return block


def flag_blocked_contact_attempt(
    *,
    initiator_persona: Persona,
    target_persona: Persona,
    scene: Any = None,
) -> BlockContactFlag | None:
    """Record a blocked player's attempt to contact the blocker, for staff (#1278).

    Fires when an active block exists where the *target* blocked the *initiator* — i.e. a blocked
    player is reaching the blocker (typically via a non-blocked identity, since the coded block
    already stops the exact pair). The anti-derivation rule means we do NOT code-prevent this
    (that would leak the alt); instead staff — who see real identities — get the flag, with zero
    signal to either player. Deduped per (blocked, blocker, scene). Returns the flag, or None when
    there is no such block.
    """
    initiator_player = _persona_player(initiator_persona)
    target_player = _persona_player(target_persona)
    if initiator_player is None or target_player is None:
        return None
    if not _active_blocks().filter(owner=target_player, blocked_player=initiator_player).exists():
        return None

    from world.scenes.models import BlockContactFlag  # noqa: PLC0415

    # PlayerData's pk is its account_id, so player.pk == the account FK target.
    flag, _ = BlockContactFlag.objects.get_or_create(
        blocker_account_id=target_player.pk,
        blocked_account_id=initiator_player.pk,
        scene=scene,
        defaults={"initiator_persona": initiator_persona, "target_persona": target_persona},
    )
    return flag
