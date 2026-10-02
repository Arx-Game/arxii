"""Interaction rows carry the event they narrate (#4101 Task 9; demo Screen 3)."""

from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind
from world.gm.factories import GMPromptFactory
from world.gm.models import GMPromptNarration
from world.scenes.constants import PersonaType
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.services import set_active_persona


class NarratedEventFieldTest(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = AccountFactory()
        cls.gm = AccountFactory()
        cls.scene = SceneFactory()
        cls.sheet = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        cls.plain_interaction = InteractionFactory(scene=cls.scene)
        cls.narrated_interaction = InteractionFactory(scene=cls.scene)
        cls.narrated_interaction_b = InteractionFactory(scene=cls.scene)
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.sheet,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
        )
        # A second real narration link (#4101 fix round 2, finding 9) -- with only
        # one link in the fixture, the pinned query count can't actually prove the
        # prompt_narrations Prefetch batches more than one row into the same query;
        # it would pass identically even if narrated_event_payload queried per link.
        cls.prompt_b = GMPromptFactory(
            kind=GMPromptKind.MIRACLE,
            scene=cls.scene,
            character_sheet=cls.sheet_b,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
        )
        GMPromptNarration.objects.create(
            prompt=cls.prompt,
            interaction=cls.narrated_interaction,
            interaction_timestamp=cls.narrated_interaction.timestamp,
        )
        GMPromptNarration.objects.create(
            prompt=cls.prompt_b,
            interaction=cls.narrated_interaction_b,
            interaction_timestamp=cls.narrated_interaction_b.timestamp,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.viewer)

    def test_narrated_rows_carry_the_event_they_narrate(self) -> None:
        url = reverse("interaction-list")
        # Pinned count (not a scaling claim): proves the prompt_narrations Prefetch
        # batches BOTH narrated rows (two distinct GMPromptNarration links, two
        # distinct subjects) in one query rather than one query per linked row.
        with self.assertNumQueries(25):
            resp = self.client.get(url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = {row["id"]: row for row in resp.data["results"]}

        narrated_row = rows[self.narrated_interaction.pk]
        self.assertEqual(
            narrated_row["narrates"],
            {
                "prompt_id": self.prompt.pk,
                "kind": "crossing",
                "kind_label": "Crossing",
                "subject_name": self.sheet.primary_persona.name,
                "subject_persona_id": self.sheet.primary_persona.pk,
            },
        )

        narrated_row_b = rows[self.narrated_interaction_b.pk]
        self.assertEqual(
            narrated_row_b["narrates"],
            {
                "prompt_id": self.prompt_b.pk,
                "kind": "miracle",
                "kind_label": "Miracle",
                "subject_name": self.sheet_b.primary_persona.name,
                "subject_persona_id": self.sheet_b.primary_persona.pk,
            },
        )

        plain_row = rows[self.plain_interaction.pk]
        self.assertIsNone(plain_row["narrates"])


class NarratedEventFieldMaskingTest(APITestCase):
    """``narrates`` must not unmask a disguise (#4101 fix round 2, ruling R9-1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = AccountFactory()
        cls.gm = AccountFactory()
        cls.scene = SceneFactory()
        cls.sheet = CharacterSheetFactory()
        cls.disguise = PersonaFactory(
            character_sheet=cls.sheet, persona_type=PersonaType.TEMPORARY, name="A Masked Stranger"
        )
        set_active_persona(cls.sheet, cls.disguise)
        cls.narrated_interaction = InteractionFactory(scene=cls.scene)
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.sheet,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
        )
        GMPromptNarration.objects.create(
            prompt=cls.prompt,
            interaction=cls.narrated_interaction,
            interaction_timestamp=cls.narrated_interaction.timestamp,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.viewer)

    def test_narrated_row_shows_the_disguise_never_the_primary_name(self) -> None:
        url = reverse("interaction-list")
        resp = self.client.get(url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        row = next(r for r in resp.data["results"] if r["id"] == self.narrated_interaction.pk)
        self.assertEqual(row["narrates"]["subject_name"], self.disguise.name)
        self.assertEqual(row["narrates"]["subject_persona_id"], self.disguise.pk)
        self.assertNotEqual(row["narrates"]["subject_name"], self.sheet.primary_persona.name)
        self.assertNotEqual(row["narrates"]["subject_persona_id"], self.sheet.primary_persona.pk)
