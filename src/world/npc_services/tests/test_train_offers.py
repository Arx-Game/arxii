"""TRAIN offer kind (#2440): Academy trainers teach techniques for AP + coin + a Hare."""

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
from world.npc_services.effects import OFFER_EFFECT_HANDLERS, run_train_offer
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
        CharacterPathHistoryFactory(character=self.character, path=self.path)
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
        CharacterPathHistoryFactory(character=self.character, path=self.path)

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
