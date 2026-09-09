"""Weekly nomination settlement (#3738).

Runs on the weekly rollover for the week that just ended and pays four paths,
each on the one stepped curve (``stepped_xp``):

1. **Nominations in general** — count = distinct people who nominated the
   character on anything this week; front-loaded (``NOMINATION_FIRST_XP``).
2. **Most nominated prose** — the character's own single most-cited piece;
   one instance per week by definition, so a flat ``MOST_NOMINATED_PROSE_XP``
   to anyone whose prose was nominated at all.
3. **Best in scene** — count = scenes in which the character's pose was the
   one the most people nominated (a tie counts for every tied writer), from
   ``BEST_IN_SCENE_FIRST_XP``.
4. **Most nominated journal** — the one journal entry in the game with the
   most distinct nominators this week pays its writer
   ``MOST_NOMINATED_JOURNAL_XP``; a tie pays every tied writer.

The reviewer's worked examples: one scene, one friend nominates you, 3 + 1 + 1
= 5; twenty scenes, a hundred distinct people, your pose the best in every
scene, 12 + 1 + 6 = 19.

Nominations are invisible until here: this is the only place a nominee learns
anything, and what they learn is the settled XP, never who or how many.
"""

from __future__ import annotations

from collections import defaultdict
import logging

from django.db import transaction
from django.db.models import Count, QuerySet

from world.game_clock.models import GameWeek
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import (
    BEST_IN_SCENE_FIRST_XP,
    MOST_NOMINATED_JOURNAL_XP,
    MOST_NOMINATED_PROSE_XP,
    NOMINATION_FIRST_XP,
    NOMINATION_TIER_FLOORS,
    NominationTargetType,
)
from world.progression.models import Nomination
from world.progression.services.awards import award_xp
from world.progression.types import ProgressionReason

logger = logging.getLogger("world.progression.nomination_processing")

#: How much each tier past the table widens over the one before.
_TIER_GROWTH = 1.5


def stepped_xp(count: int, first_xp: int) -> int:
    """XP for ``count`` on the stepped curve, ``first_xp`` at the first tier.

    Tiers to 133 are the reviewer's exact floors (``NOMINATION_TIER_FLOORS``);
    past the table each tier widens by half again. Zero pays zero.
    """
    if count <= 0:
        return 0
    tier = sum(1 for floor in NOMINATION_TIER_FLOORS if count >= floor)
    if count >= NOMINATION_TIER_FLOORS[-1]:
        width = NOMINATION_TIER_FLOORS[-1] - NOMINATION_TIER_FLOORS[-2]
        floor = NOMINATION_TIER_FLOORS[-1]
        while True:
            width = int(width * _TIER_GROWTH)
            floor += width
            if count < floor:
                break
            tier += 1
    return first_xp + tier - 1


def _award(nominee_id: int, amount: int, reason: str, description: str) -> None:
    """Pay ``amount`` to the player of sheet ``nominee_id``; skip an unplayed sheet."""
    from world.character_sheets.models import CharacterSheet
    from world.roster.selectors import get_account_for_character

    if amount <= 0:
        return
    sheet = CharacterSheet.objects.filter(pk=nominee_id).select_related("character").first()
    account = get_account_for_character(sheet.character) if sheet is not None else None
    if account is None:
        logger.warning("Nominee sheet %d has no player this week; skipping %s", nominee_id, reason)
        return
    award_xp(account=account, amount=amount, reason=reason, description=description)


def _pay_nominations_in_general(rows: QuerySet[Nomination]) -> None:
    per_nominee = rows.values("nominee").annotate(people=Count("nominator", distinct=True))
    for entry in per_nominee:
        people = entry["people"]
        _award(
            entry["nominee"],
            stepped_xp(people, NOMINATION_FIRST_XP),
            ProgressionReason.NOMINATION,
            f"Nominated for good RP by {people} {'person' if people == 1 else 'people'} this week",
        )


def _pieces_by_people(rows: QuerySet[Nomination]) -> list[dict]:
    """Every cited piece with its nominee and its count of distinct nominators."""
    return list(
        rows.values("nominee", "target_type", "target_id").annotate(
            people=Count("nominator", distinct=True)
        )
    )


def _pay_most_nominated_prose(pieces: list[dict]) -> None:
    """Each nominee's own most-cited piece: one instance, a flat award."""
    nominees = {piece["nominee"] for piece in pieces}
    for nominee_id in nominees:
        _award(
            nominee_id,
            MOST_NOMINATED_PROSE_XP,
            ProgressionReason.MOST_NOMINATED_PROSE,
            "This week's most nominated prose",
        )


def _pay_best_in_scene(pieces: list[dict]) -> None:
    """Per scene, the most-nominated pose wins; wins per nominee pay on the curve."""
    from world.scenes.models import Interaction

    pose_pieces = [p for p in pieces if p["target_type"] == NominationTargetType.INTERACTION]
    if not pose_pieces:
        return
    scene_of = dict(
        Interaction.objects.filter(
            pk__in=[p["target_id"] for p in pose_pieces], scene__isnull=False
        ).values_list("pk", "scene_id")
    )
    by_scene: dict[int, list[dict]] = defaultdict(list)
    for piece in pose_pieces:
        scene_id = scene_of.get(piece["target_id"])
        if scene_id is not None:
            by_scene[scene_id].append(piece)
    wins: dict[int, int] = defaultdict(int)
    for group in by_scene.values():
        top = max(piece["people"] for piece in group)
        for nominee_id in {piece["nominee"] for piece in group if piece["people"] == top}:
            wins[nominee_id] += 1
    for nominee_id, count in wins.items():
        _award(
            nominee_id,
            stepped_xp(count, BEST_IN_SCENE_FIRST_XP),
            ProgressionReason.BEST_IN_SCENE,
            f"Best-nominated pose in {count} {'scene' if count == 1 else 'scenes'} this week",
        )


def _pay_most_nominated_journal(pieces: list[dict]) -> None:
    """The game's single most-nominated journal entry; a tie pays every tied writer."""
    journal_pieces = [p for p in pieces if p["target_type"] == NominationTargetType.JOURNAL]
    if not journal_pieces:
        return
    top = max(piece["people"] for piece in journal_pieces)
    for nominee_id in {piece["nominee"] for piece in journal_pieces if piece["people"] == top}:
        _award(
            nominee_id,
            MOST_NOMINATED_JOURNAL_XP,
            ProgressionReason.MOST_NOMINATED_JOURNAL,
            "This week's most nominated journal",
        )


def process_weekly_nominations(game_week: GameWeek) -> None:
    """Settle every unprocessed nomination of ``game_week`` into XP, atomically."""
    with transaction.atomic():
        rows = Nomination.objects.filter(game_week=game_week, processed=False)
        pieces = _pieces_by_people(rows)
        _pay_nominations_in_general(rows)
        _pay_most_nominated_prose(pieces)
        _pay_best_in_scene(pieces)
        _pay_most_nominated_journal(pieces)
        rows.update(processed=True)


def weekly_nomination_processing_task() -> None:
    """Cron wrapper: settle the week that just ended."""
    current = get_current_game_week()
    previous = (
        GameWeek.objects.filter(ended_at__isnull=False)
        .exclude(pk=current.pk)
        .order_by("-started_at")
        .first()
    )
    if previous is None:
        logger.info("No previous game week found; skipping nomination settlement.")
        return
    logger.info("Settling nominations for %s", previous)
    process_weekly_nominations(previous)
    logger.info("Settled nominations for %s", previous)
