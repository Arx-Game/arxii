"""Per-audience reads (#3957)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory
from world.relationships.constants import LabelAwareness, TieAudience
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.reads import (
    depth_breakdown,
    third_party_can_see,
    tie_audience,
    tie_stream,
    visible_labels,
)
from world.relationships.services import declare_label, end_label, get_or_create_side
from world.scenes.factories import InteractionFactory, SceneFactory


class ReadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.c = CharacterSheetFactory()
        cls.ab = get_or_create_side(source=cls.a, target=cls.b)
        cls.ab.scene_depth, cls.ab.invested_depth, cls.ab.tier = 48, 184, 2
        cls.ab.affection, cls.ab.conflict = 41, 28
        cls.ab.save()
        cls.ba = get_or_create_side(source=cls.b, target=cls.a)
        cls.ba.scene_depth, cls.ba.invested_depth = 48, 60
        cls.ba.save()
        lover = RelationshipTypeFactory(name="Lover")
        enemy = RelationshipTypeFactory(name="Enemy")
        friend = RelationshipTypeFactory(name="Friend")
        cls.lover = declare_label(side=cls.ab, type=lover, awareness=LabelAwareness.CLANDESTINE)
        cls.enemy = declare_label(side=cls.ab, type=enemy)
        cls.former = declare_label(side=cls.ab, type=friend, awareness=LabelAwareness.PUBLIC)
        end_label(label=cls.former)

    def test_audiences(self):
        self.assertEqual(tie_audience(self.ab, self.a, False), TieAudience.OWNER)
        self.assertEqual(tie_audience(self.ab, self.b, False), TieAudience.OTHER_SIDE)
        self.assertEqual(tie_audience(self.ab, self.c, False), TieAudience.THIRD_PARTY)
        self.assertEqual(tie_audience(self.ab, self.c, True), TieAudience.STAFF)

    def test_visible_labels(self):
        self.assertEqual(len(visible_labels(self.ab, TieAudience.OWNER)), 3)
        other = visible_labels(self.ab, TieAudience.OTHER_SIDE)
        self.assertEqual([lab.pk for lab in other], [self.lover.pk, self.former.pk])
        self.assertEqual(
            [lab.pk for lab in visible_labels(self.ab, TieAudience.THIRD_PARTY)], [self.former.pk]
        )

    def test_third_party_needs_an_open_public_label(self):
        self.assertFalse(third_party_can_see(self.ab))

    def test_third_party_sees_an_open_public_label(self):
        declare_label(
            side=self.ab, type=RelationshipTypeFactory(name="Ally"), awareness=LabelAwareness.PUBLIC
        )
        self.assertTrue(third_party_can_see(self.ab))

    def test_breakdown(self):
        owner = depth_breakdown(self.ab, TieAudience.OWNER)
        self.assertEqual(
            owner,
            {
                "tier": 2,
                "scenes": 48,
                "invested": 184,
                "their_added_depth": 108,
                "affection": 41,
                "conflict": 28,
            },
        )
        other = depth_breakdown(self.ab, TieAudience.OTHER_SIDE)
        self.assertIsNone(other["affection"])
        self.assertIsNone(depth_breakdown(self.ab, TieAudience.THIRD_PARTY))

    def test_stream_filters_black_entries(self):
        JournalEntryFactory(author=self.a, about=self.b, is_public=True, title="White")
        JournalEntryFactory(author=self.a, about=self.b, is_public=False, title="Black")
        JournalEntryFactory(author=self.b, about=self.a, is_public=True, title="Theirs")
        titles = [i["title"] for i in tie_stream(self.ab, self.b, False)]
        self.assertEqual(titles, ["Theirs", "White"])
        titles = [i["title"] for i in tie_stream(self.ab, self.a, False)]
        self.assertIn("Black", titles)

    def test_stream_staff_with_no_viewer_sees_black_entries(self):
        JournalEntryFactory(author=self.a, about=self.b, is_public=False, title="Black")
        titles = [i["title"] for i in tie_stream(self.ab, None, True)]
        self.assertIn("Black", titles)

    def test_stream_includes_a_scene_both_posed_in(self):
        scene = SceneFactory(name="The Gate")
        for sheet in (self.a, self.b):
            persona = sheet.personas.first() or sheet.personas.create(name=sheet.character.db_key)
            InteractionFactory(scene=scene, persona=persona)
        items = tie_stream(self.ab, self.b, False)
        scene_items = [i for i in items if i["kind"] == "scene"]
        self.assertEqual(len(scene_items), 1)
        self.assertEqual(scene_items[0]["title"], "The Gate")
        self.assertEqual(scene_items[0]["id"], scene.pk)
