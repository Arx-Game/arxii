"""Cached handlers for covenant relationships (Spec D §3.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.covenants.models import CharacterCovenantRole, Covenant, CovenantRole


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
                .select_related("covenant_role", "covenant")
                .order_by("joined_at")
            )
            self._cached = list(qs)
        return self._cached

    def has_ever_held(self, role: CovenantRole) -> bool:
        """Return True if the character has ever held ``role`` (active or ended)."""
        return any(r.covenant_role_id == role.pk for r in self._rows)

    def max_covenant_level_for_role(self, role: CovenantRole) -> int:
        """Return the maximum covenant.level across all rows (active or historical) for this role.

        Includes ended memberships — historical peak level matters for the anchor cap formula.
        """
        levels = [r.covenant.level for r in self._rows if r.covenant_role_id == role.pk]
        return max(levels, default=0)

    def currently_held_role_in(self, covenant: Covenant) -> CovenantRole | None:
        """Return the active role in the specified covenant, or None.

        Does NOT consider engagement — for that use currently_engaged_roles().
        """
        for r in self._rows:
            if r.left_at is None and r.covenant_id == covenant.pk:
                return r.covenant_role
        return None

    def currently_engaged_roles(self) -> list[CovenantRole]:
        """Return roles for every active+engaged membership row."""
        return [r.covenant_role for r in self._rows if r.engaged and r.left_at is None]

    @property
    def active_memberships(self) -> list[CharacterCovenantRole]:
        """All active memberships (left_at IS NULL) for this character."""
        return [m for m in self._rows if m.left_at is None]

    def active_memberships_for_type(
        self,
        covenant_type: str,
    ) -> list[CharacterCovenantRole]:
        """Active memberships filtered by covenant_type — no DB."""
        return [m for m in self.active_memberships if m.covenant.covenant_type == covenant_type]

    def currently_engaged_for_type(
        self,
        covenant_type: str,
    ) -> CharacterCovenantRole | None:
        """At-most-one engaged membership for the given type per Slice A invariant."""
        for m in self.active_memberships_for_type(covenant_type):
            if m.engaged:
                return m
        return None

    def invalidate(self) -> None:
        """Clear the cached assignment list. Called by mutation services."""
        self._cached = None
