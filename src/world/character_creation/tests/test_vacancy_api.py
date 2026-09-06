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

    def test_other_accounts_draft_sees_nothing(self):
        other = AccountDB.objects.create_user(username="other", password="x")
        client = APIClient()
        client.force_authenticate(other)
        res = client.get(f"/api/character-creation/vacancies/?draft={self.draft.id}")
        assert res.status_code == 200
        assert res.json() == []


class VacancyListKinBasisQueryCountTest(TestCase):
    """Kin-basis vacancy rows don't cost per-row queries for their nested pool (#3648).

    ``CGVacancySerializer.kin_pool``/``kin_node`` serialize the
    ``allowed_genders`` M2M (and, for a pool, ``parents``);
    ``reachable_vacancies`` now prefetches those alongside ``kin_pool``/
    ``kin_node`` themselves, mirroring
    ``roster.services.kinship.open_slots_for``'s plain-string prefetch
    convention.
    """

    def _draft_with_org(self, *, username: str):
        from world.character_creation.factories import (
            BeginningsFactory,
            CharacterDraftFactory,
            OriginTemplateFactory,
        )
        from world.roster.factories import FamilyFactory, FamilyKindFactory
        from world.societies.factories import OrganizationFactory

        account = AccountDB.objects.create_user(username=username, password="x")
        beginning = BeginningsFactory()
        realm = beginning.starting_area.realm
        kind = FamilyKindFactory(name=f"{username}-kind")
        family = FamilyFactory(name=f"the {username}", kind=kind, origin_realm=realm)
        org = OrganizationFactory(name=f"the {username}", family=family)
        upbringing = OriginTemplateFactory(
            beginning=beginning, allows_name_family=False, allows_no_family=True
        )
        draft = CharacterDraftFactory(
            account=account,
            selected_area=beginning.starting_area,
            selected_beginnings=beginning,
            selected_origin_template=upbringing,
        )
        return draft, org

    def _kin_vacancy(self, org, name: str, *, gender) -> None:
        from world.roster.factories import KinSlotPoolFactory
        from world.societies.factories import VacancyFactory

        pool = KinSlotPoolFactory(count_remaining=2)
        pool.allowed_genders.add(gender)
        VacancyFactory(organization=org, name=name, kin_pool=pool)

    def test_kin_basis_query_count_does_not_grow_with_vacancy_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.character_sheets.factories import GenderFactory

        gender = GenderFactory(key="test-nonbinary", display_name="Nonbinary")

        one_draft, one_org = self._draft_with_org(username="onevac")
        self._kin_vacancy(one_org, "Cousin slot", gender=gender)

        three_draft, three_org = self._draft_with_org(username="threevac")
        for i in range(3):
            self._kin_vacancy(three_org, f"Cousin slot {i}", gender=gender)

        client_one = APIClient()
        client_one.force_authenticate(one_draft.account)
        with CaptureQueriesContext(connection) as ctx_one:
            res_one = client_one.get(f"/api/character-creation/vacancies/?draft={one_draft.id}")
        assert res_one.status_code == 200
        rows_one = res_one.json()
        assert len(rows_one) == 1
        assert rows_one[0]["basis"] == "kin"
        assert rows_one[0]["kin_pool"]["allowed_genders"] == ["Nonbinary"]

        client_three = APIClient()
        client_three.force_authenticate(three_draft.account)
        with CaptureQueriesContext(connection) as ctx_three:
            res_three = client_three.get(
                f"/api/character-creation/vacancies/?draft={three_draft.id}"
            )
        assert res_three.status_code == 200
        assert len(res_three.json()) == 3

        assert len(ctx_one.captured_queries) == len(ctx_three.captured_queries)


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
