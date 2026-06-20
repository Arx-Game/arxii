"""Effective combat level seam + bond adjustment math for Mentor's Vow (#1165).

Public API
----------
- covenant_band(covenant) -> tuple[int, int]
- is_in_band(covenant, raw_level) -> bool
- active_bond_adjusting(sheet) -> MentorBond | None
- bond_adjusted_level(sheet) -> int | None
- effective_combat_level(sheet) -> int
- is_bond_graduated(bond) -> bool

Adjustment rule
---------------
- SIDEKICK adjusted: effective = clamp(mentor_raw_level - offset, band).
- MENTOR adjusted: top = max raw primary level over all active sidekick bonds
  (fetched in one bulk query); effective = clamp(top + offset, band).
- clamp(x, (lo, hi)) = max(lo, min(hi, x)).
- Graduated (adjusted party's raw primary level is already in band) =>
  treated as inactive => returns raw primary level (bond row untouched).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import Covenant, MentorBond


def covenant_band(covenant: Covenant) -> tuple[int, int]:
    """Return (low, high) inclusive band for the covenant.

    band_width is loaded from MentorBondConfig (pk=1).
    """
    from world.covenants.services import get_mentor_bond_config  # noqa: PLC0415

    cfg = get_mentor_bond_config()
    return (covenant.level - cfg.band_width, covenant.level + cfg.band_width)


def is_in_band(covenant: Covenant, raw_level: int) -> bool:
    """Return True if raw_level is within [low, high] inclusive."""
    lo, hi = covenant_band(covenant)
    return lo <= raw_level <= hi


def _raw_primary_level(sheet: CharacterSheet) -> int:
    """Return the raw primary class level for a sheet via get_character_path_level."""
    from world.progression.services.skill_development import (  # noqa: PLC0415
        get_character_path_level,
    )

    return get_character_path_level(sheet.character)


def is_bond_graduated(bond: MentorBond) -> bool:
    """Return True if the adjusted party's raw primary level is already in band.

    Graduation means the bond is mechanically inactive — the adjusted party
    has leveled into the covenant's natural range and no longer needs
    compensation. The bond row is NOT dissolved here (Task 6 owns that).
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415

    if bond.adjusted_party == MentorBondAdjusted.SIDEKICK:
        adjusted_sheet = bond.sidekick_sheet
    else:
        adjusted_sheet = bond.mentor_sheet

    raw = _raw_primary_level(adjusted_sheet)
    return is_in_band(bond.covenant, raw)


def active_bond_adjusting(sheet: CharacterSheet) -> MentorBond | None:
    """Return the active, non-graduated bond where sheet is the adjusted party.

    Returns None if no such bond exists (no bond, dissolved, or graduated).
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415
    from world.covenants.models import MentorBond  # noqa: PLC0415

    # A sheet can be the SIDEKICK adjusted party or the MENTOR adjusted party.
    # Check both relations and return the first non-graduated active bond.
    sidekick_bond: MentorBond | None = (
        MentorBond.objects.active()
        .filter(sidekick_sheet=sheet, adjusted_party=MentorBondAdjusted.SIDEKICK)
        .select_related("covenant", "mentor_sheet")
        .first()
    )
    if sidekick_bond is not None and not is_bond_graduated(sidekick_bond):
        return sidekick_bond

    mentor_bond: MentorBond | None = (
        MentorBond.objects.active()
        .filter(mentor_sheet=sheet, adjusted_party=MentorBondAdjusted.MENTOR)
        .select_related("covenant")
        .first()
    )
    if mentor_bond is not None and not is_bond_graduated(mentor_bond):
        return mentor_bond

    return None


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _adjusted_level_for_sidekick(bond: MentorBond) -> int:
    """Compute effective level for the SIDEKICK adjusted party."""
    from world.covenants.services import get_mentor_bond_config  # noqa: PLC0415

    cfg = get_mentor_bond_config()
    mentor_raw = _raw_primary_level(bond.mentor_sheet)
    lo, hi = covenant_band(bond.covenant)
    return _clamp(mentor_raw - cfg.adjacency_offset, lo, hi)


def _adjusted_level_for_mentor(bond: MentorBond) -> int:
    """Compute effective level for the MENTOR adjusted party.

    Fetches all active MENTOR-adjusted sidekick bonds for this mentor in
    this covenant, then resolves their primary levels in ONE bulk
    CharacterClassLevel query (no per-sidekick loop queries).
    """
    from world.classes.models import CharacterClassLevel  # noqa: PLC0415
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415
    from world.covenants.models import MentorBond  # noqa: PLC0415
    from world.covenants.services import get_mentor_bond_config  # noqa: PLC0415

    cfg = get_mentor_bond_config()

    # All active MENTOR-adjusted bonds for this mentor in this covenant.
    sidekick_bonds = list(
        MentorBond.objects.active()
        .filter(
            mentor_sheet=bond.mentor_sheet,
            covenant=bond.covenant,
            adjusted_party=MentorBondAdjusted.MENTOR,
        )
        .values_list("sidekick_sheet__character_id", flat=True)
    )

    if not sidekick_bonds:
        # Fallback: no sidekick bonds found; can't compute top. Return band low.
        lo, _ = covenant_band(bond.covenant)
        return lo

    # Bulk fetch: one query — primary class level per sidekick character.
    # We need the primary level (is_primary=True) or highest level per character.
    # Strategy: fetch all is_primary=True rows for the sidekick characters in
    # one query, then fall back to highest for any without a primary.
    primary_rows = CharacterClassLevel.objects.filter(
        character_id__in=sidekick_bonds,
        is_primary=True,
    ).values("character_id", "level")
    primary_by_char: dict[int, int] = {row["character_id"]: row["level"] for row in primary_rows}

    # Characters without a primary row: fetch their highest level in one query.
    without_primary = [cid for cid in sidekick_bonds if cid not in primary_by_char]
    if without_primary:
        # Use a subquery approach: order by -level, distinct on character (PG-safe
        # in the test SQLite tier via Python-side grouping).
        highest_rows = (
            CharacterClassLevel.objects.filter(character_id__in=without_primary)
            .order_by("character_id", "-level")
            .values("character_id", "level")
        )
        seen: set[int] = set()
        for row in highest_rows:
            cid = row["character_id"]
            if cid not in seen:
                primary_by_char[cid] = row["level"]
                seen.add(cid)

    # Characters with no CharacterClassLevel at all default to 1.
    all_levels = [primary_by_char.get(cid, 1) for cid in sidekick_bonds]
    top = max(all_levels) if all_levels else 1

    lo, hi = covenant_band(bond.covenant)
    return _clamp(top + cfg.adjacency_offset, lo, hi)


def bond_adjusted_level(sheet: CharacterSheet) -> int | None:
    """Return the adjusted level if an active, non-graduated bond reshapes sheet.

    Returns None if no such bond exists (no bond, dissolved, or graduated).
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415

    bond = active_bond_adjusting(sheet)
    if bond is None:
        return None

    if bond.adjusted_party == MentorBondAdjusted.SIDEKICK:
        return _adjusted_level_for_sidekick(bond)
    return _adjusted_level_for_mentor(bond)


def effective_combat_level(sheet: CharacterSheet) -> int:
    """Return the effective combat level for a character sheet.

    Uses bond_adjusted_level when an active non-graduated bond reshapes
    the sheet, otherwise falls back to the raw primary class level via
    get_character_path_level.
    """
    adjusted = bond_adjusted_level(sheet)
    if adjusted is not None:
        return adjusted
    return _raw_primary_level(sheet)
