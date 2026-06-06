"""#743 — Renown event notifications.

When ``fire_renown_award`` lands on a player-owned persona, fire a
``NarrativeMessage`` of category ``RENOWN`` to the owning character's
sheet. ``MessagesSection`` already renders these in the web client +
Evennia's ``character.msg()`` pushes the chat line to telnet.

No-op for non-player personas (no roster tenure, no account) — those
deeds happen to NPCs and don't surface to a player inbox.

The notification body matches the spec's "Brief chat-line" intent.
Expander UX (clickable details panel) is a follow-up — surfacing the
plain chat line is the minimum required for the player to know an
award fired. The full ``RenownAwardResult`` is passed in so a future
expander can attach the per-axis deltas without changing this API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.renown import RenownAwardResult


def notify_renown_event(
    persona: Persona,
    result: RenownAwardResult,
    *,
    title: str,
) -> None:
    """Send a NarrativeMessage announcing a renown event to the persona's owner.

    No-op when no player owns the persona (no active tenure on the
    character sheet, or the sheet has no character). The fame-tier
    transition is surfaced as a separate sentence in the body when it
    fires — the spec calls those out specifically.
    """
    sheet = persona.character_sheet
    if sheet is None or not _has_active_player(sheet):
        return
    body = _build_body(result, title=title)
    send_narrative_message(
        recipients=[sheet],
        body=body,
        category=NarrativeCategory.RENOWN.value,
    )


def _has_active_player(sheet) -> bool:
    """True iff the sheet has at least one active roster tenure.

    Roster tenures expire on character return; ``end_date IS NULL``
    means the character is currently held by a player account. NPCs +
    abandoned characters return False.
    """
    try:
        roster_entry = sheet.roster_entry
    except Exception:  # noqa: BLE001 — RosterEntry.DoesNotExist plus DescriptorAttribute misses.
        return False
    return roster_entry.tenures.filter(end_date__isnull=True).exists()


def _build_body(result: RenownAwardResult, *, title: str) -> str:
    """Build the chat-line body. Plain text; categorisation does the colouring.

    Format: one line for the deed, plus an optional second line for a
    fame-tier transition. ``title`` is the deed's display name (e.g.
    "Mission deed: Save the village" or admin-provided text).
    """
    parts = [f"✦ {title} ({_summarise_deltas(result)})."]
    if result.fame_tier_changed:
        # Spec calls the tier transition out as a separate chat line.
        # Bundling here keeps both in one Notification; the FE can show
        # the second sentence with emphasis once the expander lands.
        parts.append("Your reputation has shifted to a new tier.")
    return " ".join(parts)


def _summarise_deltas(result: RenownAwardResult) -> str:
    """One-line summary of what moved. Skips zero-delta axes."""
    bits = []
    if result.fame_awarded:
        bits.append(f"+{result.fame_awarded} fame")
    if result.prestige_awarded:
        bits.append(f"+{result.prestige_awarded} prestige")
    if result.legend_awarded:
        bits.append(f"+{result.legend_awarded} legend")
    return ", ".join(bits) if bits else "minor renown"
