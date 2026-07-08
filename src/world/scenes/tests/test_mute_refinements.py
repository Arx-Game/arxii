"""Tests for Mute refinements: content blanking, OOC channel, is_muted field (#2087).

Muted personas' interactions stay in the feed with content blanked ("actions show
without text"). OOC-muted personas' pages are silently dropped.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.mute_services import (
    muted_persona_ids_for_viewer,
    ooc_muted_persona_ids_for_viewer,
    set_mute,
)


def _make_played_persona(account):
    """Create account → player_data → tenure → roster_entry → sheet → persona."""
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    sheet = CharacterSheetFactory(character=character)
    return sheet, sheet.primary_persona


class MuteContentBlankingTests(APITestCase):
    """The list serializer blanks content for muted personas (#2087)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.muter_acct = AccountFactory()
        cls.muter_sheet, cls.muter_persona = _make_played_persona(cls.muter_acct)

        cls.muted_acct = AccountFactory()
        cls.muted_sheet, cls.muted_persona = _make_played_persona(cls.muted_acct)

        cls.scene = SceneFactory()
        cls.normal_interaction = InteractionFactory(
            scene=cls.scene, persona=cls.muter_persona, content="Hello world"
        )
        cls.muted_interaction = InteractionFactory(
            scene=cls.scene, persona=cls.muted_persona, content="Annoying message"
        )
        # Muter IC-mutes the muted persona.
        cls.muter_pd, _ = PlayerData.objects.get_or_create(account=cls.muter_acct)
        set_mute(owner=cls.muter_pd, muted_persona=cls.muted_persona, ic=True, ooc=False)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.muter_acct)

    def test_muted_interaction_content_is_blanked(self) -> None:
        """The muter sees the muted persona's interaction with blanked content."""
        url = reverse("interaction-list")
        response = self.client.get(url, {"scene": self.scene.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"]
        muted_row = next(r for r in rows if r["persona"]["id"] == self.muted_persona.pk)
        assert muted_row["content"] == ""
        assert muted_row["is_muted"] is True

    def test_normal_interaction_content_is_not_blanked(self) -> None:
        """The muter sees their own interaction with real content."""
        url = reverse("interaction-list")
        response = self.client.get(url, {"scene": self.scene.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"]
        normal_row = next(r for r in rows if r["persona"]["id"] == self.muter_persona.pk)
        assert normal_row["content"] == "Hello world"
        assert normal_row["is_muted"] is False

    def test_muted_interaction_still_in_feed(self) -> None:
        """The muted interaction is NOT excluded — it stays in the feed (blanked)."""
        url = reverse("interaction-list")
        response = self.client.get(url, {"scene": self.scene.pk})
        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"]
        muted_ids = [r["persona"]["id"] for r in rows]
        assert self.muted_persona.pk in muted_ids

    def test_detail_endpoint_returns_full_content(self) -> None:
        """The detail endpoint returns full content (opt-in backfill)."""
        url = reverse("interaction-detail", args=[self.muted_interaction.pk])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["content"] == "Annoying message"


class OocMuteServiceTests(APITestCase):
    """ooc_muted_persona_ids_for_viewer returns OOC-muted persona IDs (#2087)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.muter_acct = AccountFactory()
        cls.muter_sheet, cls.muter_persona = _make_played_persona(cls.muter_acct)
        cls.muter_pd, _ = PlayerData.objects.get_or_create(account=cls.muter_acct)

        cls.muted_acct = AccountFactory()
        cls.muted_sheet, cls.muted_persona = _make_played_persona(cls.muted_acct)

    def test_ooc_mute_returns_ooc_muted_ids(self) -> None:
        set_mute(owner=self.muter_pd, muted_persona=self.muted_persona, ic=False, ooc=True)
        ids = ooc_muted_persona_ids_for_viewer(viewer_account=self.muter_acct)
        assert self.muted_persona.pk in ids

    def test_ic_only_mute_not_in_ooc_set(self) -> None:
        set_mute(owner=self.muter_pd, muted_persona=self.muted_persona, ic=True, ooc=False)
        ids = ooc_muted_persona_ids_for_viewer(viewer_account=self.muter_acct)
        assert self.muted_persona.pk not in ids

    def test_ic_only_mute_still_in_ic_set(self) -> None:
        set_mute(owner=self.muter_pd, muted_persona=self.muted_persona, ic=True, ooc=False)
        ids = muted_persona_ids_for_viewer(viewer_account=self.muter_acct)
        assert self.muted_persona.pk in ids


class OocMutePageDropTests(APITestCase):
    """OOC-muted persona's page is silently dropped (#2087)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.receiver_acct = AccountFactory()
        cls.receiver_sheet, cls.receiver_persona = _make_played_persona(cls.receiver_acct)
        cls.receiver_pd, _ = PlayerData.objects.get_or_create(account=cls.receiver_acct)
        cls.receiver_char = cls.receiver_sheet.character

        cls.sender_acct = AccountFactory()
        cls.sender_sheet, cls.sender_persona = _make_played_persona(cls.sender_acct)
        cls.sender_char = cls.sender_sheet.character

    def test_ooc_muted_page_is_dropped(self) -> None:
        """When the receiver has OOC-muted the sender, the page is silently dropped."""
        from commands.evennia_overrides.communication import _ooc_muted_by

        set_mute(owner=self.receiver_pd, muted_persona=self.sender_persona, ic=False, ooc=True)
        result = _ooc_muted_by(receiver_account=self.receiver_acct, sender_char=self.sender_char)
        assert result is True

    def test_ic_only_mute_does_not_drop_page(self) -> None:
        """IC-only mute does not affect OOC page delivery."""
        from commands.evennia_overrides.communication import _ooc_muted_by

        set_mute(owner=self.receiver_pd, muted_persona=self.sender_persona, ic=True, ooc=False)
        result = _ooc_muted_by(receiver_account=self.receiver_acct, sender_char=self.sender_char)
        assert result is False

    def test_no_mute_does_not_drop_page(self) -> None:
        """No mute at all — page delivers normally."""
        from commands.evennia_overrides.communication import _ooc_muted_by

        result = _ooc_muted_by(receiver_account=self.receiver_acct, sender_char=self.sender_char)
        assert result is False
