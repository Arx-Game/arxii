"""Vacancy: an opening on a staff family's org (#3648)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.roster.factories import FamilyFactory, KinSlotPoolFactory, KinspersonFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.models import Vacancy


class VacancyModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = FamilyFactory(name="House Marrow", influence=5)
        cls.org = OrganizationFactory(name="House Marrow", family=cls.family)

    def test_retainer_when_no_kin_link(self):
        vacancy = VacancyFactory(organization=self.org, name="Low thug")
        assert vacancy.basis == "retainer"

    def test_kin_when_pool_linked(self):
        pool = KinSlotPoolFactory(family=self.family, description="a niece")
        vacancy = VacancyFactory(organization=self.org, name="The niece", kin_pool=pool)
        assert vacancy.basis == "kin"

    def test_cost_scales_with_influence(self):
        vacancy = VacancyFactory(
            organization=self.org, name="Counsel", cg_point_cost=3, cost_per_influence=2
        )
        assert vacancy.cost_for(5) == 13
        assert vacancy.cost_for(0) == 3

    def test_standing_vacancy_is_open_without_a_count(self):
        vacancy = VacancyFactory(organization=self.org, name="Guard", count_remaining=None)
        assert vacancy.is_open is True
        closed = VacancyFactory(organization=self.org, name="Heir", count_remaining=0)
        assert closed.is_open is False
        inactive = VacancyFactory(organization=self.org, name="Old", is_active=False)
        assert inactive.is_open is False

    def test_clean_refuses_both_kin_links(self):
        pool = KinSlotPoolFactory(family=self.family)
        node = KinspersonFactory(family=self.family, is_appable=True)
        vacancy = Vacancy(organization=self.org, name="Both", kin_pool=pool, kin_node=node)
        with self.assertRaises(ValidationError):
            vacancy.clean()

    def test_clean_refuses_kin_link_outside_the_family(self):
        other = FamilyFactory(name="House Other")
        pool = KinSlotPoolFactory(family=other)
        vacancy = Vacancy(organization=self.org, name="Stray", kin_pool=pool)
        with self.assertRaises(ValidationError):
            vacancy.clean()

    def test_clean_refuses_an_org_without_a_family(self):
        guild = OrganizationFactory(name="A Guild", family=None)
        vacancy = Vacancy(organization=guild, name="Clerk")
        with self.assertRaises(ValidationError):
            vacancy.clean()

    def test_natural_key_is_org_and_name(self):
        vacancy = VacancyFactory(organization=self.org, name="Enforcer")
        assert Vacancy.objects.get_by_natural_key(*vacancy.natural_key()) == vacancy
