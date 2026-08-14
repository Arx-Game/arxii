"""Tests for #2993 language mechanics: model/service persistence (Task 4) and

read-time comprehension in the scene-log serializers (Task 7). Real per-recipient
WS-render assertions live in Task 5's action tests, where rooms/audiences exist
end-to-end — this module covers the model fields, the record/create plumbing, and
the list/detail API's per-viewer comprehension gating.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory
from world.scenes.interaction_services import create_interaction, record_interaction
from world.scenes.mute_services import set_mute
from world.species.factories import LanguageFactory
from world.traits.factories import CharacterTraitValueFactory
from world.traits.models import Trait, TraitCategory, TraitType


class TestInteractionLanguageField(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.language = LanguageFactory(name="TestKhatic")

    def test_create_interaction_persists_language(self) -> None:
        char_a = CharacterFactory(db_key="Alice")
        sheet_a = CharacterSheetFactory(character=char_a)

        interaction = create_interaction(
            persona=sheet_a.primary_persona,
            content="Ktha vess morren.",
            mode=InteractionMode.SAY,
            language=self.language,
        )
        interaction.refresh_from_db()
        self.assertEqual(interaction.language_id, self.language.pk)

    def test_create_interaction_defaults_language_to_none(self) -> None:
        char_a = CharacterFactory(db_key="Alice")
        sheet_a = CharacterSheetFactory(character=char_a)

        interaction = create_interaction(
            persona=sheet_a.primary_persona,
            content="waves.",
            mode=InteractionMode.POSE,
        )
        self.assertIsNone(interaction.language_id)


class TestRecordInteractionLanguage(TestCase):
    def setUp(self) -> None:
        patcher = patch("world.scenes.interaction_services.push_interaction")
        self.mock_push = patcher.start()
        self.addCleanup(patcher.stop)
        self.language = LanguageFactory(name="TestRecordKhatic")

    def test_record_interaction_stamps_language(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        char_b = CharacterFactory(db_key="Bob", location=room)
        CharacterSheetFactory(character=char_a)
        CharacterSheetFactory(character=char_b)

        result = record_interaction(
            character=char_a,
            content="Ktha vess morren.",
            mode=InteractionMode.SAY,
            language=self.language,
        )
        assert result is not None
        self.assertEqual(result.language_id, self.language.pk)

    def test_record_interaction_without_language_stays_none(self) -> None:
        room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        char_a = CharacterFactory(db_key="Alice", location=room)
        CharacterSheetFactory(character=char_a)

        result = record_interaction(
            character=char_a,
            content="strides in.",
            mode=InteractionMode.POSE,
        )
        assert result is not None
        self.assertIsNone(result.language_id)


class TestCharacterSheetCurrentLanguage(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.language = LanguageFactory(name="TestSheetKhatic")

    def test_defaults_to_none(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertIsNone(sheet.current_language)

    def test_set_and_read_round_trip(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.current_language = self.language
        sheet.save(update_fields=["current_language"])
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_language, self.language)


class TestInteractionListComprehensionAPI(APITestCase):
    """Task 7 (#2993): per-viewer read-time comprehension in the scene-log API.

    Bypass order under test: writer's own sheets full, staff full, fluent
    listener full, zero-fluency listener garbled and deterministic (list
    endpoint) and garbled-not-blank on a muted interaction (detail endpoint —
    the mute reveal is not a comprehension bypass).
    """

    CONTENT = "the caravan leaves at dawn through the salt gate"

    @classmethod
    def setUpTestData(cls) -> None:
        trait = Trait.objects.create(
            name="TestComprehensionAPIKhatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = LanguageFactory(name="TestComprehensionAPIKhatic", trait=trait)

        def build_account():
            account = AccountFactory()
            character = CharacterFactory()
            sheet = CharacterSheetFactory(character=character)
            roster_entry = RosterEntryFactory(character_sheet=sheet)
            player_data = PlayerDataFactory(account=account)
            RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
            return account, sheet

        cls.writer_account, cls.writer_sheet = build_account()
        CharacterTraitValueFactory(character=cls.writer_sheet, trait=trait, value=100)
        cls.writer_persona = cls.writer_sheet.primary_persona

        cls.fluent_account, cls.fluent_sheet = build_account()
        CharacterTraitValueFactory(character=cls.fluent_sheet, trait=trait, value=100)

        # Zero-fluency viewer: deliberately no CharacterTraitValue row —
        # fluency_value() treats an absent row as 0.
        cls.zero_account, cls.zero_sheet = build_account()

        cls.staff_account = AccountFactory(is_staff=True)

        cls.interaction = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.SAY,
            language=cls.language,
            content=cls.CONTENT,
        )

    def _get_row(self, account) -> dict:
        self.client.force_authenticate(user=account)
        url = reverse("interaction-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        return next(r for r in response.data["results"] if r["id"] == self.interaction.pk)

    def test_fluent_viewer_sees_full_content_and_language_name(self) -> None:
        row = self._get_row(self.fluent_account)
        self.assertEqual(row["content"], self.CONTENT)
        self.assertEqual(row["language_id"], self.language.pk)
        self.assertEqual(row["language_name"], self.language.name)

    def test_zero_fluency_viewer_sees_deterministic_garble(self) -> None:
        row_1 = self._get_row(self.zero_account)
        row_2 = self._get_row(self.zero_account)
        self.assertNotEqual(row_1["content"], self.CONTENT)
        self.assertEqual(row_1["content"], row_2["content"])

    def test_writer_sees_own_content_full(self) -> None:
        row = self._get_row(self.writer_account)
        self.assertEqual(row["content"], self.CONTENT)

    def test_staff_sees_full_content(self) -> None:
        row = self._get_row(self.staff_account)
        self.assertEqual(row["content"], self.CONTENT)

    def test_detail_endpoint_garbles_muted_language_interaction(self) -> None:
        """Mute-reveal (detail endpoint, #2087) is NOT a comprehension bypass (#2993).

        Mirrors ``test_mute_refinements.py::test_detail_endpoint_returns_full_content``'s
        idiom, but the interaction is language-tagged AND the viewer has muted the
        writer's persona. The detail endpoint must still un-blank the mute (so the
        response is not ``""``) while continuing to garble for a zero-fluency listener
        (so the response is not the raw ``CONTENT`` either) — proving the click-to-expand
        reveal only bypasses the mute blank, never per-viewer language comprehension.
        """
        zero_pd, _ = PlayerData.objects.get_or_create(account=self.zero_account)
        set_mute(owner=zero_pd, muted_persona=self.writer_persona, ic=True, ooc=False)

        self.client.force_authenticate(user=self.zero_account)
        url = reverse("interaction-detail", args=[self.interaction.pk])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        self.assertNotEqual(response.data["content"], "")
        self.assertNotEqual(response.data["content"], self.CONTENT)
