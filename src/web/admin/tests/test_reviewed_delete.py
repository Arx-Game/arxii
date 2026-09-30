"""The reviewed organization delete (#4064) and the Domain / FealtyEdge admin pages.

Through the admin's own HTTP views as a logged-in superuser, which is the page staff
use. The scenario is the one that started the issue: an organization that owns a
domain, is liege to another house, and is named as liege by a house template.
"""

from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.currency.models import OrgObligation
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.models import Domain, FealtyEdge, HouseTemplate
from world.societies.houses.services import create_domain, swear_fealty
from world.societies.models import Organization, OrganizationRank


def _delete_url(org: Organization) -> str:
    return reverse("admin:arxii_organization_delete", args=(org.pk,))


class ReviewedDeleteJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-1")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.society = SocietyFactory(name="Caretakers")

    def setUp(self) -> None:
        self.crown = OrganizationFactory(name="The Crown", society=self.society)
        self.vassal = OrganizationFactory(name="House Veyrane", society=self.society)
        self.domain = create_domain(
            area=AreaFactory(name="Thornmere", level=AreaLevel.BARONY),
            name="Thornmere Marches",
            owner_org=self.crown,
        )
        self.edge = swear_fealty(vassal=self.vassal, liege=self.crown, tithe_pct=10)
        self.template = HouseTemplateFactory(name="Barony Charter", liege=self.crown)
        self.client.force_login(self.root)

    def _keys(self):
        return {
            "domain": f"arxii.domain:{self.domain.pk}",
            "edge": f"arxii.fealtyedge:{self.edge.pk}",
            "template": f"arxii.housetemplate:{self.template.pk}",
        }

    def test_get_shows_the_plan_with_every_blocking_row_undecided(self) -> None:
        resp = self.client.get(_delete_url(self.crown))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/reviewed_delete_confirmation.html")
        rows = {row.key: row for row in resp.context["protected"]}
        self.assertEqual(set(rows), set(self._keys().values()))
        self.assertTrue(all(not row.decided for row in rows.values()))
        # An optional link offers detach; the oath's liege is required, so delete only.
        self.assertEqual(rows[self._keys()["domain"]].offers, ("detach", "delete"))
        self.assertEqual(rows[self._keys()["template"]].offers, ("detach", "delete"))
        self.assertEqual(rows[self._keys()["edge"]].offers, ("delete",))
        # The rule the page must obey: form rows need the stylesheet the base page lacks.
        self.assertContains(resp, "admin/css/forms.css")
        # Blocking rows link to their admin pages, which #4064 added for these two kinds.
        self.assertContains(resp, reverse("admin:arxii_domain_change", args=(self.domain.pk,)))
        self.assertContains(resp, reverse("admin:arxii_fealtyedge_change", args=(self.edge.pk,)))

    def test_confirm_detach_detach_delete_writes_the_plan_in_one_go(self) -> None:
        keys = self._keys()
        resp = self.client.post(
            _delete_url(self.crown),
            {
                f"choice-{keys['domain']}": "detach",
                f"choice-{keys['template']}": "detach",
                f"choice-{keys['edge']}": "delete",
                "typed_name": "The Crown",
                "review": "confirm",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Organization.objects.filter(pk=self.crown.pk).exists())
        self.assertFalse(OrganizationRank.objects.filter(organization_id=self.crown.pk).exists())
        self.assertFalse(FealtyEdge.objects.filter(pk=self.edge.pk).exists())
        self.assertFalse(OrgObligation.objects.filter(pk=self.edge.obligation_id).exists())
        self.assertIsNone(Domain.objects.get(pk=self.domain.pk).owner_org_id)
        self.assertIsNone(HouseTemplate.objects.get(pk=self.template.pk).liege_id)
        self.assertTrue(Organization.objects.filter(pk=self.vassal.pk).exists())
        # One log line per top-level row touched: the crown, the edge, the two detaches.
        self.assertEqual(LogEntry.objects.count(), 4)

    def test_choosing_delete_reveals_the_rows_cascade_on_update(self) -> None:
        keys = self._keys()
        resp = self.client.post(
            _delete_url(self.crown),
            {f"choice-{keys['domain']}": "delete", "review": "update"},
        )
        self.assertEqual(resp.status_code, 200)
        # The domain now sits in "deleted with it" and stays a decided blocking row.
        flat = str(resp.context["deleted_objects"])
        self.assertIn("Thornmere Marches", flat)
        rows = {row.key: row for row in resp.context["protected"]}
        self.assertEqual(rows[keys["domain"]].choice, "delete")
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())

    def test_confirm_with_an_undecided_row_writes_nothing(self) -> None:
        keys = self._keys()
        resp = self.client.post(
            _delete_url(self.crown),
            {
                f"choice-{keys['domain']}": "detach",
                f"choice-{keys['template']}": "detach",
                "typed_name": "The Crown",
                "review": "confirm",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())
        self.assertEqual(Domain.objects.get(pk=self.domain.pk).owner_org_id, self.crown.pk)
        self.assertEqual(len(resp.context["undecided"]), 1)

    def test_confirm_with_the_wrong_name_writes_nothing(self) -> None:
        keys = self._keys()
        resp = self.client.post(
            _delete_url(self.crown),
            {
                f"choice-{keys['domain']}": "detach",
                f"choice-{keys['template']}": "delete",
                f"choice-{keys['edge']}": "delete",
                "typed_name": "The Crow",
                "review": "confirm",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())
        self.assertTrue(HouseTemplate.objects.filter(pk=self.template.pk).exists())

    def test_a_row_added_between_review_and_confirm_refuses(self) -> None:
        keys = self._keys()
        # Another staff member swears a second vassal to the crown meanwhile.
        newcomer = OrganizationFactory(name="House Late", society=self.society)
        swear_fealty(vassal=newcomer, liege=self.crown, tithe_pct=0)
        resp = self.client.post(
            _delete_url(self.crown),
            {
                f"choice-{keys['domain']}": "detach",
                f"choice-{keys['template']}": "detach",
                f"choice-{keys['edge']}": "delete",
                "typed_name": "The Crown",
                "review": "confirm",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())
        self.assertEqual(Domain.objects.get(pk=self.domain.pk).owner_org_id, self.crown.pk)
        undecided = resp.context["undecided"]
        self.assertEqual(len(undecided), 1)
        self.assertIn("House Late", undecided[0].label)

    def test_a_detach_choice_on_a_delete_only_row_is_not_honoured(self) -> None:
        keys = self._keys()
        resp = self.client.post(
            _delete_url(self.crown),
            {
                f"choice-{keys['domain']}": "detach",
                f"choice-{keys['template']}": "detach",
                f"choice-{keys['edge']}": "detach",
                "typed_name": "The Crown",
                "review": "confirm",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())
        self.assertTrue(FealtyEdge.objects.filter(pk=self.edge.pk).exists())

    def test_a_row_that_must_point_at_someone_is_delete_only(self) -> None:
        """An ownership record's holder link is nullable in the schema but the row must
        name exactly one holder: detach would leave it invalid, so only delete is offered."""
        from world.locations.constants import HolderType
        from world.locations.factories import LocationOwnershipFactory

        deed = LocationOwnershipFactory(
            holder_type=HolderType.ORGANIZATION,
            holder_persona=None,
            holder_organization=self.crown,
        )
        resp = self.client.get(_delete_url(self.crown))
        rows = {row.key: row for row in resp.context["protected"]}
        deed_row = rows[f"arxii.locationownership:{deed.pk}"]
        self.assertEqual(deed_row.offers, ("delete",))
        self.assertTrue(deed_row.detach_note)

    def test_an_unblocked_organization_keeps_the_stock_page(self) -> None:
        resp = self.client.get(_delete_url(self.vassal))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/delete_confirmation.html")
        self.assertTemplateNotUsed(resp, "admin/reviewed_delete_confirmation.html")
        resp = self.client.post(_delete_url(self.vassal), {"post": "yes"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Organization.objects.filter(pk=self.vassal.pk).exists())

    def test_a_non_superuser_keeps_the_stock_dead_end(self) -> None:
        self.staff.user_permissions.set([])
        self.staff.is_superuser = False
        self.staff.save()
        from django.contrib.auth.models import Permission

        self.staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="arxii", codename__endswith="organization"
            )
        )
        self.client.force_login(self.staff)
        resp = self.client.get(_delete_url(self.crown))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateNotUsed(resp, "admin/reviewed_delete_confirmation.html")
        # Django's own dead end, whichever of its two forms this account's rights produce.
        self.assertContains(resp, "Cannot delete organization")
        self.assertNotContains(resp, "typed_name")


class SocietyInlineLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.society = SocietyFactory(name="Caretakers")
        cls.crown = OrganizationFactory(name="The Crown", society=cls.society)
        vassal = OrganizationFactory(name="House Veyrane", society=cls.society)
        swear_fealty(vassal=vassal, liege=cls.crown, tithe_pct=0)

    def test_ticking_delete_on_a_blocked_row_links_to_the_review(self) -> None:
        self.client.force_login(self.root)
        url = reverse("admin:arxii_society_change", args=(self.society.pk,))
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        # Post the form back as rendered, ticking delete on the crown's row.
        data = {}
        for name in page.context["adminform"].form.fields:
            value = page.context["adminform"].form[name].value()
            if value is not None:
                data[name] = value
        formset = next(
            f.formset
            for f in page.context["inline_admin_formsets"]
            if f.formset.model is Organization
        )
        for key, value in formset.management_form.initial.items():
            data[f"{formset.prefix}-{key}"] = value
        for form in formset.forms:
            for name in form.fields:
                value = form[name].value()
                if value is not None:
                    data[f"{form.prefix}-{name}"] = value
            if form.instance.pk == self.crown.pk:
                data[f"{form.prefix}-DELETE"] = "on"
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "would require deleting the following protected")
        self.assertContains(resp, reverse("admin:arxii_organization_delete", args=(self.crown.pk,)))
        self.assertContains(resp, 'target="_blank"')
        self.assertTrue(Organization.objects.filter(pk=self.crown.pk).exists())


class DomainAndFealtyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-1")
        cls.house = OrganizationFactory(name="House Veyrane")
        cls.liege = OrganizationFactory(name="The Crown")
        cls.domain = create_domain(
            area=AreaFactory(name="Veyrane Vale", level=AreaLevel.BARONY),
            name="Veyrane Vale",
            owner_org=cls.house,
        )
        cls.edge = swear_fealty(vassal=cls.house, liege=cls.liege, tithe_pct=10)

    def setUp(self) -> None:
        self.client.force_login(self.root)

    def test_domain_pages_render_and_the_owner_can_be_cleared(self) -> None:
        self.assertEqual(self.client.get(reverse("admin:arxii_domain_changelist")).status_code, 200)
        url = reverse("admin:arxii_domain_change", args=(self.domain.pk,))
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(
            url,
            {
                "name": "Veyrane Vale",
                "description": "",
                "owner_org": "",
                "hall": "",
                "population": 1000,
                "prosperity": 50,
                "unrest": 10,
                "defenses": 10,
                "territory_stream": "",
                "holdings-TOTAL_FORMS": 0,
                "holdings-INITIAL_FORMS": 0,
                "holdings-MIN_NUM_FORMS": 0,
                "holdings-MAX_NUM_FORMS": 1000,
            },
        )
        self.assertEqual(resp.status_code, 302, resp.content[:500])
        self.assertIsNone(Domain.objects.get(pk=self.domain.pk).owner_org_id)

    def test_fealty_pages_render_and_deleting_an_edge_ends_its_tithe(self) -> None:
        self.assertEqual(
            self.client.get(reverse("admin:arxii_fealtyedge_changelist")).status_code, 200
        )
        url = reverse("admin:arxii_fealtyedge_change", args=(self.edge.pk,))
        self.assertEqual(self.client.get(url).status_code, 200)
        obligation_id = self.edge.obligation_id
        self.assertIsNotNone(obligation_id)
        resp = self.client.post(
            reverse("admin:arxii_fealtyedge_delete", args=(self.edge.pk,)), {"post": "yes"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(FealtyEdge.objects.filter(pk=self.edge.pk).exists())
        self.assertFalse(OrgObligation.objects.filter(pk=obligation_id).exists())
