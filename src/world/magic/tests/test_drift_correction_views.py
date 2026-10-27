"""REST surface for the drift correction rite (#4733): pending offers, convert, decline."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory
from world.magic.factories import (
    CharacterAuraFactory,
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    set_aura_split,
)
from world.magic.models import DriftConversionOffer
from world.magic.tests.test_drift_correction_rite import (
    DriftRiteTestBase,
    _balance,
    _consumed,
    _tied_item,
)
from world.magic.tests.test_drift_offer import _hold
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory

_PENDING_URL = "/api/magic/drift-correction/pending/"
_CONVERT_URL = "/api/magic/drift-correction/convert/"
_DECLINE_URL = "/api/magic/drift-correction/decline/"


class DriftCorrectionViewTestBase(DriftRiteTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.component.holder_character_sheet = self.sheet
        self.component.save(update_fields=["holder_character_sheet"])
        tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet),
        )
        self.account = tenure.player_data.account
        self.player_data = tenure.player_data
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

        # Another account's character with its own offer, cap and carried offering.
        self.other_sheet = CharacterSheetFactory()
        self.other_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.other_sheet),
        )
        self.other_offer = DriftConversionOfferFactory(
            character_sheet=self.other_sheet, scene=SceneFactory()
        )
        DriftConversionCapFactory(offer=self.other_offer, target_resonance=self.dawnlight, cap=5)
        self.other_item = _tied_item(self.dawnlight)
        self.other_item.holder_character_sheet = self.other_sheet
        self.other_item.save(update_fields=["holder_character_sheet"])

    def convert(self, **overrides):
        body = {
            "offer_id": self.offer.pk,
            "source_resonance_id": self.dread.pk,
            "target_resonance_id": self.dawnlight.pk,
            "amount": 12,
            "component_ids": [self.component_pk],
        }
        body.update(overrides)
        with force_check_outcome(self.outcomes["Success"]):
            return self.client.post(_CONVERT_URL, body, format="json")


class PendingOfferTests(DriftCorrectionViewTestBase):
    def test_list_is_scoped_to_the_callers_own_offers(self) -> None:
        response = self.client.get(_PENDING_URL)
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.offer.pk})

    def test_offer_payload_carries_caps_sources_and_qualifying_items(self) -> None:
        response = self.client.get(_PENDING_URL)
        row = response.data["results"][0]
        self.assertEqual(row["scene_id"], self.scene.pk)
        (cap,) = row["caps"]
        self.assertEqual(cap["target_resonance"]["id"], self.dawnlight.pk)
        self.assertEqual(cap["target_resonance"]["name"], "Drift Dawnlight")
        self.assertEqual(cap["cap_remaining"], 12)
        self.assertEqual(cap["focus_bonus"], 0)
        (source,) = cap["sources"]
        self.assertEqual(source["resonance_id"], self.dread.pk)
        self.assertEqual(source["balance"], 30)
        self.assertEqual(source["max_amount"], 12)
        self.assertEqual(source["projected_output"], 6)
        (item,) = cap["qualifying_components"]
        self.assertEqual(item["item_id"], self.component_pk)
        self.assertEqual(item["mode"], "material")

    def test_items_held_by_others_never_qualify(self) -> None:
        response = self.client.get(_PENDING_URL)
        ids = {
            i["item_id"]
            for c in response.data["results"][0]["caps"]
            for i in c["qualifying_components"]
        }
        self.assertNotIn(self.other_item.pk, ids)

    def test_an_offer_left_on_a_finished_scene_is_not_listed(self) -> None:
        # A finish route that bypasses Scene.finish_scene leaves the offer row in place.
        self.scene.is_active = False
        self.scene.date_finished = timezone.now()
        self.scene.save(update_fields=["is_active", "date_finished"])
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["results"], [])
        detail = self.client.get(f"{_PENDING_URL}{self.offer.pk}/")
        self.assertEqual(detail.status_code, 404)

    def test_detail_of_another_accounts_offer_is_404(self) -> None:
        response = self.client.get(f"{_PENDING_URL}{self.other_offer.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_is_rejected(self) -> None:
        response = APIClient().get(_PENDING_URL)
        self.assertIn(response.status_code, (401, 403))


class TwoCharacterAccountTests(DriftCorrectionViewTestBase):
    """One account playing two characters, each with an offer of their own."""

    def setUp(self) -> None:
        super().setUp()
        self.second = CharacterSheetFactory()
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=RosterEntryFactory(character_sheet=self.second),
        )
        set_aura_split(
            CharacterAuraFactory(character=self.second), celestial="80", primal="10", abyssal="10"
        )
        _hold(self.second, self.dawnlight, 0, lifetime=500)
        _hold(self.second, self.dread, 30)
        self.second_offer = DriftConversionOfferFactory(
            character_sheet=self.second, scene=SceneFactory()
        )
        DriftConversionCapFactory(offer=self.second_offer, target_resonance=self.dawnlight, cap=8)
        self.second_item = _tied_item(self.dawnlight)
        self.second_item.holder_character_sheet = self.second
        self.second_item.save(update_fields=["holder_character_sheet"])

    def test_the_list_shows_both_characters_offers_and_no_one_elses(self) -> None:
        response = self.client.get(_PENDING_URL)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.offer.pk, self.second_offer.pk})

    def test_convert_acts_as_the_offers_own_character(self) -> None:
        with force_check_outcome(self.outcomes["Success"]):
            response = self.client.post(
                _CONVERT_URL,
                {
                    "offer_id": self.second_offer.pk,
                    "source_resonance_id": self.dread.pk,
                    "target_resonance_id": self.dawnlight.pk,
                    "amount": 8,
                    "component_ids": [self.second_item.pk],
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["converted_amount"], 8)
        self.assertEqual(_balance(self.second, self.dread), 22)
        self.assertEqual(_balance(self.sheet, self.dread), 30)
        self.assertTrue(_consumed(self.second_item.pk))

    def test_the_other_characters_item_is_refused_on_this_offer(self) -> None:
        response = self.convert(offer_id=self.second_offer.pk, component_ids=[self.component_pk])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(_consumed(self.component_pk))

    def test_component_order_is_preserved_in_the_resolved_list(self) -> None:
        from world.magic.serializers import DriftCorrectionConvertSerializer

        extra = ItemInstanceFactory(holder_character_sheet=self.sheet)
        request = type("R", (), {"user": self.account})()
        serializer = DriftCorrectionConvertSerializer(
            data={
                "offer_id": self.offer.pk,
                "source_resonance_id": self.dread.pk,
                "target_resonance_id": self.dawnlight.pk,
                "amount": 1,
                "component_ids": [extra.pk, self.component_pk],
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            [item.pk for item in serializer.validated_data["components"]],
            [extra.pk, self.component_pk],
        )


class ConvertTests(DriftCorrectionViewTestBase):
    def test_convert_returns_the_result_and_consumes_the_offering(self) -> None:
        response = self.convert()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["converted_amount"], 12)
        self.assertEqual(response.data["granted_amount"], 6)
        self.assertEqual(response.data["outcome_name"], "Success")
        self.assertEqual(response.data["source_resonance_id"], self.dread.pk)
        self.assertEqual(response.data["target_resonance_id"], self.dawnlight.pk)
        self.assertTrue(_consumed(self.component_pk))

    def test_another_accounts_component_is_a_400_and_untouched(self) -> None:
        response = self.convert(component_ids=[self.other_item.pk])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(_consumed(self.other_item.pk))
        self.assertEqual(self.cap_value(), 12)

    def test_unheld_item_among_good_ones_is_a_400_and_nothing_is_consumed(self) -> None:
        stray = ItemInstanceFactory()
        response = self.convert(component_ids=[self.component_pk, stray.pk])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(_consumed(self.component_pk))

    def test_another_accounts_offer_is_not_actionable(self) -> None:
        response = self.convert(offer_id=self.other_offer.pk, component_ids=[])
        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.other_offer.pk).exists())

    def test_rite_refusal_is_a_400_with_the_message(self) -> None:
        response = self.convert(amount=99)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.data["detail"], "You may convert at most 12 toward that resonance."
        )

    def test_missing_offering_is_a_400_with_the_message(self) -> None:
        response = self.convert(component_ids=[])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("offering for Drift Dawnlight", response.data["detail"])

    def test_unknown_resonance_is_a_404(self) -> None:
        response = self.convert(source_resonance_id=999999)
        self.assertEqual(response.status_code, 404, response.content)


class DeclineTests(DriftCorrectionViewTestBase):
    def test_decline_removes_the_offer(self) -> None:
        response = self.client.post(_DECLINE_URL, {"offer_id": self.offer.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_decline_of_another_accounts_offer_is_404_and_leaves_it(self) -> None:
        response = self.client.post(_DECLINE_URL, {"offer_id": self.other_offer.pk}, format="json")
        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.other_offer.pk).exists())
