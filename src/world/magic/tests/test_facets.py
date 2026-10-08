"""The facet vocabulary's spelling rule, near-matches, create endpoint and merge (#4197)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.items.factories import (
    FacetVogueMomentumFactory,
    FashionStyleFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.magic.exceptions import UnmergedFacetRelation
from world.magic.factories import (
    FacetFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    SignatureMotifBonusFactory,
)
from world.magic.models import Facet, FacetAlias
from world.magic.services import facets as svc
from world.worship.factories import BeingFacetFactory, WorshippedBeingFactory


class FacetKeyTests(TestCase):
    def test_case_punctuation_and_plural_collapse(self) -> None:
        self.assertEqual(svc.facet_key("Scythes"), "scythe")
        self.assertEqual(svc.facet_key("scythe"), "scythe")
        self.assertEqual(svc.facet_key("Scythe-like Weapons"), "scythe like weapon")
        self.assertEqual(svc.facet_key("  Farm   Instruments "), "farm instrument")
        self.assertEqual(svc.facet_key("Butterflies"), "butterfly")
        self.assertEqual(svc.facet_key("Ashes"), "ash")

    def test_short_words_and_double_s_are_left_alone(self) -> None:
        self.assertEqual(svc.facet_key("Gas"), "gas")
        self.assertEqual(svc.facet_key("Glass"), "glass")
        self.assertEqual(svc.facet_key(""), "")


class FindAndNearTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scythe = FacetFactory(name="Scythe")
        cls.silk = FacetFactory(name="Silk")
        cls.wolf = FacetFactory(name="Wolf")
        FacetAlias.objects.create(name="Reaping Hooks", facet=cls.scythe)

    def test_find_resolves_a_spelling_or_an_alias(self) -> None:
        self.assertEqual(svc.find_facet("scythes"), self.scythe)
        self.assertEqual(svc.find_facet("reaping hook"), self.scythe)
        self.assertIsNone(svc.find_facet("Sickle"))
        self.assertIsNone(svc.find_facet("   "))

    def test_near_orders_equal_then_contained_then_one_edit(self) -> None:
        self.assertEqual(svc.near_facets("Scythes"), [self.scythe])
        self.assertEqual(svc.near_facets("Scy"), [self.scythe])
        self.assertEqual(svc.near_facets("Wolfs"), [self.wolf])
        self.assertEqual(svc.near_facets("Sulk"), [self.silk])
        self.assertEqual(svc.near_facets("Reaping Hook"), [self.scythe])
        self.assertEqual(svc.near_facets("Granite"), [])
        self.assertEqual(svc.near_facets(""), [])


class FacetApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory()
        cls.scythe = FacetFactory(name="Scythe")
        FacetAlias.objects.create(name="Reaping Hooks", facet=cls.scythe)

    def test_a_player_reads_and_may_not_create(self) -> None:
        self.client.force_authenticate(self.player)
        self.assertEqual(
            self.client.get(reverse("magic:facet-list")).status_code, status.HTTP_200_OK
        )
        response = self.client.post(reverse("magic:facet-list"), {"name": "Sickle"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Facet.objects.filter(name="Sickle").exists())

    def test_staff_create_a_new_facet(self) -> None:
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            reverse("magic:facet-list"), {"name": " Sickle "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["name"], "Sickle")
        self.assertFalse(response.data["matched"])
        self.assertTrue(Facet.objects.filter(name="Sickle").exists())

    def test_a_spelling_that_resolves_answers_the_existing_facet(self) -> None:
        self.client.force_authenticate(self.staff)
        for spelling in ("scythes", "Reaping hook"):
            response = self.client.post(
                reverse("magic:facet-list"), {"name": spelling}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["id"], self.scythe.pk)
            self.assertTrue(response.data["matched"])
        self.assertEqual(Facet.objects.count(), 1)

    def test_a_blank_name_is_refused(self) -> None:
        self.client.force_authenticate(self.staff)
        response = self.client.post(reverse("magic:facet-list"), {"name": "   "}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_near_is_readable_by_a_player(self) -> None:
        self.client.force_authenticate(self.player)
        response = self.client.get(reverse("magic:facet-near"), {"name": "Scythes"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data], [self.scythe.pk])


class MergeFacetsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.winner = FacetFactory(name="Scythe")
        cls.loser = FacetFactory(name="Scythes")
        cls.other_loser = FacetFactory(name="Sickles")

    def test_every_live_relation_has_a_handler(self) -> None:
        live = {rel.get_accessor_name() for rel in Facet._meta.related_objects}
        self.assertEqual(live, set(svc.HANDLED_RELATIONS))

    def test_a_relation_without_a_handler_stops_the_merge(self) -> None:
        original = svc.HANDLED_RELATIONS
        svc.HANDLED_RELATIONS = frozenset(original - {"favored_by_beings"})
        try:
            with self.assertRaises(UnmergedFacetRelation):
                svc.merge_facets(self.winner, [self.loser])
        finally:
            svc.HANDLED_RELATIONS = original
        self.assertTrue(Facet.objects.filter(pk=self.loser.pk).exists())

    def test_bindings_follow_the_winner_and_the_losers_become_aliases(self) -> None:
        # One of each relation on the loser.
        motif_resonance = MotifResonanceFactory()
        MotifResonanceAssociationFactory(motif_resonance=motif_resonance, facet=self.loser)
        bonus = SignatureMotifBonusFactory(required_facet=self.loser)
        template = ItemTemplateFactory()
        template.inherent_facets.add(self.loser)
        item = ItemInstanceFactory()
        ItemFacetFactory(item_instance=item, facet=self.loser)
        momentum = FacetVogueMomentumFactory(facet=self.loser)
        style = FashionStyleFactory()
        style.in_vogue_facets.add(self.loser)
        being = WorshippedBeingFactory()
        BeingFacetFactory(being=being, facet=self.loser)
        FacetAlias.objects.create(name="Reaping Hooks", facet=self.loser)

        result = svc.merge_facets(self.winner, [self.loser, self.other_loser])

        self.assertFalse(Facet.objects.filter(pk__in=[self.loser.pk, self.other_loser.pk]).exists())
        self.assertEqual(
            list(motif_resonance.facet_assignments.values_list("facet", flat=True)),
            [self.winner.pk],
        )
        bonus.refresh_from_db()
        self.assertEqual(bonus.required_facet, self.winner)
        self.assertEqual(list(template.inherent_facets.all()), [self.winner])
        self.assertEqual(list(item.item_facets.values_list("facet", flat=True)), [self.winner.pk])
        momentum.refresh_from_db()
        self.assertEqual(momentum.facet, self.winner)
        self.assertEqual(list(style.in_vogue_facets.all()), [self.winner])
        self.assertEqual(list(being.being_facets.values_list("facet", flat=True)), [self.winner.pk])
        self.assertEqual(
            set(self.winner.aliases.values_list("name", flat=True)),
            {"Scythes", "Sickles", "Reaping Hooks"},
        )
        self.assertEqual(sorted(result.retired_names), ["Scythes", "Sickles"])
        self.assertEqual(result.moved, 7)
        self.assertEqual(result.dropped, 0)

    def test_an_owner_already_on_the_winner_keeps_one_binding(self) -> None:
        being = WorshippedBeingFactory()
        BeingFacetFactory(being=being, facet=self.winner)
        BeingFacetFactory(being=being, facet=self.loser)
        template = ItemTemplateFactory()
        template.inherent_facets.add(self.winner, self.loser)

        result = svc.merge_facets(self.winner, [self.loser])

        self.assertEqual(list(being.being_facets.values_list("facet", flat=True)), [self.winner.pk])
        self.assertEqual(list(template.inherent_facets.all()), [self.winner])
        self.assertEqual(result.dropped, 2)
        self.assertEqual(result.moved, 0)

    def test_the_winner_in_the_losers_is_ignored(self) -> None:
        result = svc.merge_facets(self.winner, [self.winner, self.loser])
        self.assertEqual(result.retired_names, ["Scythes"])
        self.assertTrue(Facet.objects.filter(pk=self.winner.pk).exists())


class MergeAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        cls.winner = FacetFactory(name="Scythe")
        cls.loser = FacetFactory(name="Scythes")

    def test_the_action_shows_a_confirmation_then_merges(self) -> None:
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_facet_changelist")
        selected = {"action": "merge_into", "_selected_action": [self.winner.pk, self.loser.pk]}
        page = self.client.post(url, selected)
        self.assertEqual(page.status_code, status.HTTP_200_OK)
        self.assertContains(page, "Pick the facet that survives")
        self.assertContains(page, "Scythes")

        done = self.client.post(url, {**selected, "apply": "1", "winner": self.winner.pk})
        self.assertEqual(done.status_code, status.HTTP_302_FOUND)
        self.assertFalse(Facet.objects.filter(pk=self.loser.pk).exists())
        self.assertEqual(FacetAlias.objects.get(name="Scythes").facet, self.winner)

    def test_one_selected_facet_is_refused(self) -> None:
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_facet_changelist")
        response = self.client.post(
            url, {"action": "merge_into", "_selected_action": [self.winner.pk]}
        )
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Facet.objects.count(), 2)
