"""Codex service functions.

Granting entries to characters, and link resolution for inline ``[[wikilink]]``
cross-references in codex entry content fields.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge, CodexEntry, CodexEntryFiling

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.codex.models import CodexSubject
    from world.magic.models import Technique
    from world.roster.models import RosterEntry, RosterTenure

#: Regex matching ``[[Entry Name]]`` wikilink syntax in content fields.
#: Captures everything between the brackets (excluding closing brackets).
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def grant_codex_entry(
    roster_entry: RosterEntry,
    entry: CodexEntry,
    *,
    learned_from: RosterTenure | None = None,
) -> tuple[CharacterCodexKnowledge, bool]:
    """Grant ``entry`` to ``roster_entry`` as fully KNOWN. Idempotent.

    **Every caller that means "this character now knows this" must come through
    here rather than creating a ``CharacterCodexKnowledge`` row itself.** The
    KNOWN transition is not just a column value: it stamps ``learned_at`` and
    fires the stories reactivity hook so ``CODEX_ENTRY_UNLOCKED`` beats
    re-evaluate. That hook lives on ``CharacterCodexKnowledge.add_progress``,
    which #939 chose deliberately — "a separate service wrapper used to carry
    the hook and every caller bypassed it; reactivity now lives on the only
    path".

    The bypass came back anyway (#2880), because ``add_progress`` returns early
    unless the row is UNCOVERED, and seven callers were creating rows with
    ``status=KNOWN`` directly: all six character-creation grants (beginnings,
    path, distinction, tradition, species, gift resonance) and the crossing
    ceremony. Those characters got the column value and neither the timestamp
    nor the hook. So this wrapper does not set the status itself — it opens the
    row UNCOVERED and pushes progress past the threshold, which is the same
    thing clue research already did, and which keeps the transition on the one
    path that carries the reactivity.

    Returns ``(knowledge, newly_known)``; ``newly_known`` is False when the
    character already knew the entry, which is what makes repeat calls safe.

    On ``newly_known``, fires ``achievements.discovery.announce_access_change`` (the same
    discovery/achievement ceremony a learned Technique gets — gated on a live, non-staff
    tenure and excluded for CG-catalog content, see ``announce_access_change``) and
    increments the ``codex.entries_learned`` stat (#2899).

    **Not for "the character can now start researching this."** Two callers
    deliberately create UNCOVERED rows and must keep doing so: the
    ``GRANT_CODEX`` consequence effect (a scene hands you a lead, not the
    answer) and ``CodexTeachingOffer.accept`` (the learner has paid AP and now
    has to make progress).
    """
    knowledge, _ = CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=entry,
        defaults={
            "status": CodexKnowledgeStatus.UNCOVERED,
            "learned_from": learned_from,
        },
    )
    newly_known = knowledge.add_progress(entry.learn_threshold)
    if newly_known:
        from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
        from world.achievements.discovery import announce_access_change  # noqa: PLC0415
        from world.achievements.models import StatDefinition  # noqa: PLC0415

        announce_access_change(
            roster_entry.character_sheet,
            gained=[entry],
            lost=[],
            source=AccessChangeSource.CODEX_LEARNING,
        )
        stat_def, _ = StatDefinition.objects.get_or_create(
            key="codex.entries_learned",
            defaults={
                "name": "Entries Learned",
                "description": "Total codex entries this character has fully learned.",
            },
        )
        roster_entry.character_sheet.stats.increment(stat_def)
        announce_opened_techniques(roster_entry.character_sheet, entry)
    return knowledge, newly_known


def techniques_opened_by(sheet: CharacterSheet, entry: CodexEntry) -> list[Technique]:
    """Techniques ``entry`` opens for ``sheet``: learnable now that it is known (#4501).

    A technique whose ``CodexKnowledgeRequirement`` names ``entry``, that the character does
    not already know, whose gift they hold, and whose every other prerequisite they meet.
    Not an ultimate (only Audere reaches one). Call after the entry is KNOWN: the codex
    requirement itself is then met, which is the point.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.gift_acquisition import resolve_owned_gift  # noqa: PLC0415
    from world.progression.services.spends import (  # noqa: PLC0415
        check_requirements_for_technique,
    )

    candidates = [
        req.technique
        for req in gated_technique_requirements(entry).select_related("technique__gift")
        if not req.technique.is_ultimate
    ]
    known_ids = set(
        CharacterTechnique.objects.filter(character=sheet, technique__in=candidates).values_list(
            "technique_id", flat=True
        )
    )
    opened: list[Technique] = []
    for technique in dict.fromkeys(candidates):
        if technique.pk in known_ids or resolve_owned_gift(sheet, technique.gift) is None:
            continue
        # One check per candidate; an entry opens a handful of techniques at most.
        met, _failed = check_requirements_for_technique(sheet.character, technique)
        if met:
            opened.append(technique)
    return opened


def _taught_by_sentence(technique: Technique) -> str:
    from world.magic.services.technique_acquisition import (  # noqa: PLC0415
        technique_teaching_sources,
    )

    sources = technique_teaching_sources(technique)
    if not sources.is_taught:
        return "Nobody teaches it right now."
    parts = []
    if sources.academy_names:
        parts.append("Taught by: " + ", ".join(sources.academy_names) + ".")
    if sources.player_teacher_count:
        plural = "s" if sources.player_teacher_count != 1 else ""
        parts.append(f"{sources.player_teacher_count} player teacher{plural} offering it.")
    else:
        parts.append("No player teacher offers it right now.")
    return " ".join(parts)


def announce_opened_techniques(sheet: CharacterSheet, entry: CodexEntry) -> None:
    """Tell the player which techniques a newly KNOWN entry opens, and where each is taught.

    Every route that makes an entry known comes through ``grant_codex_entry``, so a trial, a
    pledge answer and a clue all get this notice (#4501). Silent when it opens nothing.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    opened = techniques_opened_by(sheet, entry)
    if not opened:
        return
    lines = [
        f"This opens a technique: {technique.name} ({technique.gift.name}). "
        f"{_taught_by_sentence(technique)}"
        for technique in opened
    ]
    send_narrative_message(
        recipients=[sheet],
        body=" ".join(lines),
        category=NarrativeCategory.ABILITY,
        sender_account=None,
    )


def entry_gates_technique(entry: CodexEntry) -> bool:
    """True when some technique's learning requires ``entry`` to be KNOWN (#4501)."""
    return gated_technique_requirements(entry).exists()


def gated_technique_requirements(entry: CodexEntry):
    """The active technique-learning requirements that name ``entry`` (#4501)."""
    from world.progression.models import CodexKnowledgeRequirement  # noqa: PLC0415

    return CodexKnowledgeRequirement.objects.filter(
        codex_entry=entry, technique__isnull=False, is_active=True
    )


def file_entry_under(
    entry: CodexEntry,
    subject: CodexSubject,
    *,
    sort_order: int = 0,
) -> CodexEntryFiling:
    """Cross-list ``entry`` in ``subject``'s listing, in addition to its home.

    ``subject`` must not be ``entry.subject`` (the entry's canonical home) -
    filing an entry under its own home is a no-op mistake, not data, so it
    raises ``ValidationError`` instead of silently succeeding or creating a
    row that duplicates the entry's own listing.

    Idempotent: filing the same ``(entry, subject)`` pair twice returns the
    existing row rather than raising ``IntegrityError``. A filing is a link,
    not an event - a second caller wanting the same cross-listing gets the
    same row, not a conflict.
    """
    if subject.pk == entry.subject_id:
        msg = "Cannot file an entry under its own canonical subject."
        raise ValidationError(msg)
    filing, _ = CodexEntryFiling.objects.get_or_create(
        entry=entry,
        subject=subject,
        defaults={"sort_order": sort_order},
    )
    return filing


def unfile_entry(entry: CodexEntry, subject: CodexSubject) -> None:
    """Remove ``entry``'s filing under ``subject``, if any. No-op otherwise."""
    CodexEntryFiling.objects.filter(entry=entry, subject=subject).delete()


def resolve_codex_links(
    content: str | None,
    subject: CodexSubject,
    roster_entries: Sequence[RosterEntry],
) -> list[dict]:
    """Parse ``[[Entry Name]]`` wikilinks from content and resolve to link refs.

    Args:
        content: The raw ``lore_content`` or ``mechanics_content`` text.
        subject: The ``CodexSubject`` of the entry the content belongs to.
            Used for same-subject preference in name resolution.
        roster_entries: The reader's selected roster entries (all the
            account's characters, or one when the codex is scoped to a
            single character); empty for anonymous users. Controls access
            checking -- an entry any of them KNOWs is accessible.

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
    ``status=KNOWN`` for any of the roster_entries. With none, only
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
        if roster_entries:
            known_ids = set(
                CodexEntry.objects.filter(
                    pk__in=all_candidate_ids,
                    character_knowledge__roster_entry__in=roster_entries,
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


def active_member_roster_entries(organization) -> list:
    """The roster entries of an organization's active members (#3780)."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    memberships = OrganizationMembership.objects.filter(
        organization=organization, left_at__isnull=True, exiled_at__isnull=True
    ).select_related("persona__character_sheet")
    entries = []
    for membership in memberships:
        roster_entry = membership.persona.character_sheet.roster_entry_or_none
        if roster_entry is not None:
            entries.append(roster_entry)
    return entries


def grant_organization_entry_to_members(grant) -> int:
    """Hand an ``OrganizationCodexGrant``'s entry to every current member; returns
    how many first learned it (#3780)."""
    return grant_to_current_holders(grant)


def apply_organization_codex_grants(membership) -> int:
    """A new member learns everything their organization grants (#3780). Called
    from ``societies.membership_services.join_organization``. Returns how many
    entries were newly learned."""
    from world.codex.models import OrganizationCodexGrant  # noqa: PLC0415

    roster_entry = membership.persona.character_sheet.roster_entry_or_none
    if roster_entry is None:
        return 0
    learned = 0
    for grant in OrganizationCodexGrant.objects.filter(
        organization=membership.organization
    ).select_related("entry"):
        _, created = grant_codex_entry(roster_entry, grant.entry)
        learned += int(created)
    return learned


def grant_to_current_holders(grant) -> int:
    """Hand a grant row's entry to everyone already in its group (#3775).

    Works for every grant kind (beginnings, tradition, path, distinction,
    organization): the row knows its holders through ``holder_roster_entries``.
    Returns how many characters first learned the entry. Idempotent, because
    ``grant_codex_entry`` is.
    """
    learned = 0
    for roster_entry in grant.holder_roster_entries():
        _, created = grant_codex_entry(roster_entry, grant.entry)
        learned += int(created)
    return learned


def species_holder_roster_entries(entry: CodexEntry) -> list:
    """Roster entries of every character whose species lineage owns ``entry`` (#3775).

    Species have no grant table: ``Species.codex_entry`` plus ``Species.lineage``
    decide what a species character is owed (``_finalize_species_codex``).
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415

    owners = Species.objects.filter(codex_entry=entry)
    if not owners.exists():
        return []
    entries = []
    sheets = CharacterSheet.objects.filter(species__isnull=False).select_related(
        "species", "roster_entry"
    )
    for sheet in sheets:
        if entry in sheet.species.codex_entries:
            roster_entry = sheet.roster_entry_or_none
            if roster_entry is not None:
                entries.append(roster_entry)
    return entries


def grant_entry_to_species_holders(entry: CodexEntry) -> int:
    """Hand a species-owned entry to every character of that species (#3775)."""
    learned = 0
    for roster_entry in species_holder_roster_entries(entry):
        _, created = grant_codex_entry(roster_entry, entry)
        learned += int(created)
    return learned
