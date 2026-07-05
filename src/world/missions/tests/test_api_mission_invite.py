"""#887 — web endpoints for mission invite / respond.

Covers the DRF actions on ``MissionJournalViewSet``: the contract holder
invites a co-located character, the invitee accepts (→ becomes a participant),
and the invitee declines. Non-holders, non-existent characters, and foreign
invites are rejected.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInvite, MissionParticipant
from world.missions.services.run import staff_assign_mission


def _graph(name: str):
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER",
    )
    return template, entry, option


class MissionInviteEndpointTests(TestCase):
    """``POST /api/missions/journal/<pk>/invite/`` + ``POST .../respond/``."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="Tavern", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=self.room)
        self.template, self.entry, self.option = _graph(f"invite-{self._testMethodName}")

        self.holder = CharacterFactory()
        CharacterSheetFactory(character=self.holder)
        self.holder.db_location = self.room
        self.holder.save(update_fields=["db_location"])

        self.invitee = CharacterFactory()
        CharacterSheetFactory(character=self.invitee)
        self.invitee.db_location = self.room
        self.invitee.save(update_fields=["db_location"])

        self.instance = staff_assign_mission(self.template, self.holder)

        self.account = AccountFactory()
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self._patch = mock.patch("world.missions.views._puppet_character", return_value=self.holder)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_invite_creates_pending_invite(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/invite/",
            {"invitee_character_id": self.invitee.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["response"], "pending")
        self.assertEqual(body["instance_id"], self.instance.pk)
        invite = MissionInvite.objects.get(pk=body["invite_id"])
        self.assertEqual(invite.target_persona, self.invitee.sheet_data.primary_persona)

    def test_invite_by_non_participant_is_404(self) -> None:
        """A non-participant gets 404 (existence must not leak)."""
        outsider = CharacterFactory()
        CharacterSheetFactory(character=outsider)
        with mock.patch("world.missions.views._puppet_character", return_value=outsider):
            res = self.client.post(
                f"/api/missions/journal/{self.instance.pk}/invite/",
                {"invitee_character_id": self.invitee.pk},
                format="json",
            )
        self.assertEqual(res.status_code, 404, res.content)

    def test_invite_unknown_character_is_404(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/invite/",
            {"invitee_character_id": 999999},
            format="json",
        )
        self.assertEqual(res.status_code, 404, res.content)

    def test_respond_accept_shares_mission(self) -> None:
        """Accepting an invite creates a MissionParticipant for the invitee."""
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/invite/",
            {"invitee_character_id": self.invitee.pk},
            format="json",
        )
        invite_id = res.json()["invite_id"]

        with mock.patch("world.missions.views._puppet_character", return_value=self.invitee):
            res = self.client.post(
                "/api/missions/journal/respond/",
                {"invite_id": invite_id, "response": "accept"},
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["response"], "accepted")
        self.assertTrue(
            MissionParticipant.objects.filter(
                instance=self.instance,
                character_id=self.invitee.pk,
            ).exists()
        )

    def test_respond_decline_does_not_share(self) -> None:
        res = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/invite/",
            {"invitee_character_id": self.invitee.pk},
            format="json",
        )
        invite_id = res.json()["invite_id"]

        with mock.patch("world.missions.views._puppet_character", return_value=self.invitee):
            res = self.client.post(
                "/api/missions/journal/respond/",
                {"invite_id": invite_id, "response": "decline"},
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["response"], "declined")
        self.assertFalse(
            MissionParticipant.objects.filter(
                instance=self.instance,
                character_id=self.invitee.pk,
            ).exists()
        )

    def test_respond_foreign_invite_is_404(self) -> None:
        """An invite addressed to someone else 404s for the invitee."""
        third = CharacterFactory()
        CharacterSheetFactory(character=third)
        staff_assign_mission(self.template, third)
        # Holder invites `third`, not `self.invitee`.
        self.client.post(
            f"/api/missions/journal/{self.instance.pk}/invite/",
            {"invitee_character_id": third.pk},
            format="json",
        )
        invite_id = MissionInvite.objects.get(target_persona=third.sheet_data.primary_persona).pk
        with mock.patch("world.missions.views._puppet_character", return_value=self.invitee):
            res = self.client.post(
                "/api/missions/journal/respond/",
                {"invite_id": invite_id, "response": "accept"},
                format="json",
            )
        self.assertEqual(res.status_code, 404, res.content)
