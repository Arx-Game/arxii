"""Won-over rows in the aftermath digest, web and telnet (#4091, Task 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB

from world.checks.factories import CheckTypeFactory
from world.combat.aftermath import build_aftermath_digest, render_aftermath_digest
from world.combat.constants import EncounterOutcome
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import ParticipantSerializer
from world.combat.won_over import stamp_won_over_opponents, won_over_rows
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.factories import TechniqueFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import PersonaFactory


class WonOverDigestTests(TestCase):
    """won_over_rows, render_aftermath_digest, and the serializer's won_over list."""

    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Won-over digest break")
        cls.charm = ConditionTemplateFactory(
            name="Won-over digest charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        self.enc = CombatEncounterFactory()
        self.pc_a = CombatParticipantFactory(encounter=self.enc)
        self.pc_b = CombatParticipantFactory(encounter=self.enc)
        self.source = self.pc_a.character_sheet.character

        persona_a = self.pc_a.character_sheet.primary_persona
        persona_a.name = "Wren"
        persona_a.save(update_fields=["name"])

        technique = TechniqueFactory(name="Velvet Bond")

        named_persona = PersonaFactory(name="Tamsin")
        self.named = CombatOpponentFactory(
            encounter=self.enc, name="Road Bandit", persona=named_persona
        )
        # A persona-backed opponent's own ObjectDB has no location by default;
        # the row's "present" check needs one.
        room = ObjectDB.objects.get(pk=self.enc.room_id)
        self.named.objectdb.location = room
        self.named.objectdb.save()

        # can_bind now also requires the bind window be open (#4091 fix round 1):
        # the charmer must be in the SAME room as the nameless body, not merely
        # have charmed it once. CombatParticipantFactory places the charmer
        # nowhere by default.
        self.room = room
        self.source.location = room
        self.source.save()

        self.nameless = CombatOpponentFactory(encounter=self.enc, name="Lurking Foot")

        ConditionInstanceFactory(
            target=self.named.objectdb,
            condition=self.charm,
            source_character=self.source,
            source_technique=technique,
        )
        ConditionInstanceFactory(
            target=self.nameless.objectdb,
            condition=self.charm,
            source_character=self.source,
        )

        stamp_won_over_opponents(self.enc)

        # build_aftermath_digest (and the serializer's get_aftermath) require a
        # completed encounter; stamping directly (not via complete_encounter)
        # skips cleanup_completed_encounter, which would delete the nameless
        # opponent's ephemeral ObjectDB (and cascade its ConditionInstance)
        # before these assertions run.
        self.enc.status = RoundStatus.COMPLETED
        self.enc.completed_at = timezone.now()
        self.enc.outcome = EncounterOutcome.VICTORY
        self.enc.save(update_fields=["status", "completed_at", "outcome"])

    def _rows_by_opponent(self, viewer):
        return {row.opponent_id: row for row in won_over_rows(self.enc, viewer)}

    def test_charmer_viewer_can_bind_the_nameless_and_take_in_the_named(self):
        rows = self._rows_by_opponent(self.pc_a.character_sheet)
        nameless_row = rows[self.nameless.pk]
        named_row = rows[self.named.pk]

        self.assertTrue(nameless_row.can_bind)
        self.assertFalse(nameless_row.can_settle)
        self.assertTrue(nameless_row.can_send_away)

        self.assertTrue(named_row.can_take_into_service)
        self.assertTrue(named_row.can_settle)
        self.assertTrue(named_row.can_send_away)

    def test_can_bind_is_false_once_the_charmer_leaves_the_room(self):
        """#4091 fix round 1: can_bind must use the same bind-window predicate
        as telnet's ``companion promote`` and ``promote_summon_to_companion`` —
        a charm alone isn't enough once the charmer has left."""
        from evennia import create_object

        other_room = create_object("typeclasses.rooms.Room", key="Elsewhere", nohome=True)
        self.source.location = other_room
        self.source.save()

        rows = self._rows_by_opponent(self.pc_a.character_sheet)
        nameless_row = rows[self.nameless.pk]

        self.assertFalse(nameless_row.can_bind)

    def test_can_send_away_is_false_once_the_charmer_leaves_the_room(self):
        """#4091 task 12 fix round 1 ruling 1: ``can_send_away`` now goes through
        the same ONE shared presence+hold predicate as the ``send_away`` action
        prerequisite -- it used to be just ``is_source and present``, which never
        checked whether the charmer was still co-located with the target."""
        from evennia import create_object

        other_room = create_object("typeclasses.rooms.Room", key="Elsewhere Sendaway", nohome=True)
        self.source.location = other_room
        self.source.save()

        rows = self._rows_by_opponent(self.pc_a.character_sheet)
        nameless_row = rows[self.nameless.pk]
        named_row = rows[self.named.pk]

        self.assertFalse(nameless_row.can_send_away)
        self.assertFalse(named_row.can_send_away)

    def test_non_charmer_viewer_can_only_settle_the_named(self):
        rows = self._rows_by_opponent(self.pc_b.character_sheet)
        nameless_row = rows[self.nameless.pk]
        named_row = rows[self.named.pk]

        self.assertFalse(nameless_row.can_bind)
        self.assertFalse(nameless_row.can_send_away)
        self.assertFalse(named_row.can_take_into_service)
        self.assertFalse(named_row.can_send_away)
        self.assertTrue(named_row.can_settle)

    def test_render_includes_won_over_line_with_source_and_duration(self):
        digest = build_aftermath_digest(self.enc, self.pc_a)
        text = render_aftermath_digest(digest, include_secret_beat=False)

        self.assertIn(
            "Won over: Road Bandit (charmed, by Wren's Velvet Bond; holds until settled)", text
        )

    def test_serializer_carries_the_same_flags_and_a_condition_dict(self):
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.is_staff = True

        data = ParticipantSerializer(self.pc_a, context={"request": request, "is_gm": False}).data
        won_over = data["aftermath"]["won_over"]
        self.assertEqual(len(won_over), 2)

        named = next(row for row in won_over if row["name"] == "Road Bandit")
        self.assertTrue(named["can_take_into_service"])
        self.assertTrue(named["can_settle"])
        self.assertIsNotNone(named["condition"])
        self.assertEqual(named["source_label"], "Wren's Velvet Bond")
