"""Service for reconciling CharacterRitualKnowledge from grant tables.

Walks the five ritual grant tables (BeginningsRitualGrant, PathRitualGrant,
DistinctionRitualGrant, TraditionRitualGrant, CodexEntryRitualGrant) for a
given roster entry's character data and creates CharacterRitualKnowledge rows
for any granted rituals the character doesn't already know.

Idempotent: re-running creates no duplicates. Does not delete existing rows
(taught rituals or self-authored stay intact).

Called from character creation finalization (Phase 8). Future: re-fire on
relevant data changes (path swap, codex unlock) — out of scope for v1.
"""

from typing import TYPE_CHECKING

from django.db import transaction

from world.codex.constants import CodexKnowledgeStatus
from world.magic.models import CharacterRitualKnowledge
from world.magic.models.grants import (
    CodexEntryRitualGrant,
    DistinctionRitualGrant,
    PathRitualGrant,
    TraditionRitualGrant,
)

if TYPE_CHECKING:
    from world.roster.models import RosterEntry


@transaction.atomic
def reconcile_ritual_knowledge(roster_entry: "RosterEntry") -> None:
    """Ensure CharacterRitualKnowledge rows exist for all granted rituals.

    Idempotent. Reads the character's path/distinctions/tradition/codex entries
    and creates knowledge rows for any matching grants. Does not delete existing
    rows (especially those with learned_from set).

    Args:
        roster_entry: The RosterEntry to reconcile knowledge for.
    """
    char_sheet = roster_entry.character_sheet
    ritual_ids: set[int] = set()

    # 1. Walk PathRitualGrant — collect rituals for all paths in character's history
    path_ids = char_sheet.path_history.values_list("path_id", flat=True)
    if path_ids:
        ritual_ids.update(
            PathRitualGrant.objects.filter(path_id__in=path_ids).values_list("ritual_id", flat=True)
        )

    # 2. Walk TraditionRitualGrant — collect rituals for all traditions
    tradition_ids = char_sheet.character_traditions.values_list("tradition_id", flat=True)
    if tradition_ids:
        ritual_ids.update(
            TraditionRitualGrant.objects.filter(tradition_id__in=tradition_ids).values_list(
                "ritual_id", flat=True
            )
        )

    # 3. Walk DistinctionRitualGrant — collect rituals for all distinctions
    distinction_ids = char_sheet.distinctions.values_list("distinction_id", flat=True)
    if distinction_ids:
        ritual_ids.update(
            DistinctionRitualGrant.objects.filter(distinction_id__in=distinction_ids).values_list(
                "ritual_id", flat=True
            )
        )

    # 4. Walk CodexEntryRitualGrant — collect rituals for known (status=KNOWN) entries
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    known_entry_ids = CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry,
        status=CodexKnowledgeStatus.KNOWN,
    ).values_list("entry_id", flat=True)
    if known_entry_ids:
        ritual_ids.update(
            CodexEntryRitualGrant.objects.filter(codex_entry_id__in=known_entry_ids).values_list(
                "ritual_id", flat=True
            )
        )

    # 5. Create knowledge rows for all collected rituals (idempotent via get_or_create)
    for ritual_id in ritual_ids:
        CharacterRitualKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            ritual_id=ritual_id,
            defaults={"learned_from": None},
        )
