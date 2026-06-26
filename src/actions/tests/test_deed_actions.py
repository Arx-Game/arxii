"""Unit tests for deed Actions (#1503)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from actions.definitions.deeds import SaveDeedStoryAction, SpreadTaleAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory, SceneFactory, SceneParticipationFactory
from world.societies.factories import (
    LegendEntryFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)


class DeedActionSetupMixin:
    """Build a controlled persona + scene + deed graph for deed action tests."""

    @classmethod
    def _build_awareness_graph(cls, character, account):
        """Return (persona, scene, deed) where account participates and persona knows the deed."""
        cls.sheet = CharacterSheetFactory(character=character)
        persona = cls.sheet.primary_persona

        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=account)

        society = SocietyFactory()
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=persona, organization=org)
        deed = LegendEntryFactory(persona=PersonaFactory(), base_value=50)
        deed.societies_aware.add(society)

        return persona, scene, deed


class SpreadTaleActionTests(TestCase, DeedActionSetupMixin):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.account = cls.account
        cls.persona, cls.scene, cls.deed = cls._build_awareness_graph(cls.character, cls.account)
        cls.action = SpreadTaleAction()

    def _run(self, **kwargs):
        """Invoke the action directly, merging defaults."""
        defaults = {
            "persona_id": self.persona.pk,
            "scene_id": self.scene.pk,
            "deed_id": self.deed.pk,
            "effort_level": "medium",
            "specialization_id": None,
            "pose_text": "A song.",
        }
        defaults.update(kwargs)
        return self.action.run(actor=self.character, **defaults)

    def test_success_returns_outcome_and_band(self):
        fake_resolution = SimpleNamespace(
            action_resolution=SimpleNamespace(
                main_result=SimpleNamespace(
                    check_result=SimpleNamespace(outcome_name="Good Success")
                )
            )
        )
        with patch(
            "world.scenes.action_services.create_and_resolve_area_action",
            return_value=fake_resolution,
        ):
            result = self._run()

        self.assertTrue(result.success)
        self.assertEqual(result.data["outcome"], "Good Success")
        self.assertEqual(result.data["band"], "Busy")

    def test_fails_when_persona_not_owned(self):
        other_persona = PersonaFactory()
        result = self._run(persona_id=other_persona.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "You do not control that persona.")

    def test_fails_when_not_a_scene_participant(self):
        self.scene.participants.clear()
        result = self._run()

        self.assertFalse(result.success)
        self.assertEqual(result.message, "You are not a participant in that scene.")

    def test_fails_when_deed_not_known(self):
        unknown = LegendEntryFactory(persona=PersonaFactory(), base_value=10)
        result = self._run(deed_id=unknown.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "This persona is not aware of that deed.")

    def test_fails_when_specialization_not_usable(self):
        result = self._run(specialization_id=999999)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "That form cannot be used to spread a tale.")


class SaveDeedStoryActionTests(TestCase, DeedActionSetupMixin):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.account = cls.account
        cls.persona, _scene, cls.deed = cls._build_awareness_graph(cls.character, cls.account)
        cls.action = SaveDeedStoryAction()

    def _run(self, **kwargs):
        defaults = {
            "persona_id": self.persona.pk,
            "deed_id": self.deed.pk,
            "text": "I was there.",
        }
        defaults.update(kwargs)
        return self.action.run(actor=self.character, **defaults)

    def test_success_saves_story(self):
        result = self._run()

        self.assertTrue(result.success)
        self.assertEqual(result.data["text"], "I was there.")
        self.assertEqual(result.data["author_name"], self.persona.name)
        self.assertIn("story_id", result.data)

    def test_fails_when_deed_not_known(self):
        unknown = LegendEntryFactory(persona=PersonaFactory(), base_value=10)
        result = self._run(deed_id=unknown.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "This persona is not aware of that deed.")

    def test_fails_when_text_is_empty(self):
        result = self._run(text="   ")

        self.assertFalse(result.success)
        self.assertEqual(result.message, "You must write something.")
