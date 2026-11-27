"""Tests for the aura glimpse @actions on CharacterAuraViewSet (#2427)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.magic.constants import GlimpseMemory, GlimpseState, GlimpseTagAxis
from world.magic.factories import CharacterAuraFactory, GlimpseTagFactory
from world.magic.models import CharacterGlimpseTag
from world.magic.services.glimpse import set_glimpse_memory
from world.magic.tests.glimpse_helpers import axis_takes_several
from world.roster.factories import RosterTenureFactory


class GlimpseAuraActionTestBase(TestCase):
    """Shared owner/aura fixture for the four glimpse actions."""

    @classmethod
    def setUpTestData(cls):
        cls.tenure = RosterTenureFactory()
        cls.account = cls.tenure.player_data.account
        cls.character = cls.tenure.roster_entry.character_sheet.character
        cls.aura = CharacterAuraFactory(character=cls.character.sheet_data)

        cls.other_tenure = RosterTenureFactory()
        cls.other_account = cls.other_tenure.player_data.account

        cls.tone_a = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-a")
        cls.tone_b = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-b")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _url(self, action: str) -> str:
        return f"/api/magic/character-auras/{self.aura.pk}/{action}/"


class SetGlimpseTagsActionTest(GlimpseAuraActionTestBase):
    def test_owner_sets_tags_for_axis(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]}]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["glimpse_state"] == GlimpseState.TAGS_ONLY

    def test_tone_multi_select_rejected(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {
                "answers": [
                    {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id, self.tone_b.id]}
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @axis_takes_several(GlimpseTagAxis.REFLECTION)
    def test_stand_alone_tag_beside_another_is_refused_in_words(self):
        """#5193: the sheet's editor cannot save Fugue beside another Reflection answer.

        On an axis set to take several answers, the path #5292 keeps as the way back.
        """
        majestic = GlimpseTagFactory(
            axis=GlimpseTagAxis.REFLECTION, slug="api-majestic", name="Majestic"
        )
        fugue = GlimpseTagFactory(
            axis=GlimpseTagAxis.REFLECTION, slug="api-fugue", name="Fugue", stands_alone=True
        )

        both = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.REFLECTION, "tag_ids": [majestic.id, fugue.id]}]},
            format="json",
        )
        alone = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.REFLECTION, "tag_ids": [fugue.id]}]},
            format="json",
        )

        assert both.status_code == status.HTTP_400_BAD_REQUEST
        assert both.data["detail"] == "Fugue cannot be chosen with another The Reflection tag."
        assert alone.status_code == status.HTTP_200_OK

    def test_two_answers_to_one_axis_are_refused_in_words(self):
        """#5292: every axis takes one answer."""
        witness_a = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug="api-witness-a")
        witness_b = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug="api-witness-b")
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {
                "answers": [
                    {"axis": GlimpseTagAxis.WITNESS, "tag_ids": [witness_a.id, witness_b.id]}
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "Witness & Secrecy accepts a single tag."

    def test_one_axis_named_twice_is_refused(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {
                "answers": [
                    {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]},
                    {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_b.id]},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_several_axes_are_saved_together_and_give_their_cards(self):
        """#5292: the editor's one confirm sends every staged answer in one request."""
        card = DistinctionFactory(name="Wonderstruck", slug="api-wonderstruck")
        DistinctionOfferFactory(
            distinction=card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.tone_a
        )
        witness = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug="api-witness")
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {
                "answers": [
                    {"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]},
                    {"axis": GlimpseTagAxis.WITNESS, "tag_ids": [witness.id]},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        held = CharacterDistinction.objects.get(character=self.aura.character, distinction=card)
        assert held.from_glimpse_id == self.aura.pk

    def test_a_player_cannot_change_an_answer_and_staff_can(self):
        """#5292: an answer written in play is final for the player."""
        url = self._url("set-glimpse-tags")
        first = {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]}]}
        second = {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_b.id]}]}
        assert self.client.post(url, first, format="json").status_code == status.HTTP_200_OK
        refused = self.client.post(url, second, format="json")
        assert refused.status_code == status.HTTP_400_BAD_REQUEST
        assert refused.data["detail"] == "Tone is already answered, and the answer is final."

        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        changed = self.client.post(url, second, format="json")
        assert changed.status_code == status.HTTP_200_OK
        assert list(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag_id", flat=True)
        ) == [self.tone_b.id]

    def test_no_memory_refuses_a_players_answers_and_story(self):
        """#5292: the server refuses the write; hiding the editor is not the rule."""
        set_glimpse_memory(self.aura, GlimpseMemory.NO_MEMORY)
        answer = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]}]},
            format="json",
        )
        story = self.client.post(
            self._url("set-glimpse-prose"), {"text": "I remember."}, format="json"
        )
        for response in (answer, story):
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.data["detail"] == "This character has no memory of their Glimpse."
        set_glimpse_memory(self.aura, GlimpseMemory.REMEMBERED)

    def test_unknown_tag_id_rejected(self):
        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [999999]}]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_gets_404(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("set-glimpse-tags"),
            {"answers": [{"axis": GlimpseTagAxis.TONE, "tag_ids": [self.tone_a.id]}]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class SetGlimpseProseActionTest(GlimpseAuraActionTestBase):
    def test_owner_sets_prose_and_completes(self):
        response = self.client.post(
            self._url("set-glimpse-prose"),
            {"text": "I saw the threads unravel."},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["glimpse_state"] == GlimpseState.COMPLETE

    def test_non_owner_gets_404(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("set-glimpse-prose"),
            {"text": "Not my aura."},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class GlimpseDistinctionLinkActionTest(GlimpseAuraActionTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.character_distinction = CharacterDistinctionFactory(character=cls.character.sheet_data)
        cls.foreign_distinction = CharacterDistinctionFactory()  # different character

    def test_link_sets_from_glimpse(self):
        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        self.character_distinction.refresh_from_db()
        assert self.character_distinction.from_glimpse_id == self.aura.pk

    def test_unlink_clears_from_glimpse(self):
        self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        response = self.client.post(
            self._url("unlink-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        self.character_distinction.refresh_from_db()
        assert self.character_distinction.from_glimpse_id is None

    def test_linking_another_characters_distinction_404s(self):
        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.foreign_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owner_gets_404_on_link(self):
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owner_gets_404_on_unlink(self):
        self.client.post(
            self._url("link-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )
        self.client.force_authenticate(user=self.other_account)

        response = self.client.post(
            self._url("unlink-glimpse-distinction"),
            {"character_distinction_id": self.character_distinction.id},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
