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
from world.scenes.persona_display import compose_sdesc
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
        # 24, not 25 (#4101 fix round 3): subject_persona is now a plain FK on
        # GMPrompt, batched via select_related("prompt__subject_persona") on the
        # SAME Prefetch -- the round-2 nested cached_primary_persona to_attr
        # Prefetch (an extra query) is gone.
        with self.assertNumQueries(24):
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

    def test_null_subject_persona_omits_name_entirely(self) -> None:
        """#4101 fix round 3, ruling R9-3: no sheet at event time (e.g. a
        STAKE_OUTCOME prompt) -> ``subject_name``/``subject_persona_id`` are
        omitted from the payload, never sent empty/null."""
        sceneless_interaction = InteractionFactory(scene=self.scene)
        prompt = GMPromptFactory(
            kind=GMPromptKind.STAKE_OUTCOME,
            scene=None,
            character_sheet=None,
            subject_persona=None,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
        )
        GMPromptNarration.objects.create(
            prompt=prompt,
            interaction=sceneless_interaction,
            interaction_timestamp=sceneless_interaction.timestamp,
        )
        url = reverse("interaction-list")
        resp = self.client.get(url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        row = next(r for r in resp.data["results"] if r["id"] == sceneless_interaction.pk)
        self.assertEqual(
            row["narrates"],
            {"prompt_id": prompt.pk, "kind": "stake_outcome", "kind_label": "Stake outcome"},
        )
        self.assertNotIn("subject_name", row["narrates"])
        self.assertNotIn("subject_persona_id", row["narrates"])


class NarratedEventFieldMaskingTest(APITestCase):
    """``narrates`` must not unmask a disguise (#4101 fix round 2, ruling R9-1;
    fix round 3, ruling R9-3 -- the subject's face is FROZEN at event-routing
    time, and the feed shows it through the SAME per-viewer display map as
    every other persona on the page)."""

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
        # subject_persona explicit (#4101 fix round 3): this is now a FROZEN
        # field set at routing time, not re-derived from the sheet's current
        # active persona on every read -- the factory default would otherwise
        # resolve to the sheet's PRIMARY persona, not this disguise.
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.sheet,
            subject_persona=cls.disguise,
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

    def test_undisguising_after_the_fact_does_not_rewrite_the_narrated_row(self) -> None:
        """#4101 fix round 3, ruling R9-3: a later persona switch (removing the
        mask) must never rewrite what an already-narrated row says."""
        set_active_persona(self.sheet, self.sheet.primary_persona)

        url = reverse("interaction-list")
        resp = self.client.get(url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        row = next(r for r in resp.data["results"] if r["id"] == self.narrated_interaction.pk)
        self.assertEqual(row["narrates"]["subject_name"], self.disguise.name)
        self.assertEqual(row["narrates"]["subject_persona_id"], self.disguise.pk)


class NarratedEventFieldUndiscoveredMaskTest(APITestCase):
    """An anonymous (``is_fake_name``) subject the viewer hasn't discovered reads as the
    SAME composed sdesc the feed shows for an undiscovered writer persona (#4101 fix
    round 3, ruling R9-3) -- never the mask's own name, never the real identity."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = AccountFactory()
        cls.gm = AccountFactory()
        cls.scene = SceneFactory()
        cls.sheet = CharacterSheetFactory()
        cls.disguise = PersonaFactory(
            character_sheet=cls.sheet,
            persona_type=PersonaType.TEMPORARY,
            name="A Masked Stranger",
            is_fake_name=True,
        )
        cls.narrated_interaction = InteractionFactory(scene=cls.scene)
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.sheet,
            subject_persona=cls.disguise,
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

    def test_undiscovered_disguised_subject_shows_composed_sdesc(self) -> None:
        url = reverse("interaction-list")
        resp = self.client.get(url, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        row = next(r for r in resp.data["results"] if r["id"] == self.narrated_interaction.pk)
        self.assertEqual(row["narrates"]["subject_name"], compose_sdesc(self.disguise))
        self.assertNotEqual(row["narrates"]["subject_name"], self.disguise.name)
