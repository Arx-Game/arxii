"""
Shared mixins for API views.

These mixins provide common functionality needed across multiple API endpoints
without creating import dependencies on domain-specific modules like typeclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB
from rest_framework.request import Request

if TYPE_CHECKING:
    from typeclasses.characters import Character


class CharacterContextMixin:
    """
    Mixin providing header-based character context for web-first API views.

    Web clients send X-Character-ID header to specify which character they're
    playing. This mixin validates ownership via the roster system.

    Usage in frontend:
        - On login/character selection, store active character ID
        - Include header with each API request: X-Character-ID: 123
        - Different tabs can use different character IDs

    Why this is centralized:
        - Avoids duplicating this logic across goals, conditions, and future views
        - Keeps domain type imports (Character) behind TYPE_CHECKING guard
        - Views get character context without importing typeclasses
    """

    def _get_character(self, request: Request) -> Character | None:
        """
        Get the character specified in the request header.

        Validates that the authenticated user has access to the character
        through the roster system's tenure mechanism.

        Returns:
            Character if valid and owned, None otherwise.

        Note:
            Return type is annotated as Character for type checking, but at
            runtime this works with any ObjectDB instance. The type hint is
            only evaluated during static analysis (TYPE_CHECKING guard).
        """
        character_id = request.headers.get("X-Character-ID")
        if not character_id:
            return None

        try:
            character_id = int(character_id)
        except (ValueError, TypeError):
            return None

        # Validate character ownership via roster system
        # request.user.get_available_characters() returns Character instances
        available = request.user.get_available_characters()
        for character in available:
            if character.id == character_id:
                return character

        return None

    def _get_character_by_id(self, character_id: int) -> ObjectDB | None:
        """
        Get a character by ID without ownership validation.

        Use this for viewing other characters' public data (e.g., roster viewing).

        Args:
            character_id: The character's database ID.

        Returns:
            ObjectDB instance if found, None otherwise.
        """
        try:
            return ObjectDB.objects.get(id=character_id)
        except ObjectDB.DoesNotExist:
            return None
