from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import (
    _persona_organization_ids,
    is_owner,
    is_tenant,
    ownership_for,
    tenancies_for,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
)


class PersonaOrganizationIdsTests(TestCase):
    def test_returns_empty_set_for_persona_with_no_memberships(self) -> None:
        persona = PersonaFactory()
        self.assertEqual(_persona_organization_ids(persona), set())

    def test_returns_all_org_ids_for_member(self) -> None:
        persona = PersonaFactory()
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        OrganizationMembershipFactory(persona=persona, organization=org_a)
        OrganizationMembershipFactory(persona=persona, organization=org_b)
        self.assertEqual(_persona_organization_ids(persona), {org_a.pk, org_b.pk})

    def test_excludes_orgs_persona_is_not_a_member_of(self) -> None:
        persona = PersonaFactory()
        joined_org = OrganizationFactory()
        OrganizationFactory()  # unjoined org — must not appear in result
        OrganizationMembershipFactory(persona=persona, organization=joined_org)
        self.assertEqual(_persona_organization_ids(persona), {joined_org.pk})


class OwnershipForTests(TestCase):
    def setUp(self) -> None:
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.profile = RoomProfileFactory(area=self.ward)
        self.room = self.profile.objectdb

    def test_direct_persona_owner_matches(self) -> None:
        persona = PersonaFactory()
        row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        self.assertEqual(ownership_for(persona, self.room), row)
        self.assertTrue(is_owner(persona, self.room))

    def test_unrelated_persona_does_not_match(self) -> None:
        owner = PersonaFactory()
        stranger = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=owner,
        )
        self.assertIsNone(ownership_for(stranger, self.room))
        self.assertFalse(is_owner(stranger, self.room))

    def test_org_member_has_standing(self) -> None:
        org = OrganizationFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(persona=member, organization=org)
        row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        self.assertEqual(ownership_for(member, self.room), row)
        self.assertTrue(is_owner(member, self.room))

    def test_org_non_member_does_not_match(self) -> None:
        org = OrganizationFactory()
        non_member = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        self.assertIsNone(ownership_for(non_member, self.room))
        self.assertFalse(is_owner(non_member, self.room))

    def test_no_ownership_in_chain(self) -> None:
        persona = PersonaFactory()
        self.assertIsNone(ownership_for(persona, self.room))
        self.assertFalse(is_owner(persona, self.room))

    def test_org_ownership_cascades_to_room(self) -> None:
        """Building (city in this case) owns; query the room within."""
        org = OrganizationFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(persona=member, organization=org)
        row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        self.assertEqual(ownership_for(member, self.room), row)

    def test_alt_persona_of_owner_not_recognized_as_owner(self) -> None:
        """An alt_persona (secondary persona of the same character) does
        not automatically get owner standing.

        OOC the character owns the room, but the WHOLE POINT of a
        secondary persona is that it's secret — the household knows the
        outward-facing persona as the owner, and would treat the
        character's other personas as intruders unless those personas
        have been discovered/revealed. Substrate is therefore strictly
        per-persona; downstream PersonaDiscovery-aware code can compose
        a discovery-respecting check on top.

        Distinct from the alt_characters case (different CharacterSheet,
        same Account) — those never share standing under any
        circumstance.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.models import PersonaType

        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        alt_persona = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=primary,
        )
        self.assertTrue(is_owner(primary, self.room))
        self.assertFalse(is_owner(alt_persona, self.room))

    def test_alt_persona_with_own_org_membership_gets_standing(self) -> None:
        """An alt_persona with its OWN independent OrganizationMembership
        gets standing via that membership — the substrate is per-persona,
        not per-character. Locks in that having a sibling persona who
        is a member is NOT the same as having the membership.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.models import PersonaType

        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        alt_persona = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        org = OrganizationFactory()
        # Only the alt_persona joins the org — primary has no membership.
        OrganizationMembershipFactory(persona=alt_persona, organization=org)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        self.assertTrue(is_owner(alt_persona, self.room))
        self.assertFalse(is_owner(primary, self.room))


class OwnershipForQueryBudgetTests(TestCase):
    """Lock the query budget so it doesn't silently regress."""

    def test_persona_holder_short_circuits_org_lookup(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        persona = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        from evennia.objects.models import ObjectDB

        room = ObjectDB.objects.get(pk=profile.objectdb.pk)
        # PERSONA-holder match: effective_owner (2 queries) + persona compare
        # (no DB hit). Total: 2 queries.
        with self.assertNumQueries(2):
            ownership_for(persona, room)

    def test_org_holder_costs_three_queries(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        org = OrganizationFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(persona=member, organization=org)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        from evennia.objects.models import ObjectDB

        room = ObjectDB.objects.get(pk=profile.objectdb.pk)
        # ORGANIZATION-holder match: effective_owner (2) + org_ids fetch (1).
        with self.assertNumQueries(3):
            ownership_for(member, room)


class TenanciesForTests(TestCase):
    def setUp(self) -> None:
        self.building = AreaFactory(level=AreaLevel.BUILDING)
        self.profile = RoomProfileFactory(area=self.building)
        self.room = self.profile.objectdb

    def test_direct_persona_tenant_matches(self) -> None:
        tenant = PersonaFactory()
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=tenant,
        )
        self.assertEqual(list(tenancies_for(tenant, self.room)), [row])
        self.assertTrue(is_tenant(tenant, self.room))

    def test_unrelated_persona_returns_empty(self) -> None:
        tenant = PersonaFactory()
        stranger = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=tenant,
        )
        self.assertEqual(list(tenancies_for(stranger, self.room)), [])
        self.assertFalse(is_tenant(stranger, self.room))

    def test_org_member_has_tenant_standing(self) -> None:
        org = OrganizationFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(persona=member, organization=org)
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=org,
        )
        self.assertEqual(list(tenancies_for(member, self.room)), [row])
        self.assertTrue(is_tenant(member, self.room))

    def test_org_non_member_returns_empty(self) -> None:
        org = OrganizationFactory()
        non_member = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=org,
        )
        self.assertEqual(list(tenancies_for(non_member, self.room)), [])
        self.assertFalse(is_tenant(non_member, self.room))

    def test_multiple_tenancies_partial_match(self) -> None:
        """Room has 1 building-org tenancy + 2 room-level persona tenancies.
        Query as the building-org member — only the org row applies.
        """
        org = OrganizationFactory()
        org_member = PersonaFactory()
        OrganizationMembershipFactory(persona=org_member, organization=org)
        room_tenant_a = PersonaFactory()
        room_tenant_b = PersonaFactory()

        org_row = LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=org,
        )
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=room_tenant_a,
        )
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=room_tenant_b,
        )

        # Org member sees only their org row
        self.assertEqual(list(tenancies_for(org_member, self.room)), [org_row])
        # room_tenant_a sees only their own row
        result_a = list(tenancies_for(room_tenant_a, self.room))
        self.assertEqual(len(result_a), 1)
        self.assertEqual(result_a[0].tenant_persona, room_tenant_a)

    def test_alt_persona_of_tenant_not_recognized_as_tenant(self) -> None:
        """An alt_persona (secondary persona of the same character) does
        not automatically get tenant standing for the same reason as the
        ownership case: the secondary persona is secret IC and would not
        be recognized as the legitimate tenant until discovered.

        Substrate is per-persona. Discovery-aware tenant checks are a
        downstream concern.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.models import PersonaType

        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        alt_persona = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=primary,
        )
        self.assertTrue(is_tenant(primary, self.room))
        self.assertFalse(is_tenant(alt_persona, self.room))


class TenanciesForQueryBudgetTests(TestCase):
    def test_three_queries_per_call(self) -> None:
        building = AreaFactory(level=AreaLevel.BUILDING)
        profile = RoomProfileFactory(area=building)
        persona = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=persona,
        )
        from evennia.objects.models import ObjectDB

        room = ObjectDB.objects.get(pk=profile.objectdb.pk)
        # tenancies_for: org_ids (1) + closure walk (1) + tenancy fetch (1) = 3
        with self.assertNumQueries(3):
            list(tenancies_for(persona, room))
