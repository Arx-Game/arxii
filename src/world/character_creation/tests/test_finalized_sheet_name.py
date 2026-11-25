"""A character finalized into a family reads its surname once on its sheet (#5206).

Finalize names the character "First Family" (``_build_character_full_name``), so the sheet's
``identity.fullname`` must not add the family's name a second time.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import CRIME_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinSlotPoolFactory
from world.societies.factories import OrganizationFactory, VacancyFactory


class FinalizedSheetNameTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="surname_once")
        self.staff = AccountDB.objects.create(username="surname_staff", is_staff=True)
        self._setup_finalization_base(self, prefix="Surname", height_min=700, height_max=800)
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        self.family = FamilyFactory(
            name="Marrow", kind=crime, influence=5, origin_realm=self.area.realm
        )
        org = OrganizationFactory(name="Marrow", family=self.family)
        upbringing = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_claim_family=True
        )
        upbringing.claimable_kinds.add(crime)
        pool = KinSlotPoolFactory(family=self.family, description="a niece", count_remaining=2)
        vacancy = VacancyFactory(organization=org, name="The niece", kin_pool=pool)
        self.draft = self._create_base_draft(first_name="Wren")
        self.draft.selected_origin_template = upbringing
        self.draft.family = self.family
        self.draft.selected_vacancy = vacancy
        self.draft.draft_data.pop("tarot_card_name", None)
        self.draft.save()

    def test_the_family_name_is_not_repeated(self) -> None:
        character = finalize_character(self.draft, add_to_roster=True)
        self.assertEqual(character.db_key, "Wren Marrow")
        client = APIClient()
        client.force_authenticate(user=self.staff)

        response = client.get(f"/api/character-sheets/{character.pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["identity"]["fullname"], "Wren Marrow")
        self.assertEqual(response.data["identity"]["family"]["name"], "Marrow")
