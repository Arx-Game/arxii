"""A character's own secrets as its sheet shows them to its player (#5206).

Owner ruling (2026-11-26): a sheet shows its own player everything but GM and staff notes,
so the player always reads the secrets about their character that the character knows
(``secrets_owned_by``: the subject-aware ones, and any a held record has since granted),
however many other players never do. ``own_secret_entry`` is the one shape of such a row,
used by the in-game sheet (``own_secret_entries``) and by the character-creation waiting
sheet, which lists the secrets approval will write in the same order
(``own_shelf_order``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.serializers import UNKNOWN, secret_anchors

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.character_sheets.types import OwnSecretEntry

#: Who a secret no persona wrote reads as written by, the Secrets tab's own words.
NO_AUTHOR = "GM/Staff"


def own_secret_entry(  # noqa: PLR0913 - one row's every field, keyword-only
    *,
    secret_id: int,
    level: int,
    content: str,
    provenance: str,
    subject: str,
    author: str = "",
    category: str = "",
    consequences: str = "",
    anchored_to: Sequence[dict[str, str]] = (),
) -> OwnSecretEntry:
    """One own secret in the Secrets tab's shape, read in full by its subject. A blank
    category or consequences reads "Unknown", as the tab shows an unplaced layer."""
    from world.character_sheets.types import OwnSecretEntry  # noqa: PLC0415

    return OwnSecretEntry(
        id=secret_id,
        level=SecretLevel(level).label,
        content=content,
        provenance=SecretProvenance(provenance).label,
        found_at=None,
        can_grieve=False,
        subject=subject,
        category=category or UNKNOWN,
        consequences=consequences or UNKNOWN,
        author=author or NO_AUTHOR,
        anchored_to=list(anchored_to),
    )


def own_shelf_order(rows: Iterable[tuple[int, OwnSecretEntry]]) -> list[OwnSecretEntry]:
    """``(level, entry)`` pairs given in the order the secrets were made, put in the own
    shelf's order: most dangerous first, then newest first (``secrets_owned_by``'s
    "level" sort)."""
    indexed = [(level, position, entry) for position, (level, entry) in enumerate(rows)]
    indexed.sort(key=lambda row: (-row[0], -row[1]))
    return [entry for _, _, entry in indexed]


def own_secret_entries(sheet: CharacterSheet) -> list[OwnSecretEntry]:
    """The sheet's own secrets for its player, most dangerous first, then newest. One query
    (``secrets_owned_by``) with the category, author and anchors joined."""
    from world.secrets.services import secrets_owned_by  # noqa: PLC0415

    subject = sheet.character.db_key
    return [
        own_secret_entry(
            secret_id=secret.pk,
            level=secret.level,
            content=secret.content,
            provenance=secret.provenance,
            subject=subject,
            author=secret.author_persona.name if secret.author_persona_id else "",
            category=secret.category.name if secret.category_id else "",
            consequences=secret.consequences,
            anchored_to=secret_anchors(secret),
        )
        for secret in secrets_owned_by(sheet)
    ]
