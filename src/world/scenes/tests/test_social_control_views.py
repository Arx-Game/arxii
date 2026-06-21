"""Block / Mute API (#1278): the endpoints the persona menu + account lists + telnet call."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.models import Block, Mute


class SocialControlAPITests(APITestCase):
    def _played(self, account):
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        return entry.character_sheet

    def setUp(self) -> None:
        self.me = AccountFactory()
        self.my_sheet = self._played(self.me)
        self.target_sheet = self._played(AccountFactory())
        self.client.force_authenticate(user=self.me)

    def _create_block(self, reason="They crossed a line."):
        return self.client.post(
            "/api/blocks/",
            {
                "blocker_persona": self.my_sheet.primary_persona.pk,
                "blocked_persona": self.target_sheet.primary_persona.pk,
                "reason": reason,
            },
            format="json",
        )

    def test_block_create_requires_a_reason(self) -> None:
        resp = self.client.post(
            "/api/blocks/",
            {
                "blocker_persona": self.my_sheet.primary_persona.pk,
                "blocked_persona": self.target_sheet.primary_persona.pk,
                "reason": "",
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_block_create_and_list(self) -> None:
        resp = self._create_block()
        assert resp.status_code == 201
        assert resp.data["reason"] == "They crossed a line."
        listing = self.client.get("/api/blocks/")
        assert len(listing.data["results"]) == 1

    def test_cannot_block_as_a_persona_you_dont_own(self) -> None:
        resp = self.client.post(
            "/api/blocks/",
            {
                "blocker_persona": self.target_sheet.primary_persona.pk,  # not mine
                "blocked_persona": self.target_sheet.primary_persona.pk,
                "reason": "x",
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_unblock_is_cron_delayed_not_deleted(self) -> None:
        block_id = self._create_block().data["id"]
        resp = self.client.delete(f"/api/blocks/{block_id}/")
        assert resp.status_code == 200
        block = Block.objects.get(pk=block_id)
        assert block.pending_removal_at is not None  # still present, pending the cron

    def test_share_block_account_wide(self) -> None:
        block_id = self._create_block().data["id"]
        resp = self.client.post(f"/api/blocks/{block_id}/share/", format="json")
        assert resp.status_code == 200
        assert Block.objects.get(pk=block_id).account_level is True

    def test_mute_create_list_and_unmute(self) -> None:
        resp = self.client.post(
            "/api/mutes/",
            {
                "muted_persona": self.target_sheet.primary_persona.pk,
                "mute_ic": True,
                "mute_ooc": False,
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["mute_ooc"] is False
        mute_id = resp.data["id"]
        assert len(self.client.get("/api/mutes/").data["results"]) == 1
        assert self.client.delete(f"/api/mutes/{mute_id}/").status_code == 204
        assert not Mute.objects.filter(pk=mute_id).exists()

    def test_only_my_blocks_are_listed(self) -> None:
        self._create_block()
        other = AccountFactory()
        self.client.force_authenticate(user=other)
        self._played(other)
        assert self.client.get("/api/blocks/").data["results"] == []
