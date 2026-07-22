"""Telegraphed enemy wind-up lifecycle tests (#2637).

Covers: declaration creates a PendingOpponentAttack (not a same-round
CombatOpponentAction) + dual-dispatches the telegraph; cooldown bookkeeping
counts the declaration itself; maturation resolves through the normal
NPC-attack path with the downgrade ladder applied; the interception rider;
and the auto-callout v1 shape.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    PendingOpponentAttackFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction, PendingOpponentAttack
from world.combat.services import (
    _apply_windup_interception_rider,
    _batch_fetch_cooldown_data,
    _get_eligible_entries,
    resolve_round,
    select_npc_actions,
)
from world.combat.types import ActionOutcome, OpponentDamageResult
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Declaration: windup_rounds > 0 defers to a PendingOpponentAttack
# ---------------------------------------------------------------------------


class WindupDeclarationTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(
            pool=pool,
            windup_rounds=1,
            base_damage=100,
            weight=100,
            windup_telegraph="{opponent} winds up something huge!",
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_windup_entry_creates_pending_attack_not_same_round_action(
        self, mock_broadcast
    ) -> None:
        actions = select_npc_actions(self.encounter)

        self.assertEqual(actions, [])
        self.assertFalse(CombatOpponentAction.objects.filter(opponent=self.opponent).exists())
        pending = PendingOpponentAttack.objects.get(opponent=self.opponent)
        self.assertEqual(pending.threat_entry_id, self.entry.pk)
        self.assertEqual(pending.declared_round, 1)
        self.assertEqual(pending.resolves_round, 2)
        self.assertEqual(pending.target_id, self.participant.pk)
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_telegraph_dispatches_ws_and_reaches_a_real_listener_unmocked(
        self, mock_broadcast
    ) -> None:
        """Telnet half runs genuinely unmocked (HARD parity precedent):
        a real character standing in the room receives the line via its
        own .msg(), not a mocked room.msg_contents."""
        listener = CharacterFactory(location=self.encounter.room)

        with mock.patch.object(listener, "msg") as mock_msg:
            select_npc_actions(self.encounter)

        self.assertTrue(mock_broadcast.called)
        self.assertGreaterEqual(mock_msg.call_count, 1)
        _args, kwargs = mock_msg.call_args
        sent_text, _outkwargs = kwargs["text"]
        self.assertIn("winds up something huge", sent_text)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_blank_telegraph_falls_back_to_generic_line(self, mock_broadcast) -> None:  # noqa: ARG002
        self.entry.windup_telegraph = ""
        self.entry.save(update_fields=["windup_telegraph"])
        listener = CharacterFactory(location=self.encounter.room)

        with mock.patch.object(listener, "msg") as mock_msg:
            select_npc_actions(self.encounter)

        _args, kwargs = mock_msg.call_args
        sent_text, _outkwargs = kwargs["text"]
        self.assertIn("begins something enormous", sent_text)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_zero_windup_rounds_is_unchanged_same_round_behavior(self, mock_broadcast) -> None:  # noqa: ARG002
        self.entry.windup_rounds = 0
        self.entry.save(update_fields=["windup_rounds"])

        actions = select_npc_actions(self.encounter)

        self.assertEqual(len(actions), 1)
        self.assertFalse(PendingOpponentAttack.objects.filter(opponent=self.opponent).exists())


# ---------------------------------------------------------------------------
# Cooldown bookkeeping: a wind-up declaration counts as "used" (#2637)
# ---------------------------------------------------------------------------


class WindupCooldownBookkeepingTests(TestCase):
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_windup_declaration_puts_the_entry_on_cooldown(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        windup_entry = ThreatPoolEntryFactory(
            pool=pool, windup_rounds=1, cooldown_rounds=3, weight=100
        )
        filler_entry = ThreatPoolEntryFactory(pool=pool, windup_rounds=0, weight=1)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        CombatParticipantFactory(encounter=encounter)

        select_npc_actions(encounter)
        self.assertTrue(
            PendingOpponentAttack.objects.filter(
                opponent=opponent, threat_entry=windup_entry
            ).exists()
        )

        cooldown_used = _batch_fetch_cooldown_data(
            [opponent],
            {pool.pk: [windup_entry, filler_entry]},
            [windup_entry, filler_entry],
            round_number=2,
        )
        eligible = _get_eligible_entries(
            opponent, [windup_entry, filler_entry], cooldown_used.get(opponent.pk, set())
        )
        self.assertNotIn(windup_entry, eligible)
        self.assertIn(filler_entry, eligible)


# ---------------------------------------------------------------------------
# Maturation + the downgrade ladder
# ---------------------------------------------------------------------------


class WindupMaturationTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=2)
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=pool, windup_rounds=1, base_damage=100)
        # Deliberately NOT wired to this pool — decouples the opponent's live
        # selection (the resolve_round auto-select fallback, #2637 design 8)
        # from the manually-created pending row under test, which references
        # this entry by FK regardless of the opponent's current threat_pool.
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=1000, max_health=1000)

    def _pending(self, *, downgrades: int) -> PendingOpponentAttack:
        return PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            threat_entry=self.entry,
            target=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=downgrades,
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_no_downgrades_resolves_full_damage(self, mock_broadcast) -> None:  # noqa: ARG002
        pending = self._pending(downgrades=0)

        resolve_round(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 900)
        self.assertFalse(PendingOpponentAttack.objects.filter(pk=pending.pk).exists())

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_one_downgrade_scales_damage_to_075(self, mock_broadcast) -> None:  # noqa: ARG002
        self._pending(downgrades=1)

        resolve_round(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 925)  # 1000 - (100 * 0.75)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_two_downgrades_scales_damage_to_050(self, mock_broadcast) -> None:  # noqa: ARG002
        self._pending(downgrades=2)

        resolve_round(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 950)  # 1000 - (100 * 0.5)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_three_downgrades_fizzles_entirely(self, mock_broadcast) -> None:
        pending = self._pending(downgrades=3)

        resolve_round(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 1000)
        self.assertFalse(PendingOpponentAttack.objects.filter(pk=pending.pk).exists())
        self.assertFalse(
            CombatOpponentAction.objects.filter(opponent=self.opponent, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_target_left_encounter_fizzles(self, mock_broadcast) -> None:  # noqa: ARG002
        from world.combat.constants import ParticipantStatus

        pending = self._pending(downgrades=0)
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])

        resolve_round(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 1000)
        self.assertFalse(PendingOpponentAttack.objects.filter(pk=pending.pk).exists())


# ---------------------------------------------------------------------------
# Interception rider: a landing PC hit downgrades a winding-up opponent
# ---------------------------------------------------------------------------


class WindupInterceptionRiderTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        attacker_sheet = CharacterSheetFactory()
        self.attacker = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=attacker_sheet
        )

    def _landed_outcome(self, *, damage_dealt: int) -> ActionOutcome:
        outcome = ActionOutcome(entity_type="pc", entity_label=str(self.attacker))
        outcome.damage_results.append(
            OpponentDamageResult(
                damage_dealt=damage_dealt,
                health_damaged=damage_dealt > 0,
                probed=False,
                probing_increment=0,
                defeated=False,
                opponent_id=self.opponent.pk,
            )
        )
        return outcome

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_blind_hit_adds_one_downgrade(self, mock_broadcast) -> None:  # noqa: ARG002
        pending = PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=2,
            called_out=False,
        )

        _apply_windup_interception_rider(
            self.opponent, self._landed_outcome(damage_dealt=10), self.attacker
        )

        pending.refresh_from_db()
        self.assertEqual(pending.downgrades, 1)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_called_out_hit_adds_two_downgrades(self, mock_broadcast) -> None:
        pending = PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=2,
            called_out=True,
        )

        _apply_windup_interception_rider(
            self.opponent, self._landed_outcome(damage_dealt=10), self.attacker
        )

        pending.refresh_from_db()
        self.assertEqual(pending.downgrades, 2)
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_zero_damage_hit_does_not_downgrade(self, mock_broadcast) -> None:  # noqa: ARG002
        pending = PendingOpponentAttackFactory(
            encounter=self.encounter, opponent=self.opponent, declared_round=1, resolves_round=2
        )

        _apply_windup_interception_rider(
            self.opponent, self._landed_outcome(damage_dealt=0), self.attacker
        )

        pending.refresh_from_db()
        self.assertEqual(pending.downgrades, 0)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_no_pending_attack_is_a_noop(self, mock_broadcast) -> None:
        _apply_windup_interception_rider(
            self.opponent, self._landed_outcome(damage_dealt=10), self.attacker
        )
        self.assertFalse(mock_broadcast.called)


# ---------------------------------------------------------------------------
# Auto-callout v1 (#2637 design 6)
# ---------------------------------------------------------------------------


class WindupAutoCalloutTests(TestCase):
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_flagged_engaged_role_auto_calls_out(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, windup_rounds=1, weight=100)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        covenant = CovenantFactory()
        flagged_role = CovenantRoleFactory(
            covenant_type=covenant.covenant_type, calls_out_windups=True
        )
        sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=flagged_role, engaged=True
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        select_npc_actions(encounter)

        pending = PendingOpponentAttack.objects.get(opponent=opponent)
        self.assertTrue(pending.called_out)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_sub_role_rides_the_parent_flag(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, windup_rounds=1, weight=100)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        flagged_parent = CovenantRoleFactory(
            covenant_type=covenant.covenant_type, calls_out_windups=True
        )
        sub_role = SubroleCovenantRoleFactory(parent_role=flagged_parent)
        sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=sub_role, engaged=True
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        select_npc_actions(encounter)

        pending = PendingOpponentAttack.objects.get(opponent=opponent)
        self.assertTrue(pending.called_out)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_no_flagged_role_present_not_called_out(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, windup_rounds=1, weight=100)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        CombatParticipantFactory(encounter=encounter)

        select_npc_actions(encounter)

        pending = PendingOpponentAttack.objects.get(opponent=opponent)
        self.assertFalse(pending.called_out)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_at_most_one_call_out_per_round_per_encounter(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, windup_rounds=1, weight=100)
        CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        covenant = CovenantFactory()
        flagged_role = CovenantRoleFactory(
            covenant_type=covenant.covenant_type, calls_out_windups=True
        )
        sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=flagged_role, engaged=True
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        select_npc_actions(encounter)

        called_out_count = PendingOpponentAttack.objects.filter(
            encounter=encounter, declared_round=1, called_out=True
        ).count()
        self.assertEqual(called_out_count, 1)
