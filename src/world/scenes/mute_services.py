"""Mute resolution + toggle (#1278) — the lighter sibling of Block.

One-way and persona-scoped by default: a mute only changes what the *muter* sees, never bans
interaction or locks the sheet, and the muted player is never aware. The muter picks IC, OOC, or
both. Fully reversible. Slice 1 wires the IC side into the scene feed (muted personas are
skipped); the OOC channel, the "actions still show without text" refinement, and the opt-in
reveal are follow-ups.

**Account-level (#2996):** ``account_muted`` extends the family with the account-first query seam
— "does the viewer hold an account-level mute naming the target player" — mirroring
``block_services.account_block_active``. ``set_mute`` gained the ``account_level`` opt-in, which
snapshots ``Mute.muted_player`` at creation only (never re-derived on a later toggle — the same
contract as ``Block.blocked_player``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from world.scenes.models import Mute

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerData
    from world.scenes.models import Persona


def muted_persona_ids_for_viewer(*, viewer_account: Any) -> set[int]:
    """Persona ids the viewer has IC-muted — skipped from their scene feed (#1278).

    One query. Empty for an anonymous viewer. One-way: only the muter's own view changes.
    """
    if viewer_account is None or not viewer_account.is_authenticated:
        return set()
    return set(
        Mute.objects.filter(owner__account=viewer_account, mute_ic=True).values_list(
            "muted_persona_id", flat=True
        )
    )


def ooc_muted_persona_ids_for_viewer(*, viewer_account: Any) -> set[int]:
    """Persona ids the viewer has OOC-muted — their OOC messages are skipped (#2087).

    One query. Empty for an anonymous viewer. One-way: only the muter's own view changes.
    """
    if viewer_account is None or not viewer_account.is_authenticated:
        return set()
    return set(
        Mute.objects.filter(owner__account=viewer_account, mute_ooc=True).values_list(
            "muted_persona_id", flat=True
        )
    )


def _persona_player(persona: Persona) -> PlayerData | None:
    """The PlayerData currently playing this persona's character, or None (#2996).

    Mirrors ``block_services._persona_player`` — kept local (not imported) so each service module
    stays self-contained; both derive the same "current tenure's player" fact from a persona's
    character sheet.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        roster_entry = persona.character_sheet.roster_entry
    except ObjectDoesNotExist:
        return None
    if roster_entry is None:
        return None
    current = roster_entry.current_tenure
    return current.player_data if current is not None else None


def set_mute(
    *,
    owner: Any,
    muted_persona: Persona,
    ic: bool = True,
    ooc: bool = True,
    account_level: bool = False,
) -> Mute:
    """Mute ``muted_persona`` for ``owner`` (a PlayerData), or update its scope (#1278, #2996).

    ``account_level`` opts into filtering every character ``muted_persona``'s current player
    plays, not just this one face — the mute sibling of ``Block``'s ``account_level``. On first
    creation this snapshots ``muted_player`` (the persona's current player, if any) onto the row;
    a later call that only changes ``ic``/``ooc``/``account_level`` does NOT re-resolve or
    overwrite that snapshot — it stays pinned to whoever was playing the persona when the mute was
    first created, exactly like ``Block.blocked_player`` (the ``django_get_or_create`` gotcha:
    ``defaults`` only apply on INSERT, which is exploited deliberately here).

    ``account_level`` is escalate-only on update: a plain scope toggle (``account_level`` left at
    its False default) never downgrades an existing account-level mute back to persona-scoped —
    mirrors ``share_block_account_wide``'s one-way semantics on the ``Block`` side.
    """
    mute, created = Mute.objects.get_or_create(
        owner=owner,
        muted_persona=muted_persona,
        defaults={
            "mute_ic": ic,
            "mute_ooc": ooc,
            "account_level": account_level,
            "muted_player": _persona_player(muted_persona),
        },
    )
    if not created:
        mute.mute_ic = ic
        mute.mute_ooc = ooc
        # Escalate-only, mirroring Block's share semantics: a plain scope toggle (the common
        # case — no account_level passed, so it defaults False) must never silently downgrade
        # an existing account-level mute back to persona-scoped.
        mute.account_level = mute.account_level or account_level
        mute.save(update_fields=["mute_ic", "mute_ooc", "account_level"])
    return mute


def unmute(*, owner: Any, muted_persona: Persona) -> None:
    """Remove a mute (#1278) — fully reversible, no trace."""
    Mute.objects.filter(owner=owner, muted_persona=muted_persona).delete()


def account_muted(*, viewer_player: PlayerData, target_player: PlayerData) -> bool:
    """True if the viewer holds an active account-level Mute naming the target player (#2996).

    One-way (mirrors every other Mute check) — only ``viewer_player``'s own account-level mutes
    count. Reads the ``muted_player`` snapshot only; never re-derives from ``muted_persona`` at
    query time (the account might now be playing a different face, or none).
    """
    return Mute.objects.filter(
        owner=viewer_player, account_level=True, muted_player=target_player
    ).exists()


def muted_player_ids_for(*, viewer_player: PlayerData) -> set[int]:
    """Account-level Mute target ids for this viewer (#2996).

    The set-shaped sibling of ``account_muted`` — lets a delivery-seam queryset exclude every
    row from a muted target in one filter instead of an ``account_muted`` call per candidate
    row. One-way, same policy as ``account_muted``.
    """
    return set(
        Mute.objects.filter(owner=viewer_player, account_level=True).values_list(
            "muted_player_id", flat=True
        )
    )
