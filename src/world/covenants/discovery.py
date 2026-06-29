"""Sub-role discovery beat: fired when a COVENANT_ROLE thread crosses a sub-role threshold.

When a character's COVENANT_ROLE thread level crosses a sub-role's ``unlock_thread_level``,
they "discover" the variant — receiving an Achievement (with a global-first Discovery row on
the first-ever earner), a CodexEntry unlock, and a NarrativeMessage (gamewide on first-ever,
personal otherwise).

Entry point: ``fire_subrole_discoveries(*, thread, starting_level, new_level)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole
    from world.magic.models import Thread


def fire_subrole_discoveries(*, thread: Thread, starting_level: int, new_level: int) -> None:
    """Fire the discovery beat for any sub-role threshold newly crossed by this
    COVENANT_ROLE thread imbue. Idempotent. See spec §D."""
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if thread.target_kind != TargetKind.COVENANT_ROLE or new_level <= starting_level:
        return
    parent_id = thread.target_covenant_role_id
    if parent_id is None:
        return

    from world.achievements.models import CharacterAchievement  # noqa: PLC0415
    from world.achievements.services import grant_achievement  # noqa: PLC0415
    from world.covenants.models import CovenantRole  # noqa: PLC0415

    sheet: CharacterSheet = thread.owner
    newly: list[CovenantRole] = [
        sub
        for sub in CovenantRole.objects.filter(
            parent_role_id=parent_id,
            resonance_id=thread.resonance_id,
        )
        if starting_level < sub.unlock_thread_level <= new_level
    ]

    for sub in newly:
        ach = sub.discovery_achievement
        # Idempotency gate: skip the whole beat if achievement already earned.
        # Covers re-imbue replay (same range fires again) — prevents duplicates.
        if (
            ach is not None
            and CharacterAchievement.objects.filter(
                character_sheet=sheet,
                achievement=ach,
            ).exists()
        ):
            continue

        is_first = False
        if ach is not None:
            results = grant_achievement(ach, [sheet])
            is_first = bool(results and results[0].discovery_id is not None)

        _unlock_codex(sheet, sub)
        _notify(sheet, sub, is_first=is_first)


def _unlock_codex(sheet: CharacterSheet, sub: CovenantRole) -> None:
    """Create a CharacterCodexKnowledge(status=KNOWN) for the sub-role's codex_entry.

    Skips gracefully when:
    - ``sub.codex_entry`` is None (no lore entry authored for this sub-role), or
    - the sheet has no roster_entry (character not yet on the roster).
    """
    entry = sub.codex_entry
    if entry is None:
        return

    # CharacterCodexKnowledge is keyed on RosterEntry, not CharacterSheet.
    # sheet.roster_entry is a OneToOne reverse — may not exist.
    roster_entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL
    if roster_entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=entry,
        defaults={"status": CodexKnowledgeStatus.KNOWN},
    )


def _notify(sheet: CharacterSheet, sub: CovenantRole, *, is_first: bool) -> None:
    """Send a NarrativeMessage announcing the sub-role discovery.

    Delegates to ``announce_achievement`` (achievements/discovery.py), preserving
    the exact wording and COVENANT category.

    First-ever (``is_first=True``): gamewide — all active player character sheets.
    Not first (``is_first=False``): personal — only the discovering sheet.
    """
    from world.achievements.discovery import announce_achievement  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

    announce_achievement(
        [sheet],
        is_first=is_first,
        first_body=(
            f"For the first time in recorded history, a character has manifested "
            f"the {sub.name} sub-role — a convergence of {sub.resonance.name} and "
            f"covenant purpose no one has achieved before."
        ),
        personal_body=(
            f"Your covenant path has deepened. You have manifested the "
            f"{sub.name} sub-role, channelled through {sub.resonance.name}."
        ),
        category=NarrativeCategory.COVENANT,
    )
