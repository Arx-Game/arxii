"""Finalize turns a chosen Vacancy into a membership (and a kin claim) (#3648)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import CRIME_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinSlotPoolFactory
from world.roster.models import Kinsperson
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.models import OrganizationMembership


class VacancyFinalizeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="vacancy_finalize")
        self._setup_finalization_base(self, prefix="Vacancy", height_min=700, height_max=800)
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        self.family = FamilyFactory(
            name="the Marrow", kind=crime, influence=5, origin_realm=self.area.realm
        )
        self.org = OrganizationFactory(name="the Marrow", family=self.family)
        self.claim_upbringing = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_claim_family=True
        )
        self.claim_upbringing.claimable_kinds.add(crime)

    def _claim_draft(self, vacancy):
        draft = self._create_base_draft()
        draft.selected_origin_template = self.claim_upbringing
        draft.family = self.family
        draft.selected_vacancy = vacancy
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()
        return draft

    def test_kin_vacancy_mints_from_the_pool_and_joins_at_its_rank(self) -> None:
        pool = KinSlotPoolFactory(family=self.family, description="a niece", count_remaining=2)
        rank = self.org.ranks.get(tier=3)
        vacancy = VacancyFactory(
            organization=self.org, name="The niece", kin_pool=pool, rank=rank, count_remaining=1
        )
        character = finalize_character(self._claim_draft(vacancy), add_to_roster=True)
        sheet = character.sheet_data

        node = Kinsperson.objects.get(sheet=sheet)
        assert node.family == self.family
        assert pool.__class__.objects.get(pk=pool.pk).count_remaining == 1
        membership = OrganizationMembership.objects.get(
            organization=self.org, persona__character_sheet=sheet
        )
        assert membership.rank == rank
        assert membership.vacancy == vacancy
        vacancy.refresh_from_db()
        assert vacancy.count_remaining == 0

    def test_standing_retainer_vacancy_on_the_none_path(self) -> None:
        none_upbringing = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_no_family=True
        )
        vacancy = VacancyFactory(organization=self.org, name="Low thug", count_remaining=None)
        draft = self._create_base_draft()
        draft.selected_origin_template = none_upbringing
        draft.selected_vacancy = vacancy
        draft.save()
        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        membership = OrganizationMembership.objects.get(
            organization=self.org, persona__character_sheet=sheet
        )
        assert membership.vacancy == vacancy
        assert membership.rank == self.org.ranks.get(tier=5)
        assert sheet.family is None
        vacancy.refresh_from_db()
        assert vacancy.count_remaining is None

    def test_closed_vacancy_logs_and_continues_without_a_membership(self) -> None:
        # A kin vacancy in the claimed family, not a retainer one (#3648
        # validators.py refuses a retainer post inside the family you are
        # already joining - see test_vacancy_validation.py).
        pool = KinSlotPoolFactory(family=self.family, description="an heir")
        vacancy = VacancyFactory(
            organization=self.org, name="Heir", kin_pool=pool, count_remaining=0
        )
        with self.assertLogs("world.character_creation.services", level="WARNING"):
            character = finalize_character(self._claim_draft(vacancy), add_to_roster=True)
        sheet = character.sheet_data
        assert not OrganizationMembership.objects.filter(persona__character_sheet=sheet).exists()
        assert Kinsperson.objects.get(sheet=sheet).family == self.family
