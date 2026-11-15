"""REST surface for the open chance to atone and the rite of settling (#4733, #5124)."""

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
    ReflectionFactory,
    set_aura_split,
)
from world.magic.models import DriftConversionOffer, Reflection
from world.magic.serializers import SettlingRitePerformSerializer
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
_RITE_URL = "/api/magic/settling-rite/"


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

    def settle(self, sheet=None, **overrides):
        body = {
            "character_sheet_id": (sheet or self.sheet).pk,
            "component_ids": [self.component_pk],
        }
        body.update(overrides)
        with force_check_outcome(self.outcomes["Success"]):
            return self.client.post(_RITE_URL, body, format="json")


class PendingOfferTests(DriftCorrectionViewTestBase):
    def test_list_is_scoped_to_the_callers_own_offers(self) -> None:
        response = self.client.get(_PENDING_URL)
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.offer.pk})

    def test_offer_payload_carries_the_character_and_its_caps(self) -> None:
        row = self.client.get(_PENDING_URL).data["results"][0]
        self.assertEqual(row["scene_id"], self.scene.pk)
        self.assertEqual(row["character_id"], self.sheet.pk)
        (cap,) = row["caps"]
        self.assertEqual(cap["target_resonance"]["id"], self.dawnlight.pk)
        self.assertEqual(cap["target_resonance"]["name"], "Drift Dawnlight")
        self.assertEqual(cap["target_resonance"]["affinity"], "Celestial")
        self.assertEqual(cap["cap_remaining"], 12)

    def test_an_offer_whose_scene_finished_is_still_listed(self) -> None:
        # The chance stays open until the rite spends it (#5124).
        self.scene.is_active = False
        self.scene.date_finished = timezone.now()
        self.scene.save(update_fields=["is_active", "date_finished"])

        response = self.client.get(_PENDING_URL)

        self.assertEqual([row["id"] for row in response.data["results"]], [self.offer.pk])
        self.assertEqual(self.client.get(f"{_PENDING_URL}{self.offer.pk}/").status_code, 200)

    def test_detail_of_another_accounts_offer_is_404(self) -> None:
        response = self.client.get(f"{_PENDING_URL}{self.other_offer.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_is_rejected(self) -> None:
        response = APIClient().get(_PENDING_URL)
        self.assertIn(response.status_code, (401, 403))


class TwoCharacterAccountTests(DriftCorrectionViewTestBase):
    """One account playing two characters, each with its own reflection and offering."""

    def setUp(self) -> None:
        super().setUp()
        self.second = CharacterSheetFactory()
        RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=RosterEntryFactory(character_sheet=self.second),
        )
        set_aura_split(
            CharacterAuraFactory(character=self.second), celestial="100", primal="0", abyssal="0"
        )
        # 30 Abyssal on 170 Celestial: unsettled, with something to atone for.
        _hold(self.second, self.dawnlight, 0, lifetime=170)
        _hold(self.second, self.dread, 30)
        self.second_offer = DriftConversionOfferFactory(
            character_sheet=self.second, scene=SceneFactory()
        )
        DriftConversionCapFactory(offer=self.second_offer, target_resonance=self.dawnlight, cap=8)
        self.second_item = _tied_item(self.dawnlight)
        self.second_item.holder_character_sheet = self.second
        self.second_item.save(update_fields=["holder_character_sheet"])
        ReflectionFactory(character_sheet=self.second, resonance=self.dread)

    def test_the_list_shows_both_characters_offers_and_no_one_elses(self) -> None:
        ids = {row["id"] for row in self.client.get(_PENDING_URL).data["results"]}
        self.assertEqual(ids, {self.offer.pk, self.second_offer.pk})

    def test_the_rite_acts_as_the_character_named(self) -> None:
        response = self.settle(self.second, component_ids=[self.second_item.pk])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["outcome_name"], "Success")
        self.assertEqual(_balance(self.second, self.dread), 22)
        self.assertEqual(_balance(self.sheet, self.dread), 30)
        self.assertTrue(_consumed(self.second_item.pk))

    def test_the_other_characters_item_is_refused(self) -> None:
        response = self.settle(self.second, component_ids=[self.component_pk])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(_consumed(self.component_pk))
        self.assertEqual(Reflection.objects.filter(rite__isnull=True).count(), 1)

    def test_component_order_is_preserved_in_the_resolved_list(self) -> None:
        extra = ItemInstanceFactory(holder_character_sheet=self.sheet)
        request = type("R", (), {"user": self.account})()
        serializer = SettlingRitePerformSerializer(
            data={
                "character_sheet_id": self.sheet.pk,
                "component_ids": [extra.pk, self.component_pk],
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            [item.pk for item in serializer.validated_data["components"]],
            [extra.pk, self.component_pk],
        )


class SettlingRiteTests(DriftCorrectionViewTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.reflect_disown_dread()

    def test_a_malformed_request_is_one_plain_detail_with_no_field_names(self) -> None:
        response = self.client.post(_RITE_URL, {"component_ids": "no"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.data), ["detail"])

    def test_another_accounts_character_is_a_404_and_nothing_moves(self) -> None:
        response = self.settle(self.other_sheet, component_ids=[self.other_item.pk])
        self.assertEqual(response.status_code, 404)
        self.assertFalse(_consumed(self.other_item.pk))

    def test_a_refusal_is_a_400_with_the_message_and_changes_nothing(self) -> None:
        response = self.settle(component_ids=[])
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)
        self.assertFalse(_consumed(self.component_pk))
        self.assertEqual(Reflection.objects.filter(rite__isnull=True).count(), 1)

    def test_the_reading_is_the_owners_alone(self) -> None:
        mine = self.client.get(_RITE_URL, {"character_sheet": self.sheet.pk})
        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertEqual(len(mine.data["reflections"]), 1)
        self.assertEqual([o["item_id"] for o in mine.data["offerings"]], [self.component_pk])
        theirs = self.client.get(_RITE_URL, {"character_sheet": self.other_sheet.pk})
        self.assertEqual(theirs.status_code, 404)

    def test_the_rite_spends_the_open_chance_the_pending_inbox_lists(self) -> None:
        response = self.settle()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.data["lines"],
            ["You disown your Drift Dread: 12 Drift Dread became 6 Drift Dawnlight."],
        )
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())
        ids = {row["id"] for row in self.client.get(_PENDING_URL).data["results"]}
        self.assertEqual(ids, set())
