"""#743 — Renown event notifications.

When ``fire_renown_award`` lands on a player-owned persona, fire one
``NarrativeMessage`` of category ``RENOWN`` for the deed itself, plus
(when applicable) a second message for the fame-tier transition. The
spec calls tier transitions out as a separate chat line.

``MessagesSection`` already renders these in the web client; Evennia's
``character.msg()`` pushes the chat line to telnet.

No-op for non-player personas (no roster tenure, no account) — those
deeds happen to NPCs and don't surface to a player inbox.

Body intent: natural-language framing per the #676 spec. Magnitude
maps to a qualitative descriptor ("minor", "moderate", "significant",
"renowned"); raw point deltas stay off the chat line (per the
"hidden mechanics stay tribal" project rule). The expander UX —
clickable per-axis breakdown — is a follow-up that will read the same
``RenownAwardResult`` we already pass around.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.societies.constants import FameTier, RenownMagnitude, RenownRisk

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.renown import RenownAwardResult


# Magnitude → qualitative descriptor (admin-tunable starting point).
_MAGNITUDE_DESCRIPTORS: dict[str, str] = {
    RenownMagnitude.SMALL.value: "minor",
    RenownMagnitude.MODERATE.value: "moderate",
    RenownMagnitude.HIGH.value: "significant",
    RenownMagnitude.VERY_HIGH.value: "renowned",
}

_RISK_DESCRIPTORS: dict[str, str] = {
    RenownRisk.LOW.value: "small",
    RenownRisk.MODERATE.value: "real",
    RenownRisk.HIGH.value: "grave",
    RenownRisk.EXTREME.value: "lethal",
}


def notify_renown_event(
    persona: Persona,
    result: RenownAwardResult,
    *,
    magnitude: str | None = None,
    risk: str | None = None,
    title: str = "Renown deed",
) -> None:
    """Send NarrativeMessage(s) announcing a renown event to the persona's owner.

    No-op when no player owns the persona. Always fires the deed
    message first; fires a separate tier-transition message after when
    ``result.fame_tier_changed`` (spec: distinct chat lines).
    """
    sheet = persona.character_sheet
    if sheet is None or not _has_active_player(sheet):
        return
    send_narrative_message(
        recipients=[sheet],
        body=_build_deed_body(magnitude=magnitude, risk=risk, title=title),
        category=NarrativeCategory.RENOWN.value,
    )
    if result.fame_tier_changed:
        send_narrative_message(
            recipients=[sheet],
            body=_build_tier_transition_body(persona),
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
    except ObjectDoesNotExist:
        return False
    return roster_entry.tenures.filter(end_date__isnull=True).exists()


def _build_deed_body(
    *,
    magnitude: str | None,
    risk: str | None,
    title: str,
) -> str:
    """Spec-style chat line for the deed itself.

    Format: ``"✦ {title} earns {magnitude_word} renown. (details)"``,
    with a risk clause appended when risk is non-NONE.

    When neither magnitude nor risk fires (admin-fired bare event), the
    body falls back to a minimal recognition line.
    """
    mag_word = _MAGNITUDE_DESCRIPTORS.get(magnitude) if magnitude else None
    risk_word = _RISK_DESCRIPTORS.get(risk) if risk else None

    if mag_word is None and risk_word is None:
        return f"✦ {title} is quietly recognised. (details)"

    parts = [f"✦ {title}"]
    if mag_word:
        parts.append(f"earns {mag_word} renown")
        if risk_word:
            parts.append(f"at {risk_word} risk")
    elif risk_word:
        # Risk-only event: legend without fame/prestige.
        parts.append(f"survives {risk_word} risk")
    return " ".join(parts) + ". (details)"


def _build_tier_transition_body(persona: Persona) -> str:
    """Standalone chat line for fame-tier transitions.

    Spec example: ``"✦ You've become a Household Name."`` — the player
    sees the new tier named explicitly.
    """
    tier_label = FameTier(persona.fame_tier).label
    return f"✦ You've become {_tier_with_article(tier_label)}."


def _tier_with_article(tier_label: str) -> str:
    """Add the right indefinite article to the tier label."""
    if not tier_label:
        return tier_label
    return (
        f"an {tier_label}"
        if tier_label[0].lower() in "aeiou"  # noqa: STRING_LITERAL — vowel set, not an identifier
        else f"a {tier_label}"
    )
