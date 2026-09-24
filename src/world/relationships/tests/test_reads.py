"""Per-audience reads (#3957)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory
from world.relationships.constants import LabelAwareness, TieAudience, TypeValence
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import RelationshipLabel
from world.relationships.reads import (
    _labels_are_mutual,  # unit-testing the batched sibling directly
    build_tie_page,
    depth_breakdown,
    third_party_can_see,
    tie_audience,
    tie_stream,
    visible_labels,
)
from world.relationships.services import declare_label, end_label, get_or_create_side, is_mutual
from world.roster.factories import grant_test_tenure
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
        titles = [i["title"] for i in tie_stream(self.ab, self.b, False, account=None)]
        self.assertEqual(titles, ["Theirs", "White"])
        titles = [i["title"] for i in tie_stream(self.ab, self.a, False, account=None)]
        self.assertIn("Black", titles)

    def test_stream_staff_with_no_viewer_sees_black_entries(self):
        JournalEntryFactory(author=self.a, about=self.b, is_public=False, title="Black")
        titles = [i["title"] for i in tie_stream(self.ab, None, True, account=None)]
        self.assertIn("Black", titles)

    def test_stream_includes_a_scene_both_posed_in(self):
        """A PUBLIC scene reaches even the anonymous (``account=None``) audience.

        The privacy gate itself is request-level (``test_views``): ``viewable_by`` needs a
        real account to tell a participant from a stranger.
        """
        scene = SceneFactory(name="The Gate")
        for sheet in (self.a, self.b):
            persona = sheet.personas.first() or sheet.personas.create(name=sheet.character.db_key)
            InteractionFactory(scene=scene, persona=persona)
        items = tie_stream(self.ab, self.b, False, account=None)
        scene_items = [i for i in items if i["kind"] == "scene"]
        self.assertEqual(len(scene_items), 1)
        self.assertEqual(scene_items[0]["title"], "The Gate")
        self.assertEqual(scene_items[0]["id"], scene.pk)


class MutualEquivalenceTests(TestCase):
    """``reads._labels_are_mutual`` (batched, Python) must agree with ``services.is_mutual``
    (single-row, SQL) on every case the rule distinguishes (#3957 review) — two spellings of
    one predicate, held against each other the way ``world.journals``' ``CanRetortAnnotationTests``
    holds its own annotation-vs-service pair together.
    """

    def _pair(self):
        a = CharacterSheetFactory()
        b = CharacterSheetFactory()
        return a, b, grant_test_tenure(a), grant_test_tenure(b)

    def _labels(self, side):
        return list(
            RelationshipLabel.objects.filter(relationship=side).select_related(
                "type", "type__counterpart", "declared_by_tenure"
            )
        )

    def _assert_agree(self, side, reverse, label_type):
        side.refresh_from_db()
        if reverse is not None:
            reverse.refresh_from_db()
        my_labels = self._labels(side)
        their_labels = self._labels(reverse) if reverse is not None else []
        for public_only in (False, True):
            expected = is_mutual(side, label_type, public_only=public_only)
            actual = _labels_are_mutual(
                side, my_labels, reverse, their_labels, label_type, public_only=public_only
            )
            self.assertEqual(
                actual,
                expected,
                f"public_only={public_only}: reads._labels_are_mutual()={actual} but "
                f"services.is_mutual()={expected}",
            )

    def test_both_public_open_active_is_mutual_both_ways(self):
        a, b, tenure_a, tenure_b = self._pair()
        ally = RelationshipTypeFactory(name="Ally0")
        side = get_or_create_side(source=a, target=b)
        reverse = get_or_create_side(source=b, target=a)
        declare_label(side=side, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_a)
        declare_label(side=reverse, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_b)
        self._assert_agree(side, reverse, ally)

    def test_one_clandestine_is_mutual_for_other_side_only(self):
        a, b, tenure_a, tenure_b = self._pair()
        ally = RelationshipTypeFactory(name="Ally1")
        side = get_or_create_side(source=a, target=b)
        reverse = get_or_create_side(source=b, target=a)
        declare_label(side=side, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_a)
        declare_label(
            side=reverse, type=ally, awareness=LabelAwareness.CLANDESTINE, tenure=tenure_b
        )
        self._assert_agree(side, reverse, ally)

    def test_closed_tenure_is_never_mutual(self):
        a, b, tenure_a, tenure_b = self._pair()
        ally = RelationshipTypeFactory(name="Ally2")
        side = get_or_create_side(source=a, target=b)
        reverse = get_or_create_side(source=b, target=a)
        declare_label(side=side, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_a)
        tenure_b.end_date = tenure_b.start_date
        tenure_b.save(update_fields=["end_date"])
        declare_label(side=reverse, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_b)
        self._assert_agree(side, reverse, ally)

    def test_frozen_reverse_side_is_never_mutual(self):
        a, b, tenure_a, tenure_b = self._pair()
        ally = RelationshipTypeFactory(name="Ally3")
        side = get_or_create_side(source=a, target=b)
        reverse = get_or_create_side(source=b, target=a)
        side.scene_depth = 25
        side.save(update_fields=["scene_depth"])
        reverse.scene_depth = 40
        reverse.save(update_fields=["scene_depth"])
        declare_label(side=side, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_a)
        declare_label(side=reverse, type=ally, awareness=LabelAwareness.PUBLIC, tenure=tenure_b)
        reverse.is_active = False
        reverse.save(update_fields=["is_active"])
        self._assert_agree(side, reverse, ally)

        # A frozen side stops EARNING but keeps the depth it already earned (spec Decision
        # 2): build_tie_page's displayed depth must still match the model's own unfiltered
        # pair_depth() even though the same frozen reverse correctly kills mutuality above.
        side.refresh_from_db()
        reverse.refresh_from_db()
        row = build_tie_page([side], viewer_sheet=a, is_staff=False)[0]
        self.assertEqual(row["depth"], side.pair_depth())
        self.assertEqual(row["breakdown"]["their_added_depth"], reverse.depth)

    def test_hostile_counterpart_pair_agrees(self):
        a, b, tenure_a, tenure_b = self._pair()
        rival = RelationshipTypeFactory(name="Rival4", valence=TypeValence.HOSTILE)
        side = get_or_create_side(source=a, target=b)
        reverse = get_or_create_side(source=b, target=a)
        declare_label(side=side, type=rival, awareness=LabelAwareness.PUBLIC, tenure=tenure_a)
        declare_label(side=reverse, type=rival, awareness=LabelAwareness.PUBLIC, tenure=tenure_b)
        self._assert_agree(side, reverse, rival)
