"""Service functions for authoring Character Secrets (#1334).

Slice 1 covers authoring (the content surface). The held/partial-knowledge record, the
clue-target discovery wiring, evidence-as-sharing, and the action-anchored minting (blackmail/
murder/affair/crime → Secret + Evidence) are later slices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.models import Secret

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona
    from world.secrets.models import SecretCategory


class SecretError(Exception):
    """A secret could not be authored as requested (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def author_secret(  # noqa: PLR0913 — keyword-only; each arg is a distinct secret field
    *,
    subject_sheet: CharacterSheet,
    provenance: str,
    level: int = SecretLevel.UNCOMMON_KNOWLEDGE,
    content: str = "",
    category: SecretCategory | None = None,
    consequences: str = "",
    author_persona: Persona | None = None,
    second_party_sheet: CharacterSheet | None = None,
) -> Secret:
    """Author a secret about ``subject_sheet``, enforcing the anchor-scales-with-level rule.

    Raises ``SecretError`` if the request violates the invariant (e.g. a player-flavor secret
    above Level 1). The model's ``clean`` is the single source of truth for that rule; this
    surface just translates its ``ValidationError`` into a typed, user-facing error.
    """
    secret = Secret(
        subject_sheet=subject_sheet,
        provenance=provenance,
        level=level,
        content=content,
        category=category,
        consequences=consequences,
        author_persona=author_persona,
        second_party_sheet=second_party_sheet,
    )
    try:
        secret.full_clean()
    except ValidationError as exc:
        msg = "; ".join(exc.messages)
        raise SecretError(msg, user_message=msg) from exc
    secret.save()
    return secret


def author_player_flavor_secret(
    *,
    subject_sheet: CharacterSheet,
    author_persona: Persona,
    content: str,
    category: SecretCategory | None = None,
) -> Secret:
    """Author a Level-1 player-flavor secret (the only tier a player may free-write).

    Capped at Level 1 by construction — flavor has no mechanical effect, so its truth is moot
    and it can never be mistaken for canon (the OOC author attribution rides on
    ``author_persona``).
    """
    return author_secret(
        subject_sheet=subject_sheet,
        provenance=SecretProvenance.PLAYER_FLAVOR,
        level=SecretLevel.UNCOMMON_KNOWLEDGE,
        content=content,
        category=category,
        author_persona=author_persona,
    )
