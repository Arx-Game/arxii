"""Prayers and visions (#3779).

A prayer is a character's freeform words to a being: a plain log, one of the
few freeform channels a player has straight to staff, with no mechanical
effect of its own. Three independent, stackable conditions make one prayer
mechanically meaningful: dire straits (Soulfray active, or health in the
knockout band) invokes the divine-intervention check on the NEAR_DEATH trigger;
the first prayer per game week made at a shrine or temple of the being pays a
little devotion; and a GM may answer any prayer with a vision. A vision is the
GM's prose, delivered through the narrative message system in its own
category, spending the sending being's pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.services.soulfray import get_soulfray_warning
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.vitals.constants import KNOCKOUT_HEALTH_THRESHOLD, CharacterLifeState
from world.vitals.models import CharacterVitals
from world.worship.constants import (
    PRAYER_INTERVENTION_EVENT_PREFIX,
    PRAYER_SITE_DEVOTION_AMOUNT,
    PRAYER_TEXT_MAX_LENGTH,
    VISION_RESONANCE_POOL_COST,
    DireStraitsKind,
    MiracleTrigger,
)
from world.worship.exceptions import (
    PrayerBeingInactive,
    PrayerEmpty,
    PrayerTooLong,
    VisionClueNotCodex,
    VisionEmpty,
    VisionEpisodeNotShared,
    VisionPoolInsufficient,
    VisionPrayerMismatch,
    VisionRecipientUnrostered,
)
from world.worship.models import MiraclePerformance, Prayer, Vision, WorshippedBeing

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.clues.models import Clue
    from world.game_clock.models import GameWeek
    from world.stories.models import Episode


@dataclass(frozen=True)
class DireStraits:
    """Whether a character is in danger a god might answer."""

    soulfray: bool = False
    near_death: bool = False

    @property
    def any(self) -> bool:
        return self.soulfray or self.near_death

    @property
    def kind(self) -> str:
        """The ``DireStraitsKind`` recorded on the prayer; near death outranks Soulfray."""
        if self.near_death:
            return DireStraitsKind.NEAR_DEATH
        if self.soulfray:
            return DireStraitsKind.SOULFRAY
        return ""


def dire_straits_for(character_sheet: CharacterSheet) -> DireStraits:
    """Soulfray active (the safety checkpoint's own read, a touch on the magic
    domain), or health at or below the knockout band while alive."""
    character = character_sheet.character
    soulfray = get_soulfray_warning(character) is not None
    vitals = CharacterVitals.objects.filter(character_sheet=character_sheet).first()
    near_death = (
        vitals is not None
        and vitals.life_state == CharacterLifeState.ALIVE
        and vitals.health_percentage <= KNOCKOUT_HEALTH_THRESHOLD
    )
    return DireStraits(soulfray=soulfray, near_death=near_death)


@dataclass(frozen=True)
class PrayerOutcome:
    prayer: Prayer
    at_holy_site: bool
    devotion_granted: int
    dire_straits: DireStraits
    intervention: MiraclePerformance | None


def site_prayer_capped_this_week(
    character_sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> bool:
    """Whether a holy-site prayer to ``being`` already paid devotion this game week."""
    if game_week is None:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

        game_week = get_current_game_week()
    return _week_prayers(character_sheet, being, game_week).exists()


def _week_prayers(character_sheet: CharacterSheet, being: WorshippedBeing, game_week: GameWeek):
    return Prayer.objects.filter(
        character_sheet=character_sheet,
        being=being,
        game_week=game_week,
        devotion_granted__gt=0,
    )


def _room_profile_of(character_sheet: CharacterSheet) -> RoomProfile | None:
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    location = character_sheet.character.location
    if location is None:
        return None
    # RoomProfile shares ObjectDB's pk.
    return RoomProfile.objects.filter(pk=location.pk).first()


def pray(character_sheet: CharacterSheet, being: WorshippedBeing, text: str) -> PrayerOutcome:
    """Log a prayer, then apply whichever qualifying conditions hold.

    The log row is written first and stands on its own. The holy-site devotion
    joins it in one transaction. The intervention check runs after, outside it:
    a miracle is its own committed act with its own broadcast, and a prayer that
    went unanswered is still a prayer.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.worship.consecration_services import sites_of  # noqa: PLC0415
    from world.worship.services import bump_devotion, fire_divine_intervention  # noqa: PLC0415

    words = text.strip()
    if not words:
        raise PrayerEmpty
    if len(words) > PRAYER_TEXT_MAX_LENGTH:
        raise PrayerTooLong
    if not being.is_active:
        raise PrayerBeingInactive

    week = get_current_game_week()
    room_profile = _room_profile_of(character_sheet)
    sites = sites_of(room_profile, being)
    at_site = sites.shrine is not None or sites.temple is not None
    straits = dire_straits_for(character_sheet)

    with transaction.atomic():
        prayer = Prayer.objects.create(
            character_sheet=character_sheet,
            being=being,
            text=words,
            room_profile=room_profile,
            game_week=week,
            dire_straits=straits.kind,
        )
        devotion = 0
        # Locked while deciding, so two prayers landing together cannot both pay.
        already_paid = (
            at_site and _week_prayers(character_sheet, being, week).select_for_update().exists()
        )
        if at_site and not already_paid:
            devotion = PRAYER_SITE_DEVOTION_AMOUNT
            bump_devotion(character_sheet, being, devotion)
            prayer.devotion_granted = devotion
            prayer.save(update_fields=["devotion_granted"])

    intervention = None
    if straits.any:
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        intervention = fire_divine_intervention(
            character_sheet,
            trigger=MiracleTrigger.NEAR_DEATH,
            trigger_event=f"{PRAYER_INTERVENTION_EVENT_PREFIX}{straits.kind}",
            scene=get_active_scene(character_sheet.character.location),
            being=being,
        )
        if intervention is not None:
            prayer.intervention = intervention
            prayer.save(update_fields=["intervention"])

    return PrayerOutcome(
        prayer=prayer,
        at_holy_site=at_site,
        devotion_granted=devotion,
        dire_straits=straits,
        intervention=intervention,
    )


def _vision_text(being: WorshippedBeing, body: str, *, reveal_source: bool) -> str:
    """The delivered prose: the GM's words, and the sender's name only when revealed."""
    if reveal_source:
        return f"{body}\n\nYou know whose vision this is: {being.name}."
    return body


def send_vision(  # noqa: PLR0913 - the attachments are keyword-only and each optional
    *,
    recipient: CharacterSheet,
    being: WorshippedBeing,
    body: str,
    sent_by: AccountDB | None = None,
    reveal_source: bool = False,
    prayer: Prayer | None = None,
    clue: Clue | None = None,
    episode: Episode | None = None,
) -> Vision:
    """A GM sends ``recipient`` a vision from ``being``.

    Spends ``VISION_RESONANCE_POOL_COST`` from the being's pool (the same spend
    a miracle makes), delivers the prose as a VISIONS narrative message (live
    push when the recipient is online, login catch-up otherwise), and records
    the ``Vision``. A Codex ``clue`` is handed to the recipient on the spot; an
    ``episode`` links the vision to a story the recipient participates in.
    """
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.clues.services import acquire_clue  # noqa: PLC0415
    from world.stories.models import StoryParticipation  # noqa: PLC0415
    from world.worship.services import spend_worship_pool  # noqa: PLC0415

    prose = body.strip()
    if not prose:
        raise VisionEmpty
    if prayer is not None and prayer.character_sheet_id != recipient.pk:
        raise VisionPrayerMismatch
    if clue is not None and clue.target_kind != ClueTargetKind.CODEX:
        raise VisionClueNotCodex
    story = None
    if episode is not None:
        story = episode.chapter.story
        in_story = StoryParticipation.objects.filter(
            story=story, character=recipient, is_active=True
        ).exists()
        if not in_story:
            raise VisionEpisodeNotShared
    roster_entry = None
    if clue is not None:
        roster_entry = recipient.roster_entry_or_none
        if roster_entry is None:
            raise VisionRecipientUnrostered

    # The spend, the row and the clue commit first; the delivery follows, since
    # send_narrative_message pushes to the recipient's session the moment its
    # own transaction ends, and a push inside a transaction that then rolls back
    # would show the player a vision the record never kept.
    with transaction.atomic():
        if not spend_worship_pool(being, VISION_RESONANCE_POOL_COST, reason="vision"):
            raise VisionPoolInsufficient
        vision = Vision.objects.create(
            recipient=recipient,
            being=being,
            sent_by=sent_by,
            body=prose,
            reveal_source=reveal_source,
            prayer=prayer,
            clue=clue,
            episode=episode,
            resonance_spent=VISION_RESONANCE_POOL_COST,
        )
        if clue is not None and roster_entry is not None:
            acquire_clue(roster_entry, clue)
    message = send_narrative_message(
        recipients=[recipient],
        body=_vision_text(being, prose, reveal_source=reveal_source),
        category=NarrativeCategory.VISIONS,
        sender_account=sent_by,
        ooc_note=f"A vision from {being.name}"
        + (", source revealed." if reveal_source else ", source concealed."),
        related_story=story,
    )
    vision.message = message
    vision.save(update_fields=["message"])
    return vision
