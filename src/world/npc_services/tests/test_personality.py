"""Thin personality layer tests (#2827 phase 4)."""

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.instantiation import materialize_functionary
from world.npc_services.models import NpcPreference, PersonalityTrait, PreferenceValence
from world.npc_services.personality import assign_random_personality, preference_modifier
from world.scenes.factories import PersonaFactory


class PreferenceModifierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.persuasion = CheckTypeFactory(name="Persuasion Test Check")
        cls.flattery = PersonalityTrait.objects.create(
            name="Flattery", eased_check=cls.persuasion, ease_magnitude=5
        )
        cls.bluntness = PersonalityTrait.objects.create(
            name="Bluntness", eased_check=cls.persuasion, ease_magnitude=3
        )
        cls.persona = PersonaFactory()

    def test_likes_ease_and_dislikes_harden(self):
        NpcPreference.objects.create(
            persona=self.persona, trait=self.flattery, valence=PreferenceValence.LIKES
        )
        NpcPreference.objects.create(
            persona=self.persona, trait=self.bluntness, valence=PreferenceValence.DISLIKES
        )
        self.assertEqual(preference_modifier(self.persona, self.persuasion), 2)

    def test_faceless_or_indifferent_is_zero(self):
        self.assertEqual(preference_modifier(None, self.persuasion), 0)
        other_check = CheckTypeFactory(name="Unrelated Check")
        self.assertEqual(preference_modifier(self.persona, other_check), 0)


class PersonalityAssignmentTests(TestCase):
    def test_materialization_rolls_quirks(self):
        PersonalityTrait.objects.create(name="Gossip")
        PersonalityTrait.objects.create(name="Coin")
        PersonalityTrait.objects.create(name="Piety")
        functionary = FunctionaryFactory()
        persona = materialize_functionary(functionary)
        self.assertEqual(NpcPreference.objects.filter(persona=persona).count(), 3)

    def test_assignment_is_idempotent_and_content_safe(self):
        persona = PersonaFactory()
        self.assertEqual(assign_random_personality(persona), 0)  # no traits authored
        PersonalityTrait.objects.create(name="Later Trait")
        created = assign_random_personality(persona)
        self.assertEqual(created, 1)
        self.assertEqual(assign_random_personality(persona), 0)


class AptitudeTests(TestCase):
    def test_band_mints_once_and_stays_stable(self):
        from world.tasking.constants import TaskCategory
        from world.tasking.services import aptitude_band

        persona = PersonaFactory()
        first = aptitude_band(persona, TaskCategory.SPYCRAFT)
        self.assertIn(first, (-1, 0, 1, 2))
        for _ in range(5):
            self.assertEqual(aptitude_band(persona, TaskCategory.SPYCRAFT), first)
