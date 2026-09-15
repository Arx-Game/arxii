"""Nominating for good RP (#3738): what can be nominated, by whom, once."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.game_clock.week_services import get_current_game_week
from world.journals.factories import JournalEntryFactory
from world.progression.constants import NominationTargetType
from world.progression.models import Nomination
from world.progression.services.nominations import (
    has_nominated,
    nominate,
    nominations_by_account,
    withdraw_nomination,
)
from world.progression.types import ProgressionError
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionVisibility
from world.scenes.factories import InteractionFactory, PersonaFactory
from world.scenes.models import Interaction


def _player(account=None):
    """A played character: (account, sheet, persona) with a live roster tenure."""
    account = account or AccountFactory()
    player_data = PlayerData.objects.filter(account=account).first() or PlayerDataFactory(
        account=account
    )
    persona = PersonaFactory()
    entry = RosterEntryFactory(character_sheet=persona.character_sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return account, persona.character_sheet, persona


class NominateTest(TestCase):
    def setUp(self) -> None:
        Nomination.flush_instance_cache()
        self.week = get_current_game_week()
        self.nominator, _, _ = _player()
        self.writer_account, self.writer_sheet, self.writer_persona = _player()

    def test_nominates_the_writer_of_a_public_pose(self) -> None:
        pose = InteractionFactory(persona=self.writer_persona)

        row = nominate(self.nominator, NominationTargetType.INTERACTION, pose.pk)

        assert row.nominee_id == self.writer_sheet.pk
        assert row.nominator_id == self.nominator.pk
        assert row.game_week_id == self.week.pk
        assert has_nominated(self.nominator, NominationTargetType.INTERACTION, pose.pk)

    def test_nominates_the_author_of_a_public_journal(self) -> None:
        entry = JournalEntryFactory(author=self.writer_sheet, is_public=True)

        row = nominate(self.nominator, NominationTargetType.JOURNAL, entry.pk)

        assert row.nominee_id == self.writer_sheet.pk

    def test_a_private_journal_cannot_be_nominated(self) -> None:
        entry = JournalEntryFactory(author=self.writer_sheet, is_public=False)

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.JOURNAL, entry.pk)
        assert ctx.exception.user_message == ProgressionError.NOT_VISIBLE

    def test_own_characters_are_never_nominable_even_through_an_alt(self) -> None:
        """The nominator is the account: a second character of the same player is still you."""
        _, _, alt_persona = _player(account=self.nominator)
        pose = InteractionFactory(persona=alt_persona)

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.INTERACTION, pose.pk)
        assert ctx.exception.user_message == ProgressionError.SELF_NOMINATION

    def test_an_unplayed_character_cannot_be_nominated(self) -> None:
        pose = InteractionFactory()  # persona with no roster tenure behind it

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.INTERACTION, pose.pk)
        assert ctx.exception.user_message == ProgressionError.NO_PLAYER

    def test_only_this_weeks_prose_counts(self) -> None:
        pose = InteractionFactory(persona=self.writer_persona)
        Interaction.objects.filter(pk=pose.pk).update(
            timestamp=self.week.started_at - timedelta(days=1)
        )
        Interaction.flush_instance_cache()

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.INTERACTION, pose.pk)
        assert ctx.exception.user_message == ProgressionError.NOT_THIS_WEEK

    def test_what_you_could_not_see_cannot_be_nominated(self) -> None:
        whisper = InteractionFactory(
            persona=self.writer_persona, visibility=InteractionVisibility.VERY_PRIVATE
        )

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.INTERACTION, whisper.pk)
        assert ctx.exception.user_message == ProgressionError.NOT_VISIBLE

    def test_a_missing_piece_is_refused(self) -> None:
        with self.assertRaises(ProgressionError):
            nominate(self.nominator, NominationTargetType.INTERACTION, 999999)

    def test_the_same_piece_twice_is_refused_but_another_piece_cites_more(self) -> None:
        first = InteractionFactory(persona=self.writer_persona)
        second = InteractionFactory(persona=self.writer_persona)
        nominate(self.nominator, NominationTargetType.INTERACTION, first.pk)

        with self.assertRaises(ProgressionError) as ctx:
            nominate(self.nominator, NominationTargetType.INTERACTION, first.pk)
        assert ctx.exception.user_message == ProgressionError.ALREADY_NOMINATED

        nominate(self.nominator, NominationTargetType.INTERACTION, second.pk)
        rows = Nomination.objects.filter(nominator=self.nominator, game_week=self.week)
        assert rows.count() == 2
        assert rows.values("nominee").distinct().count() == 1


class WithdrawNominationTest(TestCase):
    def setUp(self) -> None:
        Nomination.flush_instance_cache()
        get_current_game_week()  # the week must exist before the prose it will contain
        self.nominator, _, _ = _player()
        _, self.writer_sheet, self.writer_persona = _player()
        self.pose = InteractionFactory(persona=self.writer_persona)

    def test_withdraws_this_weeks_citation(self) -> None:
        nominate(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)

        withdraw_nomination(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)

        assert not Nomination.objects.filter(nominator=self.nominator).exists()

    def test_nothing_to_withdraw(self) -> None:
        with self.assertRaises(ProgressionError) as ctx:
            withdraw_nomination(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)
        assert ctx.exception.user_message == ProgressionError.NOMINATION_NOT_FOUND

    def test_a_settled_nomination_stands(self) -> None:
        row = nominate(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)
        Nomination.objects.filter(pk=row.pk).update(processed=True)
        Nomination.flush_instance_cache()

        with self.assertRaises(ProgressionError) as ctx:
            withdraw_nomination(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)
        assert ctx.exception.user_message == ProgressionError.NOMINATION_PROCESSED

    def test_the_nominator_sees_only_their_own_list(self) -> None:
        other, _, _ = _player()
        nominate(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)
        nominate(other, NominationTargetType.INTERACTION, self.pose.pk)

        mine = list(nominations_by_account(self.nominator))
        assert [row.nominator_id for row in mine] == [self.nominator.pk]
