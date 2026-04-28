"""Cached handlers for covenant relationships (Spec D §3.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.covenants.models import CharacterCovenantRole, CovenantRole


class CharacterCovenantRoleHandler:
    """Cached handler for a character's covenant role assignments.

    Returns active and historical assignments. Mutators (assign_covenant_role,
    end_covenant_role) invalidate explicitly via ``handler.invalidate()``.
    """

    def __init__(self, character: Character) -> None:
        self._character = character
        self._cached: list[CharacterCovenantRole] | None = None

    @property
    def _rows(self) -> list[CharacterCovenantRole]:
        if self._cached is None:
            from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

            sheet = self._character.sheet_data
            qs = (
                CharacterCovenantRole.objects.filter(character_sheet=sheet)
                .select_related("covenant_role")
                .order_by("joined_at")
            )
            self._cached = list(qs)
        return self._cached

    def has_ever_held(self, role: CovenantRole) -> bool:
        """Return True if the character has ever held ``role`` (active or ended)."""
        return any(r.covenant_role_id == role.pk for r in self._rows)

    def currently_held(self) -> CovenantRole | None:
        """Return the active CovenantRole, or None if the character holds no active role."""
        for r in self._rows:
            if r.left_at is None:
                return r.covenant_role
        return None

    def invalidate(self) -> None:
        """Clear the cached assignment list. Called by mutation services."""
        self._cached = None
