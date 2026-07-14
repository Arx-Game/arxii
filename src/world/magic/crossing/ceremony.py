"""Crossing ceremony entry point + shared beat helper (ADR-0094, #1987).

``execute_crossing_ceremonies`` is the generalized successor to
``fire_variant_discoveries``. It dispatches on ``thread.target_kind`` via the
handler registry so every kind gets a ceremony at PathStage crossing levels
(3, 6, 11, 16, 21), not just GIFT and COVENANT_ROLE.

``execute_ceremony_beat`` is the shared beat extracted from the old
``_fire_one`` — achievement grant + codex unlock + narrative notify — callable
by any handler regardless of whether it uses variant-discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from world.magic.crossing.registry import get_crossing_handler

if TYPE_CHECKING:
    from world.achievements.models import Achievement, CodexEntry
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Thread
    from world.narrative.constants import NarrativeCategory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CeremonyNarrative:
    """Narrative copy + category for a ceremony beat.

    Bundles the three narrative params so ``execute_ceremony_beat`` stays under
    the 5-arg limit (PLR0913). Both bodies are fetched; gamewide-vs-personal
    recipient selection is owned by ``announce_achievement``.
    """

    first_body: str = ""
    personal_body: str = ""
    category: NarrativeCategory | None = None

    def __post_init__(self) -> None:
        if self.category is None:
            from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

            object.__setattr__(self, "category", NarrativeCategory.VISIONS)


def execute_crossing_ceremonies(
    *,
    thread: Thread,
    starting_level: int,
    new_level: int,
) -> None:
    """Dispatch the crossing ceremony for any ``TargetKind``.

    Called by ``spend_resonance_for_imbuing`` after every thread advance. Looks
    up the registered handler for ``thread.target_kind`` and delegates. If no
    handler is registered, logs a debug no-op — the gap is explicit, not silent.
    """
    if new_level <= starting_level:
        return

    handler = get_crossing_handler(thread.target_kind)
    if handler is None:
        logger.debug(
            "No crossing ceremony handler registered for target_kind=%s",
            thread.target_kind,
        )
        return

    handler.execute(
        thread=thread,
        starting_level=starting_level,
        new_level=new_level,
    )


def execute_ceremony_beat(
    *,
    sheet: CharacterSheet,
    narrative: CeremonyNarrative,
    achievement: Achievement | None = None,
    codex_entry: CodexEntry | None = None,
) -> None:
    """Shared ceremony beat: achievement + codex unlock + narrative notify.

    Extracted from the old ``_fire_one`` in ``world.covenants.discovery`` so
    non-variant handlers (TRAIT, SANCTUM, etc.) can fire the same beat without
    an ``AbstractSpecializedVariant`` instance.

    Idempotent on achievement: if the sheet already has ``achievement``, the
    whole beat is skipped (covers re-imbue replay).

    Args:
        sheet: The discovering character sheet.
        narrative: The narrative copy + category for the message.
        achievement: Achievement to grant (+ global-first Discovery). None skips.
        codex_entry: CodexEntry to unlock as KNOWN. None skips.
    """
    from world.achievements.discovery import announce_achievement  # noqa: PLC0415
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415

    is_first = False
    if achievement is not None:
        # Idempotency gate: skip the whole beat if achievement already earned.
        if CharacterAchievement.objects.filter(
            character_sheet=sheet,
            achievement=achievement,
        ).exists():
            return

        from world.achievements.services import grant_achievement  # noqa: PLC0415

        results = grant_achievement(achievement, [sheet])
        is_first = bool(results and results[0].discovery_id is not None)

    if codex_entry is not None:
        _unlock_codex(sheet, codex_entry)

    announce_achievement(
        [sheet],
        is_first=is_first,
        first_body=narrative.first_body,
        personal_body=narrative.personal_body,
        category=narrative.category,
    )


def _unlock_codex(sheet: CharacterSheet, codex_entry: CodexEntry) -> None:
    """Create a CharacterCodexKnowledge(status=KNOWN) for ``codex_entry``.

    Skips gracefully when the sheet has no roster_entry (character not yet on
    the roster). Extracted verbatim from ``_unlock_codex`` in discovery.py.
    """
    # CharacterCodexKnowledge is keyed on RosterEntry, not CharacterSheet.
    # sheet.roster_entry is a OneToOne reverse — may not exist.
    roster_entry = sheet.roster_entry_or_none
    if roster_entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=codex_entry,
        defaults={"status": CodexKnowledgeStatus.KNOWN},
    )
