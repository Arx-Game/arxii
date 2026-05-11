from django.test import TestCase

from world.locations.services import _persona_organization_ids
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
