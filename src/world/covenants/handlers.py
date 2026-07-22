"""Cached handlers for covenant relationships (Spec D §3.3)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
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
                .prefetch_related("covenant_role__sub_roles")  # noqa: PREFETCH_STRING
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

    def days_held_in_role(self, role: CovenantRole) -> int:
        """Return total whole days this character has held ``role``, summed across covenants.

        Active rows (left_at IS NULL) accrue time continuously up to now; historical
        rows count their [joined_at, left_at] span. Cumulative across every row for
        the role — mirrors max_covenant_level_for_role keying off the same all-time set.
        """
        now = timezone.now()
        total = timedelta()
        for r in self._rows:
            if r.covenant_role_id == role.pk:
                total += (r.left_at or now) - r.joined_at
        return total.days

    def covenant_ids_for_role(self, role: CovenantRole) -> list[int]:
        """Return covenant PKs where this character has held ``role`` (active or historical).

        Reads the cached rows — no DB query. Lets callers (e.g. the COVENANT_ROLE
        anchor-cap legend lookup) skip re-querying covenant membership that is
        already in the handler cache.
        """
        return [r.covenant_id for r in self._rows if r.covenant_role_id == role.pk]

    def currently_held_role_in(self, covenant: Covenant) -> CovenantRole | None:
        """Return the active role in the specified covenant, or None.

        Does NOT consider engagement — for that use currently_engaged_roles().
        """
        for r in self._rows:
            if r.left_at is None and r.covenant_id == covenant.pk:
                return r.covenant_role
        return None

    def currently_engaged_roles(self) -> list[CovenantRole]:
        """Return resolved (effective) roles for every active+engaged membership row.

        Derives sub-role specialization on read: if the character's COVENANT_ROLE
        thread on a role qualifies for a resonance sub-role, the sub-role is returned
        instead of the parent. Anchor identity is always stored on the membership row;
        use ``anchor_role_in`` for consumers that must key on the stored parent role.

        Secondary memberships (``is_secondary=True``, #2641) resolve at their
        ANCHOR role ONLY — never a resolved sub-role — since deep rungs/
        graduation/signature/name stay primary-only; primary memberships
        resolve normally. Kept as the ALL-engaged-roles view for non-layer
        callers (eligibility gates, precedence fallbacks); chassis callers
        (Layer 1/3) use ``currently_engaged_primary_roles`` instead, and
        Layer 2/4 callers use ``currently_engaged_roles_with_flags``.
        """
        from world.covenants.services import resolve_effective_role  # noqa: PLC0415

        char = self._character
        roles: list[CovenantRole] = []
        for r in self._rows:
            if not (r.engaged and r.left_at is None):
                continue
            if r.is_secondary:
                roles.append(r.covenant_role)
            else:
                roles.append(resolve_effective_role(character=char, role=r.covenant_role))
        return roles

    def currently_engaged_primary_roles(self) -> list[CovenantRole]:
        """Resolved roles for engaged PRIMARY (``is_secondary=False``) memberships
        only (#2641).

        Chassis layers (Layer 1 combat-identity blend, Layer 3 defense/gear/
        stat scaling) key off primary vows exclusively — sub-role graduation
        is unrestricted here (primary depth has no cap). Secondary vows never
        reach the chassis; see ``currently_engaged_roles_with_flags`` for the
        flagged view Layer 2/4 use instead.
        """
        from world.covenants.services import resolve_effective_role  # noqa: PLC0415

        char = self._character
        return [
            resolve_effective_role(character=char, role=r.covenant_role)
            for r in self._rows
            if r.engaged and r.left_at is None and not r.is_secondary
        ]

    def currently_engaged_roles_with_flags(self) -> list[tuple[CovenantRole, bool]]:
        """``(role, is_secondary)`` pairs for every active+engaged membership row (#2641).

        PRIMARY rows resolve the same way ``currently_engaged_primary_roles``
        does (sub-role graduation applies). SECONDARY rows resolve at their
        ANCHOR role ONLY — a secondary's own sub-role investment never
        surfaces here (depth stays primary-only). Layer 2
        (``covenant_role_specialty_power_term``) and Layer 4 (the perk
        candidate gatherers) read this to scale a secondary-sourced
        contribution by ``SecondaryVowConfig.potency_tenths``.
        """
        from world.covenants.services import resolve_effective_role  # noqa: PLC0415

        char = self._character
        pairs: list[tuple[CovenantRole, bool]] = []
        for r in self._rows:
            if not (r.engaged and r.left_at is None):
                continue
            if r.is_secondary:
                pairs.append((r.covenant_role, True))
            else:
                pairs.append((resolve_effective_role(character=char, role=r.covenant_role), False))
        return pairs

    def anchor_role_in(self, covenant: Covenant) -> CovenantRole | None:
        """Return the stored (parent/anchor) covenant_role for the active membership in
        ``covenant``, ignoring sub-role resolution.

        Consumers that must key on the anchor identity (e.g. thread's
        ``target_covenant_role_id``) use this instead of ``currently_engaged_roles()``.
        Returns None if the character has no active membership in ``covenant``.
        """
        return self.currently_held_role_in(covenant)

    @property
    def active_memberships(self) -> list[CharacterCovenantRole]:
        """All active memberships (left_at IS NULL) for this character."""
        return [m for m in self._rows if m.left_at is None]

    def active_covenant_ids(self) -> frozenset[int]:
        """Return the frozenset of covenant PKs where this character is currently active.

        Used by ``Character.shares_covenant_with`` for the reactive-filter
        ``shares_covenant`` op.
        """
        return frozenset(m.covenant_id for m in self.active_memberships)

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


class CovenantMembershipHandler:
    """Cached handler for a Covenant's active memberships.

    Per project SharedMemoryModel discipline: services and serializers route
    membership lookups through this handler, never via .filter() on the
    related manager.
    """

    def __init__(self, covenant: Covenant) -> None:
        self._covenant = covenant
        self._cached: list[CharacterCovenantRole] | None = None

    @property
    def _rows(self) -> list[CharacterCovenantRole]:
        if self._cached is None:
            self._cached = list(
                self._covenant.memberships.select_related(
                    "character_sheet",
                    "covenant_role",
                )
            )
        return self._cached

    @property
    def active_memberships(self) -> list[CharacterCovenantRole]:
        return [m for m in self._rows if m.left_at is None]

    @property
    def active_character_sheets(self) -> list[CharacterSheet]:
        return [m.character_sheet for m in self.active_memberships]

    def invalidate(self) -> None:
        self._cached = None


def can_engage_membership(membership: CharacterCovenantRole) -> bool:
    """Shared prerequisite check used by manual + auto engage paths.

    - BATTLE: engageable iff the covenant is risen (not dormant). A dormant
      battle covenant cannot be engaged — vows lie latent until a "call the
      banners" rise ritual brings the covenant back (Slice E).
    - COURT: the servant is "on the master's business" — a participant in an
      active mission given by the Court's backing organization (#1589 Task 5),
      OR a persona the master holds a nonzero opinion of (positive or negative)
      is present in the servant's current scene (#1717). Either gate engages.
    - DURANCE: the character is in a room with an active scene AND at least one
      other active member of the same covenant is co-present in that room.

    All membership lookups go through cached handlers per project rule §3.9 of
    the Slice B spec — no .filter() on related managers.
    """
    from world.covenants.constants import CovenantType  # noqa: PLC0415
    from world.covenants.court_missions import (  # noqa: PLC0415
        has_active_court_mission,
        has_regarded_target_present,
    )
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    covenant = membership.covenant
    if covenant.covenant_type == CovenantType.BATTLE:
        return not covenant.is_dormant
    if covenant.covenant_type == CovenantType.COURT:
        return has_active_court_mission(
            character_sheet=membership.character_sheet, covenant=covenant
        ) or has_regarded_target_present(
            character_sheet=membership.character_sheet, covenant=covenant
        )

    char = membership.character_sheet.character
    location = char.location
    if location is None:
        return False
    if get_active_scene(location) is None:
        return False
    self_sheet = membership.character_sheet
    target_covenant = membership.covenant
    for obj in location.contents:
        sheet = obj.character_sheet
        if sheet is None or sheet == self_sheet:
            continue
        if sheet.character.covenant_roles.currently_held_role_in(target_covenant) is not None:
            return True
    return False
