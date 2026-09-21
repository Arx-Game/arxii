"""Tie actions (#3957) run through action.run(): the one seam telnet and web share."""

from django.test import TestCase

from actions.definitions.relationships import (
    AdvanceLabelAwarenessAction,
    AdvanceRelationshipTierAction,
    DeclareLabelAction,
    EndLabelAction,
    SetTieAllocationAction,
    SetTieSummaryAction,
    ShiftLabelAction,
)
from evennia_extensions.factories import CharacterFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import CharacterRelationship, RelationshipLabel
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _character():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry)
    return character


class TieActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = _character()
        cls.other = _character()
        cls.friend = RelationshipTypeFactory(name="Friend")
        cls.lover = RelationshipTypeFactory(name="Lover")

    def _declare(self, **kwargs):
        return DeclareLabelAction().run(
            actor=self.actor, target_sheet=self.other.sheet_data, type=self.friend, **kwargs
        )

    def test_declare_defaults_private(self):
        result = self._declare()
        self.assertTrue(result.success, result.message)
        label = RelationshipLabel.objects.get()
        self.assertEqual(label.awareness, LabelAwareness.PRIVATE)
        self.assertEqual(label.relationship.source_id, self.actor.sheet_data.pk)
        self.assertEqual(result.data["relationship_id"], label.relationship_id)
        self.assertIsNotNone(label.declared_by_tenure_id)

    def test_declare_self_refused(self):
        result = DeclareLabelAction().run(
            actor=self.actor, target_sheet=self.actor.sheet_data, type=self.friend
        )
        self.assertFalse(result.success)
        self.assertEqual(CharacterRelationship.objects.count(), 0)

    def test_declare_twice_refused(self):
        self._declare()
        result = self._declare()
        self.assertFalse(result.success)
        self.assertEqual(result.message, "That label is already declared.")

    def test_shift_end_awareness(self):
        self._declare()
        label = RelationshipLabel.objects.get()
        result = ShiftLabelAction().run(
            actor=self.actor, label=label, new_type=self.lover, note="at the gate"
        )
        self.assertTrue(result.success, result.message)
        new = RelationshipLabel.objects.get(ended_at__isnull=True)
        self.assertEqual(new.type_id, self.lover.pk)
        result = AdvanceLabelAwarenessAction().run(
            actor=self.actor, label=new, awareness=LabelAwareness.PUBLIC
        )
        self.assertTrue(result.success, result.message)
        result = AdvanceLabelAwarenessAction().run(
            actor=self.actor, label=new, awareness=LabelAwareness.PRIVATE
        )
        self.assertFalse(result.success)
        result = EndLabelAction().run(actor=self.actor, label=new)
        self.assertTrue(result.success, result.message)
        self.assertEqual(RelationshipLabel.objects.filter(ended_at__isnull=True).count(), 0)

    def test_label_actions_refuse_someone_elses_label(self):
        self._declare()
        label = RelationshipLabel.objects.get()
        result = EndLabelAction().run(actor=self.other, label=label)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "That is not your relationship.")

    def test_allocation_and_summary(self):
        pool = ActionPointPool.get_or_create_for_character(self.actor)
        pool.current = 40
        pool.save(update_fields=["current"])
        result = SetTieAllocationAction().run(
            actor=self.actor, target_sheet=self.other.sheet_data, ap_amount=9
        )
        self.assertTrue(result.success, result.message)
        side = CharacterRelationship.objects.get()
        self.assertEqual(side.allocation.ap_amount, 9)
        result = SetTieSummaryAction().run(
            actor=self.actor, target_sheet=self.other.sheet_data, summary="  A throat. "
        )
        self.assertTrue(result.success, result.message)
        side.refresh_from_db()
        self.assertEqual(side.summary, "A throat.")

    def test_advance_tier_reports_the_gate(self):
        from world.journals.factories import JournalEntryFactory

        entry = JournalEntryFactory(author=self.actor.sheet_data, about=self.other.sheet_data)
        result = AdvanceRelationshipTierAction().run(
            actor=self.actor, target_sheet=self.other.sheet_data, journal_entry=entry
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "The relationship is not deep enough for the next tier.")
