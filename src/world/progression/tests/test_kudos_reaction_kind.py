"""Kudos as a reaction-window kind (#911)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.progression.models import KudosPointsData, KudosTransaction
from world.progression.reaction_kinds import KUDOS_KIND, POSE_KUDOS_CATEGORY
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_services import (
    get_reaction_kind,
    react_to_interaction,
)


def make_participant(scene, *, link_account=True):
    """Account-backed persona participating in ``scene`` (full roster chain)."""
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    if link_account:
        character.db_account = account
        character.save()
    return roster_entry.character_sheet.primary_persona


class KudosReactionKindTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.writer = make_participant(cls.scene)
        cls.reactor = make_participant(cls.scene)
        cls.interaction = InteractionFactory(persona=cls.writer, scene=cls.scene)

    def test_kind_is_registered_and_lazy(self) -> None:
        config = get_reaction_kind(ReactionWindowKind.KUDOS)
        assert config is KUDOS_KIND
        assert config.lazy_open is True
        assert config.public is True

    def test_kudos_reaction_awards_to_poser_account(self) -> None:
        poser_account = self.writer.character_sheet.character.db_account

        reaction = react_to_interaction(
            interaction=self.interaction,
            kind=ReactionWindowKind.KUDOS,
            reactor_persona=self.reactor,
            choice="kudos",
        )

        assert reaction.window.kind == ReactionWindowKind.KUDOS
        points = KudosPointsData.objects.get(account=poser_account)
        assert points.total_earned == 1
        txn = KudosTransaction.objects.get(account=poser_account)
        assert txn.source_category.name == POSE_KUDOS_CATEGORY
        assert txn.awarded_by == self.reactor.character_sheet.character.db_account

    def test_lazy_open_is_idempotent_across_reactors(self) -> None:
        second_reactor = make_participant(self.scene)

        first = react_to_interaction(
            interaction=self.interaction,
            kind=ReactionWindowKind.KUDOS,
            reactor_persona=self.reactor,
            choice="kudos",
        )
        second = react_to_interaction(
            interaction=self.interaction,
            kind=ReactionWindowKind.KUDOS,
            reactor_persona=second_reactor,
            choice="kudos",
        )

        assert first.window_id == second.window_id
        poser_account = self.writer.character_sheet.character.db_account
        assert KudosPointsData.objects.get(account=poser_account).total_earned == 2

    def test_duplicate_kudos_from_same_reactor_rejected(self) -> None:
        react_to_interaction(
            interaction=self.interaction,
            kind=ReactionWindowKind.KUDOS,
            reactor_persona=self.reactor,
            choice="kudos",
        )
        with self.assertRaises(ValidationError):
            react_to_interaction(
                interaction=self.interaction,
                kind=ReactionWindowKind.KUDOS,
                reactor_persona=self.reactor,
                choice="kudos",
            )

    def test_poser_without_account_rejected_and_rolls_back(self) -> None:
        accountless_writer = make_participant(self.scene, link_account=False)
        interaction = InteractionFactory(persona=accountless_writer, scene=self.scene)

        with self.assertRaises(ValidationError):
            react_to_interaction(
                interaction=interaction,
                kind=ReactionWindowKind.KUDOS,
                reactor_persona=self.reactor,
                choice="kudos",
            )
        assert not KudosTransaction.objects.exists()

    def test_entrance_kind_cannot_lazy_open(self) -> None:
        with self.assertRaises(ValidationError):
            react_to_interaction(
                interaction=self.interaction,
                kind=ReactionWindowKind.ENTRANCE,
                reactor_persona=self.reactor,
                choice="anything",
            )
