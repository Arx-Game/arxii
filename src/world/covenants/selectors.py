"""Read-only membership selectors shared by the covenant viewsets and the
telnet Actions — one capability-filtered actor lookup, not two copies."""

from __future__ import annotations

from collections.abc import Iterable

from world.character_sheets.models import CharacterSheet
from world.covenants.models import CharacterCovenantRole, Covenant

_CAPABILITY_FIELDS = {"can_kick", "can_manage_ranks"}


def resolve_actor_membership(
    *,
    covenant: Covenant,
    character_sheets: Iterable[CharacterSheet],
    capability: str | None = None,
) -> CharacterCovenantRole | None:
    """First active membership in ``covenant`` among ``character_sheets`` that
    carries ``capability`` (a rank flag), or any active membership if None."""
    qs = CharacterCovenantRole.objects.filter(
        covenant=covenant,
        left_at__isnull=True,
        character_sheet__in=character_sheets,
    )
    if capability is not None:
        if capability not in _CAPABILITY_FIELDS:
            msg = f"Unknown capability {capability!r}"
            raise ValueError(msg)
        qs = qs.filter(**{f"rank__{capability}": True})
    return qs.select_related("rank").first()


def get_active_memberships(*, character_sheet: CharacterSheet) -> list[CharacterCovenantRole]:
    """All active (left_at IS NULL) memberships for one character sheet."""
    return list(
        CharacterCovenantRole.objects.filter(
            character_sheet=character_sheet, left_at__isnull=True
        ).select_related("covenant", "rank", "covenant_role")
    )
