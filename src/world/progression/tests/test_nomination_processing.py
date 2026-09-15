"""Weekly nomination settlement (#3738): four paths on one stepped curve."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.game_clock.week_services import advance_game_week, get_current_game_week
from world.journals.factories import JournalEntryFactory
from world.progression.constants import (
    BEST_IN_SCENE_FIRST_XP,
    NOMINATION_FIRST_XP,
    NominationTargetType,
)
from world.progression.models import Nomination, XPTransaction
from world.progression.services.nomination_processing import (
    process_weekly_nominations,
    stepped_xp,
    weekly_nomination_processing_task,
)
from world.progression.types import ProgressionReason
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory


def _player():
    account = AccountFactory()
    player_data = PlayerDataFactory(account=account)
    persona = PersonaFactory()
    entry = RosterEntryFactory(character_sheet=persona.character_sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return account, persona


def _cite(nominator, piece, *, kind=NominationTargetType.INTERACTION, week=None):
    """A nomination row straight into the table (the service's rules are tested elsewhere)."""
    sheet = (
        piece.persona.character_sheet if kind == NominationTargetType.INTERACTION else piece.author
    )
    return Nomination.objects.create(
        nominator=nominator,
        game_week=week or get_current_game_week(),
        nominee=sheet,
        target_type=kind,
        target_id=piece.pk,
    )


def _xp(account, reason=None) -> int:
    rows = XPTransaction.objects.filter(account=account)
    if reason is not None:
        rows = rows.filter(reason=reason)
    return sum(row.amount for row in rows)


class SteppedXPTest(TestCase):
    """The reviewer's tiers: 1 | 2-3 | 4-6 | 7-10 | 11-16 | 17-25 | 26-38 | 39-58 | 59-88
    | 89-133."""

    def test_front_loaded_nomination_curve(self) -> None:
        expected = {
            0: 0,
            1: 3,
            2: 4,
            3: 4,
            4: 5,
            6: 5,
            7: 6,
            10: 6,
            11: 7,
            16: 7,
            17: 8,
            25: 8,
            26: 9,
            38: 9,
            39: 10,
            58: 10,
            59: 11,
            88: 11,
            89: 12,
            100: 12,
            133: 12,
            134: 13,
        }
        for count, xp in expected.items():
            assert stepped_xp(count, NOMINATION_FIRST_XP) == xp, (count, xp)

    def test_best_in_scene_curve_from_one(self) -> None:
        assert stepped_xp(1, BEST_IN_SCENE_FIRST_XP) == 1
        assert stepped_xp(3, BEST_IN_SCENE_FIRST_XP) == 2
        assert stepped_xp(10, BEST_IN_SCENE_FIRST_XP) == 4
        assert stepped_xp(12, BEST_IN_SCENE_FIRST_XP) == 5
        assert stepped_xp(20, BEST_IN_SCENE_FIRST_XP) == 6

    def test_past_the_table_each_tier_widens_by_half(self) -> None:
        # The last table width is 45 (89 to 133); then 67 (134 to 200), then 100 (201 to 300).
        assert stepped_xp(200, NOMINATION_FIRST_XP) == 13
        assert stepped_xp(201, NOMINATION_FIRST_XP) == 14
        assert stepped_xp(300, NOMINATION_FIRST_XP) == 14
        assert stepped_xp(301, NOMINATION_FIRST_XP) == 15
        prev = 0
        for count in range(400):
            current = stepped_xp(count, NOMINATION_FIRST_XP)
            assert current >= prev
            prev = current


class SettlementTest(TestCase):
    def setUp(self) -> None:
        Nomination.flush_instance_cache()
        XPTransaction.flush_instance_cache()
        self.week = get_current_game_week()
        self.scene = SceneFactory()

    def test_one_scene_one_friend_pays_five(self) -> None:
        """The reviewer's example: 3 for the person, 1 for their best prose, 1 best in scene."""
        writer_account, writer = _player()
        friend, _ = _player()
        pose = InteractionFactory(persona=writer, scene=self.scene)
        _cite(friend, pose)

        process_weekly_nominations(self.week)

        assert _xp(writer_account, ProgressionReason.NOMINATION) == 3
        assert _xp(writer_account, ProgressionReason.MOST_NOMINATED_PROSE) == 1
        assert _xp(writer_account, ProgressionReason.BEST_IN_SCENE) == 1
        assert _xp(writer_account) == 5

    def test_twelve_people_in_one_scene_pay_nine(self) -> None:
        """Twelve people sit in the 11 to 16 tier: 7 for the person, 1 prose, 1 scene."""
        writer_account, writer = _player()
        pose = InteractionFactory(persona=writer, scene=self.scene)
        for _ in range(12):
            _cite(AccountFactory(), pose)

        process_weekly_nominations(self.week)

        assert _xp(writer_account) == 7 + 1 + 1, list(
            XPTransaction.objects.filter(account=writer_account).values_list("reason", "amount")
        )

    def test_many_pieces_from_one_person_is_one_nomination(self) -> None:
        writer_account, writer = _player()
        friend, _ = _player()
        for _ in range(5):
            _cite(friend, InteractionFactory(persona=writer, scene=self.scene))

        process_weekly_nominations(self.week)

        assert _xp(writer_account, ProgressionReason.NOMINATION) == 3
        assert _xp(writer_account, ProgressionReason.MOST_NOMINATED_PROSE) == 1

    def test_best_in_scene_goes_to_the_most_nominated_pose_and_ties_pay_everyone(self) -> None:
        a_account, a = _player()
        b_account, b = _player()
        c_account, c = _player()
        pose_a = InteractionFactory(persona=a, scene=self.scene)
        pose_b = InteractionFactory(persona=b, scene=self.scene)
        pose_c = InteractionFactory(persona=c, scene=self.scene)
        for _ in range(2):
            _cite(AccountFactory(), pose_a)
            _cite(AccountFactory(), pose_b)
        _cite(AccountFactory(), pose_c)

        process_weekly_nominations(self.week)

        assert _xp(a_account, ProgressionReason.BEST_IN_SCENE) == 1
        assert _xp(b_account, ProgressionReason.BEST_IN_SCENE) == 1
        assert _xp(c_account, ProgressionReason.BEST_IN_SCENE) == 0

    def test_scene_wins_pay_on_the_curve(self) -> None:
        writer_account, writer = _player()
        for _ in range(3):
            _cite(AccountFactory(), InteractionFactory(persona=writer, scene=SceneFactory()))

        process_weekly_nominations(self.week)

        assert _xp(writer_account, ProgressionReason.BEST_IN_SCENE) == 2

    def test_a_pose_outside_any_scene_earns_no_scene_award(self) -> None:
        writer_account, writer = _player()
        _cite(AccountFactory(), InteractionFactory(persona=writer, scene=None))

        process_weekly_nominations(self.week)

        assert _xp(writer_account, ProgressionReason.BEST_IN_SCENE) == 0
        assert _xp(writer_account, ProgressionReason.MOST_NOMINATED_PROSE) == 1

    def test_the_most_nominated_journal_pays_its_writer_and_ties_pay_both(self) -> None:
        a_account, a = _player()
        b_account, b = _player()
        c_account, c = _player()
        entry_a = JournalEntryFactory(author=a.character_sheet)
        entry_b = JournalEntryFactory(author=b.character_sheet)
        entry_c = JournalEntryFactory(author=c.character_sheet)
        for _ in range(2):
            _cite(AccountFactory(), entry_a, kind=NominationTargetType.JOURNAL)
            _cite(AccountFactory(), entry_b, kind=NominationTargetType.JOURNAL)
        _cite(AccountFactory(), entry_c, kind=NominationTargetType.JOURNAL)

        process_weekly_nominations(self.week)

        assert _xp(a_account, ProgressionReason.MOST_NOMINATED_JOURNAL) == 1
        assert _xp(b_account, ProgressionReason.MOST_NOMINATED_JOURNAL) == 1
        assert _xp(c_account, ProgressionReason.MOST_NOMINATED_JOURNAL) == 0
        # A journal is prose too: c still has their most nominated prose.
        assert _xp(c_account) == 3 + 1

    def test_settlement_marks_rows_and_never_pays_twice(self) -> None:
        writer_account, writer = _player()
        _cite(AccountFactory(), InteractionFactory(persona=writer, scene=self.scene))

        process_weekly_nominations(self.week)
        process_weekly_nominations(self.week)

        assert _xp(writer_account) == 5
        Nomination.flush_instance_cache()
        assert not Nomination.objects.filter(processed=False).exists()

    def test_an_unplayed_nominee_is_skipped_without_breaking_the_week(self) -> None:
        played_account, played = _player()
        orphan = PersonaFactory()  # no tenure: nobody to pay
        _cite(AccountFactory(), InteractionFactory(persona=orphan, scene=self.scene))
        _cite(AccountFactory(), InteractionFactory(persona=played, scene=self.scene))

        process_weekly_nominations(self.week)

        assert _xp(played_account) == 5

    def test_the_weekly_task_settles_the_week_that_just_ended(self) -> None:
        writer_account, writer = _player()
        pose = InteractionFactory(persona=writer, scene=self.scene)
        _cite(AccountFactory(), pose, week=self.week)
        advance_game_week()

        weekly_nomination_processing_task()

        assert _xp(writer_account) == 5
