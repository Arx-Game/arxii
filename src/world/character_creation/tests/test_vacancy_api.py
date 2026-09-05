"""CG API for Vacancies and Family Templates (#3648)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
)
from world.roster.constants import CRIME_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.factories import HouseTemplateFactory


class VacancyListTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user(username="vac", password="x")
        cls.beginning = BeginningsFactory()
        realm = cls.beginning.starting_area.realm
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        family = FamilyFactory(name="the Marrow", kind=crime, influence=5, origin_realm=realm)
        cls.org = OrganizationFactory(name="the Marrow", family=family)
        cls.upbringing = OriginTemplateFactory(
            beginning=cls.beginning, allows_name_family=False, allows_no_family=True
        )
        cls.thug = VacancyFactory(
            organization=cls.org, name="Low thug", cg_point_cost=1, cost_per_influence=1
        )
        VacancyFactory(organization=cls.org, name="Hidden", trust_required=99)
        cls.draft = CharacterDraftFactory(
            account=cls.account,
            selected_area=cls.beginning.starting_area,
            selected_beginnings=cls.beginning,
            selected_origin_template=cls.upbringing,
        )

    def test_lists_reachable_with_cost_for_this_draft(self):
        client = APIClient()
        client.force_authenticate(self.account)
        res = client.get(f"/api/character-creation/vacancies/?draft={self.draft.id}")
        assert res.status_code == 200
        rows = res.json()
        assert [r["name"] for r in rows] == ["Low thug"]
        row = rows[0]
        assert row["basis"] == "retainer"
        assert row["cost"] == 6
        assert row["organization"]["family"]["influence"] == 5

    def test_other_accounts_draft_is_forbidden(self):
        other = AccountDB.objects.create_user(username="other", password="x")
        client = APIClient()
        client.force_authenticate(other)
        res = client.get(f"/api/character-creation/vacancies/?draft={self.draft.id}")
        assert res.status_code == 200
        assert res.json() == []


class OriginTemplateFamilyTemplatesTest(TestCase):
    def test_origin_template_carries_family_templates(self):
        account = AccountDB.objects.create_user(username="tpl", password="x")
        beginning = BeginningsFactory()
        template = HouseTemplateFactory(
            name="Caretaker Household", realm=beginning.starting_area.realm
        )
        served = OrganizationFactory(name="House Regency")
        template.served_house_choices.add(served)
        upbringing = OriginTemplateFactory(beginning=beginning, family_templates=[template])
        client = APIClient()
        client.force_authenticate(account)
        res = client.get(f"/api/character-creation/origin-templates/?beginning={beginning.id}")
        row = next(r for r in res.json() if r["id"] == upbringing.id)
        assert row["family_templates"][0]["name"] == "Caretaker Household"
        assert row["family_templates"][0]["served_house_choices"] == [
            {"id": served.id, "name": "House Regency"}
        ]
