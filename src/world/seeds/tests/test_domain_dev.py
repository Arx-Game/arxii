"""Dev domain slice (#930/#1464): the books loop is walkable on a seeded DB."""

from django.test import TestCase

from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCRole, NPCServiceOffer
from world.seeds.domain_dev import DEV_HOUSE_NAME, STEWARD_ROLE_NAME, ensure_dev_domain
from world.societies.models import Organization, PhilosophicalArchetype


class DomainDevSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_dev_domain()

    def test_house_and_streams_exist(self) -> None:
        organization = Organization.objects.get(name=DEV_HOUSE_NAME)
        self.assertEqual(organization.income_streams.count(), 2)

    def test_steward_carries_both_domain_offers(self) -> None:
        role = NPCRole.objects.get(name=STEWARD_ROLE_NAME)
        self.assertEqual(role.faction_affiliation.name, DEV_HOUSE_NAME)
        kinds = set(NPCServiceOffer.objects.filter(role=role).values_list("kind", flat=True))
        self.assertEqual(kinds, {OfferKind.COLLECTION, OfferKind.IMPROVEMENT})
        for offer in NPCServiceOffer.objects.filter(role=role):
            self.assertGreater(offer.ap_cost, 0)
            self.assertIsNotNone(offer.cooldown)

    def test_authored_scandal_archetypes_exist(self) -> None:
        rows = PhilosophicalArchetype.objects.filter(name__endswith="Scandal")
        self.assertGreaterEqual(rows.count(), 9)

    def test_idempotent(self) -> None:
        ensure_dev_domain()
        ensure_dev_domain()
        self.assertEqual(Organization.objects.filter(name=DEV_HOUSE_NAME).count(), 1)
        role = NPCRole.objects.get(name=STEWARD_ROLE_NAME)
        self.assertEqual(NPCServiceOffer.objects.filter(role=role).count(), 2)
