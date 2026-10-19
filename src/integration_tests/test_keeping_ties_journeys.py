"""Journeys through ``relationship`` (#3657, tranche 10).

Ysmay records her own side of a tie with Hobb and reads it back. Each journey
types what a player types through the command handler and asserts what she was
told and what the rows hold. No consent gate: a tie describes her side only
(ADR-0024).
"""

from __future__ import annotations

from evennia.utils.create import create_object

from integration_tests.harness import JourneyCase
from typeclasses.companions import CompanionObject
from world.action_points.models import ActionPointPool
from world.companions.factories import CompanionFactory
from world.journals.factories import JournalEntryFactory
from world.relationships.constants import LabelAwareness
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import CharacterRelationship, RelationshipBump, RelationshipLabel

NOT_HERE = "Could not find '{}'."


class KeepingTies(JourneyCase):
    """Ysmay names what Hobb is to her, changes her mind, and tells the world (or not)."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.friend = RelationshipTypeFactory(name="Friend")
        self.lover = RelationshipTypeFactory(name="Lover")

    def her_side(self) -> CharacterRelationship:
        return CharacterRelationship.objects.get(
            source=self.ysmay.sheet_data, target=self.hobb.sheet_data
        )

    def open_labels(self) -> list[RelationshipLabel]:
        return list(RelationshipLabel.objects.filter(ended_at__isnull=True).order_by("pk"))

    def test_a_label_is_declared_shifted_revealed_and_ended(self) -> None:
        self.assertIn(
            "You have recorded no relationships.", self.telnet(self.ysmay, "relationship")
        )
        self.assertIn(
            "Friend declared toward Hobb.", self.telnet(self.ysmay, "rel declare Hobb=Friend")
        )
        (label,) = self.open_labels()
        self.assertEqual(label.awareness, LabelAwareness.PRIVATE)
        self.assertEqual(label.relationship.source_id, self.ysmay.sheet_data.pk)
        self.assertEqual(label.relationship.target_id, self.hobb.sheet_data.pk)

        # The list and the detail read her side back; the detail adds the gauges.
        listed = self.telnet(self.ysmay, "relationship list")
        self.assertIn("Hobb: Friend (private) | depth", listed)
        self.assertIn("| tier", listed)
        shown = self.telnet(self.ysmay, "relationship show Hobb")
        self.assertIn("Hobb: Friend (private)", shown)
        self.assertIn("ap this week 0", shown)
        self.assertIn("Hobb:", self.telnet(self.ysmay, f"relationship show #{self.her_side().pk}"))
        self.assertIn(
            "Usage: relationship show <name|#>.", self.telnet(self.ysmay, "relationship show")
        )
        self.make_player("Bram", room=self.lantern)
        self.assertIn(
            "No relationship with 'Bram' found.", self.telnet(self.ysmay, "relationship show Bram")
        )

        # Made known, never hidden again.
        self.assertIn(
            "Friend is now public.",
            self.telnet(self.ysmay, "relationship reveal Hobb=Friend,public"),
        )
        self.assertIn(
            "A label can be made known, never hidden again.",
            self.telnet(self.ysmay, "relationship reveal Hobb=Friend,private"),
        )
        self.assertIn("Hobb: Friend | depth", self.telnet(self.ysmay, "relationship"))

        # A shift ends the old label and opens the new one with the note kept.
        self.assertIn(
            "Friend becomes Lover.",
            self.telnet(self.ysmay, "relationship shift Hobb=Friend,Lover,at the gate"),
        )
        (label,) = self.open_labels()
        self.assertEqual(label.type_id, self.lover.pk)
        self.assertEqual(label.note, "at the gate")
        self.assertFalse(RelationshipLabel.objects.filter(ended_at__isnull=True, type=self.friend))
        self.assertIn(
            "You have not declared Friend toward them.",
            self.telnet(self.ysmay, "relationship shift Hobb=Friend,Lover"),
        )
        self.assertIn("Lover ended.", self.telnet(self.ysmay, "relationship end Hobb=Lover"))
        self.assertEqual(self.open_labels(), [])
        self.assertIn("Lover (former)", self.telnet(self.ysmay, "relationship"))

    def test_the_lines_that_go_nowhere(self) -> None:
        usage = "Usage: relationship declare <name>=<type>[,private|clandestine|public]"
        self.assertIn(usage, self.telnet(self.ysmay, "relationship declare =Friend"))
        self.assertIn(usage, self.telnet(self.ysmay, "relationship declare Hobb"))
        self.assertIn(
            "No relationship type 'Nemesis'.",
            self.telnet(self.ysmay, "relationship declare Hobb=Nemesis"),
        )
        # Once, not twice: the loud search had said it first.
        self.assertEqual(
            NOT_HERE.format("Nobody"),
            self.telnet(self.ysmay, "relationship declare Nobody=Friend").strip(),
        )
        self.assertIn(
            "Usage: relationship [list|show", self.telnet(self.ysmay, "relationship frobnicate")
        )
        self.assertIn(
            "Usage: relationship plus <name>", self.telnet(self.ysmay, "relationship plus")
        )
        self.assertIn(
            "Usage: relationship shift <name>=<from>,<to>[,note]",
            self.telnet(self.ysmay, "relationship shift Hobb=Friend"),
        )
        self.assertIn(
            "Usage: relationship reveal <name>=<type>,<clandestine|public>",
            self.telnet(self.ysmay, "relationship reveal Hobb=Friend"),
        )
        self.assertIn(
            "Usage: relationship end <name>=<type>",
            self.telnet(self.ysmay, "relationship end Hobb"),
        )
        self.assertEqual(RelationshipLabel.objects.count(), 0)
        self.assertIn(
            "You cannot record a relationship with yourself.",
            self.telnet(self.ysmay, "relationship declare Ysmay=Friend"),
        )

    def test_ap_a_summary_and_a_tier_she_has_not_earned(self) -> None:
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 40
        pool.save(update_fields=["current"])
        self.assertIn(
            "9 AP this week toward Hobb.", self.telnet(self.ysmay, "relationship ap Hobb=9")
        )
        self.assertEqual(self.her_side().allocation.ap_amount, 9)
        self.assertIn("ap this week 9", self.telnet(self.ysmay, "relationship show Hobb"))
        self.assertIn("AP must be a number.", self.telnet(self.ysmay, "relationship ap Hobb=nine"))
        self.assertIn(
            "Usage: relationship ap <name>=<n>", self.telnet(self.ysmay, "relationship ap Hobb")
        )

        self.assertIn(
            "Summary saved.", self.telnet(self.ysmay, "relationship summary Hobb=A throat I owe.")
        )
        self.assertEqual(self.her_side().summary, "A throat I owe.")
        self.assertIn("A throat I owe.", self.telnet(self.ysmay, "relationship show Hobb"))

        entry = JournalEntryFactory(author=self.ysmay.sheet_data, about=self.hobb.sheet_data)
        self.assertIn(
            "The relationship is not deep enough for the next tier.",
            self.telnet(self.ysmay, f"relationship advance Hobb={entry.pk}"),
        )
        theirs = JournalEntryFactory(author=self.hobb.sheet_data, about=self.ysmay.sheet_data)
        self.assertIn(
            f"No journal entry #{theirs.pk} of yours found.",
            self.telnet(self.ysmay, f"relationship advance Hobb={theirs.pk}"),
        )
        self.assertIn(
            "journal entry id must be a number.",
            self.telnet(self.ysmay, "relationship advance Hobb=the one about the gate"),
        )

    def test_a_pose_in_a_scene_may_warm_or_cool_her_regard_once(self) -> None:
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.hobb, "pose tips his hat.")
        self.assertIn(
            "Your regard for Hobb warms.", self.telnet(self.ysmay, "relationship plus Hobb")
        )
        bump = RelationshipBump.objects.get()
        self.assertEqual(bump.valence, 1)
        self.assertEqual(self.her_side().affection, 1)
        self.assertIn(
            "You've already acknowledged everything they've done this scene.",
            self.telnet(self.ysmay, "relationship plus Hobb"),
        )
        # The switch spelling reaches the same verb.
        self.telnet(self.hobb, "pose turns his back.")
        self.assertIn("Your regard for Hobb cools.", self.telnet(self.ysmay, "rel/neg Hobb"))
        self.assertEqual(RelationshipBump.objects.filter(valence=-1).count(), 1)

    def test_a_bonded_companion_may_be_named_too(self) -> None:
        ash = CompanionFactory(owner=self.ysmay.sheet_data, name="Ash")
        ash_obj = create_object(CompanionObject, key="Ash", location=self.lantern)
        ash.objectdb = ash_obj
        ash.save(update_fields=["objectdb"])
        RelationshipTypeFactory(name="Loyalty")
        self.assertIn(
            "Loyalty declared toward Ash.",
            self.telnet(self.ysmay, "relationship declare Ash=Loyalty"),
        )
        side = CharacterRelationship.objects.get(source=self.ysmay.sheet_data, target_companion=ash)
        self.assertEqual(RelationshipLabel.objects.filter(relationship=side).count(), 1)
        self.assertIn("Ash: Loyalty (private)", self.telnet(self.ysmay, "relationship"))
        self.assertIn("Ash: Loyalty (private)", self.telnet(self.ysmay, "relationship show Ash"))
        self.assertIn(
            "A relationship tier can only be advanced with a character.",
            self.telnet(self.ysmay, "relationship advance Ash=1"),
        )
