"""Tests for the ghost interlude gating (#2287).

Dead actors are whitelisted to spectator verbs; emit/pose are further bounded
by GhostWindowPrerequisite (death scene / same IC day).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from evennia.utils import create as evennia_create

from actions.definitions.communication import EmitAction, SayAction
from actions.definitions.perception import LookAction
from actions.prerequisites import GhostWindowPrerequisite
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


def _make_room(key: str):
    return evennia_create.create_object(typeclass="typeclasses.rooms.Room", key=key, nohome=True)


class DeadActionGateTests(TestCase):
    """The central whitelist in Action.run refuses IC verbs for the dead."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        cls.character = cls.sheet.character

    def setUp(self) -> None:
        self.room = _make_room("Gate Room")
        self.character.location = self.room

    def test_dead_say_is_blocked(self) -> None:
        result = SayAction().run(actor=self.character, text="I still have things to say")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "The dead cannot do that.")

    def test_dead_look_is_allowed(self) -> None:
        result = LookAction().run(actor=self.character, target=self.room)
        self.assertTrue(result.success)

    def test_alive_say_is_not_gated(self) -> None:
        alive_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=alive_sheet)
        alive = alive_sheet.character
        alive.location = self.room
        result = SayAction().run(actor=alive, text="hello")
        self.assertNotEqual(result.message, "The dead cannot do that.")

    def test_dead_emit_same_real_day_is_allowed(self) -> None:
        # Died just now, no scene: the same-day window is open (real-day
        # fallback with no game clock seeded).
        result = EmitAction().run(actor=self.character, text="A cold wind passes.")
        self.assertTrue(result.success)


class GhostWindowPrerequisiteTests(TestCase):
    """The emit/pose window: death scene while active, or same IC day."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet)
        cls.character = cls.sheet.character

    def _kill(self, *, days_ago: int = 0, scene=None) -> None:
        self.vitals.life_state = CharacterLifeState.DEAD
        self.vitals.died_at = timezone.now() - timedelta(days=days_ago)
        self.vitals.died_in_scene = scene
        self.vitals.save(update_fields=["life_state", "died_at", "died_in_scene"])

    def test_alive_actor_passes(self) -> None:
        met, _ = GhostWindowPrerequisite().is_met(self.character)
        self.assertTrue(met)

    def test_dead_in_active_death_scene_passes(self) -> None:
        room = _make_room("Death Scene Room")
        self.character.location = room
        scene = SceneFactory(location=room)
        self._kill(days_ago=3, scene=scene)
        met, _ = GhostWindowPrerequisite().is_met(self.character)
        self.assertTrue(met)

    def test_dead_after_scene_closed_and_day_passed_is_blocked(self) -> None:
        room = _make_room("Closed Scene Room")
        self.character.location = room
        scene = SceneFactory(location=room, is_active=False, date_finished=timezone.now())
        self._kill(days_ago=3, scene=scene)
        met, reason = GhostWindowPrerequisite().is_met(self.character)
        self.assertFalse(met)
        self.assertIn("voice is spent", reason)

    def test_dead_same_day_without_scene_passes(self) -> None:
        self._kill(days_ago=0)
        met, _ = GhostWindowPrerequisite().is_met(self.character)
        self.assertTrue(met)
