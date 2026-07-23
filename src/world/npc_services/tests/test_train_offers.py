"""TRAIN offer kind (#2440): Academy trainers teach techniques for AP + coin + a Hare."""

import math
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.classes.factories import PathFactory
from world.currency.models import FavorTokenDetails
from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    mint_favor_token,
)
from world.magic.constants import GiftKind
from world.magic.factories import (
    CharacterGiftUnlockFactory,
    CharacterTraditionFactory,
    GiftFactory,
    GiftUnlockFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterTechnique
from world.npc_services.constants import OfferKind
from world.npc_services.effects import (
    OFFER_EFFECT_HANDLERS,
    TrainOfferMisconfiguredError,
    run_train_offer,
)
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    TrainOfferDetailsFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationObligationFactory


class TrainOfferHappyPathTests(TestCase):
    def setUp(self) -> None:
        from world.action_points.models import ActionPointPool

        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.technique = TechniqueFactory(gift=self.gift)
        self.path = PathFactory()
        CharacterPathHistoryFactory(character=self.character.sheet_data, path=self.path)
        grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

        # XP-unlock receipt: the first technique from an unowned gift needs
        # the gate satisfied (mirrors accept_technique_offer's own gate).
        CharacterGiftUnlockFactory(character=self.sheet, unlock=GiftUnlockFactory(gift=self.gift))

        self.role = NPCRoleFactory(faction_affiliation=self.academy)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a technique", is_final=True
        )
        self.details = TrainOfferDetailsFactory(
            offer=self.offer, technique=self.technique, learn_ap_cost=5, gold_cost=100
        )

        self.ap_pool = ActionPointPool.get_or_create_for_character(self.character)
        self.ap_pool.current = 200
        self.ap_pool.save()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 1000
        self.purse.save()
        self.token = mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

    def test_registered(self) -> None:
        self.assertIn(OfferKind.TRAIN.value, OFFER_EFFECT_HANDLERS)

    def test_happy_path_debits_all_three_currencies_and_creates_technique(self) -> None:
        result = run_train_offer(self.offer, self.persona)

        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertTrue(known.exists())
        self.assertIsNotNone(result.object_pk)

        # AP: gift not yet owned -> first_technique_ap_multiplier applies.
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        config = get_gift_acquisition_config()
        expected_ap = self.details.learn_ap_cost * config.first_technique_ap_multiplier
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200 - expected_ap)

        # Coin: purse -> Academy treasury.
        self.purse.refresh_from_db()
        treasury = get_or_create_treasury(self.academy)
        treasury.refresh_from_db()
        self.assertEqual(self.purse.balance, 1000 - self.details.gold_cost)
        self.assertEqual(treasury.balance, self.details.gold_cost)

        # Hare: redeemed to the Academy.
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNotNone(row.redeemed_at)

    def test_obligation_gate_blocks(self) -> None:
        OrganizationObligationFactory(debtor=self.sheet, creditor=self.academy)

        result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("debt", result.message)
        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertFalse(known.exists())
        # Nothing charged — the gate fires before Hare resolution.
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNone(row.redeemed_at)

    def test_no_hare_is_a_typed_soft_refusal(self) -> None:
        # No unredeemed Hare held by the learner at all now.
        self.token.delete()

        result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("Golden Hare", result.message)
        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertFalse(known.exists())

    def test_outside_availability_blocked(self) -> None:
        other_gift = GiftFactory(kind=GiftKind.MINOR)
        stray_technique = TechniqueFactory(gift=other_gift)
        # No PathGiftGrant/TraditionGiftGrant row makes this technique
        # reachable for this learner via this role.
        stray_offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a stray technique", is_final=True
        )
        TrainOfferDetailsFactory(offer=stray_offer, technique=stray_technique)

        result = run_train_offer(stray_offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("isn't yours to learn", result.message)
        known = CharacterTechnique.objects.filter(character=self.sheet, technique=stray_technique)
        self.assertFalse(known.exists())
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNone(row.redeemed_at)


class TrainOfferSignatureMembersOnlyTests(TestCase):
    """Signature-list techniques are teachable only to Tradition members (ruling 3, #2440)."""

    def setUp(self) -> None:
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.signature_technique = TechniqueFactory(gift=self.gift)
        self.path = PathFactory()
        CharacterPathHistoryFactory(character=self.character.sheet_data, path=self.path)

        self.tradition = TraditionFactory()
        sig_grant = TraditionGiftGrantFactory(tradition=self.tradition, gift=self.gift)
        sig_grant.signature_techniques.add(self.signature_technique)
        # Deliberately no PathGiftGrant row for this technique — it is ONLY
        # reachable via the tradition's signature list.

        CharacterGiftUnlockFactory(character=self.sheet, unlock=GiftUnlockFactory(gift=self.gift))

        self.role = NPCRoleFactory(
            faction_affiliation=self.academy, teaches_tradition=self.tradition
        )
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn the signature", is_final=True
        )
        TrainOfferDetailsFactory(offer=self.offer, technique=self.signature_technique)

        from world.action_points.models import ActionPointPool

        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 200
        pool.save()
        purse = get_or_create_purse(self.sheet)
        purse.balance = 1000
        purse.save()
        mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

    def test_non_member_is_blocked(self) -> None:
        result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("isn't yours to learn", result.message)
        known = CharacterTechnique.objects.filter(
            character=self.sheet, technique=self.signature_technique
        )
        self.assertFalse(known.exists())

    def test_member_can_learn_the_signature(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.tradition)

        result = run_train_offer(self.offer, self.persona)

        self.assertIsNotNone(result.object_pk)
        known = CharacterTechnique.objects.filter(
            character=self.sheet, technique=self.signature_technique
        )
        self.assertTrue(known.exists())

    def test_left_member_is_blocked(self) -> None:
        """A membership row with left_at set is not active — TRAIN treats it as if the
        character never joined (#2441 Task 8: signature-list access is active-only)."""
        from django.utils import timezone

        CharacterTraditionFactory(
            character=self.sheet, tradition=self.tradition, left_at=timezone.now()
        )

        result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("isn't yours to learn", result.message)
        known = CharacterTechnique.objects.filter(
            character=self.sheet, technique=self.signature_technique
        )
        self.assertFalse(known.exists())


class TrainOfferAtomicChargeSequenceTests(TestCase):
    """Hare-resolve + charge_and_learn + redeem_favor_token are all-or-nothing.

    Review fix on #2440 (commit 93ff6c83c): before this fix, charge_and_learn
    committed its own separate transaction, then redeem_favor_token ran in a
    SECOND separate transaction. A race (or any redeem_favor_token failure)
    would leave the learner charged AP + coin + a technique with no Hare
    spent. run_train_offer now wraps the whole sequence in one outer
    transaction.atomic() — a redeem_favor_token failure rolls back
    everything charge_and_learn already did.
    """

    def setUp(self) -> None:
        from world.action_points.models import ActionPointPool

        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.technique = TechniqueFactory(gift=self.gift)
        self.path = PathFactory()
        CharacterPathHistoryFactory(character=self.character.sheet_data, path=self.path)
        grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

        CharacterGiftUnlockFactory(character=self.sheet, unlock=GiftUnlockFactory(gift=self.gift))

        self.role = NPCRoleFactory(faction_affiliation=self.academy)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a technique", is_final=True
        )
        self.details = TrainOfferDetailsFactory(
            offer=self.offer, technique=self.technique, learn_ap_cost=5, gold_cost=100
        )

        self.ap_pool = ActionPointPool.get_or_create_for_character(self.character)
        self.ap_pool.current = 200
        self.ap_pool.save()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 1000
        self.purse.save()
        self.token = mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

    def test_redeem_favor_token_failure_rolls_back_charge_and_learn(self) -> None:
        """A redeem_favor_token failure must undo charge_and_learn's AP/coin/technique.

        SharedMemoryModel's identity map returns the SAME cached Python
        instance on re-query by pk (see ``sharedmemory-model`` skill) — its
        in-memory attributes were already mutated by charge_and_learn before
        the rollback, and a SQL ROLLBACK cannot undo a Python attribute
        assignment. ``refresh_from_db()``/re-querying by pk on that cached
        instance is therefore a no-op that would mask a real bug here; each
        model's class-wide cache must be flushed first to force a genuine
        DB read of the post-rollback row.
        """
        from world.action_points.models import ActionPointPool
        from world.currency.models import CharacterPurse, OrganizationTreasury

        with mock.patch(
            "world.currency.services.redeem_favor_token",
            side_effect=ValidationError("This Golden Hare has already been redeemed."),
        ):
            result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("Hare", result.message)

        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertFalse(known.exists())

        ActionPointPool.flush_instance_cache()
        pool = ActionPointPool.get_or_create_for_character(self.character)
        self.assertEqual(pool.current, 200)

        CharacterPurse.flush_instance_cache()
        OrganizationTreasury.flush_instance_cache()
        purse = get_or_create_purse(self.sheet)
        self.assertEqual(purse.balance, 1000)
        treasury = get_or_create_treasury(self.academy)
        self.assertEqual(treasury.balance, 0)

        FavorTokenDetails.flush_instance_cache()
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNone(row.redeemed_at)

    def test_charge_and_learn_failure_leaves_hare_unredeemed(self) -> None:
        """Insufficient AP fails charge_and_learn before the Hare is ever touched."""
        from world.currency.models import CharacterPurse, OrganizationTreasury

        self.ap_pool.current = 0
        self.ap_pool.save()

        result = run_train_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertFalse(known.exists())

        FavorTokenDetails.flush_instance_cache()
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNone(row.redeemed_at)

        CharacterPurse.flush_instance_cache()
        OrganizationTreasury.flush_instance_cache()
        purse = get_or_create_purse(self.sheet)
        self.assertEqual(purse.balance, 1000)
        treasury = get_or_create_treasury(self.academy)
        self.assertEqual(treasury.balance, 0)


class TrainOfferDetailsCleanTests(TestCase):
    """TrainOfferDetails.clean() is the authoring-time guard for ap_cost=0."""

    def setUp(self) -> None:
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.technique = TechniqueFactory(gift=self.gift)
        self.role = NPCRoleFactory(faction_affiliation=self.academy)

    def test_nonzero_ap_cost_rejected(self) -> None:
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.TRAIN, ap_cost=3)
        details = TrainOfferDetailsFactory(offer=offer, technique=self.technique)

        with self.assertRaises(ValidationError):
            details.clean()

    def test_zero_ap_cost_accepted(self) -> None:
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.TRAIN, ap_cost=0)
        details = TrainOfferDetailsFactory(offer=offer, technique=self.technique)

        details.clean()  # should not raise


class TrainOfferApCostGuardTests(TestCase):
    """Runtime backstop for a nonzero NPCServiceOffer.ap_cost on TRAIN offers.

    TrainOfferDetails.clean() (see TrainOfferDetailsCleanTests above) is the
    authoring-time guard, but nothing currently calls full_clean() on the
    authoring path (no admin or serializer surface exists yet for
    TrainOfferDetails) — so run_train_offer asserts defensively too.
    """

    def setUp(self) -> None:
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.technique = TechniqueFactory(gift=self.gift)
        self.role = NPCRoleFactory(faction_affiliation=self.academy)

    def test_nonzero_ap_cost_raises_misconfigured_error(self) -> None:
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.TRAIN, ap_cost=3)
        TrainOfferDetailsFactory(offer=offer, technique=self.technique)

        with self.assertRaises(TrainOfferMisconfiguredError):
            run_train_offer(offer, self.persona)

    def test_zero_ap_cost_does_not_trip_the_guard(self) -> None:
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.TRAIN, ap_cost=0)
        TrainOfferDetailsFactory(offer=offer, technique=self.technique)

        # No PathGiftGrant/signature authored, so this falls through to the
        # ordinary availability gate rather than raising — proving the
        # ap_cost guard itself stays quiet at ap_cost=0.
        result = run_train_offer(offer, self.persona)
        self.assertIsNone(result.object_pk)
        self.assertIn("isn't yours to learn", result.message)


class TrainOfferUnboundSurchargeTests(TestCase):
    """The Unbound magic-learning AP surcharge (#2442) on the Academy TRAIN
    door — the other of ``charge_and_learn``'s two front doors (#2440), proving
    the surcharge applies identically here as it does on the PC-teaching-accept
    door (see world.magic.tests.test_gift_acquisition_service
    .UnboundMagicLearningApSurchargeTest)."""

    def setUp(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.seeds.character_creation import ensure_unbound_drawback_distinction

        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.technique = TechniqueFactory(gift=self.gift)
        self.path = PathFactory()
        CharacterPathHistoryFactory(character=self.character.sheet_data, path=self.path)
        grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

        CharacterGiftUnlockFactory(character=self.sheet, unlock=GiftUnlockFactory(gift=self.gift))

        self.role = NPCRoleFactory(faction_affiliation=self.academy)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a technique", is_final=True
        )
        self.details = TrainOfferDetailsFactory(
            offer=self.offer, technique=self.technique, learn_ap_cost=5, gold_cost=0
        )

        self.ap_pool = ActionPointPool.get_or_create_for_character(self.character)
        self.ap_pool.current = 200
        self.ap_pool.save()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 1000
        self.purse.save()
        self.token = mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

        self.unbound_distinction = ensure_unbound_drawback_distinction()

    def test_unbound_learner_pays_surcharge_on_train(self) -> None:
        from world.distinctions.services import grant_distinction
        from world.distinctions.types import DistinctionOrigin
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        grant_distinction(
            self.sheet, self.unbound_distinction, origin=DistinctionOrigin.CHARACTER_CREATION
        )

        result = run_train_offer(self.offer, self.persona)

        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertTrue(known.exists())
        self.assertIsNotNone(result.object_pk)

        config = get_gift_acquisition_config()
        # gift not yet owned -> first_technique_ap_multiplier applies, THEN the
        # +50% Unbound surcharge (ceil).
        base = self.details.learn_ap_cost * config.first_technique_ap_multiplier
        expected_ap = math.ceil(base * 1.5)
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200 - expected_ap)

    def test_non_unbound_learner_unaffected_on_train(self) -> None:
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        result = run_train_offer(self.offer, self.persona)

        known = CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        self.assertTrue(known.exists())
        self.assertIsNotNone(result.object_pk)

        config = get_gift_acquisition_config()
        expected_ap = self.details.learn_ap_cost * config.first_technique_ap_multiplier
        self.ap_pool.refresh_from_db()
        self.assertEqual(self.ap_pool.current, 200 - expected_ap)
