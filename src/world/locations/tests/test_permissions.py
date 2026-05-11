from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import (
    _persona_organization_ids,
    is_owner,
    ownership_for,
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

    def test_no_alt_piercing(self) -> None:
        """An alt persona of the same character that owns the room does
        not get owner standing. Persona scoping is strict per the
        no-alt-outing hard rule.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.models import PersonaType

        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        alt = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=primary,
        )
        self.assertTrue(is_owner(primary, self.room))
        self.assertFalse(is_owner(alt, self.room))


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
