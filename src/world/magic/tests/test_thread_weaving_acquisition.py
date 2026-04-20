"""Tests for ThreadWeaving acquisition service functions (Spec A §6).

Phase 14: compute_thread_weaving_xp_cost + accept_thread_weaving_unlock.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.action_points.factories import ActionPointPoolFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.exceptions import XPInsufficient
from world.magic.factories import (
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import CharacterThreadWeavingUnlock
from world.magic.services import accept_thread_weaving_unlock, compute_thread_weaving_xp_cost
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import ExperiencePointsData, XPTransaction
from world.roster.factories import RosterTenureFactory


def _seed_xp(learner: object, amount: int) -> ExperiencePointsData:
    """Attach an AccountDB to learner.character and seed its XP tracker.

    Uses the Evennia M2M pattern: set .account on the in-memory instance AND
    call account.characters.add() so both directions of the M2M are populated.
    """
    from evennia.objects.models import ObjectDB

    account = AccountFactory()
    character = learner.character  # type: ignore[union-attr]
    # Set on the in-memory instance (Evennia typeclass caching layer)
    character.account = account
    # Persist via the M2M relation on the AccountDB side
    ObjectDB.objects.filter(pk=character.pk).update()
    account.characters.add(character)
    xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={"total_earned": amount, "total_spent": 0},
    )
    xp_tracker.total_earned = amount
    xp_tracker.total_spent = 0
    xp_tracker.save(update_fields=["total_earned", "total_spent"])
    return xp_tracker


# =============================================================================
# §6.2 — compute_thread_weaving_xp_cost
# =============================================================================


class ComputedXPCostTests(TestCase):
    """Tests for compute_thread_weaving_xp_cost (Spec A §6.2)."""

    def test_path_neutral_unlock_returns_base_cost(self) -> None:
        """Path-neutral unlock (no paths M2M) returns base xp_cost."""
        unlock = ThreadWeavingUnlockFactory(xp_cost=100)
        learner = CharacterSheetFactory()
        self.assertEqual(compute_thread_weaving_xp_cost(unlock, learner), 100)

    def test_in_path_unlock_returns_base_cost(self) -> None:
        """Learner on same path as unlock pays base xp_cost only."""
        steel = PathFactory(name="Steel")
        unlock = ThreadWeavingUnlockFactory(xp_cost=100)
        unlock.paths.add(steel)
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner.character, path=steel)
        self.assertEqual(compute_thread_weaving_xp_cost(unlock, learner), 100)

    def test_out_of_path_unlock_applies_multiplier(self) -> None:
        """Learner on a different path than unlock pays xp_cost * multiplier."""
        steel = PathFactory(name="Steel")
        whispers = PathFactory(name="Whispers")
        unlock = ThreadWeavingUnlockFactory(xp_cost=100, out_of_path_multiplier=Decimal("2.0"))
        unlock.paths.add(whispers)
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner.character, path=steel)
        self.assertEqual(compute_thread_weaving_xp_cost(unlock, learner), 200)

    def test_out_of_path_result_is_int(self) -> None:
        """Out-of-path multiplier result is cast to int, not Decimal."""
        whispers = PathFactory(name="Whispers2")
        unlock = ThreadWeavingUnlockFactory(xp_cost=100, out_of_path_multiplier=Decimal("1.5"))
        unlock.paths.add(whispers)
        learner = CharacterSheetFactory()
        result = compute_thread_weaving_xp_cost(unlock, learner)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 150)

    def test_learner_with_multiple_paths_in_path_wins(self) -> None:
        """If learner has multiple paths and one matches, in-path cost applies."""
        steel = PathFactory(name="SteelM")
        whispers = PathFactory(name="WhispersM")
        unlock = ThreadWeavingUnlockFactory(xp_cost=80, out_of_path_multiplier=Decimal("3.0"))
        unlock.paths.add(steel)
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner.character, path=steel)
        CharacterPathHistoryFactory(character=learner.character, path=whispers)
        self.assertEqual(compute_thread_weaving_xp_cost(unlock, learner), 80)


# =============================================================================
# §6.1 — accept_thread_weaving_unlock
# =============================================================================


class AcceptThreadWeavingUnlockTests(TestCase):
    """Tests for accept_thread_weaving_unlock (Spec A §6.1)."""

    def setUp(self) -> None:
        """Clear ActionPointPool identity cache between tests."""
        ActionPointPool.flush_instance_cache()

    def _make_offer_with_teacher_ap(
        self,
        *,
        banked_ap: int = 5,
        xp_cost: int = 100,
    ) -> object:
        """Build a ThreadWeavingTeachingOffer with the teacher having enough banked AP."""
        tenure = RosterTenureFactory()
        ActionPointPoolFactory(character=tenure.character, current=0, maximum=200, banked=banked_ap)
        unlock = ThreadWeavingUnlockFactory(xp_cost=xp_cost)
        return ThreadWeavingTeachingOfferFactory(teacher=tenure, unlock=unlock, banked_ap=banked_ap)

    def test_accept_creates_character_unlock_row(self) -> None:
        """Accepting an offer creates a CharacterThreadWeavingUnlock row."""
        offer = self._make_offer_with_teacher_ap(xp_cost=100)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 500)

        result = accept_thread_weaving_unlock(learner, offer)

        self.assertIsInstance(result, CharacterThreadWeavingUnlock)
        self.assertTrue(
            CharacterThreadWeavingUnlock.objects.filter(
                character=learner, unlock=offer.unlock
            ).exists()
        )

    def test_accept_records_xp_paid(self) -> None:
        """xp_spent on the unlock row matches the computed cost."""
        offer = self._make_offer_with_teacher_ap(xp_cost=100)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 500)

        result = accept_thread_weaving_unlock(learner, offer)

        self.assertEqual(result.xp_spent, 100)

    def test_accept_records_xp_paid_out_of_path(self) -> None:
        """xp_spent reflects out-of-path multiplier when learner is off-path."""
        whispers = PathFactory(name="WhispersOOP")
        steel = PathFactory(name="SteelOOP")
        unlock = ThreadWeavingUnlockFactory(xp_cost=100, out_of_path_multiplier=Decimal("2.0"))
        unlock.paths.add(whispers)
        tenure = RosterTenureFactory()
        ActionPointPoolFactory(character=tenure.character, current=0, maximum=200, banked=5)
        offer = ThreadWeavingTeachingOfferFactory(teacher=tenure, unlock=unlock, banked_ap=5)

        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner.character, path=steel)
        _seed_xp(learner, 500)

        result = accept_thread_weaving_unlock(learner, offer)

        self.assertEqual(result.xp_spent, 200)

    def test_double_accept_raises(self) -> None:
        """Accepting the same offer twice raises IntegrityError (unique_together)."""
        offer = self._make_offer_with_teacher_ap(xp_cost=10, banked_ap=10)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 5000)

        accept_thread_weaving_unlock(learner, offer)
        # Second accept hits the unique_together constraint
        with self.assertRaises(IntegrityError):
            accept_thread_weaving_unlock(learner, offer)

    def test_accept_consumes_teacher_banked_ap(self) -> None:
        """Teacher's banked AP decrements by offer.banked_ap after acceptance."""
        offer = self._make_offer_with_teacher_ap(banked_ap=7, xp_cost=50)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 500)

        accept_thread_weaving_unlock(learner, offer)

        pool = ActionPointPool.objects.get(character=offer.teacher.character)
        self.assertEqual(pool.banked, 0)

    def test_accept_deducts_xp_from_learner(self) -> None:
        """Learner's XP tracker is decremented by the computed cost."""
        offer = self._make_offer_with_teacher_ap(xp_cost=100)
        learner = CharacterSheetFactory()
        xp_tracker = _seed_xp(learner, 500)

        accept_thread_weaving_unlock(learner, offer)

        xp_tracker.refresh_from_db()
        self.assertEqual(xp_tracker.current_available, 400)

    def test_insufficient_xp_raises(self) -> None:
        """Learner with insufficient XP raises XPInsufficient; no unlock row created."""
        offer = self._make_offer_with_teacher_ap(xp_cost=300)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 100)

        with self.assertRaises(XPInsufficient):
            accept_thread_weaving_unlock(learner, offer)

        self.assertFalse(
            CharacterThreadWeavingUnlock.objects.filter(
                character=learner, unlock=offer.unlock
            ).exists()
        )

    def test_accept_records_teacher(self) -> None:
        """CharacterThreadWeavingUnlock.teacher matches offer.teacher."""
        offer = self._make_offer_with_teacher_ap(xp_cost=50)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 500)

        result = accept_thread_weaving_unlock(learner, offer)

        self.assertEqual(result.teacher, offer.teacher)

    def test_accept_writes_xp_transaction(self) -> None:
        """An XPTransaction row is created for the learner's account."""
        offer = self._make_offer_with_teacher_ap(xp_cost=100)
        learner = CharacterSheetFactory()
        xp_tracker = _seed_xp(learner, 500)

        accept_thread_weaving_unlock(learner, offer)

        txn = XPTransaction.objects.filter(account=xp_tracker.account).last()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, -100)

    def test_no_learner_ap_spent(self) -> None:
        """ThreadWeavingUnlock has no learn_cost — learner AP is NOT spent."""
        # Verify no ActionPointPool is created or modified for the learner
        offer = self._make_offer_with_teacher_ap(xp_cost=50)
        learner = CharacterSheetFactory()
        _seed_xp(learner, 500)

        accept_thread_weaving_unlock(learner, offer)

        # Learner should have no AP pool touched
        self.assertFalse(ActionPointPool.objects.filter(character=learner.character).exists())
