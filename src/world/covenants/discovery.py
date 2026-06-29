"""Variant discovery beat: fired when a thread crosses a variant's unlock_thread_level.

Generalized from the covenant sub-role ceremony (#1578). When a thread's level
crosses a variant's ``unlock_thread_level``, the character "discovers" the
variant — receiving an Achievement (with a global-first Discovery row on the
first-ever earner), a CodexEntry unlock, and a NarrativeMessage (gamewide on
first-ever, personal otherwise).

Entry point: ``fire_variant_discoveries(*, thread, starting_level, new_level)``.

Dispatches on ``thread.target_kind`` to the variant model
(``CovenantRole`` / ``TechniqueVariant``), which supplies
``newly_crossed_variants`` (the threshold predicate) and ``discovery_narrative``
(the flavor copy + recipients). The grant/unlock/notify ceremony body is
shared and unchanged from the original sub-role beat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Thread
    from world.magic.specialization.models import AbstractSpecializedVariant


# Maintained for the existing covenant canary tests that import
# ``fire_subrole_discoveries``. New code should call ``fire_variant_discoveries``.
# TODO(#1578): drop this alias once test imports are migrated.
fire_subrole_discoveries = None  # set at module bottom after definition


def _variant_model_for(target_kind: str) -> type[AbstractSpecializedVariant] | None:
    """Return the variant model class for a Thread target_kind, or None."""
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if target_kind == TargetKind.COVENANT_ROLE:
        from world.covenants.models import CovenantRole  # noqa: PLC0415

        return CovenantRole
    if target_kind == TargetKind.GIFT:
        from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

        return TechniqueVariant
    return None


def fire_variant_discoveries(*, thread: Thread, starting_level: int, new_level: int) -> None:
    """Fire the discovery beat for any variant threshold newly crossed by this
    thread imbue. Idempotent. Dispatches on target_kind (#1578)."""
    if new_level <= starting_level:
        return

    variant_model = _variant_model_for(thread.target_kind)
    if variant_model is None:
        return

    sheet: CharacterSheet = thread.owner
    for parent in _parents_for(thread):
        newly = variant_model.newly_crossed_variants(
            parent,
            resonance_id=thread.resonance_id,
            starting_level=starting_level,
            new_level=new_level,
        )
        for variant in newly:
            _fire_one(sheet, variant)


def _parents_for(thread: Thread) -> Iterable:
    """Return the parent entities whose variants should be searched for this thread.

    - COVENANT_ROLE: the thread's ``target_covenant_role``.
    - GIFT: each ``Technique`` of the thread's ``target_gift``.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if thread.target_kind == TargetKind.COVENANT_ROLE:
        if thread.target_covenant_role_id is not None:
            return [thread.target_covenant_role]
        return []
    if thread.target_kind == TargetKind.GIFT:
        if thread.target_gift_id is not None:
            return thread.target_gift.techniques.all()
        return []
    return []


def _fire_one(sheet: CharacterSheet, variant: AbstractSpecializedVariant) -> None:
    """Run the grant/unlock/notify beat for a single newly-crossed variant."""
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415
    from world.achievements.services import grant_achievement  # noqa: PLC0415

    ach = variant.discovery_achievement
    # Idempotency gate: skip the whole beat if achievement already earned.
    # Covers re-imbue replay (same range fires again) — prevents duplicates.
    if (
        ach is not None
        and CharacterAchievement.objects.filter(
            character_sheet=sheet,
            achievement=ach,
        ).exists()
    ):
        return

    is_first = False
    if ach is not None:
        results = grant_achievement(ach, [sheet])
        is_first = bool(results and results[0].discovery_id is not None)

    _unlock_codex(sheet, variant)
    _notify(sheet, variant, is_first=is_first)


def _unlock_codex(sheet: CharacterSheet, variant: AbstractSpecializedVariant) -> None:
    """Create a CharacterCodexKnowledge(status=KNOWN) for the variant's codex_entry.

    Skips gracefully when:
    - ``variant.codex_entry`` is None (no lore entry authored for this variant), or
    - the sheet has no roster_entry (character not yet on the roster).
    """
    entry = variant.codex_entry
    if entry is None:
        return

    # CharacterCodexKnowledge is keyed on RosterEntry, not CharacterSheet.
    # sheet.roster_entry is a OneToOne reverse — may not exist.
    roster_entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL
    if roster_entry is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=entry,
        defaults={"status": CodexKnowledgeStatus.KNOWN},
    )


def _notify(sheet: CharacterSheet, variant: AbstractSpecializedVariant, *, is_first: bool) -> None:
    """Send a NarrativeMessage announcing the variant discovery.

    ``variant.discovery_narrative(is_first=...)`` returns (recipients, body).
    When ``is_first=True`` the variant returns the gamewide recipient list.
    When ``is_first=False`` the variant returns ``[]`` and we use ``[sheet]``.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    recipients, body = variant.discovery_narrative(is_first=is_first)
    if not recipients:
        recipients = [sheet]

    # Covenant sub-roles use COVENANT category; technique-form manifestations use
    # VISIONS (a mystical manifestation). NarrativeCategory has no MAGIC value
    # (verified: STORY/ATMOSPHERE/VISIONS/HAPPENSTANCE/SYSTEM/COVENANT/RENOWN/WEATHER),
    # so VISIONS is the closest existing fit for a gift-awakening beat.
    from world.covenants.models import CovenantRole  # noqa: PLC0415

    if isinstance(variant, CovenantRole):
        category = NarrativeCategory.COVENANT
    else:
        category = NarrativeCategory.VISIONS

    send_narrative_message(
        recipients=recipients,
        body=body,
        category=category,
        sender_account=None,
    )


fire_subrole_discoveries = fire_variant_discoveries
