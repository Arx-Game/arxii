"""The live frame carries the room-wide fields the REST feed carries (#4508).

A pose that arrived over the websocket used to show without its endorse buttons,
entrance endorsement or tags until a reload, because the frame had fewer fields than
``InteractionListSerializer`` and the page filled the gap with placeholders.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, SceneEntryEndorsementFactory
from world.scenes.constants import InteractionMode, PoseKind
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_services import (
    push_interaction,
    scene_entry_endorsements_for,
)

FEED_FIELDS = (
    "visibility",
    "pose_kind",
    "endorsee_sheet_id",
    "endorsable_resonances",
    "conversation",
    "availability",
    "pose_endorsers",
    "entry_endorsers",
    "reactions",
    "reaction_windows",
    "dramatic_moment_tags",
)


class PushFeedFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        cls.author_char = CharacterFactory(db_key="Author", location=cls.room)
        cls.author = CharacterSheetFactory(character=cls.author_char)
        cls.viewer = CharacterSheetFactory(character=CharacterFactory(db_key="Viewer"))
        cls.scene = SceneFactory()
        cls.resonance = CharacterResonanceFactory(character_sheet=cls.author).resonance
        cls.interaction = InteractionFactory(
            persona=cls.author.primary_persona,
            mode=InteractionMode.POSE,
            pose_kind=PoseKind.ENTRY,
            scene=cls.scene,
        )

    def _pushed_payload(self) -> dict:
        with patch("world.scenes.interaction_services._broadcast_to_location") as broadcast:
            push_interaction(self.interaction)
        return broadcast.call_args.args[1]

    def test_live_pose_carries_room_wide_feed_fields(self):
        payload = self._pushed_payload()
        context = {
            "character_sheet_ids": {self.viewer.pk},
            "viewer_sheet": self.viewer,
            "scene_entry_endorsements": scene_entry_endorsements_for(self.scene),
        }
        rest = InteractionListSerializer(self.interaction, context=context).data
        for field in FEED_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(payload[field], rest[field])
        self.assertEqual(payload["pose_kind"], "entry")
        self.assertEqual(
            payload["endorsable_resonances"],
            [{"id": self.resonance.pk, "name": self.resonance.name}],
        )

    def test_second_entrance_carries_existing_entry_endorsers(self):
        endorser = CharacterSheetFactory(character=CharacterFactory(db_key="Endorser"))
        SceneEntryEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=self.author,
            scene=self.scene,
            resonance=self.resonance,
        )
        payload = self._pushed_payload()
        self.assertEqual(
            [e["persona_id"] for e in payload["entry_endorsers"]],
            [endorser.primary_persona.pk],
        )
