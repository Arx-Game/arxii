"""Dissolving graduated bonds when an encounter starts."""

from __future__ import annotations

from django.db.models import Q

from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant
from world.combat.services.encounter.levels import _bulk_primary_levels


def _dissolve_graduated_bonds(enc: CombatEncounter) -> None:
    """Dissolve any MentorBond that has graduated for ACTIVE participants in *enc*.

    A bond is "graduated" when the adjusted party's raw primary level is now
    within the covenant band — the bond is mechanically inactive and should be
    persisted as dissolved so future reads skip it cleanly.

    Write-safe: called only from ``begin_declaration_phase`` (encounter start).
    No per-bond queries: bulk-fetches bonds in one query, resolves primary levels
    for all adjusted-party characters in a second bulk query, then determines
    graduation inline — O(1) queries regardless of graduated-bond count.
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415
    from world.covenants.mentorship import dissolve_mentor_bond, is_in_band  # noqa: PLC0415
    from world.covenants.models import MentorBond  # noqa: PLC0415

    sheet_ids = list(
        CombatParticipant.objects.filter(
            encounter=enc,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )
    if not sheet_ids:
        return

    # One bulk query: all active bonds where any participant is either the
    # mentor or the sidekick side. Resolve covenant + both character FKs so
    # no per-bond queries are needed below.
    active_bonds = list(
        MentorBond.objects.active()
        .filter(Q(mentor_sheet_id__in=sheet_ids) | Q(sidekick_sheet_id__in=sheet_ids))
        .select_related(
            "covenant",
            "mentor_sheet__character",
            "sidekick_sheet__character",
        )
    )
    if not active_bonds:
        return

    # Collect the adjusted-party character id for each bond (one id per bond).
    adjusted_char_ids = [
        bond.sidekick_sheet.character_id
        if bond.adjusted_party == MentorBondAdjusted.SIDEKICK
        else bond.mentor_sheet.character_id
        for bond in active_bonds
    ]

    # Two bulk queries at most: primary levels + highest-level fallback.
    level_map = _bulk_primary_levels(adjusted_char_ids)

    for bond, char_id in zip(active_bonds, adjusted_char_ids, strict=True):
        raw = level_map.get(char_id, 1)
        if is_in_band(bond.covenant, raw):
            dissolve_mentor_bond(bond)
