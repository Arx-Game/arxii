"""Shared discovery-announcement helpers for the achievements system.

Two entry points:

``announce_achievement`` — sends one NarrativeMessage for an achievement ceremony:
gamewide (all active player sheets) when ``is_first`` else personal (earners only).
The caller supplies both message bodies; the discoverer is never named in the
first-ever body.

``announce_access_change`` — notifies a character about techniques/capabilities
gained or lost from any source, then fires first-ever discovery for each gained item
that carries a non-null ``discovery_achievement`` FK.  Capability handling is
identical regardless of source — never branch on covenant (spec Decision 11).
"""

from world.achievements.constants import AccessChangeSource
from world.achievements.services import grant_achievement


def announce_achievement(
    earners,
    *,
    is_first,
    first_body,
    personal_body,
    category,
):
    """Send the gamewide-vs-personal achievement ceremony message.

    First-ever (``is_first``): gamewide to every active player character sheet,
    using ``first_body`` (which must NOT name the discoverer). Otherwise:
    personal, to ``earners``, using ``personal_body``.
    """
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if is_first:
        from world.roster.selectors import active_player_character_sheets  # noqa: PLC0415

        recipients = active_player_character_sheets()
        body = first_body
    else:
        recipients = list(earners)
        body = personal_body
    send_narrative_message(recipients=recipients, body=body, category=category, sender_account=None)


def _names(items):
    """Return a comma-separated display string of item names."""
    return ", ".join(i.name for i in items)


def announce_access_change(character_sheet, *, gained, lost, source):
    """Tell the player about techniques/capabilities gained/lost from any source,
    and fire first-ever Discovery for each gained item that is discoverable.

    ``gained``/``lost``: content instances (Techniques and/or CapabilityTypes),
    mixed, from any mechanism. Capability handling is identical regardless of
    source — never branch on covenant (spec Decision 11).
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    lead = AccessChangeSource(source).label
    parts = []
    if gained:
        parts.append(f"Through {lead}, you can now use: {_names(gained)}.")
    if lost:
        parts.append(f"You can no longer use: {_names(lost)}.")
    if parts:
        send_narrative_message(
            recipients=[character_sheet],
            body=" ".join(parts),
            category=NarrativeCategory.ABILITY,
            sender_account=None,
        )
    if not _ceremony_eligible(character_sheet):
        return

    excluded_ids = _cg_catalog_exclusions(gained)

    for item in gained:
        # Only DiscoverableContent subclasses carry discovery_achievement;
        # CapabilityType grants never do.
        from world.achievements.models import DiscoverableContent  # noqa: PLC0415

        ach = item.discovery_achievement if isinstance(item, DiscoverableContent) else None
        if ach is None or item.pk in excluded_ids:
            continue
        from world.achievements.models import CharacterAchievement  # noqa: PLC0415

        if CharacterAchievement.objects.filter(
            achievement=ach, character_sheet=character_sheet
        ).exists():
            continue
        is_first = not CharacterAchievement.objects.filter(achievement=ach).exists()
        grant_achievement(ach, [character_sheet])
        name = item.name
        announce_achievement(
            [character_sheet],
            is_first=is_first,
            first_body=(
                f"For the first time in recorded history, a character has manifested {name}."
            ),
            personal_body=f"You have manifested {name}.",
            category=NarrativeCategory.ABILITY,
        )


def _ceremony_eligible(character_sheet):
    """Whether ``character_sheet`` can trigger the discovery/achievement ceremony.

    Requires a current, non-staff RosterTenure. A sheet mid-character-creation (no
    RosterEntry yet), a GM-created sheet sitting untenured on the Available roster,
    or one piloted by a staff account never fires the ceremony — the plain
    gained/lost narrative message above this check is unaffected (#2899).
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415

    roster_entry = character_sheet.roster_entry_or_none
    tenure = roster_entry.current_tenure if roster_entry is not None else None
    if tenure is None:
        return False
    return not is_staff_observer(tenure.player_data.account)


def _cg_catalog_exclusions(gained):
    """Pks of ``gained`` items reachable through a CG catalog table.

    Common knowledge — nearly every character reaches this content automatically at
    character creation, so it never fires the discovery ceremony regardless of the
    route (CG grant, research, teaching) or timing used to reach it (#2899).
    """
    from world.codex.models import CodexEntry  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    codex_ids = [item.pk for item in gained if isinstance(item, CodexEntry)]
    technique_ids = [item.pk for item in gained if isinstance(item, Technique)]
    excluded = set()
    if codex_ids:
        excluded |= _cg_catalog_codex_entry_ids(codex_ids)
    if technique_ids:
        excluded |= _cg_catalog_technique_ids(technique_ids)
    return excluded


def _cg_catalog_codex_entry_ids(entry_ids):
    """Entries granted by a Beginning/Tradition/Path/Distinction/Species/Resonance."""
    from django.db.models import Q  # noqa: PLC0415

    from world.codex.models import CodexEntry  # noqa: PLC0415

    return set(
        CodexEntry.objects.filter(pk__in=entry_ids)
        .filter(
            Q(beginnings_grants__isnull=False)
            | Q(tradition_grants__isnull=False)
            | Q(path_grants__isnull=False)
            | Q(distinction_grants__isnull=False)
            | Q(species__isnull=False)
            | Q(resonances__isnull=False)
        )
        .values_list("pk", flat=True)
        .distinct()
    )


def _cg_catalog_technique_ids(technique_ids):
    """Techniques in a Path's starter pool or a Tradition's special-technique set."""
    from django.db.models import Q  # noqa: PLC0415

    from world.magic.models import Technique  # noqa: PLC0415

    return set(
        Technique.objects.filter(pk__in=technique_ids)
        .filter(
            Q(granted_by_path_gifts__isnull=False) | Q(granted_by_tradition_gifts__isnull=False)
        )
        .values_list("pk", flat=True)
        .distinct()
    )
