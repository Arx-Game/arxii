"""Domain garrison tests (#696 gap 5): the DomainGarrisonPost seam.

Lives alongside ``test_houses.py`` rather than under a ``houses/tests/``
package - houses tests already sit in ``world/societies/tests/`` (see
``test_houses.py``'s ``DomainTests``); no ``houses/tests/`` package exists in
this repo.
"""

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.military.factories import MilitaryUnitFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.models import DomainGarrisonPost
from world.societies.houses.services import (
    HousesServiceError,
    assign_garrison,
    create_domain,
    effective_defenses,
    garrison_term,
    relieve_garrison,
)


class GarrisonServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory(name="House Westrock")
        cls.domain = create_domain(area=AreaFactory(), name="Westrock Vale", owner_org=cls.org)

    def test_assign_garrison_posts_the_unit(self):
        unit = MilitaryUnitFactory(owner_org=self.org)
        post = assign_garrison(domain=self.domain, unit=unit)
        self.assertEqual(post.domain, self.domain)
        self.assertEqual(post.unit, unit)
        self.assertTrue(DomainGarrisonPost.objects.filter(domain=self.domain, unit=unit).exists())

    def test_assign_garrison_refuses_cross_org_unit(self):
        other_org = OrganizationFactory(name="House Eastrock")
        unit = MilitaryUnitFactory(owner_org=other_org)
        with self.assertRaises(HousesServiceError):
            assign_garrison(domain=self.domain, unit=unit)
        self.assertFalse(DomainGarrisonPost.objects.filter(unit=unit).exists())

    def test_assign_garrison_refuses_a_unit_already_posted(self):
        unit = MilitaryUnitFactory(owner_org=self.org)
        assign_garrison(domain=self.domain, unit=unit)
        other_domain = create_domain(
            area=AreaFactory(), name="Westrock Marches", owner_org=self.org
        )
        with self.assertRaises(HousesServiceError):
            assign_garrison(domain=other_domain, unit=unit)
        self.assertEqual(DomainGarrisonPost.objects.filter(unit=unit).count(), 1)

    def test_relieve_garrison_clears_the_post(self):
        unit = MilitaryUnitFactory(owner_org=self.org)
        assign_garrison(domain=self.domain, unit=unit)
        self.assertTrue(relieve_garrison(unit=unit))
        self.assertFalse(DomainGarrisonPost.objects.filter(unit=unit).exists())

    def test_relieve_garrison_is_a_noop_for_an_unposted_unit(self):
        unit = MilitaryUnitFactory(owner_org=self.org)
        self.assertFalse(relieve_garrison(unit=unit))

    def test_garrison_term_is_a_seam_returning_zero(self):
        unit = MilitaryUnitFactory(owner_org=self.org, strength=500)
        assign_garrison(domain=self.domain, unit=unit)
        self.assertEqual(garrison_term(self.domain), 0)

    def test_effective_defenses_equals_stored_stat_while_the_seam_is_stubbed(self):
        self.domain.defenses = 42
        self.domain.save(update_fields=["defenses"])
        self.assertEqual(effective_defenses(self.domain), 42)
