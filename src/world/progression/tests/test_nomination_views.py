"""The nominations API (#3738): the nominator's own side, nothing else."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import NominationTargetType
from world.progression.models import Nomination
from world.progression.services.nominations import nominate
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterEntry
from world.scenes.factories import InteractionFactory, PersonaFactory


def _played_persona(account):
    player_data = PlayerData.objects.filter(account=account).first() or PlayerDataFactory(
        account=account
    )
    persona = PersonaFactory()
    entry = RosterEntryFactory(character_sheet=persona.character_sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return persona


class NominationViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        get_current_game_week()  # the week must exist before the prose it will contain
        cls.nominator = AccountDB.objects.create_user(
            username="nominator", email="nominator@test.com", password="testpass123"
        )
        _played_persona(cls.nominator)
        cls.writer_account = AccountFactory()
        cls.writer_persona = _played_persona(cls.writer_account)
        cls.pose = InteractionFactory(persona=cls.writer_persona)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.nominator)
        Nomination.flush_instance_cache()
        RosterEntry.flush_instance_cache()


class NominateViewTests(NominationViewTestCase):
    def test_nominate_returns_the_row_with_the_nominee_named(self) -> None:
        response = self.client.post(
            "/api/progression/nominations/",
            {"target_type": NominationTargetType.INTERACTION, "target_id": self.pose.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["nominee_name"] == self.writer_persona.character_sheet.character.db_key
        assert response.data["target_type"] == NominationTargetType.INTERACTION
        assert Nomination.objects.filter(nominator=self.nominator, target_id=self.pose.pk).exists()

    def test_self_nomination_is_a_400_with_the_user_message(self) -> None:
        own = InteractionFactory(persona=_played_persona(self.nominator))
        response = self.client.post(
            "/api/progression/nominations/",
            {"target_type": NominationTargetType.INTERACTION, "target_id": own.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "own characters" in response.data["detail"]

    def test_anonymous_is_refused(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/progression/nominations/",
            {"target_type": NominationTargetType.INTERACTION, "target_id": self.pose.pk},
            format="json",
        )
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class ListAndWithdrawViewTests(NominationViewTestCase):
    def test_list_shows_only_my_own_nominations(self) -> None:
        other = AccountFactory()
        _played_persona(other)
        nominate(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)
        nominate(other, NominationTargetType.INTERACTION, self.pose.pk)

        response = self.client.get("/api/progression/nominations/")

        assert response.status_code == status.HTTP_200_OK
        assert [row["target_id"] for row in response.data] == [self.pose.pk]
        assert "nominator" not in response.data[0]

    def test_withdraw_deletes_my_row(self) -> None:
        row = nominate(self.nominator, NominationTargetType.INTERACTION, self.pose.pk)

        response = self.client.delete(f"/api/progression/nominations/{row.pk}/")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Nomination.objects.filter(pk=row.pk).exists()

    def test_cannot_withdraw_someone_elses_row(self) -> None:
        other = AccountFactory()
        _played_persona(other)
        row = nominate(other, NominationTargetType.INTERACTION, self.pose.pk)

        response = self.client.delete(f"/api/progression/nominations/{row.pk}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_there_is_no_budget_and_no_received_view(self) -> None:
        assert self.client.get("/api/progression/votes/budget/").status_code == 404
        assert self.client.get("/api/progression/votes/").status_code == 404
