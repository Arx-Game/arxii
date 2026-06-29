"""Shared class-level advancement helpers (#1352).

Used by cross_threshold (Audere Majora) and the Ritual of the Durance to perform
the minimal level-write + cache invalidation on a character's primary class level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.progression.exceptions import (
    AdvancementRequirementsNotMet,
    OfficiantIneligibleError,
    TierBoundaryRequiresCrossing,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import CharacterClassLevel, Path
    from world.magic.models.sessions import RitualSession
    from world.magic.types.path_magic import PathMagicGrantResult
    from world.progression.models import ClassLevelAdvancement
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
    # Recompute max_health so level-derived base scales immediately. Guard with hasattr
    # because bare ObjectDB fixtures (used by some tests / non-PC NPCs) don't carry
    # the threads or combat_pulls handlers that recompute_max_health_with_threads needs.
    if hasattr(sheet.character, "threads"):
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
    """
    from world.magic.services.path_magic import grant_path_magic
    from world.progression.models import CharacterPathHistory

    CharacterPathHistory.objects.create(character=sheet.character, path=path)
    return grant_path_magic(sheet, path)


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

        testament = participant.participant_kwargs.get("testament", "")
        scene, interaction = _post_testament(inductee, testament=testament)

        apply_class_level_advance(inductee, level_after=target_level)

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
        receipts.append(receipt)

    return receipts
