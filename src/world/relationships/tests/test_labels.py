"""Label writes (#3957): declare, shift, end, awareness, mutual."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness, TypeValence
from world.relationships.exceptions import (
    AwarenessBackwardError,
    LabelAlreadyDeclaredError,
    LabelEndedError,
    SameTypeShiftError,
)
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import CharacterRelationship
from world.relationships.services import (
    advance_awareness,
    declare_label,
    end_label,
    get_or_create_side,
    is_mutual,
    mutual_hostile,
    shift_label,
)
from world.roster.factories import RosterTenureFactory, grant_test_tenure


class DeclareLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.friend = RelationshipTypeFactory(name="Friend", valence=TypeValence.WARM)
        cls.lover = RelationshipTypeFactory(name="Lover", valence=TypeValence.WARM)

    def test_declare_creates_side_and_private_label(self):
        side = get_or_create_side(source=self.a, target=self.b)
        label = declare_label(side=side, type=self.friend)
        self.assertEqual(label.awareness, LabelAwareness.PRIVATE)
        self.assertEqual(CharacterRelationship.objects.filter(source=self.a).count(), 1)

    def test_declare_twice_refused(self):
        side = get_or_create_side(source=self.a, target=self.b)
        declare_label(side=side, type=self.friend)
        with self.assertRaises(LabelAlreadyDeclaredError):
            declare_label(side=side, type=self.friend)

    def test_shift_ends_old_and_records_replaced(self):
        side = get_or_create_side(source=self.a, target=self.b)
        old = declare_label(side=side, type=self.friend, awareness=LabelAwareness.PUBLIC)
        new = shift_label(label=old, new_type=self.lover, note="at the gate")
        old.refresh_from_db()
        self.assertIsNotNone(old.ended_at)
        self.assertEqual(new.replaced_id, old.pk)
        self.assertEqual(new.awareness, LabelAwareness.PUBLIC)
        self.assertEqual(new.note, "at the gate")
        self.assertEqual([lab.pk for lab in side.open_labels()], [new.pk])

    def test_shift_to_same_type_refused(self):
        side = get_or_create_side(source=self.a, target=self.b)
        old = declare_label(side=side, type=self.friend)
        with self.assertRaises(SameTypeShiftError):
            shift_label(label=old, new_type=self.friend)

    def test_end_keeps_row(self):
        side = get_or_create_side(source=self.a, target=self.b)
        label = declare_label(side=side, type=self.friend)
        end_label(label=label)
        label.refresh_from_db()
        self.assertTrue(label.is_former)
        with self.assertRaises(LabelEndedError):
            end_label(label=label)

    def test_awareness_forward_only(self):
        side = get_or_create_side(source=self.a, target=self.b)
        label = declare_label(side=side, type=self.friend)
        advance_awareness(label=label, to=LabelAwareness.CLANDESTINE)
        self.assertIsNotNone(label.clandestine_at)
        advance_awareness(label=label, to=LabelAwareness.PUBLIC)
        self.assertIsNotNone(label.public_at)
        with self.assertRaises(AwarenessBackwardError):
            advance_awareness(label=label, to=LabelAwareness.CLANDESTINE)
        private = declare_label(side=side, type=self.lover)
        advance_awareness(label=private, to=LabelAwareness.PUBLIC)
        self.assertEqual(private.awareness, LabelAwareness.PUBLIC)


class MutualTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.tenure_a = grant_test_tenure(cls.a)
        cls.tenure_b = grant_test_tenure(cls.b)
        cls.rival = RelationshipTypeFactory(name="Rival", valence=TypeValence.HOSTILE)
        cls.mentor = RelationshipTypeFactory(name="Mentor")
        cls.student = RelationshipTypeFactory(name="Student", counterpart=cls.mentor)
        cls.mentor.counterpart = cls.student
        cls.mentor.save(update_fields=["counterpart"])
        cls.ab = get_or_create_side(source=cls.a, target=cls.b)
        cls.ba = get_or_create_side(source=cls.b, target=cls.a)

    def test_symmetric_mutual_needs_both_known(self):
        declare_label(
            side=self.ab, type=self.rival, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        self.assertFalse(is_mutual(self.ab, self.rival))
        declare_label(
            side=self.ba, type=self.rival, awareness=LabelAwareness.PRIVATE, tenure=self.tenure_b
        )
        self.assertFalse(is_mutual(self.ab, self.rival))
        label = self.ba.open_labels().get(type=self.rival)
        advance_awareness(label=label, to=LabelAwareness.CLANDESTINE)
        self.assertTrue(is_mutual(self.ab, self.rival))
        self.assertTrue(mutual_hostile(self.a, self.b))
        self.assertTrue(mutual_hostile(self.b, self.a))

    def test_counterpart_pair(self):
        declare_label(
            side=self.ab, type=self.mentor, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        declare_label(
            side=self.ba, type=self.student, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_b
        )
        self.assertTrue(is_mutual(self.ab, self.mentor))
        self.assertTrue(is_mutual(self.ba, self.student))
        self.assertFalse(mutual_hostile(self.a, self.b))

    def test_closed_tenure_does_not_count(self):
        declare_label(
            side=self.ab, type=self.rival, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        stale = RosterTenureFactory(roster_entry=self.b.roster_entry)
        stale.end_date = stale.start_date
        stale.save(update_fields=["end_date"])
        declare_label(side=self.ba, type=self.rival, awareness=LabelAwareness.PUBLIC, tenure=stale)
        self.assertFalse(mutual_hostile(self.a, self.b))

    def test_ended_label_does_not_count(self):
        la = declare_label(
            side=self.ab, type=self.rival, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        declare_label(
            side=self.ba, type=self.rival, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_b
        )
        self.assertTrue(mutual_hostile(self.a, self.b))
        end_label(label=la)
        self.assertFalse(mutual_hostile(self.a, self.b))
