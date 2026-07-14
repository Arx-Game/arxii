"""Intestacy cascade + escheat resolution (#1985, spec Decision 6)."""

from pathlib import Path

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
import world.areas.models as areas_models
from world.character_sheets.factories import CharacterSheetFactory
from world.estates.services import resolve_escheat_org, resolve_intestate_heir
from world.locations.constants import LocationParentType
from world.locations.models import HolderType, LocationTenancy
from world.roster.constants import MembershipBasis
from world.roster.factories import (
    FamilyFactory,
    KinspersonFactory,
    ParentageEdgeFactory,
    UnionFactory,
    UnionKindFactory,
)
from world.roster.models.families import FamilyMembership
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import Domain
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


def _person(*, age=None, sheeted=True, alive=True):
    """A kinsperson, optionally bound to a living sheeted character."""
    if not sheeted:
        return KinspersonFactory(age=age)
    sheet = CharacterSheetFactory()
    CharacterVitalsFactory(
        character_sheet=sheet,
        life_state=CharacterLifeState.ALIVE if alive else CharacterLifeState.DEAD,
    )
    return KinspersonFactory(sheet=sheet, age=age, is_deceased=not alive)


def _family_member(kinsperson, family):
    return FamilyMembership.objects.create(
        kinsperson=kinsperson,
        family=family,
        basis=MembershipBasis.BORN,
        started_at=timezone.now(),
    )


class FamilyOrgHeadTests(TestCase):
    def setUp(self):
        self.family = FamilyFactory()
        self.org = OrganizationFactory(family=self.family)
        self.deceased = _person()
        _family_member(self.deceased, self.family)
        OrganizationMembershipFactory(
            organization=self.org, persona=self.deceased.sheet.primary_persona, rank=3
        )

    def _add_member(self, *, tier, family_member=True, alive=True):
        person = _person(alive=alive)
        if family_member:
            _family_member(person, self.family)
        OrganizationMembershipFactory(
            organization=self.org, persona=person.sheet.primary_persona, rank=tier
        )
        return person

    def test_top_ranked_family_member_is_head(self):
        self._add_member(tier=3)
        head = self._add_member(tier=2)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertEqual(result, head.sheet.primary_persona)

    def test_vassal_outranking_family_is_skipped(self):
        vassal = self._add_member(tier=1, family_member=False)
        head = self._add_member(tier=2)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertNotEqual(result, vassal.sheet.primary_persona)
        self.assertEqual(result, head.sheet.primary_persona)

    def test_dead_head_candidate_is_skipped(self):
        self._add_member(tier=1, alive=False)
        living = self._add_member(tier=2)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertEqual(result, living.sheet.primary_persona)

    def test_family_without_org_falls_through_to_kin(self):
        lone_family = FamilyFactory(name="House Orgless")
        deceased = _person()
        _family_member(deceased, lone_family)
        self.assertIsNone(resolve_intestate_heir(deceased.sheet))


class NextOfKinTests(TestCase):
    def setUp(self):
        self.deceased = _person()

    def test_wedlock_spouse_wins(self):
        spouse = _person(age=40)
        child = _person(age=20)
        UnionFactory(members=[self.deceased, spouse])
        ParentageEdgeFactory(child=child, parent=self.deceased)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertEqual(result, spouse.sheet.primary_persona)

    def test_non_wedlock_union_falls_to_eldest_child(self):
        lover = _person(age=40)
        kind = UnionKindFactory(name="Concubinage", confers_wedlock=False)
        UnionFactory(members=[self.deceased, lover], kind=kind)
        younger = _person(age=18)
        elder = _person(age=25)
        ParentageEdgeFactory(child=younger, parent=self.deceased)
        ParentageEdgeFactory(child=elder, parent=self.deceased)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertEqual(result, elder.sheet.primary_persona)

    def test_hidden_kin_never_auto_inherit(self):
        secret_child = _person(age=30)
        ParentageEdgeFactory(child=secret_child, parent=self.deceased, is_public_record=False)
        self.assertIsNone(resolve_intestate_heir(self.deceased.sheet))

    def test_npc_name_node_kin_skipped(self):
        npc_child = _person(age=30, sheeted=False)
        ParentageEdgeFactory(child=npc_child, parent=self.deceased)
        self.assertIsNone(resolve_intestate_heir(self.deceased.sheet))

    def test_dead_spouse_falls_to_parent(self):
        dead_spouse = _person(age=40, alive=False)
        UnionFactory(members=[self.deceased, dead_spouse])
        parent = _person(age=60)
        ParentageEdgeFactory(child=self.deceased, parent=parent)
        result = resolve_intestate_heir(self.deceased.sheet)
        self.assertEqual(result, parent.sheet.primary_persona)

    def test_no_kin_returns_none(self):
        self.assertIsNone(resolve_intestate_heir(self.deceased.sheet))


class EscheatTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Area.save() refreshes the AreaClosure matview on PG. The cached PG
        # test schema drops RunSQL artifacts, so restore the view when absent
        # (SQLite no-ops the refresh wrapper and never needs it).
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('areas_areaclosure')")
                if cursor.fetchone()[0] is None:
                    sql_path = (
                        Path(areas_models.__file__).resolve().parent / "sql" / "areaclosure.sql"
                    )
                    cursor.execute(sql_path.read_text())

    def test_primary_home_domain_org(self):
        org = OrganizationFactory()
        domain_area = AreaFactory(level=AreaLevel.REGION)
        Domain.objects.create(area=domain_area, name="Testmark", owner_org=org)
        sheet = CharacterSheetFactory()
        from evennia_extensions.factories import RoomProfileFactory

        room = RoomProfileFactory(area=domain_area)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            tenant_type=HolderType.PERSONA,
            tenant_persona=sheet.primary_persona,
            is_primary_home=True,
        )
        self.assertEqual(resolve_escheat_org(sheet), org)

    def test_no_region_returns_none(self):
        sheet = CharacterSheetFactory()
        self.assertIsNone(resolve_escheat_org(sheet))
