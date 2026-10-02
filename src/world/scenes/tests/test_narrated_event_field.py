"""Interaction rows carry the event they narrate (#4101 Task 9; demo Screen 3)."""

from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind
from world.gm.factories import GMPromptFactory
from world.gm.models import GMPromptNarration
from world.scenes.factories import InteractionFactory, SceneFactory


class NarratedEventFieldTest(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = AccountFactory()
        cls.gm = AccountFactory()
        cls.scene = SceneFactory()
        cls.sheet = CharacterSheetFactory()
        cls.narrated_interaction = InteractionFactory(scene=cls.scene)
        cls.plain_interaction = InteractionFactory(scene=cls.scene)
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

    def test_narrated_row_carries_the_event_it_narrates(self) -> None:
        url = reverse("interaction-list")
        # Pinned count (not a scaling claim): proves the prompt_narrations Prefetch
        # batches both rows in one query (see query #18 of the captured list when this
        # was derived) rather than issuing one per narrated row.
        with self.assertNumQueries(26):
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

        plain_row = rows[self.plain_interaction.pk]
        self.assertIsNone(plain_row["narrates"])
