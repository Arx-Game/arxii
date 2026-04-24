"""Login catch-up hook — re-evaluates active stories when a character is puppeted.

Called from Character.at_post_puppet. Iterates the character's active
progress records and calls evaluate_auto_beats. Catches any mutations
that happened while the character was offline and for which no
real-time hook fired (direct admin action, data import, race
condition, etc.).

Also drains queued NarrativeMessageDeliveries so any messages fanned
out while the character was offline get pushed to the session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.character_sheets.models import CharacterSheet

if TYPE_CHECKING:
    from typeclasses.characters import Character


def catch_up_character_stories(character: Character) -> None:
    """Re-evaluate auto-beats and deliver queued narrative messages.

    Safe to call from at_post_puppet even when the character has no
    sheet (NPC, stub object) — silently skips in that case.
    """
    try:
        sheet = character.sheet_data
    except CharacterSheet.DoesNotExist:
        return

    # Re-evaluate active stories across all three scopes.
    from world.stories.services.reactivity import on_character_state_changed  # noqa: PLC0415

    on_character_state_changed(sheet)

    # Push any queued narrative messages for this character.
    from world.narrative.services import deliver_queued_messages  # noqa: PLC0415

    deliver_queued_messages(sheet)
