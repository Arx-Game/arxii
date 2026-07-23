"""Shared class-level advancement helpers (#1352).

Used by cross_threshold (Audere Majora) and the Ritual of the Durance to perform
the minimal level-write + cache invalidation on a character's primary class level.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.progression.exceptions import (
    AdvancementRequirementsNotMet,
    AdvancementUnlockNotPurchasedError,
    NoDuranceSiteError,
    OfficiantIneligibleError,
    PathAlreadySelectedError,
    TierBoundaryRequiresCrossing,
)

# Service-function path that the Ritual of the Durance's Ritual row references.
# Defined here (the literal string is this module's own function) so the constant
# can be used both in convene_durance_at_site and in tests.
_DURANCE_SERVICE_PATH = "world.progression.services.advancement.advance_class_level_via_session"

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import CharacterClassLevel, Path
    from world.magic.models.sessions import RitualSession, RitualSessionParticipant
    from world.magic.types.path_magic import PathMagicGrantResult
    from world.progression.models import (
        CharacterPathHistory,
        ClassLevelAdvancement,
        ClassLevelUnlock,
    )
    from world.scenes.models import Interaction, Scene


def primary_class_level(character: ObjectDB) -> CharacterClassLevel | None:  # noqa: OBJECTDB_PARAM
    """Return the primary CharacterClassLevel, or the highest-level row, else None.

    Priority:
    1. The row marked is_primary=True.
    2. The row with the highest ``level`` value (when no primary is set).
    3. None when the character has no CharacterClassLevel rows at all.
    """
    from world.classes.models import CharacterClassLevel as _CharacterClassLevel

    primary = _CharacterClassLevel.objects.filter(character=character, is_primary=True).first()
    if primary is not None:
        return primary
    return _CharacterClassLevel.objects.filter(character=character).order_by("-level").first()


def apply_class_level_advance(sheet: CharacterSheet, *, level_after: int) -> None:
    """Write ``level_after`` to the primary CharacterClassLevel and invalidate the sheet cache.

    Pure level-write + cache invalidation — no receipt creation, no scene side-effects.
    Those belong to the caller (cross_threshold or the Durance action).

    No-op when the character has no CharacterClassLevel rows.
    """
    cl = primary_class_level(sheet.character)
    if cl is not None:
        cl.level = level_after
        cl.save(update_fields=["level"])
    sheet.invalidate_class_level_cache()
    # Recompute max_health so level-derived base scales immediately. Every character
    # with a CharacterSheet is a real typeclassed Character (via create_character_with_sheet
    # / CharacterFactory), so the threads + combat_pulls handlers always exist. The
    # former hasattr guard was a workaround for bare-ObjectDB test fixtures, which have
    # since been migrated to CharacterFactory (#1367).
    from world.magic.services.threads import recompute_max_health_with_threads

    recompute_max_health_with_threads(sheet)


def cross_into_path(sheet: CharacterSheet, path: Path) -> PathMagicGrantResult:
    """Switch ``sheet`` onto ``path`` and grant that path's magic (#1579).

    The single in-play path-change seam: writes the ``CharacterPathHistory`` row and
    fires ``grant_path_magic`` so a path change always carries its gift + technique
    grants (you cannot switch path and forget to grant). Used by both the Audere
    Majora crossing (``cross_threshold``, levels 5/10/15/20) and the Ritual of the
    Durance POTENTIAL-stage semi-crossing (level 3, no Audere Majora). Returns the
    ``PathMagicGrantResult``.

    Raises ``PathRequirementsNotMet`` (#2538) when the path has authored
    TraitRequirements the character does not meet. The semi-crossing resolver
    catches this for a non-breaking level-only advance; Audere Majora lets it
    propagate, rolling back the crossing.
    """
    from world.magic.services.path_magic import grant_path_magic
    from world.progression.models import CharacterPathHistory
    from world.progression.services.spends import check_requirements_for_path

    met, failed_messages = check_requirements_for_path(sheet.character, path)
    if not met:
        from world.progression.exceptions import PathRequirementsNotMet

        raise PathRequirementsNotMet(path_name=path.name, failed_messages=failed_messages)

    CharacterPathHistory.objects.create(character=sheet, path=path)
    return grant_path_magic(sheet, path)


def select_initial_path(character: ObjectDB, path: Path) -> CharacterPathHistory:  # noqa: OBJECTDB_PARAM
    """Late-selection recovery: write the first CharacterPathHistory row (#2121).

    For characters created via a CG-bypassing path — GM-finalize quickstart
    (``finalize_gm_character``, which never writes ``CharacterPathHistory`` and
    has no ``can_submit()`` gate) or NPCAsset -> PC promotion
    (``world/assets/effects.py``, which calls ``create_character_with_sheet``
    directly) — ``current_path_for_character`` returns ``None``, which
    **permanently** blocks the Ritual of the Durance: ``assert_can_officiate``
    can never establish path lineage with no path on record. This is the
    one-time recovery surface.

    Deliberately mirrors the CG finalize step exactly
    (``CharacterPathHistory.objects.create`` only) — NOT ``cross_into_path``,
    which also grants the path's magic (gift + starter techniques via
    ``grant_path_magic``). That is a bigger side effect than this narrow
    recovery is meant to have; a bypassing character's magic provisioning (or
    lack of it) is a separate concern from "unblock the Durance."

    Raises:
        PathAlreadySelectedError: the character already has a
            CharacterPathHistory row — this is not a general path-change tool
            (use ``cross_into_path`` for that).
    """
    from world.progression.models import CharacterPathHistory
    from world.progression.selectors import current_path_for_character

    if current_path_for_character(character) is not None:
        raise PathAlreadySelectedError
    return CharacterPathHistory.objects.create(character=character.sheet_data, path=path)


# =============================================================================
# Ritual of the Durance — officiant guard + advancement service (#1352)
# =============================================================================


def _path_lineage_allows(officiant_sheet: CharacterSheet, inductee_sheet: CharacterSheet) -> bool:
    """Return True when the officiant shares the inductee's path lineage and is on a
    same-or-more-advanced path.

    The officiant's current path must equal the inductee's current path, or the
    inductee's current path must be an ancestor of the officiant's path reachable by
    walking ``Path.parent_paths`` upward from the officiant's path. Either case means
    "the officiant has already trodden the road the inductee now walks." If either
    character has no recorded path, lineage cannot be established → False.
    """
    from world.progression.selectors import current_path_for_character

    officiant_path = current_path_for_character(officiant_sheet.character)
    inductee_path = current_path_for_character(inductee_sheet.character)
    if officiant_path is None or inductee_path is None:
        return False
    if officiant_path.pk == inductee_path.pk:
        return True
    # Walk parent_paths upward from the officiant's path; the inductee's path must
    # appear in that ancestry (officiant evolved from the inductee's current path).
    seen: set[int] = set()
    frontier = [officiant_path]
    while frontier:
        current = frontier.pop()
        for parent in current.parent_paths.all():
            if parent.pk == inductee_path.pk:
                return True
            if parent.pk not in seen:
                seen.add(parent.pk)
                frontier.append(parent)
    return False


def assert_can_officiate(
    *,
    officiant_sheet: CharacterSheet,
    inductee_sheet: CharacterSheet,
    target_level: int,
) -> None:
    """Raise OfficiantIneligibleError unless the officiant may induct this advance.

    Two gates:
    1. Level gate (mandatory): ``officiant_sheet.current_level > target_level`` —
       the officiant must stand strictly above the level the inductee is reaching.
    2. Same-Path lineage: the officiant must share the inductee's path lineage and
       be on a same-or-more-advanced path (see ``_path_lineage_allows``).
    """
    if officiant_sheet.current_level <= target_level:
        raise OfficiantIneligibleError
    if not _path_lineage_allows(officiant_sheet, inductee_sheet):
        raise OfficiantIneligibleError


def _cite_deeds(inductee_sheet: CharacterSheet) -> str:
    """Return a short citation of the inductee's recorded deeds, or "" when none.

    Reads the primary persona's active LegendEntry rows. No-ops to an empty string
    when the sheet has no primary persona or has recorded no deeds.
    """
    from world.scenes.models import Persona

    try:
        persona = inductee_sheet.primary_persona
    except Persona.DoesNotExist:
        return ""
    titles = list(
        persona.legend_entries.filter(is_active=True)
        .order_by("-base_value")
        .values_list("title", flat=True)[:3]
    )
    if not titles:
        return ""
    return " Their deeds are remembered: " + "; ".join(titles) + "."


def _record_witnesses(
    receipt: ClassLevelAdvancement,
    scene: Scene | None,
    *,
    inductee: CharacterSheet,
    officiant: CharacterSheet,
) -> None:
    """Record the scene's attending personas as official witnesses (no boon — record only)."""
    if scene is None:
        return
    from world.societies.knowledge_services import scene_witness_personas

    excluded = {inductee.pk, officiant.pk}
    personas = [p for p in scene_witness_personas(scene) if p.character_sheet_id not in excluded]
    if personas:
        receipt.witnesses.add(*personas)


def _post_testament(
    inductee_sheet: CharacterSheet, *, testament: str
) -> tuple[Scene | None, Interaction | None]:
    """Post the testament oration as a POSE via the active-scene helper.

    Reuses ``world.magic.audere_majora._post_declaration`` (the shared active-scene
    POSE poster). Appends a citation of the inductee's recorded deeds to the oration.
    Returns ``(scene, interaction)`` — both None when no active scene exists.
    """
    from world.magic.audere_majora import _post_declaration

    oration = (testament or "").strip()
    citation = _cite_deeds(inductee_sheet)
    text = (oration + citation).strip()
    return _post_declaration(inductee_sheet.character, text)


def _eligible_child_paths_at_stage(current: Path, target_stage: int) -> dict[int, Path]:
    """Return a pk→Path dict of active child paths of *current* at *target_stage*.

    Shared by ``_resolve_declared_advanced_path`` (post-level-write, receives an
    explicit stage) and mirrors the query in ``eligible_advanced_paths_for`` in
    selectors.py (pre-fire, derives stage from current_level). Both call the same
    DB filter so the eligibility logic lives in one place.
    """
    return {p.pk: p for p in current.child_paths.filter(stage=target_stage, is_active=True)}


def _resolve_declared_advanced_path(
    inductee: CharacterSheet, participant: RitualSessionParticipant, target_stage: int
) -> Path | None:
    """The eligible advanced path the inductee chose for a semi-crossing.

    Explicit ``participant_kwargs["path_id"]`` wins; else the character's declared
    ``PathIntent``. Validated as an active child of the current path at
    ``target_stage``. Returns the Path, or None when unset/ineligible (then the
    advance is level-only — no path switch, non-breaking).
    """
    from world.progression.models import PathIntent
    from world.progression.selectors import current_path_for_character

    current = current_path_for_character(inductee.character)
    if current is None:
        return None
    eligible = _eligible_child_paths_at_stage(current, target_stage)
    if not eligible:
        return None
    path_id = participant.participant_kwargs.get("path_id")
    if path_id is None:
        intent = PathIntent.objects.filter(character_sheet=inductee).first()
        path_id = intent.intended_path_id if intent is not None else None
    if path_id is None:
        return None
    return eligible.get(int(path_id))


def _maybe_semi_cross_into_potential_path(
    inductee: CharacterSheet,
    participant: RitualSessionParticipant,
    *,
    level_before: int,
    target_level: int,
) -> None:
    """The level-3 POTENTIAL "semi-crossing" (#1579) — no Audere Majora.

    When a Durance advance enters a new path stage (past the Audere Majora
    tier-boundary refusal, that is the PROSPECT→POTENTIAL transition) and the
    inductee has declared an eligible advanced path, switch onto it and grant its
    gift+techniques through the shared ``cross_into_path`` seam — the same machinery
    a crossing uses. No-op when the advance stays within a stage or no path was
    declared.

    If the declared path has authored TraitRequirements the inductee does not meet
    (#2538), ``cross_into_path`` raises ``PathRequirementsNotMet`` — caught here for
    a non-breaking level-only advance (the level still increases, just without the
    path switch). This mirrors the existing non-breaking behavior when no path is
    declared.
    """
    from world.classes.services import stage_for_level
    from world.progression.exceptions import PathRequirementsNotMet

    new_stage = stage_for_level(target_level)
    if new_stage == stage_for_level(level_before):
        return
    new_path = _resolve_declared_advanced_path(inductee, participant, new_stage)
    if new_path is not None:
        # Non-breaking: if the path has unmet TraitRequirements (#2538), the level
        # advance still commits, just without the path switch. The eligible-paths
        # selector should have filtered this path out already, but the gate in
        # cross_into_path is the backstop.
        with contextlib.suppress(PathRequirementsNotMet):
            cross_into_path(inductee, new_path)


def _assert_unlock_purchased(character: ObjectDB, unlock: ClassLevelUnlock) -> None:  # noqa: OBJECTDB_PARAM
    """Raise AdvancementUnlockNotPurchasedError unless the XP unlock is purchased.

    Additional, independently-required gate stacked alongside
    ``check_requirements_for_unlock`` (see the "XP unlocks, never grants" ADR) —
    passing the authored requirements is necessary but not sufficient; the
    character must also hold a ``CharacterUnlock`` receipt for this exact
    (class, target_level) pair, purchased via ``progression unlock class=<id>``.
    """
    from world.progression.models import CharacterUnlock

    purchased = CharacterUnlock.objects.filter(
        character=character.sheet_data,
        character_class=unlock.character_class,
        target_level=unlock.target_level,
    ).exists()
    if not purchased:
        raise AdvancementUnlockNotPurchasedError(
            class_name=unlock.character_class.name,
            target_level=unlock.target_level,
            xp_cost=unlock.get_xp_cost_for_character(character),
        )


def convene_durance_at_site(*, inductee_sheet: CharacterSheet, room: ObjectDB) -> RitualSession:
    """Open a Durance session at a training site, with its trainer-of-record as officiant.

    Pre-checks the same gates fire would (tier boundary, authored unlock, requirements)
    so a doomed rite is refused up front with a specific message. Returns the drafted
    session; the inductee then speaks their testament via ``ritual join`` (which
    auto-fires, since the initiator is a site officiant).
    """
    from datetime import timedelta

    from django.utils import timezone

    from world.areas.services import get_room_profile
    from world.magic.audere_majora import AudereMajoraThreshold
    from world.magic.models import Ritual
    from world.magic.services.sessions import draft_session
    from world.progression.models import ClassLevelUnlock, DuranceTrainingSite
    from world.progression.services.spends import check_requirements_for_unlock

    cl = primary_class_level(inductee_sheet.character)
    if cl is None:
        raise AdvancementRequirementsNotMet(["This character has no class level to advance."])
    level_before, target_level = cl.level, cl.level + 1
    if AudereMajoraThreshold.objects.filter(boundary_level=level_before).exists():
        raise TierBoundaryRequiresCrossing
    try:
        unlock = ClassLevelUnlock.objects.get(
            character_class=cl.character_class, target_level=target_level
        )
    except ClassLevelUnlock.DoesNotExist as exc:
        raise AdvancementRequirementsNotMet(
            ["No advancement path has been authored for this level."]
        ) from exc
    met, failed = check_requirements_for_unlock(inductee_sheet.character, unlock)
    if not met:
        raise AdvancementRequirementsNotMet(failed)
    _assert_unlock_purchased(inductee_sheet.character, unlock)

    profile = get_room_profile(room)
    for site in DuranceTrainingSite.objects.filter(room_profile=profile, is_active=True):
        try:
            assert_can_officiate(
                officiant_sheet=site.officiant,
                inductee_sheet=inductee_sheet,
                target_level=target_level,
            )
        except OfficiantIneligibleError:
            continue
        ritual = Ritual.objects.get(service_function_path=_DURANCE_SERVICE_PATH)
        return draft_session(
            ritual=ritual,
            initiator=site.officiant,
            proposed_terms="",
            session_kwargs={"site_convened": "1"},
            invitee_sheets=[inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=timezone.now() + timedelta(hours=24),
        )
    raise NoDuranceSiteError


# Service-function path for the intake registration rite (new character enters the
# Durance arc, distinct from the ongoing level-advancement rite). #2479
_DURANCE_REGISTRATION_SERVICE_PATH = (
    "world.progression.services.durance_registration.register_durance_via_session"
)


def convene_durance_registration_at_site(
    *,
    inductee_sheet: CharacterSheet,
    room: ObjectDB,
) -> RitualSession:
    """Open a registration-only Durance session at the Academy training site.

    Unlike ``convene_durance_at_site``, this does NOT advance a class level. It
    registers a new Gifted into the Durance arc via the intake cohort. The
    officiant gate is relaxed because a new character has no path lineage yet.
    """
    from datetime import timedelta

    from django.utils import timezone

    from world.areas.services import get_room_profile
    from world.magic.models import Ritual
    from world.magic.services.sessions import draft_session
    from world.progression.models import DuranceTrainingSite

    profile = get_room_profile(room)
    for site in DuranceTrainingSite.objects.filter(room_profile=profile, is_active=True):
        ritual = Ritual.objects.get(service_function_path=_DURANCE_REGISTRATION_SERVICE_PATH)
        return draft_session(
            ritual=ritual,
            initiator=site.officiant,
            proposed_terms="",
            session_kwargs={"site_convened": "1", "registration": "1"},
            invitee_sheets=[inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=timezone.now() + timedelta(hours=24),
        )
    raise NoDuranceSiteError


def advance_class_level_via_session(*, session: RitualSession) -> list[ClassLevelAdvancement]:
    """Advance each ACCEPTED inductee one class level via the Ritual of the Durance.

    Dispatched by ``fire_session`` as ``fn(session=locked)`` INSIDE the session's
    transaction; if this raises, the whole fire rolls back and the session survives.
    No outer ``transaction.atomic`` is opened here (the caller holds one).

    Convention (matches the covenant precedent): the **officiant** is
    ``session.initiator``; the **inductees** are the ACCEPTED participants whose
    ``character_sheet`` is not the initiator.

    Per inductee, in order:
    1. Resolve the primary class level → ``target_level = level + 1``.
    2. Refuse a tier boundary (an ``AudereMajoraThreshold`` row at ``level_before``)
       with ``TierBoundaryRequiresCrossing``.
    3. Officiant guard (``assert_can_officiate``).
    4. Resolve the authored ``ClassLevelUnlock`` and check its requirements; an
       absent unlock or unmet requirements raise ``AdvancementRequirementsNotMet``.
    4b. Require the purchased XP unlock (``CharacterUnlock``) for this exact
        (class, target_level) — an *additional*, independently-required gate
        stacked alongside step 4's requirements (see the "XP unlocks, never
        grants" ADR); missing it raises ``AdvancementUnlockNotPurchasedError``.
    5. Post the testament oration (with cited deeds) as a POSE in the active scene.
    6. Apply the level write and create the ``ClassLevelAdvancement`` receipt.

    Several inductees share the one scene; each gets its own receipt. Returns the
    list of created receipts.
    """
    from world.magic.audere_majora import AudereMajoraThreshold
    from world.magic.constants import ParticipantState
    from world.progression.models import ClassLevelAdvancement, ClassLevelUnlock
    from world.progression.services.spends import check_requirements_for_unlock

    officiant_sheet = session.initiator

    accepted = session.participants.filter(state=ParticipantState.ACCEPTED)
    inductees = [p for p in accepted if p.character_sheet_id != session.initiator_id]

    receipts: list[ClassLevelAdvancement] = []
    for participant in inductees:
        inductee = participant.character_sheet
        cl = primary_class_level(inductee.character)
        if cl is None:
            raise AdvancementRequirementsNotMet(["This character has no class level to advance."])
        level_before = cl.level
        target_level = cl.level + 1
        character_class = cl.character_class

        # Tier-boundary refusal: a threshold row keyed at this step's level_before
        # means the next step crosses into a new tier — Audere Majora territory.
        if AudereMajoraThreshold.objects.filter(boundary_level=level_before).exists():
            raise TierBoundaryRequiresCrossing

        assert_can_officiate(
            officiant_sheet=officiant_sheet,
            inductee_sheet=inductee,
            target_level=target_level,
        )

        try:
            unlock = ClassLevelUnlock.objects.get(
                character_class=character_class,
                target_level=target_level,
            )
        except ClassLevelUnlock.DoesNotExist as exc:
            raise AdvancementRequirementsNotMet(
                ["No advancement path has been authored for this level."]
            ) from exc

        met, failed = check_requirements_for_unlock(inductee.character, unlock)
        if not met:
            raise AdvancementRequirementsNotMet(failed)
        _assert_unlock_purchased(inductee.character, unlock)

        testament = participant.participant_kwargs.get("testament", "")
        scene, interaction = _post_testament(inductee, testament=testament)

        apply_class_level_advance(inductee, level_after=target_level)

        # Level-3 POTENTIAL semi-crossing: if this advance enters a new path stage and
        # the inductee declared an eligible advanced path, switch onto it + grant its
        # magic (the same seam Audere Majora uses; no crossing ceremony) (#1579).
        _maybe_semi_cross_into_potential_path(
            inductee, participant, level_before=level_before, target_level=target_level
        )

        receipt = ClassLevelAdvancement.objects.create(
            character_sheet=inductee,
            character_class=character_class,
            officiant=officiant_sheet,
            ritual=session.ritual,
            scene=scene,
            declaration_interaction=interaction,
            level_before=level_before,
            level_after=target_level,
        )
        _record_witnesses(receipt, scene, inductee=inductee, officiant=officiant_sheet)
        receipts.append(receipt)

    return receipts
