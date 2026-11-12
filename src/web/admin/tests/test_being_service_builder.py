"""The Being Service builder (#4333 slice 2): a being's favored resonances, favored
facets and pledge types, written together with their context."""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import PlayerData
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionEffectFactory
from world.items.factories import ItemTemplateFactory
from world.items.market.models import CraftingServiceOffer
from world.magic.factories import FacetFactory
from world.mechanics.constants import FAVOR_INVOCATION_CATEGORY_NAME
from world.mechanics.models import ModifierTarget
from world.pacts.constants import CharacterPactCommitmentKind
from world.pacts.factories import (
    PactOfferCommitmentFactory,
    PactOfferFactory,
    PactPeriodDetailsFactory,
    make_pact_condition,
)
from world.pacts.models import PactOffer, PactOfferCommitment
from world.scenes.factories import PersonaFactory
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    PledgeFactory,
    RequestedItemFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    designate_chosen_distinction,
)
from world.worship.models import BeingFacet, Pledge, RequestedItem


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
        cls.silk_row = BeingFacetFactory(being=cls.being, facet__name="Silk")
        cls.silk = cls.silk_row.facet
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
            "facets-TOTAL_FORMS": "2",
            "facets-INITIAL_FORMS": "1",
            "facets-MIN_NUM_FORMS": "0",
            "facets-MAX_NUM_FORMS": "1000",
            "facets-0-id": str(self.silk_row.pk),
            "facets-0-being": str(self.being.pk),
            "facets-0-facet": str(self.silk.pk),
            "facets-0-invocation_ease_points": "3",
            "facets-0-earning_bonus_percent": "2",
            "facets-1-being": str(self.being.pk),
            "facets-1-facet": str(self.wolf.pk),
            "facets-1-invocation_ease_points": "1",
            "facets-1-earning_bonus_percent": "1",
            "requests-TOTAL_FORMS": "0",
            "requests-INITIAL_FORMS": "0",
            "requests-MIN_NUM_FORMS": "0",
            "requests-MAX_NUM_FORMS": "1000",
            "pact_offers-TOTAL_FORMS": "0",
            "pact_offers-INITIAL_FORMS": "0",
            "pact_offers-MIN_NUM_FORMS": "0",
            "pact_offers-MAX_NUM_FORMS": "1000",
            "pact_commitments-TOTAL_FORMS": "0",
            "pact_commitments-INITIAL_FORMS": "0",
            "pact_commitments-MIN_NUM_FORMS": "0",
            "pact_commitments-MAX_NUM_FORMS": "1000",
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
        # The Chosen column reads the designated Chosen distinction's earning effect (#4341).
        designate_chosen_distinction()
        body = self.body()
        self.assertIn("Being Service builder: Ombrin", body)
        self.assertIn("100% of amount", body)  # deed favor for the favored resonance
        self.assertIn(
            "At the weekly deed cap, from deeds alone: stranger 3 weeks · "
            "+50% favor earning modifier 2 weeks · Chosen 2 weeks",
            body,
        )
        self.assertIn("Ombrin favor invocation", body)  # the targets exist once it opens
        # The patron targets list the Chosen distinction under their own names.
        self.assertIn("Your patron favor earning", body)
        self.assertIn("Distinction effect: Chosen", body)
        self.assertIn("Every pledge type has an active closing rite.", body)

    def test_the_favored_facets_table_shows_the_worn_rates_and_the_side_panel_who_supplies_them(
        self,
    ) -> None:
        artist = PersonaFactory(name="Corwen")
        CraftingServiceOffer.objects.create(
            crafter_persona=artist,
            recipe_kind="facet_attach",
            shop_room=RoomProfileFactory(),
            fee=10,
        )
        ItemTemplateFactory().inherent_facets.add(self.silk)
        body = self.body()

        self.assertIn("1 template carry it", body)
        self.assertIn("Invocation ease points", body)
        self.assertIn("Earning bonus percent", body)
        self.assertIn("Who supplies these facets", body)
        self.assertIn("Corwen", body)
        # A worn Silk piece with 4 points eases 8 and adds 4%; at the cap of 8 points, 16 and 8%.
        self.assertIn("A worn Silk piece with 4 points eases 8 and adds 4%", body)
        self.assertIn("with 8 points (the cap) eases 16 and adds 8%", body)
        self.assertIn("Cap for all meaning ease on one invocation: 40", body)

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
            sorted(
                BeingFacet.objects.filter(being=self.being).values_list(
                    "facet__name", "invocation_ease_points", "earning_bonus_percent"
                )
            ),
            [("Silk", 3, 2), ("Wolf", 1, 1)],
        )
        pledges = list(Pledge.objects.filter(being=self.being).order_by("pk"))
        self.assertEqual(
            [(p.name, p.favor_target) for p in pledges][1], ("PLACEHOLDER second pledge", 10)
        )
        self.assertEqual(pledges[0].favor_target, 24)
        self.assertTrue(all(p.written_by == self.writer for p in pledges))

    def test_a_favored_facet_can_be_deleted_from_the_table(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data(**{"facets-0-DELETE": "on"})
        data.pop("facets-1-facet")
        data["facets-TOTAL_FORMS"] = "1"
        self.client.post(self.url(), data)

        self.assertFalse(BeingFacet.objects.filter(being=self.being).exists())

    def test_a_negative_worn_rate_is_refused(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url(), self.post_data(**{"facets-0-invocation_ease_points": "-1"})
        )

        self.assertEqual(response.status_code, 200)
        self.silk_row.refresh_from_db()
        self.assertEqual(self.silk_row.invocation_ease_points, 2)

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


class ServiceBuilderRequestedItemTests(ServiceBuilderTestCase):
    """The items a being's pledges and rites ask for are written on the same page (#4530)."""

    def _request_data(self, **overrides) -> dict:
        data = self.post_data(
            **{
                "requests-TOTAL_FORMS": "1",
                "requests-INITIAL_FORMS": "0",
                "requests-0-target": f"pledge:{self.pledge.pk}",
                "requests-0-item_template": str(
                    ItemTemplateFactory(name="weathervane pin", value=2).pk
                ),
                "requests-0-facet": "",
                "requests-0-quantity": "1",
                "requests-0-points": "3",
                "requests-0-hint": "[staff-authored hint]",
            }
        )
        data.update(overrides)
        return data

    def test_the_page_has_the_requests_table_and_its_rule(self) -> None:
        body = self.body()

        self.assertIn("Requested items (pledges and rites)", body)
        self.assertIn("Pledge: PLACEHOLDER pledge", body)
        # A tier 3 rite is a ceremony: it is not offered as something that can ask.
        self.assertNotIn("Rite: Great rite", body)
        self.assertIn("Rite: Small rite", body)

    def test_a_request_is_written_with_its_pledge_and_item(self) -> None:
        self.client.force_login(self.author)

        response = self.client.post(self.url(), self._request_data())

        self.assertEqual(response.status_code, 302)
        request = RequestedItem.objects.get()
        self.assertEqual(request.pledge, self.pledge)
        self.assertEqual(request.item_template.name, "weathervane pin")
        self.assertEqual((request.quantity, request.points), (1, 3))
        self.assertEqual(request.hint, "[staff-authored hint]")

    def test_a_request_can_belong_to_a_rite_and_ask_for_a_facet(self) -> None:
        self.client.force_login(self.author)
        data = self._request_data(
            **{
                "requests-0-target": f"rite:{self.rite.pk}",
                "requests-0-item_template": "",
                "requests-0-facet": str(self.wolf.pk),
            }
        )

        self.client.post(self.url(), data)

        request = RequestedItem.objects.get()
        self.assertEqual(
            (request.rite, request.facet, request.pledge), (self.rite, self.wolf, None)
        )

    def test_a_template_worth_too_much_is_refused(self) -> None:
        self.client.force_login(self.author)
        data = self._request_data(
            **{
                "requests-0-item_template": str(
                    ItemTemplateFactory(name="gilt mirror", value=400).pk
                )
            }
        )

        response = self.client.post(self.url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Requests must be cheap")
        self.assertFalse(RequestedItem.objects.exists())

    def test_a_row_must_name_exactly_one_of_a_template_or_a_facet(self) -> None:
        self.client.force_login(self.author)
        both = self._request_data(**{"requests-0-facet": str(self.wolf.pk)})
        neither = self._request_data(**{"requests-0-item_template": ""})

        for data in (both, neither):
            response = self.client.post(self.url(), data)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(RequestedItem.objects.exists())

    def test_the_rail_says_where_each_request_can_be_found(self) -> None:
        template = ItemTemplateFactory(name="wick trimmer", value=1)
        RequestedItemFactory(pledge=self.pledge, item_template=template)

        body = self.body()

        self.assertIn("Where the requested items come from", body)
        self.assertIn("nothing supplies it yet", body)

    def test_a_request_can_be_deleted_from_the_table(self) -> None:
        request = RequestedItemFactory(pledge=self.pledge)
        self.client.force_login(self.author)
        data = self.post_data(
            **{
                "requests-TOTAL_FORMS": "1",
                "requests-INITIAL_FORMS": "1",
                "requests-0-id": str(request.pk),
                "requests-0-target": f"pledge:{self.pledge.pk}",
                "requests-0-item_template": str(request.item_template_id),
                "requests-0-facet": "",
                "requests-0-quantity": "1",
                "requests-0-points": "3",
                "requests-0-hint": "",
                "requests-0-DELETE": "on",
            }
        )

        self.client.post(self.url(), data)

        self.assertFalse(RequestedItem.objects.exists())


class ServiceBuilderPactTests(ServiceBuilderTestCase):
    """The Pacts section and the pledge's "Pact offered at the close" field (#4341)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.offer = PactOfferFactory(being=cls.being, name="Ombrin's bargain")
        cls.favor = PactOfferCommitmentFactory(offer=cls.offer, amount=8)

    def _commitment_rows(self) -> dict:
        return {
            "pact_commitments-TOTAL_FORMS": "1",
            "pact_commitments-INITIAL_FORMS": "1",
            "pact_commitments-0-id": str(self.favor.pk),
            "pact_commitments-0-offer": str(self.offer.pk),
            "pact_commitments-0-kind": CharacterPactCommitmentKind.FAVOR_EARNED,
            "pact_commitments-0-amount": "8",
            "pact_commitments-0-notes": "",
        }

    def test_the_page_shows_the_pacts_section_its_context_and_the_pledge_field(self) -> None:
        self.pledge.pact_offer = self.offer
        self.pledge.save()
        body = self.body()

        self.assertIn('id="pacts-module"', body)
        self.assertIn("Pact offered at the close", body)
        self.assertIn("Edit this condition", body)
        # The pledge's saved choice, read-only.
        self.assertIn("Commitments: 8 favor per 2 game weeks", body)
        self.assertIn("Stages: Sworn · Strained · Soured · Breached", body)
        # The rail beside the offer.
        self.assertIn("How demanding is 8 per 2 weeks", body)
        self.assertIn("Deeds alone: at most 16 per period (cap 8 a week).", body)
        self.assertIn(
            "OK: 50% is between the warning lines at 25% (4 favor) and 67% (about 11 favor).",
            body,
        )
        self.assertIn("Stage spacing (10) matches severity per missed period (10).", body)
        self.assertIn("Pledge: PLACEHOLDER pledge, at its close", body)

    def test_a_tiny_commitment_is_warned(self) -> None:
        self.favor.amount = 2
        self.favor.save()

        body = self.body()

        self.assertIn("Warn: 12% is below the warning lines", body)

    def test_one_save_writes_an_offer_its_commitments_and_the_pledge_link(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data(
            **{
                **self._commitment_rows(),
                "pact_offers-TOTAL_FORMS": "2",
                "pact_offers-INITIAL_FORMS": "1",
                "pact_offers-0-id": str(self.offer.pk),
                "pact_offers-0-being": str(self.being.pk),
                "pact_offers-0-name": "Ombrin's bargain",
                "pact_offers-0-offer_text": "[staff-authored offer text]",
                "pact_offers-0-period_weeks": "2",
                "pact_offers-0-condition": str(self.offer.condition_id),
                "pact_offers-0-severity_per_miss": "10",
                "pact_offers-0-is_active": "on",
                "pact_offers-1-being": str(self.being.pk),
                "pact_offers-1-name": "A second bargain",
                "pact_offers-1-offer_text": "[staff-authored offer text]",
                "pact_offers-1-period_weeks": "1",
                "pact_offers-1-condition": str(make_pact_condition().pk),
                "pact_offers-1-severity_per_miss": "10",
                "pact_offers-1-is_active": "on",
                "pact_commitments-TOTAL_FORMS": "2",
                "pact_commitments-1-offer": str(self.offer.pk),
                "pact_commitments-1-kind": CharacterPactCommitmentKind.CUSTOM,
                "pact_commitments-1-amount": "0",
                "pact_commitments-1-notes": "[staff-authored promise]",
                "pledges-0-pact_offer": str(self.offer.pk),
            },
        )

        response = self.client.post(self.url(), data)

        self.assertEqual(response.status_code, 302)
        second = PactOffer.objects.get(being=self.being, name="A second bargain")
        self.assertEqual(second.written_by, self.writer)
        self.assertEqual(
            sorted(
                PactOfferCommitment.objects.filter(offer=self.offer).values_list("kind", flat=True)
            ),
            [CharacterPactCommitmentKind.CUSTOM, CharacterPactCommitmentKind.FAVOR_EARNED],
        )
        self.assertEqual(Pledge.objects.get(pk=self.pledge.pk).pact_offer, self.offer)

    def test_a_commitment_with_graded_periods_cannot_be_deleted(self) -> None:
        PactPeriodDetailsFactory(pact__offer=self.offer, commitment=self.favor)
        self.client.force_login(self.author)
        data = self.post_data(
            **{
                **self._commitment_rows(),
                "pact_commitments-0-amount": "3",
                "pact_commitments-0-DELETE": "on",
            }
        )

        response = self.client.post(self.url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "holders have periods graded against it")
        cached = PactOfferCommitment.objects.get(pk=self.favor.pk)
        self.assertEqual(cached.amount, 8)

    def test_the_pacts_rules_reach_the_page(self) -> None:
        css = reachable_css(self.body())
        self.assertIn("#being-service-root .bs-pact-rail {", css)
        self.assertIn("#being-service-root .bs-res-chip {", css)


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
