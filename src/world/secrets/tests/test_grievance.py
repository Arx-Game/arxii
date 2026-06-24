"""Secret-victim grievance flow (#1429) — shared service + web API.

A secret's victim, once they've learned it, registers a chosen relationship swing against the
perpetrator. The same ``register_secret_grievance`` service backs both the web endpoint and the
telnet ``+grievance`` command.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.relationships.factories import GrievanceOptionFactory
from world.relationships.models import CharacterRelationship, RelationshipCapstone
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import (
    SecretError,
    grant_secret_knowledge,
    register_secret_grievance,
)


def _piloted_entry():
    entry = RosterEntryFactory()
    RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=AccountFactory()))
    return entry


class RegisterSecretGrievanceServiceTests(TestCase):
    def setUp(self) -> None:
        self.entry = _piloted_entry()
        self.secret = SecretFactory()  # the subject_sheet is the perpetrator
        SecretVictimFactory(
            secret=self.secret,
            organization=None,
            persona=self.entry.character_sheet.primary_persona,
        )
        self.option = GrievanceOptionFactory(points=900)

    def test_victim_who_knows_registers_a_one_sided_grievance(self) -> None:
        grant_secret_knowledge(roster_entry=self.entry, secret=self.secret)

        capstone = register_secret_grievance(
            roster_entry=self.entry, secret=self.secret, option=self.option
        )

        assert isinstance(capstone, RelationshipCapstone)
        relationship = CharacterRelationship.objects.get(
            source=self.entry.character_sheet, target=self.secret.subject_sheet
        )
        assert relationship.is_pending is True  # unilateral

    def test_a_non_victim_is_rejected(self) -> None:
        other = _piloted_entry()
        grant_secret_knowledge(roster_entry=other, secret=self.secret)
        with self.assertRaises(SecretError):
            register_secret_grievance(roster_entry=other, secret=self.secret, option=self.option)

    def test_a_victim_who_has_not_learned_it_is_rejected(self) -> None:
        with self.assertRaises(SecretError):
            register_secret_grievance(
                roster_entry=self.entry, secret=self.secret, option=self.option
            )

    def test_grieving_is_one_shot_per_secret(self) -> None:
        from world.secrets.models import SecretGrievance

        grant_secret_knowledge(roster_entry=self.entry, secret=self.secret)
        register_secret_grievance(roster_entry=self.entry, secret=self.secret, option=self.option)
        # A second attempt is rejected — no stacking grudge swings.
        with self.assertRaises(SecretError):
            register_secret_grievance(
                roster_entry=self.entry, secret=self.secret, option=self.option
            )
        assert (
            SecretGrievance.objects.filter(
                secret=self.secret, victim_sheet=self.entry.character_sheet
            ).count()
            == 1
        )


class SecretGrievanceAPITests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=self.entry, player_data=PlayerDataFactory(account=self.account)
        )
        self.secret = SecretFactory()
        SecretVictimFactory(
            secret=self.secret,
            organization=None,
            persona=self.entry.character_sheet.primary_persona,
        )
        grant_secret_knowledge(roster_entry=self.entry, secret=self.secret)
        self.option = GrievanceOptionFactory(label="Furious Revelation")
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_options_list(self) -> None:
        response = self.client.get("/api/secrets/grievance-options/")
        assert response.status_code == 200
        assert any(opt["label"] == "Furious Revelation" for opt in response.data)

    def test_submit_applies_the_grievance(self) -> None:
        response = self.client.post(
            "/api/secrets/grievance/",
            {"secret": self.secret.pk, "viewer": self.entry.pk, "option": self.option.pk},
            format="json",
        )
        assert response.status_code == 204
        assert CharacterRelationship.objects.filter(
            source=self.entry.character_sheet, target=self.secret.subject_sheet
        ).exists()

    def test_submit_rejected_for_an_owned_non_victim(self) -> None:
        other_account = AccountFactory()
        other_entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=other_entry, player_data=PlayerDataFactory(account=other_account)
        )
        client = APIClient()
        client.force_authenticate(user=other_account)

        response = client.post(
            "/api/secrets/grievance/",
            {"secret": self.secret.pk, "viewer": other_entry.pk, "option": self.option.pk},
            format="json",
        )
        assert response.status_code == 403
