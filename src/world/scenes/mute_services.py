"""Mute resolution + toggle (#1278) — the lighter sibling of Block.

One-way and persona-scoped: a mute only changes what the *muter* sees, never bans interaction or
locks the sheet, and the muted player is never aware. The muter picks IC, OOC, or both. Fully
reversible. Slice 1 wires the IC side into the scene feed (muted personas are skipped); the OOC
channel, the "actions still show without text" refinement, and the opt-in reveal are follow-ups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from world.scenes.models import Mute

if TYPE_CHECKING:
    from world.scenes.models import Persona


def muted_persona_ids_for_viewer(*, viewer_account: Any) -> set[int]:
    """Persona ids the viewer has IC-muted — skipped from their scene feed (#1278).

    One query. Empty for an anonymous viewer. One-way: only the muter's own view changes.
    """
    if viewer_account is None or not getattr(viewer_account, "is_authenticated", False):  # noqa: GETATTR_LITERAL
        return set()
    return set(
        Mute.objects.filter(owner__account=viewer_account, mute_ic=True).values_list(
            "muted_persona_id", flat=True
        )
    )


def set_mute(*, owner: Any, muted_persona: Persona, ic: bool = True, ooc: bool = True) -> Mute:
    """Mute ``muted_persona`` for ``owner`` (a PlayerData), or update its IC/OOC scope (#1278)."""
    mute, _ = Mute.objects.update_or_create(
        owner=owner,
        muted_persona=muted_persona,
        defaults={"mute_ic": ic, "mute_ooc": ooc},
    )
    return mute


def unmute(*, owner: Any, muted_persona: Persona) -> None:
    """Remove a mute (#1278) — fully reversible, no trace."""
    Mute.objects.filter(owner=owner, muted_persona=muted_persona).delete()
