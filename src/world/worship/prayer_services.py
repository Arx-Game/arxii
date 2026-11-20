"""Prayers and visions (#3779).

A prayer is a character's freeform words to a being: a plain log, one of the
few freeform channels a player has straight to staff, with no mechanical
effect of its own. Three independent, stackable conditions make one prayer
mechanically meaningful: dire straits (Soulfray active, or health in the
knockout band, for the one praying or the character prayed for, #4349) rolls the
divine-intervention check on the NEAR_DEATH trigger; action points spent praying at a
shrine or temple of the being earn favor, up to a weekly limit (#4349); and a GM may
answer any prayer with a vision. A vision is the GM's prose, delivered through the
narrative message system in its own category, spending the sending being's pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum

from world.magic.services.soulfray import get_soulfray_warning
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.vitals.constants import KNOCKOUT_HEALTH_THRESHOLD, CharacterLifeState
from world.vitals.models import CharacterVitals
from world.worship.constants import (
    PRAYER_INTERVENTION_EVENT_PREFIX,
    PRAYER_TEXT_MAX_LENGTH,
    VISION_RESONANCE_POOL_COST,
    DireStraitsKind,
    MiracleTrigger,
)
from world.worship.exceptions import (
    PrayerApInsufficient,
    PrayerApLimit,
    PrayerBeingInactive,
    PrayerEmpty,
    PrayerError,
    PrayerForOwnCharacter,
    PrayerTargetNotHere,
    PrayerTargetNotInDanger,
    PrayerTooLong,
    VisionClueNotFact,
    VisionEmpty,
    VisionEpisodeNotShared,
    VisionPoolInsufficient,
    VisionPrayerMismatch,
    VisionRecipientUnrostered,
)
from world.worship.models import Answer, Prayer, Vision, WorshippedBeing

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.clues.models import Clue
    from world.game_clock.models import GameWeek
    from world.stories.models import Episode
    from world.worship.types import InterventionResult


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
    """What one prayer did: the log row, the holy-site favor and the intervention call.

    ``intervention`` is the divine intervention call made when the one in danger (the one
    praying, or the character prayed for) was in dire straits, rolled or not; None when no call
    was made. ``lines`` are the private lines the one praying reads about it.
    """

    prayer: Prayer
    at_holy_site: bool
    devotion_granted: int
    dire_straits: DireStraits
    intervention: InterventionResult | None = None
    ap_spent: int = 0
    lines: tuple[str, ...] = ()

    @property
    def answered(self) -> bool:
        return self.intervention is not None and self.intervention.answered


def prayer_ap_used_this_week(
    character_sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> int:
    """Action points ``character_sheet`` has spent praying at holy sites of ``being`` this game
    week, the number the weekly limit counts (#4349)."""
    if game_week is None:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

        game_week = get_current_game_week()
    total = Prayer.objects.filter(
        character_sheet=character_sheet, being=being, game_week=game_week
    ).aggregate(total=Sum("ap_spent"))["total"]
    return total or 0


def prayer_ap_left_this_week(
    character_sheet: CharacterSheet, being: WorshippedBeing, *, game_week: GameWeek | None = None
) -> int:
    """How many more action points ``character_sheet`` may spend praying to ``being`` this week."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    cap = get_devotion_config().prayer_weekly_ap_cap
    return max(cap - prayer_ap_used_this_week(character_sheet, being, game_week=game_week), 0)


def _room_profile_of(character_sheet: CharacterSheet) -> RoomProfile | None:
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    location = character_sheet.character.location
    if location is None:
        return None
    # RoomProfile shares ObjectDB's pk.
    return RoomProfile.objects.filter(pk=location.pk).first()


def _check_prayer_for_another(praying: CharacterSheet, target: CharacterSheet) -> DireStraits:
    """Refuse a prayer for ``target`` unless it is for someone else's character who is here and
    in dire straits; return their straits.

    A player never benefits from play between their own characters, so a prayer for another
    character of the same account is refused.
    """
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415

    own_account = account_for_sheet(praying)
    if own_account is not None and own_account == account_for_sheet(target):
        raise PrayerForOwnCharacter
    location = praying.character.location
    if location is None or target.character.db_location_id != location.pk:
        raise PrayerTargetNotHere
    straits = dire_straits_for(target)
    if not straits.any:
        raise PrayerTargetNotInDanger
    return straits


def _spend_prayer_ap(character_sheet: CharacterSheet, being: WorshippedBeing, ap: int) -> None:
    """Spend ``ap`` praying at a holy site, refusing before anything is spent when it passes the
    weekly limit or the character's action points."""
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    left = prayer_ap_left_this_week(character_sheet, being)
    if ap > left:
        raise PrayerApLimit(being.name, left)
    pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if pool is None or not pool.spend(ap):
        raise PrayerApInsufficient


def _call_on_being(
    prayer: Prayer,
    being: WorshippedBeing,
    target: CharacterSheet,
    straits: DireStraits,
    *,
    for_another: bool,
) -> tuple[InterventionResult, tuple[str, ...]]:
    """Roll the divine intervention a prayer in dire straits calls for (#4349) and tell
    everyone what they are due: onlookers the prayer for another, the one praying the result,
    the fallen character who prayed for them.

    Returns the result and the one praying's private lines.
    """
    from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.worship.intervention_services import (  # noqa: PLC0415
        PRAYER_FOR_ANOTHER,
        PRAYER_FOR_SELF,
        fire_divine_intervention,
        intervention_lines,
        prayed_for_you_line,
        prayer_room_line,
    )
    from world.worship.services import broadcast_prayer_line  # noqa: PLC0415

    praying = prayer.character_sheet
    scene = get_active_scene(praying.character.location)
    if for_another:
        broadcast_prayer_line(praying.character, prayer_room_line(praying, target, being), scene)
    result = fire_divine_intervention(
        praying,
        trigger=MiracleTrigger.NEAR_DEATH,
        trigger_event=f"{PRAYER_INTERVENTION_EVENT_PREFIX}{straits.kind}",
        scene=scene,
        being=being,
        target=target,
    )
    if result.performance is not None:
        prayer.intervention = result.performance
        prayer.save(update_fields=["intervention"])
    mode = PRAYER_FOR_ANOTHER if for_another else PRAYER_FOR_SELF
    if for_another and result.answered:
        send_stored_notice(target, prayed_for_you_line(result), ooc_note="A prayer for you")
    return result, tuple(intervention_lines(result, mode=mode))


def pray(
    character_sheet: CharacterSheet,
    being: WorshippedBeing,
    text: str,
    *,
    on_behalf_of: CharacterSheet | None = None,
    ap: int = 0,
) -> PrayerOutcome:
    """Log a prayer, then apply whichever qualifying conditions hold.

    The log row is written first and stands on its own. At a holy site of the being, ``ap``
    action points spent praying earn base favor (``DevotionConfig.prayer_ap_per_favor`` per
    point, rounded down, then the earning rate), up to the weekly limit; the spend and the
    favor join the row in one transaction. When the one in danger is in dire straits, the
    intervention roll runs after, outside it: a miracle is its own committed act with its
    own broadcast, and a prayer that went unanswered is still a prayer. ``on_behalf_of`` names
    a character present who is in dire straits (a prayer for another): the roll, its cost and
    its wait are the one praying's, and the help lands on them.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.worship.consecration_services import sites_of  # noqa: PLC0415
    from world.worship.constants import PledgeCreditSource  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415
    from world.worship.services import bump_devotion  # noqa: PLC0415
    from world.worship.steward_services import stewarded_refusal  # noqa: PLC0415
    from world.worship.types import FavorSource  # noqa: PLC0415

    words = text.strip()
    if not words:
        raise PrayerEmpty
    if len(words) > PRAYER_TEXT_MAX_LENGTH:
        raise PrayerTooLong
    if not being.is_active:
        raise PrayerBeingInactive
    refusal = stewarded_refusal(character_sheet, being)
    if refusal:
        raise PrayerError(refusal)
    if ap < 0:
        raise PrayerApInsufficient

    for_another = on_behalf_of is not None and on_behalf_of.pk != character_sheet.pk
    target = on_behalf_of if for_another else character_sheet
    straits = (
        _check_prayer_for_another(character_sheet, target)
        if for_another
        else dire_straits_for(character_sheet)
    )
    week = get_current_game_week()
    room_profile = _room_profile_of(character_sheet)
    sites = sites_of(room_profile, being)
    at_site = sites.shrine is not None or sites.temple is not None
    spent = ap if at_site else 0

    with transaction.atomic():
        if spent:
            _spend_prayer_ap(character_sheet, being, spent)
        prayer = Prayer.objects.create(
            character_sheet=character_sheet,
            being=being,
            text=words,
            room_profile=room_profile,
            game_week=week,
            dire_straits=straits.kind,
            ap_spent=spent,
        )
        devotion = 0
        base_favor = spent // get_devotion_config().prayer_ap_per_favor
        if base_favor > 0:
            # #4333: the earning rate scales the prayer's favor; record what landed.
            devotion = bump_devotion(
                character_sheet,
                being,
                base_favor,
                source=FavorSource(kind=PledgeCreditSource.PRAYER),
            ).credited
            prayer.devotion_granted = devotion
            prayer.save(update_fields=["devotion_granted"])

    result, lines = None, ()
    if straits.any:
        result, lines = _call_on_being(prayer, being, target, straits, for_another=for_another)

    return PrayerOutcome(
        prayer=prayer,
        at_holy_site=at_site,
        devotion_granted=devotion,
        dire_straits=straits,
        intervention=result,
        ap_spent=spent,
        lines=lines,
    )


def _vision_text(
    being: WorshippedBeing, body: str, *, reveal_source: bool, footnotes: tuple[str, ...] = ()
) -> str:
    """The delivered prose: the written words, the sender's name only when revealed, then
    any footnotes naming what came with it (an answer's clue, follow-up and condition)."""
    text = f"{body}\n\nYou know whose vision this is: {being.name}." if reveal_source else body
    if footnotes:
        text += "\n" + " ".join(footnotes)
    return text


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
    answer: Answer | None = None,
    footnotes: tuple[str, ...] = (),
) -> Vision:
    """A GM sends ``recipient`` a vision from ``being``, or a closing rite releases a
    written-ahead ``answer`` as one (#4333 slice 3, ``sent_by`` None).

    Spends ``VISION_RESONANCE_POOL_COST`` from the being's pool (the same spend
    a miracle makes), delivers the prose as a VISIONS narrative message (live
    push when the recipient is online, login catch-up otherwise), and records
    the ``Vision``. A Codex or secret ``clue`` (an answer's fact clue) is handed to
    the recipient on the spot: it is always held, and an AUTOMATIC clue also
    grants its target (``find_clue``, as room search does, #4327). A RESEARCH
    clue is only held. An ``episode`` links the vision to a story the recipient
    participates in.
    """
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.clues.services import find_clue  # noqa: PLC0415
    from world.stories.models import StoryParticipation  # noqa: PLC0415
    from world.worship.services import spend_worship_pool  # noqa: PLC0415

    prose = body.strip()
    if not prose:
        raise VisionEmpty
    if prayer is not None and prayer.character_sheet_id != recipient.pk:
        raise VisionPrayerMismatch
    if clue is not None and clue.target_kind not in (ClueTargetKind.CODEX, ClueTargetKind.SECRET):
        raise VisionClueNotFact
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
            answer=answer,
            resonance_spent=VISION_RESONANCE_POOL_COST,
        )
        if clue is not None and roster_entry is not None:
            find_clue(roster_entry, clue)
    message = send_narrative_message(
        recipients=[recipient],
        body=_vision_text(being, prose, reveal_source=reveal_source, footnotes=footnotes),
        category=NarrativeCategory.VISIONS,
        sender_account=sent_by,
        ooc_note=f"A vision from {being.name}"
        + (", source revealed." if reveal_source else ", source concealed."),
        related_story=story,
    )
    vision.message = message
    vision.save(update_fields=["message"])
    return vision
