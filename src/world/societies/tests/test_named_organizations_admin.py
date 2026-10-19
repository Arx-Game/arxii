"""The admin pages that author named organizations and relations render as designed (#4473)."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory
from world.missions.factories import MissionOptionRouteFactory
from world.missions.models import MissionRenownAward
from world.societies.constants import (
    NamedOrganizationRole,
    OrganizationRelationKind,
    RenownMagnitude,
)
from world.societies.factories import (
    LegendSourceTypeFactory,
    NamedOrganizationFactory,
    OrganizationFactory,
    OrganizationRelationFactory,
    PhilosophicalArchetypeFactory,
    SocietyFactory,
)


class NamedOrganizationAdminTests(TestCase):
    def setUp(self) -> None:
        staff = AccountFactory(username="admin_named", is_staff=True, is_superuser=True)
        self.client.force_login(staff)

    def _page(self, name: str, *args: int) -> str:
        response = self.client.get(reverse(f"admin:arxii_{name}_change", args=args))
        self.assertEqual(response.status_code, 200)
        return " ".join(response.content.decode().split())

    def test_the_award_page_shows_each_organization_with_its_estimate(self) -> None:
        sly = PhilosophicalArchetypeFactory(name="Sly Work", method_delta=-3)
        award = MissionRenownAward.objects.create(
            route=MissionOptionRouteFactory(), magnitude=RenownMagnitude.MODERATE
        )
        award.archetypes.add(sly)
        NamedOrganizationFactory(
            mission_award=award,
            organization=OrganizationFactory(method_override=-4),
            role=NamedOrganizationRole.HELPED,
        )
        html = self._page("missionrenownaward", award.pk)
        self.assertIn("Organizations this act names", html)
        self.assertIn("Base 120, adjustment +36 (cap 60). Total +156", html)
        self.assertIn("named organization 120", html)
        self.assertIn("never flip the direction", html)

    def test_the_consequence_effect_page_shows_the_base_amount(self) -> None:
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=5,
            legend_source_type=LegendSourceTypeFactory(),
        )
        NamedOrganizationFactory(consequence_effect=effect, base_amount=200)
        html = self._page("consequenceeffect", effect.pk)
        self.assertIn("Organizations this act names", html)
        self.assertIn("Base 200", html)
        self.assertIn("Consequences have no magnitude", html)

    def test_the_organization_page_authors_and_lists_relations(self) -> None:
        society = SocietyFactory(name="Rt Society", method=1)
        wardens = OrganizationFactory(name="Wardens", society=society, method_override=-4)
        court = OrganizationFactory(name="Court", society=society)
        OrganizationRelationFactory(
            organization=wardens,
            toward=court,
            kind=OrganizationRelationKind.RIVAL,
            share_percent=50,
        )
        own = self._page("organization", wardens.pk)
        self.assertIn("Reacts to changes with", own)
        self.assertIn("Other organization", own)
        self.assertIn("Rt Society value: 1. Effective: -4.", own)
        theirs = self._page("organization", court.pk)
        self.assertIn("Organizations that react to Court (read only)", theirs)
