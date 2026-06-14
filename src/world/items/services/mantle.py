"""Mantle clearance services (Spec D / #512).

Clearance gating is **Codex research**: a mantle level clears when its
``codex_entry_required`` is fully learned (``CharacterCodexKnowledge`` with
status KNOWN) by the character — recorded by an idempotent on-demand service.
No Django signals: callers invoke ``record_mantle_clearances`` when they want
the clearance state recomputed. A staff override (``grant_mantle_clearance``)
bypasses the codex check entirely.

``CharacterCodexKnowledge`` is keyed by ``RosterEntry`` (knowledge belongs to
the character itself, surviving handoffs), so the codex query resolves the
sheet's ``roster_entry`` reverse OneToOne first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.codex.constants import CodexKnowledgeStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import Mantle, MantleLevelClearance


def get_max_cleared_mantle_level(sheet: CharacterSheet, mantle: Mantle) -> int:
    """Return the highest cleared level for (sheet, mantle), or 0 if none."""
    from world.items.models import MantleLevelClearance  # noqa: PLC0415

    cleared = (
        MantleLevelClearance.objects.filter(character_sheet=sheet, mantle=mantle)
        .order_by("-level")
        .values_list("level", flat=True)
        .first()
    )
    return cleared or 0


def _codex_entry_learned(sheet: CharacterSheet, entry_id: int) -> bool:
    """Return True if the character behind ``sheet`` has fully learned ``entry_id``.

    Codex knowledge is keyed by RosterEntry; resolve the sheet's roster_entry
    reverse OneToOne. A sheet with no roster entry can hold no codex knowledge.
    """
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    roster_entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL — reverse OneToOne may not exist
    if roster_entry is None:
        return False
    return CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry,
        entry_id=entry_id,
        status=CodexKnowledgeStatus.KNOWN,
    ).exists()


def record_mantle_clearances(sheet: CharacterSheet, mantle: Mantle) -> list[MantleLevelClearance]:
    """Idempotently record codex-gated mantle clearances for ``sheet``.

    Walks ``mantle.level_defs`` in level order. For each level not yet cleared,
    the level clears only if (a) its ``codex_entry_required`` is fully learned
    and (b) all lower levels are already cleared. Stops at the first level whose
    codex gate is unmet (in-order gate). Returns the newly created clearance
    rows (empty if nothing new cleared).
    """
    from world.items.models import MantleLevelClearance  # noqa: PLC0415

    already_cleared = set(
        MantleLevelClearance.objects.filter(character_sheet=sheet, mantle=mantle).values_list(
            "level", flat=True
        )
    )
    created: list[MantleLevelClearance] = []
    for level_def in mantle.level_defs.order_by("level"):
        if level_def.level in already_cleared:
            continue
        if not _codex_entry_learned(sheet, level_def.codex_entry_required_id):
            # In-order gate: a level whose codex requirement is unmet blocks
            # every higher level too.
            break
        clearance, was_created = MantleLevelClearance.objects.get_or_create(
            character_sheet=sheet,
            mantle=mantle,
            level=level_def.level,
        )
        already_cleared.add(level_def.level)
        if was_created:
            created.append(clearance)
    return created


def grant_mantle_clearance(
    sheet: CharacterSheet, mantle: Mantle, level: int
) -> MantleLevelClearance:
    """Staff override: record a clearance at ``level`` without the codex check.

    Idempotent via ``get_or_create`` on the unique (sheet, mantle, level).
    """
    from world.items.models import MantleLevelClearance  # noqa: PLC0415

    clearance, _ = MantleLevelClearance.objects.get_or_create(
        character_sheet=sheet,
        mantle=mantle,
        level=level,
    )
    return clearance
