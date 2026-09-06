"""Taking a Vacancy is locked and counted; reachability is data-driven (#3648)."""

from django.db import transaction
from django.test import TestCase

from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
)
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.vacancy_services import (
    VacancyExhaustedError,
    reachable_vacancies,
    take_vacancy,
)


class TakeVacancyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        family = FamilyFactory(name="House Marrow", influence=5)
        cls.org = OrganizationFactory(name="House Marrow", family=family)

    def test_counted_vacancy_decrements_and_closes(self):
        vacancy = VacancyFactory(organization=self.org, name="Enforcer", count_remaining=1)
        with transaction.atomic():
            taken = take_vacancy(vacancy.pk)
        assert taken.count_remaining == 0
        with self.assertRaises(VacancyExhaustedError), transaction.atomic():
            take_vacancy(vacancy.pk)

    def test_standing_vacancy_never_decrements(self):
        vacancy = VacancyFactory(organization=self.org, name="Thug", count_remaining=None)
        with transaction.atomic():
            take_vacancy(vacancy.pk)
            take_vacancy(vacancy.pk)
        vacancy.refresh_from_db()
        assert vacancy.count_remaining is None

    def test_inactive_vacancy_refuses(self):
        vacancy = VacancyFactory(organization=self.org, name="Gone", is_active=False)
        with self.assertRaises(VacancyExhaustedError), transaction.atomic():
            take_vacancy(vacancy.pk)


class ReachableVacanciesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beginning = BeginningsFactory()
        cls.realm = cls.beginning.starting_area.realm
        cls.upbringing = OriginTemplateFactory(beginning=cls.beginning)
        cls.other_upbringing = OriginTemplateFactory(beginning=cls.beginning)
        family = FamilyFactory(name="House Local", origin_realm=cls.realm, influence=3)
        cls.org = OrganizationFactory(name="House Local", family=family)
        far_family = FamilyFactory(name="House Far", influence=3)
        far_family.origin_realm = OriginTemplateFactory().beginning.starting_area.realm
        far_family.save()
        cls.far_org = OrganizationFactory(name="House Far", family=far_family)

    def _draft(self, **extra):
        return CharacterDraftFactory(
            selected_area=self.beginning.starting_area,
            selected_beginnings=self.beginning,
            selected_origin_template=self.upbringing,
            **extra,
        )

    def test_open_local_vacancy_is_reachable(self):
        vacancy = VacancyFactory(organization=self.org, name="Guard")
        assert list(reachable_vacancies(self._draft())) == [vacancy]

    def test_other_realm_is_not_reachable(self):
        VacancyFactory(organization=self.far_org, name="Guard")
        assert list(reachable_vacancies(self._draft())) == []

    def test_upbringing_gate(self):
        vacancy = VacancyFactory(organization=self.org, name="Counsel")
        vacancy.allowed_upbringings.add(self.other_upbringing)
        assert list(reachable_vacancies(self._draft())) == []
        vacancy.allowed_upbringings.add(self.upbringing)
        assert list(reachable_vacancies(self._draft())) == [vacancy]

    def test_closed_and_trust_gated_are_hidden(self):
        VacancyFactory(organization=self.org, name="Heir", count_remaining=0)
        VacancyFactory(organization=self.org, name="Secret", trust_required=99)
        assert list(reachable_vacancies(self._draft())) == []
