"""Tests for scene attachment on duel encounter creation (Task 4 — #1236)."""

from django.test import TestCase
from evennia import create_object

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.duels import create_lethal_duel, create_pvp_duel
from world.combat.factories import ThreatPoolFactory
from world.scenes.constants import ScenePrivacyMode


class DuelSceneAttachmentTests(TestCase):
    """create_pvp_duel and create_lethal_duel must attach a scene; privacy derived from room."""

    @classmethod
    def setUpTestData(cls):
        cls.challenger_sheet = CharacterSheetFactory()
        cls.challenged_sheet = CharacterSheetFactory()
        cls.pc_sheet = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        # Room must be created per test — ObjectDB is not deepcopy-safe.
        self.room = create_object("typeclasses.rooms.Room", key="Duel Scene Room", nohome=True)
        self.opponent_kwargs = {
            "name": "Test Duelist",
            "max_health": 200,
            "threat_pool": self.threat_pool,
            "soak_value": 50,
        }

    def test_pvp_duel_creates_scene_private_by_default(self) -> None:
        # Explicitly set the auto-created profile to is_public=False (default is True).
        RoomProfileFactory(objectdb=self.room, is_public=False)
        enc = create_pvp_duel(self.challenger_sheet, self.challenged_sheet, self.room)
        self.assertIsNotNone(enc.scene)
        self.assertEqual(enc.scene.privacy_mode, ScenePrivacyMode.PRIVATE)

    def test_pvp_duel_public_room_creates_public_scene(self) -> None:
        RoomProfileFactory(objectdb=self.room, is_public=True)
        enc = create_pvp_duel(self.challenger_sheet, self.challenged_sheet, self.room)
        self.assertEqual(enc.scene.privacy_mode, ScenePrivacyMode.PUBLIC)

    def test_lethal_duel_creates_scene(self) -> None:
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertIsNotNone(enc.scene)
