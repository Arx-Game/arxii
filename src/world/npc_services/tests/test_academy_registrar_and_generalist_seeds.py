"""Tests for the Academy Registrar and ungated generalist trainer seeds
(#2428 whole-branch fix).

Both close gaps the whole-branch review found on the tradition-economy
cluster: the Registrar is the live caller ``settle_obligation`` was missing;
the generalist trainer means a fresh-DB Prospect has a reachable TRAIN offer
without first completing the Great Archive's (not-yet-authored) quest.
"""

from __future__ import annotations

from django.test import TestCase

from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCRole, NPCServiceOffer, TrainOfferDetails
from world.npc_services.seeds import (
    ACADEMY_GENERALIST_TRAINER_ROLE_NAME,
    ACADEMY_REGISTRAR_ROLE_NAME,
    ensure_academy_generalist_trainer_role,
    ensure_academy_registrar_role,
)


class EnsureAcademyRegistrarRoleTests(TestCase):
    def test_creates_role_and_ungated_settle_offer(self) -> None:
        role = ensure_academy_registrar_role()

        self.assertEqual(role.name, ACADEMY_REGISTRAR_ROLE_NAME)
        self.assertIsNotNone(role.faction_affiliation)
        self.assertEqual(role.faction_affiliation.name, "Shroudwatch Academy")

        offers = list(NPCServiceOffer.objects.filter(role=role))
        self.assertEqual(len(offers), 1)
        offer = offers[0]
        self.assertEqual(offer.kind, OfferKind.SETTLE_OBLIGATION)
        self.assertEqual(offer.eligibility_rule, {})
        self.assertEqual(offer.rapport_requirement, 0)
        self.assertTrue(offer.is_final)

    def test_idempotent(self) -> None:
        ensure_academy_registrar_role()
        ensure_academy_registrar_role()
        ensure_academy_registrar_role()

        self.assertEqual(NPCRole.objects.filter(name=ACADEMY_REGISTRAR_ROLE_NAME).count(), 1)
        self.assertEqual(
            NPCServiceOffer.objects.filter(role__name=ACADEMY_REGISTRAR_ROLE_NAME).count(), 1
        )


class EnsureAcademyGeneralistTrainerRoleTests(TestCase):
    def test_creates_role_and_ungated_train_offers(self) -> None:
        role = ensure_academy_generalist_trainer_role()

        self.assertEqual(role.name, ACADEMY_GENERALIST_TRAINER_ROLE_NAME)
        self.assertIsNotNone(role.faction_affiliation)
        self.assertEqual(role.faction_affiliation.name, "Shroudwatch Academy")
        self.assertIsNone(role.teaches_tradition)

        offers = list(NPCServiceOffer.objects.filter(role=role))
        self.assertGreater(len(offers), 0)
        for offer in offers:
            self.assertEqual(offer.kind, OfferKind.TRAIN)
            self.assertEqual(offer.ap_cost, 0)
            self.assertEqual(offer.eligibility_rule, {})
            self.assertTrue(TrainOfferDetails.objects.filter(offer=offer).exists())

    def test_covers_every_starter_gift(self) -> None:
        """One offer per starter Gift (one representative technique each) — the
        same coverage shape the Great Archive self-study seed uses, just ungated."""
        from world.seeds.game_content.magic import seed_starter_gift_catalog

        catalog = seed_starter_gift_catalog()
        role = ensure_academy_generalist_trainer_role()

        offered_gift_ids = set(
            TrainOfferDetails.objects.filter(offer__role=role).values_list(
                "technique__gift_id", flat=True
            )
        )
        expected_gift_ids = {gift.pk for gift in catalog.gifts.values()}
        self.assertEqual(offered_gift_ids, expected_gift_ids)

    def test_idempotent(self) -> None:
        ensure_academy_generalist_trainer_role()
        ensure_academy_generalist_trainer_role()
        ensure_academy_generalist_trainer_role()

        self.assertEqual(
            NPCRole.objects.filter(name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME).count(), 1
        )
        offers_first_pass = list(
            NPCServiceOffer.objects.filter(role__name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        ensure_academy_generalist_trainer_role()
        offers_second_pass = list(
            NPCServiceOffer.objects.filter(role__name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        self.assertEqual(offers_first_pass, offers_second_pass)
