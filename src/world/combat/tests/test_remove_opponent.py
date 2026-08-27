"""Tests for the remove_opponent service (#3382)."""

from evennia.utils.test_resources import EvenniaTestCase

from world.combat.constants import (
    CombatAllegiance,
    EncounterOutcome,
    EngagementLockStatus,
    LockBreakReason,
    OpponentStatus,
)
from world.scenes.constants import RoundStatus


class RemoveOpponentTests(EvenniaTestCase):
    def test_remove_opponent_flips_status(self):
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory()
        self.assertEqual(opponent.status, OpponentStatus.ACTIVE)

        remove_opponent(opponent)

        opponent.refresh_from_db()
        self.assertEqual(opponent.status, OpponentStatus.REMOVED)

    def test_remove_opponent_guards_on_non_active(self):
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory(status=OpponentStatus.DEFEATED)

        with self.assertRaises(ValueError):
            remove_opponent(opponent)

    def test_remove_opponent_breaks_active_engagement_lock(self):
        from world.combat.factories import CombatOpponentFactory, EngagementLockFactory
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory()
        lock = EngagementLockFactory(
            encounter=opponent.encounter,
            opponent=opponent,
            status=EngagementLockStatus.ACTIVE,
        )

        remove_opponent(opponent)

        lock.refresh_from_db()
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.REMOVED)

    def test_remove_opponent_with_no_lock_does_not_error(self):
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory()

        remove_opponent(opponent)  # no lock — should not raise

        opponent.refresh_from_db()
        self.assertEqual(opponent.status, OpponentStatus.REMOVED)

    def test_remove_opponent_fizzles_pending_windup(self):
        from world.combat.factories import CombatOpponentFactory, PendingOpponentAttackFactory
        from world.combat.models import PendingOpponentAttack
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory()
        pending = PendingOpponentAttackFactory(encounter=opponent.encounter, opponent=opponent)

        remove_opponent(opponent)

        self.assertFalse(PendingOpponentAttack.objects.filter(pk=pending.pk).exists())

    def test_remove_opponent_leaves_other_pending_windups_alone(self):
        from world.combat.factories import CombatOpponentFactory, PendingOpponentAttackFactory
        from world.combat.models import PendingOpponentAttack
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory()
        other = CombatOpponentFactory(encounter=opponent.encounter)
        other_pending = PendingOpponentAttackFactory(encounter=opponent.encounter, opponent=other)

        remove_opponent(opponent)

        self.assertTrue(PendingOpponentAttack.objects.filter(pk=other_pending.pk).exists())

    def test_remove_last_active_enemy_completes_encounter_victory(self):
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import remove_opponent

        opponent = CombatOpponentFactory(allegiance=CombatAllegiance.ENEMY)
        encounter = opponent.encounter

        remove_opponent(opponent)

        encounter.refresh_from_db()
        self.assertEqual(encounter.status, RoundStatus.COMPLETED)
        self.assertEqual(encounter.outcome, EncounterOutcome.VICTORY)

    def test_remove_ally_summon_does_not_force_completion(self):
        """Removing an ALLY opponent must not trip completion while an ENEMY remains (#1584)."""
        from world.combat.factories import CombatOpponentFactory, CombatParticipantFactory
        from world.combat.services import remove_opponent

        ally = CombatOpponentFactory(allegiance=CombatAllegiance.ALLY)
        encounter = ally.encounter
        CombatOpponentFactory(encounter=encounter, allegiance=CombatAllegiance.ENEMY)
        # A live ACTIVE PC keeps _check_encounter_completion's all_pcs_down clause
        # from vacuously tripping on an empty participant set.
        CombatParticipantFactory(encounter=encounter)

        remove_opponent(ally)

        ally.refresh_from_db()
        encounter.refresh_from_db()
        self.assertEqual(ally.status, OpponentStatus.REMOVED)
        self.assertNotEqual(encounter.status, RoundStatus.COMPLETED)

    def test_remove_opponent_does_not_complete_while_other_enemy_active(self):
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatOpponentFactory,
            CombatParticipantFactory,
        )
        from world.combat.services import remove_opponent

        encounter = CombatEncounterFactory()
        opponent_a = CombatOpponentFactory(encounter=encounter)
        CombatOpponentFactory(encounter=encounter)  # opponent B stays ACTIVE
        CombatParticipantFactory(encounter=encounter)

        remove_opponent(opponent_a)

        encounter.refresh_from_db()
        self.assertNotEqual(encounter.status, RoundStatus.COMPLETED)


class RemoveOpponentJourneyTests(EvenniaTestCase):
    """Journey test (#3382): mid-round removal, then last-enemy removal completes."""

    def test_remove_one_mid_round_then_remove_last_completes_victory(self):
        from world.combat.constants import EngagementLockStatus, LockInitiator
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            CombatRoundActionFactory,
            EngagementLockFactory,
            PendingOpponentAttackFactory,
        )
        from world.combat.models import CombatOpponent, PendingOpponentAttack
        from world.combat.services import remove_opponent
        from world.scenes.constants import RoundStatus as _RoundStatus

        opponent_a = CombatOpponentFactory(allegiance=CombatAllegiance.ENEMY)
        encounter = opponent_a.encounter
        opponent_b = CombatOpponentFactory(encounter=encounter, allegiance=CombatAllegiance.ENEMY)
        participant = CombatParticipantFactory(encounter=encounter)

        # A PC declares a technique focused on opponent A this round.
        CombatRoundActionFactory(
            participant=participant,
            round_number=1,
            focused_opponent_target=opponent_a,
        )
        # Opponent A has both an active engagement lock and a pending wind-up.
        lock = EngagementLockFactory(
            encounter=encounter,
            opponent=opponent_a,
            participant=participant,
            status=EngagementLockStatus.ACTIVE,
            initiated_by=LockInitiator.THREAT,
        )
        pending = PendingOpponentAttackFactory(encounter=encounter, opponent=opponent_a)
        opponent_a_ephemeral_objectdb_id = opponent_a.objectdb_id

        # --- GM removes opponent A mid-round ---
        remove_opponent(opponent_a)

        opponent_a.refresh_from_db()
        lock.refresh_from_db()
        self.assertEqual(opponent_a.status, OpponentStatus.REMOVED)
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.REMOVED)
        self.assertFalse(PendingOpponentAttack.objects.filter(pk=pending.pk).exists())

        # The fight continues — opponent B is still active, encounter not completed.
        encounter.refresh_from_db()
        opponent_b.refresh_from_db()
        self.assertIn(encounter.status, (_RoundStatus.DECLARING, _RoundStatus.BETWEEN_ROUNDS))
        self.assertEqual(opponent_b.status, OpponentStatus.ACTIVE)

        # --- GM removes opponent B, the last active enemy ---
        remove_opponent(opponent_b)

        encounter.refresh_from_db()
        opponent_b.refresh_from_db()
        self.assertEqual(encounter.status, _RoundStatus.COMPLETED)
        self.assertEqual(encounter.outcome, EncounterOutcome.VICTORY)
        self.assertEqual(opponent_b.status, OpponentStatus.REMOVED)

        # cleanup_completed_encounter's effects ran: opponent A's ephemeral
        # CombatNPC ObjectDB is gone (CombatOpponent rows themselves persist —
        # historical record, decision 5).
        from evennia.objects.models import ObjectDB

        self.assertFalse(ObjectDB.objects.filter(pk=opponent_a_ephemeral_objectdb_id).exists())
        self.assertTrue(CombatOpponent.objects.filter(pk=opponent_a.pk).exists())
        self.assertTrue(CombatOpponent.objects.filter(pk=opponent_b.pk).exists())
