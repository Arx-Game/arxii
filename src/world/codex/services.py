"""Codex service functions.

Link resolution for inline ``[[wikilink]]`` cross-references in codex entry
content fields.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CodexEntry

if TYPE_CHECKING:
    from world.codex.models import CodexSubject
    from world.roster.models import RosterEntry

#: Regex matching ``[[Entry Name]]`` wikilink syntax in content fields.
#: Captures everything between the brackets (excluding closing brackets).
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def resolve_codex_links(
    content: str | None,
    subject: CodexSubject,
    roster_entry: RosterEntry | None,
) -> list[dict]:
    """Parse ``[[Entry Name]]`` wikilinks from content and resolve to link refs.

    Args:
        content: The raw ``lore_content`` or ``mechanics_content`` text.
        subject: The ``CodexSubject`` of the entry the content belongs to.
            Used for same-subject preference in name resolution.
        roster_entry: The reader's active roster entry, or ``None`` for
            anonymous users. Controls access checking.

    Returns:
        A list of dicts, one per wikilink found, in order of appearance::

            {
                "match_text": "[[Shrouded Veil]]",   # raw [[...]] text
                "entry_id": 42,                       # null if not found/inaccessible
                "display_text": "Shrouded Veil",     # entry name, "???", or raw text
                "accessible": True,                  # whether reader can view the entry
            }

    Resolution order for each link text:
        1. Same-subject match (entry in *subject* with matching name).
        2. Global match (any entry with matching name, first by display_order).
        3. No match (typo or not-yet-created entry).

    Three display_text cases:
        - **Accessible** (entry found, reader can view): real entry name.
        - **Inaccessible** (entry found, reader cannot view): ``"???"`` — the
          entry name is never exposed.
        - **No match** (no entry with that name): raw link text, so authors can
          spot typos.

    Name matching is case-sensitive (matches ``CharField`` ``__exact`` lookup).
    ``[[shrouded veil]]`` will NOT match an entry named ``"Shrouded Veil"``.

    Access check: ``is_public=True`` OR ``CharacterCodexKnowledge`` with
    ``status=KNOWN`` for the roster_entry. If no roster_entry, only
    ``is_public`` entries are accessible.
    """
    if not content:
        return []

    link_texts: list[str] = [match.group(1) for match in WIKILINK_RE.finditer(content)]

    if not link_texts:
        return []

    # Batch-fetch all candidate entries matching any link text.
    # Same-subject entries are preferred, so fetch them separately.
    same_subject_entries = {
        e.name: e for e in CodexEntry.objects.filter(subject=subject, name__in=link_texts)
    }
    same_subject_ids = set(same_subject_entries.values())
    global_entries = {
        e.name: e
        for e in CodexEntry.objects.filter(name__in=link_texts).exclude(
            pk__in=[e.pk for e in same_subject_ids]
        )
    }

    # Build the set of accessible entry IDs for this reader.
    all_candidate_ids = [e.pk for e in {**same_subject_entries, **global_entries}.values()]
    accessible_ids: set[int] = set()
    if all_candidate_ids:
        public_ids = set(
            CodexEntry.objects.filter(pk__in=all_candidate_ids, is_public=True).values_list(
                "pk", flat=True
            )
        )
        accessible_ids = public_ids
        if roster_entry is not None:
            known_ids = set(
                CodexEntry.objects.filter(
                    pk__in=all_candidate_ids,
                    character_knowledge__roster_entry=roster_entry,
                    character_knowledge__status=CodexKnowledgeStatus.KNOWN,
                ).values_list("pk", flat=True)
            )
            accessible_ids |= known_ids

    results: list[dict] = []
    for match in WIKILINK_RE.finditer(content):
        raw_text = match.group(1)
        match_text = match.group(0)

        entry = same_subject_entries.get(raw_text) or global_entries.get(raw_text)

        if entry is None:
            # No match — typo or not-yet-created entry. Show raw text so
            # authors can spot the problem.
            results.append(
                {
                    "match_text": match_text,
                    "entry_id": None,
                    "display_text": raw_text,
                    "accessible": False,
                }
            )
        elif entry.pk in accessible_ids:
            results.append(
                {
                    "match_text": match_text,
                    "entry_id": entry.pk,
                    "display_text": entry.name,
                    "accessible": True,
                }
            )
        else:
            # Entry exists but reader can't access it. Never expose the name.
            results.append(
                {
                    "match_text": match_text,
                    "entry_id": None,
                    "display_text": "???",
                    "accessible": False,
                }
            )

    return results
