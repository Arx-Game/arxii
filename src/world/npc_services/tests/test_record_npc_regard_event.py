"""Tests for record_npc_regard_event — the NpcRegardEvent write seam (#2039)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.factories import CombatOpponentActionFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.models import REGARD_MAX, NpcRegard
from world.npc_services.regard import get_regard_event_config, record_npc_regard_event
from world.scenes.factories import PersonaFactory


class RecordNpcRegardEventTests(TestCase):
    def test_creates_regard_row_and_event_on_first_call(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        event = record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=10,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        regard = NpcRegard.objects.get(holder_persona=holder, target_persona=target)
        self.assertEqual(regard.value, 10)
        self.assertEqual(event.regard_id, regard.pk)
        self.assertEqual(event.amount, 10)

    def test_second_call_accumulates_on_existing_regard(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=10,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=-3,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        regard = NpcRegard.objects.get(holder_persona=holder, target_persona=target)
        self.assertEqual(regard.value, 7)

    def test_amount_clamped_to_config_max_delta(self):
        cfg = get_regard_event_config()
        cfg.max_event_delta = 20
        cfg.save(update_fields=["max_event_delta"])
        holder = PersonaFactory()
        target = PersonaFactory()
        event = record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=999,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        self.assertEqual(event.amount, 20)

    def test_negative_amount_clamped_symmetrically(self):
        cfg = get_regard_event_config()
        cfg.max_event_delta = 20
        cfg.save(update_fields=["max_event_delta"])
        holder = PersonaFactory()
        target = PersonaFactory()
        event = record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=-999,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        self.assertEqual(event.amount, -20)

    def test_regard_value_clamped_to_regard_min_max(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        for _ in range(200):
            record_npc_regard_event(
                holder_persona=holder,
                target=target,
                amount=100,
                reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
            )
        regard = NpcRegard.objects.get(holder_persona=holder, target_persona=target)
        self.assertEqual(regard.value, REGARD_MAX)

    def test_npc_harmed_pc_without_citation_raises(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        with self.assertRaises(ValidationError):
            record_npc_regard_event(
                holder_persona=holder,
                target=target,
                amount=-10,
                reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
            )

    def test_invalid_citation_does_not_leave_orphan_regard_row(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        with self.assertRaises(ValidationError):
            record_npc_regard_event(
                holder_persona=holder,
                target=target,
                amount=-10,
                reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
            )
        self.assertEqual(
            NpcRegard.objects.filter(holder_persona=holder, target_persona=target).count(),
            0,
        )

    def test_npc_harmed_pc_with_citation_succeeds(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        opponent_action = CombatOpponentActionFactory()
        event = record_npc_regard_event(
            holder_persona=holder,
            target=target,
            amount=-10,
            reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
            source_npc_combat_action=opponent_action,
        )
        self.assertEqual(event.source_npc_combat_action_id, opponent_action.pk)
