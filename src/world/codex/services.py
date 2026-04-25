"""Service functions for the Codex app.

Model methods on CharacterCodexKnowledge handle pure mechanics (progress
accumulation, status transitions). Cross-app reactivity — such as notifying
the stories engine when an entry is unlocked — lives here, following project
convention that cross-app hooks belong in service functions, not model methods.
"""

from world.codex.models import CharacterCodexKnowledge


def add_codex_progress(
    *,
    knowledge: CharacterCodexKnowledge,
    amount: int,
) -> CharacterCodexKnowledge:
    """Add learning progress to a CharacterCodexKnowledge instance.

    Delegates the mechanics to ``knowledge.add_progress(amount)``. If a new
    entry is unlocked (status transitions to KNOWN), fires the stories
    reactivity hook so any active CODEX_ENTRY_UNLOCKED beats on the character's
    stories re-evaluate.

    Args:
        knowledge: The CharacterCodexKnowledge instance to update.
        amount: The amount of progress to add.

    Returns:
        The updated CharacterCodexKnowledge instance.
    """
    just_unlocked = knowledge.add_progress(amount)
    if just_unlocked:
        _notify_stories_unlocked(knowledge)
    return knowledge


def _notify_stories_unlocked(knowledge: CharacterCodexKnowledge) -> None:
    """Fire the stories reactivity hook on KNOWN transition.

    Resolves sheet via roster_entry.character_sheet. Cross-app lazy import
    avoids circular imports and keeps codex decoupled at module load time.
    """
    from world.stories.services.reactivity import on_codex_entry_unlocked  # noqa: PLC0415

    sheet = knowledge.roster_entry.character_sheet
    if sheet is not None:
        on_codex_entry_unlocked(sheet, knowledge.entry)
