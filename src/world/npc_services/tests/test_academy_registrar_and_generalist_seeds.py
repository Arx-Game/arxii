"""Tests for the Academy Registrar and ungated generalist trainer seeds
(#2428 whole-branch fix).

Both close gaps the whole-branch review found on the tradition-economy
cluster: the Registrar is the live caller ``settle_obligation`` was missing;
the generalist trainer means a fresh-DB Prospect has a reachable TRAIN offer
without first completing the Great Archive's (not-yet-authored) quest.
"""

from __future__ import annotations

from django.test import TestCase

from core_management.content_fixtures import ContentError
from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCRole, NPCServiceOffer, TrainOfferDetails
from world.npc_services.seeds import (
    _GENERALIST_TRAINER_STARTER_TECHNIQUES,
    ACADEMY_GENERALIST_TRAINER_ROLE_NAME,
    ACADEMY_REGISTRAR_ROLE_NAME,
    _resolve_starter_techniques,
    ensure_academy_generalist_trainer_role,
    ensure_academy_registrar_role,
)
from world.seeds.game_content.magic import MagicContent


def _build_generalist_trainer_catalog():
    """Factory-build a synthetic Path/Gift/Technique catalog for the generalist
    trainer tests (#2474) — one (Path, Gift) pair per hardcoded (gift, technique)
    pair ``ensure_academy_generalist_trainer_role`` looks up, using the SAME
    gift names the production lookup scopes by
    (``_GENERALIST_TRAINER_STARTER_TECHNIQUES``), so its gift-scoped ORM lookup
    (``Technique.objects.filter(gift__name=..., name=...)``, #2474 review fix)
    finds real rows instead of a catalog seeded by the now-retired
    ``seed_starter_gift_catalog()``.
    """
    specs = [
        (f"Test Path {i}", gift_name, technique_name)
        for i, (gift_name, technique_name) in enumerate(
            _GENERALIST_TRAINER_STARTER_TECHNIQUES, start=1
        )
    ]
    return MagicContent.create_starter_gift_catalog(specs)


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
    """#2474: the retired ``seed_starter_gift_catalog()`` used to synthesize its
    own catalog on every call, so these tests never needed one set up ahead of
    time. Now that ``ensure_academy_generalist_trainer_role()`` reads the
    catalog via ORM lookups instead, every test needs a real one built first —
    ``setUpTestData`` builds one covering every hardcoded technique name the
    seed looks up.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.catalog = _build_generalist_trainer_catalog()

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
        role = ensure_academy_generalist_trainer_role()

        offered_gift_ids = set(
            TrainOfferDetails.objects.filter(offer__role=role).values_list(
                "technique__gift_id", flat=True
            )
        )
        expected_gift_ids = {gift.pk for gift in self.catalog.gifts.values()}
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


class ResolveStarterTechniquesGiftScopingTests(TestCase):
    """#2474 review fix: a same-named Technique on the WRONG Gift must never be
    silently picked up by ``_resolve_starter_techniques``.

    ``Technique.name`` is not globally unique (only ``(gift, name)`` is, per
    ``unique_technique_gift_name``) — lore reuse or a player-crafted technique
    (``Technique.creator``) could share one of the hardcoded starter-technique
    names on a completely different Gift. An unscoped ``name__in=`` lookup
    would let the DB pick whichever matching row it returned first, silently
    mis-wiring ``TrainOfferDetails.technique`` to a technique from the wrong
    gift's pool. The lookup must be scoped to the (gift, name) pair, never
    just the name.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import GiftFactory, TechniqueFactory

        cls.catalog = _build_generalist_trainer_catalog()
        # Decoy: a same-named Technique ("Burning Strike") on an UNRELATED
        # gift — not one of _GENERALIST_TRAINER_STARTER_TECHNIQUES' pairs.
        cls.decoy_gift = GiftFactory(name="Decoy Gift")
        cls.decoy_technique = TechniqueFactory(name="Burning Strike", gift=cls.decoy_gift)

    def test_resolve_starter_techniques_never_picks_the_decoy(self) -> None:
        resolved = _resolve_starter_techniques(_GENERALIST_TRAINER_STARTER_TECHNIQUES)

        technique = resolved["Burning Strike"]
        self.assertNotEqual(
            technique.pk,
            self.decoy_technique.pk,
            "resolved 'Burning Strike' must be the real starter-catalog row, "
            "not the same-named decoy on a different gift",
        )
        self.assertEqual(technique.gift.name, "Emberwork")

    def test_train_offer_wires_the_real_technique_not_the_decoy(self) -> None:
        role = ensure_academy_generalist_trainer_role()

        offer = TrainOfferDetails.objects.get(
            offer__role=role, technique__name="Burning Strike"
        ).offer
        wired_technique = offer.train_offer_details.technique
        self.assertNotEqual(wired_technique.pk, self.decoy_technique.pk)
        self.assertEqual(wired_technique.gift.name, "Emberwork")

    def test_resolve_starter_techniques_raises_when_no_pair_resolves(self) -> None:
        """#2474: when NONE of the (gift, technique) pairs match a real row —
        the content repo hasn't been loaded — the lookup must fail loudly
        (``ContentError``) rather than silently returning an empty mapping,
        which would leave callers wiring zero TRAIN offers on a fresh DB."""
        with self.assertRaises(ContentError):
            _resolve_starter_techniques((("Nonexistent Gift", "Nonexistent Technique"),))
