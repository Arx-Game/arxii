"""Clue services (#1144) — acquire a clue, and the already-known check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import CharacterClue, Clue, ClueTrigger, ItemClueTrigger, RoomClue

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.captivity.models import Captivity
    from world.checks.models import CheckType
    from world.items.models import ItemInstance
    from world.predicates.predicates import CharacterPredicateContext
    from world.roster.models import RosterEntry
    from world.secrets.models import Secret


def acquire_clue(roster_entry: RosterEntry, clue: Clue) -> CharacterClue:
    """Record that a character has found a clue (idempotent).

    The single entry point acquisition surfaces (room search, triggers) call once a
    clue is surfaced to a character. Creates the held-clue row on first find and
    returns the existing one thereafter — re-finding the same clue is harmless.
    """
    held, _ = CharacterClue.objects.get_or_create(roster_entry=roster_entry, clue=clue)
    return held


# PLACEHOLDER magnitude (#1825): at most this many hub placements per counter-clue.
ACCUSATION_CLUE_HUB_CAP = 3


def create_accusation_counter_clue(secret: Secret, *, region: Area, difficulty: int) -> Clue:
    """Plant the investigable trail an accusation leaves behind (#1825). Idempotent.

    Creates (or reuses) a RESEARCH-resolution SECRET clue targeting ``secret`` and
    places it in up to ``ACCUSATION_CLUE_HUB_CAP`` of the region's social hubs at
    ``detect_difficulty=difficulty`` — the accuser's own roll sets how hard their
    trail is to unearth. Existing placements keep their original difficulty (no
    silent re-difficulty on re-runs). Clue name/description are PLACEHOLDER prose.
    """
    clue, _ = Clue.objects.get_or_create(
        target_kind=ClueTargetKind.SECRET,
        target_secret=secret,
        defaults={
            "name": "Whispers That Don't Add Up",
            "description": (
                "PLACEHOLDER Something about this rumor's shape is off — the kind of "
                "off a patient investigator could pull a thread from."
            ),
            "resolution_mode": ClueResolution.RESEARCH,
        },
    )
    for profile in _hub_profiles_in_region(region)[:ACCUSATION_CLUE_HUB_CAP]:
        RoomClue.objects.get_or_create(
            room_profile=profile,
            clue=clue,
            defaults={"detect_difficulty": difficulty},
        )
    return clue


def _hub_profiles_in_region(region: Area) -> list[RoomProfile]:
    """The social-hub room profiles whose area chain tops out at ``region``."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.services import get_ancestor_at_level  # noqa: PLC0415

    hubs = RoomProfile.objects.filter(is_social_hub=True, area__isnull=False).select_related("area")
    return [
        profile
        for profile in hubs
        if get_ancestor_at_level(profile.area, AreaLevel.REGION) == region
    ]


def target_already_known(clue: Clue, roster_entry: RosterEntry) -> bool:
    """Whether the character already has what this clue points at.

    Drives the "this clue refers to X, but you already know this" flag — discovery
    surfaces a known-target clue rather than hiding it. Dispatches on target kind.
    """
    if clue.target_kind == ClueTargetKind.CODEX:
        from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
        from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

        return CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            entry=clue.target_codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        ).exists()

    if clue.target_kind == ClueTargetKind.MISSION:
        from world.missions.models import MissionParticipant  # noqa: PLC0415

        character = roster_entry.character_sheet.character
        if character is None:
            return False
        return MissionParticipant.objects.filter(
            character=character,
            instance__template=clue.target_mission,
        ).exists()

    if clue.target_kind == ClueTargetKind.SECRET:
        from world.secrets.services import secret_known_to  # noqa: PLC0415

        return clue.target_secret is not None and secret_known_to(clue.target_secret, roster_entry)

    return False


def grant_clue_target(clue: Clue, roster_entry: RosterEntry) -> None:
    """AUTOMATIC resolution — grant a clue's target to the character on the spot.

    - CODEX: the character learns the entry (KNOWN, firing the codex reactivity hook).
    - RESCUE: the character is handed the rescue mission for the held captive.
    - SECRET: the character learns the secret's fact (#1334).
    - PERSONA_LINK: the character pierces the masked-identity pair (#2120).
    The MISSION target kind is a documented extension point.
    """
    if clue.target_kind == ClueTargetKind.CODEX:
        _grant_codex_target(clue, roster_entry)
    elif clue.target_kind == ClueTargetKind.RESCUE:
        _grant_rescue_target(clue, roster_entry)
    elif clue.target_kind == ClueTargetKind.SECRET:
        _grant_secret_target(clue, roster_entry)
    elif clue.target_kind == ClueTargetKind.PERSONA_LINK:
        _grant_persona_link_target(clue, roster_entry)


def _grant_codex_target(clue: Clue, roster_entry: RosterEntry) -> None:
    entry = clue.target_codex_entry
    if entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    knowledge, _ = CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=entry,
        defaults={"status": CodexKnowledgeStatus.UNCOVERED},
    )
    knowledge.add_progress(entry.learn_threshold)


def _grant_rescue_target(clue: Clue, roster_entry: RosterEntry) -> None:
    """Hand the discoverer the rescue mission for the clue's still-held captive (#931).

    No-op if the captivity is missing its rescue template, no longer held (already freed),
    or the discoverer has no puppet — finding a stale rescue clue is harmless.
    """
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.missions.services.run import grant_rescue_mission  # noqa: PLC0415

    captivity = clue.target_captivity
    if captivity is None or captivity.rescue_template is None:
        return
    if captivity.status != CaptivityStatus.HELD:
        return
    character = roster_entry.character_sheet.character
    if character is None:
        return
    grant_rescue_mission(captivity.rescue_template, character, captivity.captive)


def _grant_secret_target(clue: Clue, roster_entry: RosterEntry) -> None:
    """Grant the discoverer the fact of the clue's secret (#1334). No-op if untargeted."""
    secret = clue.target_secret
    if secret is None:
        return
    from world.secrets.services import grant_secret_knowledge  # noqa: PLC0415

    grant_secret_knowledge(roster_entry=roster_entry, secret=secret)


def _grant_persona_link_target(clue: Clue, roster_entry: RosterEntry) -> None:
    """Grant the discoverer a pierced masked-identity pair (#2120). No-op if untargeted.

    Records a ``PersonaDiscovery`` linking ``target_persona``/``target_persona_linked``
    for ``roster_entry``'s character sheet via ``world.scenes.services.record_persona_discovery``
    — the single writer of ``PersonaDiscovery`` rows, shared with the rolled-check path
    (``world.forms.services.identification.attempt_identification``, #1107 slice 5) so the
    pair-normalization logic lives in one place. Piercing here is GM-authored: the clue must
    exist and be planted (ADR-0033) — there is no direct "study persona" roll against an
    arbitrary masked character.
    """
    from world.scenes.services import record_persona_discovery  # noqa: PLC0415

    record_persona_discovery(
        clue.target_persona, clue.target_persona_linked, roster_entry.character_sheet
    )


def plant_rescue_clue(
    captivity: Captivity,
    room_profile: RoomProfile,
    *,
    name: str,
    description: str,
    detect_difficulty: int = 0,
) -> RoomClue:
    """Plant a discoverable rescue clue at a location for a held captive (#931 Phase 4).

    Creates a RESCUE-target ``Clue`` pointing at the captivity and places it in the room,
    so allies who search there and spot it are handed the rescue mission. The clue's text
    is authored capture-setup content (the GM's voice, or a CaptivityConfig default).
    AUTOMATIC by design — finding it grants the rescue at once.
    """
    clue = Clue.objects.create(
        target_kind=ClueTargetKind.RESCUE,
        target_captivity=captivity,
        name=name,
        description=description,
        resolution_mode=ClueResolution.AUTOMATIC,
    )
    return RoomClue.objects.create(
        room_profile=room_profile,
        clue=clue,
        detect_difficulty=detect_difficulty,
    )


def clear_rescue_clues(captivity: Captivity) -> None:
    """Delete a captivity's rescue clues (and their placements) when it resolves (#931).

    The RoomClue placements and any held CharacterClue rows cascade off the Clue, so a
    freed captive leaves no stale rescue trail to discover.
    """
    Clue.objects.filter(target_captivity=captivity).delete()


def _placement_passes_eligibility(
    placement: RoomClue,
    character: ObjectDB,
    context_holder: list,
) -> bool:
    """Return True if character passes the placement's eligibility gate.

    ``context_holder`` is a one-element list used to lazily build and cache the
    predicate context across calls within a single search sweep.
    """
    from world.predicates.predicates import evaluate  # noqa: PLC0415

    if not placement.eligibility_rule:
        return True
    if not context_holder:
        context_holder.append(_predicate_context(character))
    return evaluate(placement.eligibility_rule, context_holder[0])


def search_room(
    character: ObjectDB,
    room_profile: RoomProfile,
    search_check_type: CheckType,
) -> list[Clue]:
    """Search a room: roll ``search_check_type`` against each hidden clue's difficulty.

    Surfaces and acquires every not-yet-held clue the character spots (a success against
    its ``detect_difficulty``); AUTOMATIC clues also grant their target immediately. The
    caller (the Search action) charges AP + fatigue and resolves which check type to use.
    Returns the clues found this search (empty if the searcher has no roster entry).
    """
    from world.checks.services import perform_check  # noqa: PLC0415

    roster_entry = _roster_entry_for(character)
    if roster_entry is None:
        return []
    held_ids = set(
        CharacterClue.objects.filter(roster_entry=roster_entry).values_list("clue_id", flat=True)
    )
    found: list[Clue] = []
    context_holder: list = []
    placements = RoomClue.objects.filter(room_profile=room_profile, is_active=True).select_related(
        "clue"
    )
    for placement in placements:
        clue = placement.clue
        if clue.pk in held_ids:
            continue
        if not _placement_passes_eligibility(placement, character, context_holder):
            continue
        result = perform_check(
            character, search_check_type, target_difficulty=placement.detect_difficulty
        )
        if result.outcome is None or result.outcome.success_level < 0:
            continue
        acquire_clue(roster_entry, clue)
        if clue.resolution_mode == ClueResolution.AUTOMATIC:
            grant_clue_target(clue, roster_entry)
        found.append(clue)
    return found


def _predicate_context(character: ObjectDB) -> CharacterPredicateContext:
    """Build the predicate context for ``character`` (mask-aware, like missions).

    Resolves the presented persona so persona-keyed leaves gate on the right identity;
    a sheet-less / primary-persona-less character yields ``None`` (those leaves then
    fail closed), matching the mission trigger-dispatch convention.
    """
    from world.predicates.predicates import CharacterPredicateContext  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        persona = persona_for_character(character)
    except MissingPrimaryPersonaError:
        persona = None
    return CharacterPredicateContext(character, presented_persona=persona)


def _roster_entry_for(character: ObjectDB) -> RosterEntry | None:
    """The searching character's roster entry, or None (off-roster / sheet-less)."""
    try:
        return character.sheet_data.roster_entry
    except (AttributeError, ObjectDoesNotExist):
        return None


def maybe_grant_clue_triggers(character: ObjectDB, room: ObjectDB) -> list[Clue]:
    """Grant clues triggered passively by entering ``room`` (#1160).

    For each active trigger in the room the character is eligible for (empty rule = anyone)
    and has not already held, acquire the clue, resolve it (AUTOMATIC), and tell the player
    via its authored description. Returns the clues granted. Best-effort entry point — called
    from the movement hook, wrapped so a hiccup never breaks movement; the cheap "any
    triggers here?" query short-circuits ordinary rooms.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    try:
        room_profile = room.room_profile
    except (AttributeError, RoomProfile.DoesNotExist):
        return []
    triggers = list(
        ClueTrigger.objects.filter(room_profile=room_profile, is_active=True).select_related("clue")
    )
    if not triggers:
        return []
    roster_entry = _roster_entry_for(character)
    if roster_entry is None:
        return []
    return _grant_triggered_clues(character, roster_entry, triggers)


def maybe_grant_item_acquisition_clues(character: ObjectDB, item: ItemInstance) -> list[Clue]:
    """Grant clues triggered passively by ``character`` acquiring ``item`` (#1160).

    The item-anchored sibling of ``maybe_grant_clue_triggers``: for each active
    ``ItemClueTrigger`` on the acquired item's template the character is eligible for and
    hasn't already held, acquire the clue, resolve it (AUTOMATIC), and notify. Best-effort
    entry point — called from the inventory give/pick-up chokepoint (after commit, wrapped)
    so a hiccup never breaks the transfer; the cheap "any triggers for this kind?" query
    short-circuits ordinary items.
    """
    triggers = list(
        ItemClueTrigger.objects.filter(
            item_template_id=item.template_id, is_active=True
        ).select_related("clue")
    )
    if not triggers:
        return []
    roster_entry = _roster_entry_for(character)
    if roster_entry is None:
        return []
    return _grant_triggered_clues(character, roster_entry, triggers)


def _grant_triggered_clues(
    character: ObjectDB,
    roster_entry: RosterEntry,
    triggers: Sequence[ClueTrigger | ItemClueTrigger],
) -> list[Clue]:
    """Grant each trigger's clue to an eligible, not-yet-holding character (#1160).

    Shared by the room-entry and item-acquisition trigger paths. Each row exposes ``.clue``
    and ``.eligibility_rule``; the predicate context is built lazily, only when a gated
    trigger is actually hit. Held clues are skipped (idempotent), AUTOMATIC clues resolve
    their target on the spot, and each grant is announced to the player.
    """
    from world.predicates.predicates import evaluate  # noqa: PLC0415

    held_ids = set(
        CharacterClue.objects.filter(roster_entry=roster_entry).values_list("clue_id", flat=True)
    )
    context = None
    granted: list[Clue] = []
    for trigger in triggers:
        clue = trigger.clue
        if clue.pk in held_ids:
            continue
        if trigger.eligibility_rule:
            if context is None:
                context = _predicate_context(character)
            if not evaluate(trigger.eligibility_rule, context):
                continue
        acquire_clue(roster_entry, clue)
        if clue.resolution_mode == ClueResolution.AUTOMATIC:
            grant_clue_target(clue, roster_entry)
        _notify_clue_found(roster_entry, clue)
        granted.append(clue)
    return granted


def _notify_clue_found(roster_entry: RosterEntry, clue: Clue) -> None:
    """Tell the player a passive trigger revealed a clue (its authored description).

    The clue is already granted before this runs, so a notification failure must not undo
    the grant — but we log it rather than swallow it, so a real fault stays visible.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    try:
        send_narrative_message(
            recipients=[roster_entry.character_sheet],
            body=clue.description,
            category=NarrativeCategory.HAPPENSTANCE,
            ooc_note=f"Surfaced by a clue trigger (clue #{clue.pk}).",
        )
    except Exception as exc:  # noqa: BLE001 — best-effort notify; capture, don't propagate
        from world.player_submissions.services import report_error  # noqa: PLC0415

        report_error(exc, label="clue_found_notification")
