"""The Being Service builder (#4333 slice 2): a being's favored resonances, favored
facets and pledge types, written together with their context."""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionEffectFactory
from world.magic.factories import FacetFactory
from world.mechanics.constants import FAVOR_INVOCATION_CATEGORY_NAME
from world.mechanics.models import ModifierTarget
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    PledgeFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
)
from world.worship.models import BeingFacet, Pledge


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class ServiceBuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("bsauthor")
        cls.writer = ContentContributorFactory(name="Service Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("bsunlinked")
        cls.being = WorshippedBeingFactory(name="Ombrin", domains="[PLACEHOLDER domains]")
        cls.favored = BeingResonanceFactory(being=cls.being, tier=BeingResonanceTier.FAVORED)
        cls.silk = BeingFacetFactory(being=cls.being, facet__name="Silk").facet
        cls.wolf = FacetFactory(name="Wolf")
        cls.rite = WorshipRiteFactory(
            being=cls.being, kind=RiteKindFactory(tier=RiteTier.DEVOTIONAL), name="Small rite"
        )
        cls.ceremony_rite = WorshipRiteFactory(
            being=cls.being, kind=RiteKindFactory(tier=RiteTier.PERILOUS), name="Great rite"
        )
        cls.pledge = PledgeFactory(
            being=cls.being, name="PLACEHOLDER pledge", favor_target=20, closing_rite=cls.rite
        )

    def url(self) -> str:
        return reverse("admin_being_service", args=[self.being.pk])

    def body(self, account=None) -> str:
        self.client.force_login(account or self.author)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def post_data(self, **overrides) -> dict:
        data = {
            "resonances-TOTAL_FORMS": "1",
            "resonances-INITIAL_FORMS": "1",
            "resonances-MIN_NUM_FORMS": "0",
            "resonances-MAX_NUM_FORMS": "1000",
            "resonances-0-id": str(self.favored.pk),
            "resonances-0-being": str(self.being.pk),
            "resonances-0-resonance": str(self.favored.resonance_id),
            "resonances-0-tier": BeingResonanceTier.ASSOCIATED,
            "facets-favored_facets": [str(self.wolf.pk)],
            "pledges-TOTAL_FORMS": "2",
            "pledges-INITIAL_FORMS": "1",
            "pledges-MIN_NUM_FORMS": "0",
            "pledges-MAX_NUM_FORMS": "1000",
            "pledges-0-id": str(self.pledge.pk),
            "pledges-0-being": str(self.being.pk),
            "pledges-0-name": "PLACEHOLDER pledge",
            "pledges-0-description": "[PLACEHOLDER description]",
            "pledges-0-favor_target": "24",
            "pledges-0-span_weeks": "2",
            "pledges-0-closing_rite": str(self.rite.pk),
            "pledges-0-is_active": "on",
            "pledges-1-being": str(self.being.pk),
            "pledges-1-name": "PLACEHOLDER second pledge",
            "pledges-1-description": "",
            "pledges-1-favor_target": "10",
            "pledges-1-span_weeks": "1",
            "pledges-1-closing_rite": str(self.rite.pk),
            "pledges-1-is_active": "on",
            "save": "Save",
        }
        data.update(overrides)
        return data


class ServiceBuilderPageTests(ServiceBuilderTestCase):
    def test_the_page_shows_the_beings_service_and_its_context(self) -> None:
        body = self.body()
        self.assertIn("Being Service builder: Ombrin", body)
        self.assertIn("100% of amount", body)  # deed favor for the favored resonance
        self.assertIn(
            "At the weekly deed cap, from deeds alone: stranger 3 weeks · "
            "+50% favor earning modifier 2 weeks · Chosen 2 weeks",
            body,
        )
        self.assertIn("Ombrin favor invocation", body)  # the targets exist once it opens
        self.assertIn("Every pledge type has an active closing rite.", body)

    def test_opening_creates_the_beings_favor_targets(self) -> None:
        self.body()
        self.assertTrue(
            ModifierTarget.objects.filter(
                category__name=FAVOR_INVOCATION_CATEGORY_NAME, target_being=self.being
            ).exists()
        )

    def test_the_favor_modifiers_table_lists_a_distinction_effect(self) -> None:
        self.body()
        target = ModifierTarget.objects.get(
            category__name=FAVOR_INVOCATION_CATEGORY_NAME, target_being=self.being
        )
        DistinctionEffectFactory(target=target, value_per_rank=15, distinction__name="Devout")
        body = self.body()
        self.assertIn("Distinction effect: Devout", body)
        self.assertIn("15 points per rank", body)

    def test_the_closing_rite_picker_lists_only_tier_1_and_2_rites(self) -> None:
        body = self.body()
        self.assertIn("Small rite", body)
        self.assertNotIn("Great rite", body)

    def test_the_being_change_page_links_here(self) -> None:
        self.client.force_login(self.author)
        response = self.client.get(
            reverse("admin:arxii_worshippedbeing_change", args=[self.being.pk])
        )
        self.assertContains(response, self.url())

    def test_an_unlinked_operator_sees_setup_and_saves_nothing(self) -> None:
        self.client.force_login(self.unlinked)
        self.client.post(self.url(), self.post_data())
        self.assertEqual(Pledge.objects.filter(being=self.being).count(), 1)


class ServiceBuilderSaveTests(ServiceBuilderTestCase):
    def test_one_save_writes_resonances_facets_and_pledges(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(self.url(), self.post_data())
        self.assertRedirects(
            response,
            reverse("admin:arxii_worshippedbeing_change", args=[self.being.pk]),
            fetch_redirect_response=False,
        )
        self.favored.refresh_from_db()
        self.assertEqual(self.favored.tier, BeingResonanceTier.ASSOCIATED)
        self.assertEqual(
            list(BeingFacet.objects.filter(being=self.being).values_list("facet", flat=True)),
            [self.wolf.pk],
        )
        pledges = list(Pledge.objects.filter(being=self.being).order_by("pk"))
        self.assertEqual(
            [(p.name, p.favor_target) for p in pledges][1], ("PLACEHOLDER second pledge", 10)
        )
        self.assertEqual(pledges[0].favor_target, 24)
        self.assertTrue(all(p.written_by == self.writer for p in pledges))

    def test_a_ceremony_rite_cannot_close_a_pledge(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url(), self.post_data(**{"pledges-1-closing_rite": str(self.ceremony_rite.pk)})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pledge.objects.filter(being=self.being).count(), 1)
        self.assertEqual(Pledge.objects.get(pk=self.pledge.pk).favor_target, 20)

    def test_mark_reviewed_stamps_every_pledge_type(self) -> None:
        self.client.force_login(self.author)
        self.client.post(reverse("admin_being_service_review", args=[self.being.pk]))
        self.assertEqual(Pledge.objects.get(pk=self.pledge.pk).reviewed_by, self.writer)


class ServiceBuilderStylingTest(ServiceBuilderTestCase):
    """Every rule the page's layout needs must reach the page (#3667's guard)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-table",
            "object-tools",
            "form-row",
            "flex-container",
        }
    )

    def test_the_page_links_the_stylesheets_its_layout_needs(self) -> None:
        linked = stylesheet_hrefs(self.body())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"linked: {linked}")

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self) -> None:
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/being_service"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        css = reachable_css(self.body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
