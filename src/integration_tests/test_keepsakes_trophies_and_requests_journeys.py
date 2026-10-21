"""Journeys for keepsakes, trophies and the items a being asks for (#4530, slice 4 of #4462).

Wenna worships the Highwind and keeps a frayed climbing rope. She declares it a keepsake of a
deed, then of the being, and the rope counts for nothing until its wait has passed and never
by her words. A mission hands her a lantern that becomes a trophy of the deed it was won on.
Ysmay worships Ombrin, whose pledge asks for a weathervane pin: she tracks one down and gives
it up, and the roll it eased cannot botch. Every step goes through the real commands
(`keepsake`, `invoke`, `look`, `pledge`, `sacrifice`), the mission reward router and the
Being Service builder, and reads back the rows and what the players were told.
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.ceremonies.models import CeremonyOffering
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.constants import KeepsakeSubject, MeaningSignalKind
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, Keepsake
from world.items.services.meaning import item_meaning
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import MissionDeedRecordFactory, MissionDeedRewardLineFactory
from world.missions.services.rewards import apply_deed_rewards
from world.societies.factories import LegendEntryFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.answer_services import sacrifice_detail
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    PledgeFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import Relic, RequestedItem, WorshipDeclaration

WORDS = "My brother held the other end, and neither of us let go. [player-written]"


def _carry(holder, name: str, *, days: int, value: int = 1) -> ItemInstance:
    """An item called ``name`` in ``holder``'s hands, held ``days`` days. Bought: it has no
    history of its own, so whatever it comes to mean is what the journey gives it."""
    obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.objects.Object")
    obj.db_location = holder
    obj.save(update_fields=["db_location"])
    return ItemInstanceFactory(
        template=ItemTemplateFactory(name=name, value=value),
        game_object=obj,
        holder_character_sheet=holder.sheet_data,
        held_since=timezone.now() - timedelta(days=days),
    )


def _wait_passed(keepsake: Keepsake, days: int = 15) -> None:
    keepsake.created_at = timezone.now() - timedelta(days=days)
    keepsake.save(update_fields=["created_at"])


class KeepingWhatMatters(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.cliff = self.make_room("The Cliff Shrine")
        profile = RoomProfileFactory(objectdb=self.cliff)
        self.wenna = self.make_player("Wenna", room=self.cliff)
        self.watch(self.wenna)
        self.sheet = self.wenna.sheet_data
        self.highwind = WorshippedBeingFactory(name="Highwind", resonance_pool=0)
        ShrineDetailsFactory(feature_instance__room_profile=profile, being=self.highwind)
        WorshipDeclaration.objects.create(character_sheet=self.sheet, public_being=self.highwind)
        DevotionStandingFactory(character_sheet=self.sheet, being=self.highwind, favor=20)
        config = get_devotion_config()
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.SACRIFICE, outcome_tier=self.success, amount=4
        )
        self.deed = LegendEntryFactory(
            persona=self.sheet.primary_persona, title="Cliff rescue", base_value=20
        )
        self.rope = _carry(self.wenna, "frayed climbing rope", days=60)

    def _keepsake(self) -> Keepsake:
        return Keepsake.objects.get(item_instance=self.rope)

    def _points(self, **kwargs) -> int:
        item = ItemInstance.objects.get(pk=self.rope.pk)
        return item_meaning(item, self.sheet, config=get_devotion_config(), **kwargs).points

    def test_a_keepsake_of_a_deed_counts_after_the_wait_and_never_by_her_words(self) -> None:
        told = self.telnet(
            self.wenna, f"keepsake frayed climbing rope = deed Cliff rescue ; {WORDS}"
        )

        self.assertIn("You keep frayed climbing rope as a keepsake of the deed Cliff rescue.", told)
        self.assertEqual(self._keepsake().text, WORDS)
        listed = self.telnet(self.wenna, "keepsake")
        self.assertIn("1 of 5 kept", listed)
        self.assertIn("stands for the deed Cliff rescue (counts in 14 days)", listed)
        self.assertEqual(self._points(), 0)

        _wait_passed(self._keepsake())

        # The deed's legend 20 over ten, plus one: 3. Carried joins now there is a signal.
        self.assertEqual(self._points(), 3 + 1)
        self.assertIn("counts now", self.telnet(self.wenna, "keepsake"))
        # A longer, different story is worth exactly the same.
        keepsake = self._keepsake()
        keepsake.text = "A far longer story. " * 25
        keepsake.save(update_fields=["text"])
        self.assertEqual(self._points(), 3 + 1)

    def test_a_keepsake_of_the_being_she_carries_eases_her_call(self) -> None:
        self.telnet(self.wenna, f"keepsake frayed climbing rope = being Highwind ; {WORDS}")

        waiting = self.telnet(self.wenna, "invoke Highwind")
        self.assertIn(
            "Kept: frayed climbing rope (a keepsake of Highwind): not counting yet", waiting
        )
        self.assertNotIn("What you wear or carry", waiting)

        _wait_passed(self._keepsake())

        told = self.telnet(self.wenna, "invoke Highwind")
        # 1 for the subject and 2 because it is the being: 3 points, 3 ease a point.
        self.assertIn(
            "Kept: frayed climbing rope (a keepsake of Highwind): 3 points x 3 = eased 9", told
        )
        self.assertIn("What you wear or carry: frayed climbing rope", told)
        self.assertNotIn(WORDS, told)

        self.assertIn(
            "no longer keep", self.telnet(self.wenna, "keepsake/release frayed climbing rope")
        )
        self.assertNotIn("Kept:", self.telnet(self.wenna, "invoke Highwind"))
        self.assertFalse(Keepsake.objects.exists())

    def test_the_relic_she_carries_eases_by_the_points_staff_set(self) -> None:
        Relic.objects.create(being=self.highwind, item_instance=self.rope, invocation_points=2)

        told = self.telnet(self.wenna, "invoke Highwind")

        self.assertIn(
            "Relic: frayed climbing rope (a relic of Highwind): 2 points x 3 = eased 6", told
        )

    def test_she_keeps_only_so_many_and_the_refusals_are_told_in_words(self) -> None:
        for number in range(5):
            item = _carry(self.wenna, f"token {number}", days=20)
            told = self.telnet(
                self.wenna, f"keepsake token {number} = place the harbor ; [player words]"
            )
            self.assertIn("as a keepsake of the harbor", told)
            self.assertTrue(Keepsake.objects.filter(item_instance=item).exists())

        sixth = self.telnet(
            self.wenna, "keepsake frayed climbing rope = place the harbor ; [player words]"
        )
        self.assertIn("You keep 5 keepsakes already; release one first.", sixth)
        self.assertIn(
            "You have no 'Nobody' to keep it for.",
            self.telnet(self.wenna, "keepsake token 0 = being Nobody ; [words]"),
        )
        self.assertIn(
            "Usage: keepsake", self.telnet(self.wenna, "keepsake token 0 = harbor ; [words]")
        )
        self.assertEqual(Keepsake.objects.count(), 5)

    def test_examine_shows_her_words_only_when_she_chose_to_show_them(self) -> None:
        self.telnet(self.wenna, f"keepsake frayed climbing rope = place the harbor ; {WORDS}")
        self.assertNotIn(WORDS, self.telnet(self.wenna, "look frayed climbing rope"))

        self.telnet(self.wenna, "keepsake/release frayed climbing rope")
        self.telnet(self.wenna, f"keepsake/show frayed climbing rope = place the harbor ; {WORDS}")
        looked = self.telnet(self.wenna, "look frayed climbing rope")

        self.assertIn(f"Kept as a keepsake by Wenna: {WORDS}", looked)

    def test_giving_a_keepsake_up_keeps_what_it_stood_for_and_not_her_words(self) -> None:
        self.telnet(self.wenna, f"keepsake frayed climbing rope = being Highwind ; {WORDS}")
        _wait_passed(self._keepsake())

        with force_check_outcome(self.success):
            told = self.telnet(self.wenna, "sacrifice frayed climbing rope")

        self.assertIn("keepsake 1", told)
        self.assertIn("keepsake match 2", told)
        self.assertNotIn(WORDS, told)
        offering = CeremonyOffering.objects.get()
        self.assertEqual(
            {s.kind for s in offering.signals.all()},
            {
                MeaningSignalKind.CARRIED,
                MeaningSignalKind.KEEPSAKE,
                MeaningSignalKind.KEEPSAKE_MATCH,
            },
        )
        detail = sacrifice_detail(offering)
        self.assertNotIn(WORDS, repr(detail))
        self.assertIsNotNone(ItemInstance.objects.get(pk=self.rope.pk).destroyed_at)

    def test_the_item_panel_reads_its_keepsake_and_the_deeds_it_is_a_trophy_of(self) -> None:
        self.rope.legend_deeds.add(self.deed)
        self.telnet(self.wenna, f"keepsake frayed climbing rope = deed Cliff rescue ; {WORDS}")
        client = self.api(self.account_of(self.wenna))

        response = client.get(f"/api/items/inventory/{self.rope.pk}/keepsake/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["keepsake"]["subject_name"], "the deed Cliff rescue")
        self.assertEqual(body["keepsake"]["text"], WORDS)
        self.assertEqual(body["trophy_of"], ["Cliff rescue"])
        self.assertEqual((body["status"]["used"], body["status"]["limit"]), (1, 5))
        self.assertEqual([row["label"] for row in body["subjects"]["deed"]], ["Cliff rescue"])
        self.assertEqual(
            self.api(self.account_of(self.wenna))
            .get("/api/items/inventory/999999/keepsake/")
            .status_code,
            404,
        )

    def test_the_web_form_keeps_and_lets_go_through_the_same_actions(self) -> None:
        kept = self.web(
            self.wenna,
            "keepsake_declare",
            item_id=self.rope.pk,
            subject_kind=KeepsakeSubject.DEED,
            subject_id=self.deed.pk,
            text=WORDS,
            shown_on_examine=True,
        )
        self.assertTrue(kept.detail.success, kept.detail.message)
        self.assertEqual(self._keepsake().subject_deed, self.deed)
        stranger = self.web(
            self.wenna, "keepsake_declare", item_id=self.rope.pk, subject_kind="place", text="x"
        )
        self.assertFalse(stranger.detail.success)

        let_go = self.web(self.wenna, "keepsake_release", item_id=self.rope.pk)

        self.assertTrue(let_go.detail.success, let_go.detail.message)
        self.assertFalse(Keepsake.objects.exists())


class WinningATrophy(JourneyCase):
    """A mission hands Wenna a lantern on a win; it is a trophy of the deed, and the item
    she is handed on a Partial Success is not."""

    def setUp(self) -> None:
        super().setUp()
        self.camp = self.make_room("The Camp")
        RoomProfileFactory(objectdb=self.camp)
        self.wenna = self.make_player("Wenna", room=self.camp)
        self.watch(self.wenna)
        self.sheet = self.wenna.sheet_data
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)

    def _win(self, outcome, name: str):
        deed = MissionDeedRecordFactory(actor=self.sheet, outcome=outcome)
        deed.legend_entries.add(
            LegendEntryFactory(
                persona=self.sheet.primary_persona, title="The gorge crossing", base_value=30
            )
        )
        MissionDeedRewardLineFactory(
            deed=deed,
            recipient=self.sheet,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            item_template=ItemTemplateFactory(name=name, value=5),
        )
        apply_deed_rewards(deed)
        return ItemInstance.objects.get(template__name=name)

    def test_a_win_makes_the_reward_a_trophy_she_can_examine_and_it_counts_by_the_deed(
        self,
    ) -> None:
        lantern = self._win(self.success, "brass lantern")

        looked = self.telnet(self.wenna, "look brass lantern")

        self.assertIn("Trophy of The gorge crossing.", looked)
        meaning = item_meaning(lantern, self.sheet, config=get_devotion_config())
        # Earned by risk: no carry gate. 1 plus legend 30 over ten, at most 4.
        self.assertEqual({s.kind: s.points for s in meaning.signals}, {MeaningSignalKind.TROPHY: 4})

    def test_a_partial_success_hands_the_item_over_with_no_deed_to_link(self) -> None:
        lantern = self._win(self.partial, "tin lantern")

        self.assertFalse(lantern.legend_deeds.exists())
        self.assertEqual(item_meaning(lantern, self.sheet, config=get_devotion_config()).points, 0)


class WhatTheBeingAsksFor(JourneyCase):
    """Ombrin's pledge asks for a weathervane pin. Staff write the request on the Being
    Service builder; Ysmay takes the pledge, tracks a pin down and gives it up."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Shrine of Ombrin")
        profile = RoomProfileFactory(objectdb=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.watch(self.ysmay)
        self.sheet = self.ysmay.sheet_data
        self.ombrin = WorshippedBeingFactory(name="Ombrin", resonance_pool=100)
        ShrineDetailsFactory(feature_instance__room_profile=profile, being=self.ombrin)
        WorshipDeclaration.objects.create(character_sheet=self.sheet, public_being=self.ombrin)
        self.pledge = PledgeFactory(being=self.ombrin, name="Keep the lamp", favor_target=20)
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        self.botch = CheckOutcomeFactory(name="Critical Failure", success_level=-2)
        config = get_devotion_config()
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.SACRIFICE, outcome_tier=self.success, amount=4
        )
        self.pin_template = ItemTemplateFactory(name="weathervane pin", value=2)

    def _staff_writes_the_request(self) -> RequestedItem:
        from evennia_extensions.models import PlayerData
        from world.contributors.factories import ContentContributorFactory

        staff = AccountDB.objects.create_superuser("bsauthor", "bs@example.com", "pw-123456")
        PlayerData.objects.create(account=staff, contributor=ContentContributorFactory(name="W"))
        self.client.force_login(staff)
        prefix = {
            "TOTAL_FORMS": "0",
            "INITIAL_FORMS": "0",
            "MIN_NUM_FORMS": "0",
            "MAX_NUM_FORMS": "1000",
        }
        data = {
            f"{name}-{key}": value
            for name in ("resonances", "facets")
            for key, value in prefix.items()
        }
        data.update(
            {
                "pledges-TOTAL_FORMS": "1",
                "pledges-INITIAL_FORMS": "1",
                "pledges-MIN_NUM_FORMS": "0",
                "pledges-MAX_NUM_FORMS": "1000",
                "pledges-0-id": str(self.pledge.pk),
                "pledges-0-being": str(self.ombrin.pk),
                "pledges-0-name": self.pledge.name,
                "pledges-0-description": "",
                "pledges-0-favor_target": "20",
                "pledges-0-span_weeks": "2",
                "pledges-0-closing_rite": str(self.pledge.closing_rite_id),
                "pledges-0-is_active": "on",
                "requests-TOTAL_FORMS": "1",
                "requests-INITIAL_FORMS": "0",
                "requests-MIN_NUM_FORMS": "0",
                "requests-MAX_NUM_FORMS": "1000",
                "requests-0-target": f"pledge:{self.pledge.pk}",
                "requests-0-item_template": str(self.pin_template.pk),
                "requests-0-facet": "",
                "requests-0-quantity": "1",
                "requests-0-points": "3",
                "requests-0-hint": "[staff-authored hint]",
            }
        )
        response = self.client.post(reverse("admin_being_service", args=[self.ombrin.pk]), data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:1500])
        return RequestedItem.objects.get()

    def test_staff_ask_the_pledge_taker_tracks_it_down_and_the_roll_it_eased_cannot_botch(
        self,
    ) -> None:
        request = self._staff_writes_the_request()
        self.telnet(self.ysmay, "pledge Ombrin/Keep the lamp")
        card = self.telnet(self.ysmay, "pledge")
        self.assertIn("Ombrin asks for:", card)
        self.assertIn(
            "weathervane pin: 0 of 1 given, 3 points each, at the pledge ([staff-authored hint])",
            card,
        )
        pin = _carry(self.ysmay, "weathervane pin", days=1, value=2)
        pin.template = self.pin_template
        pin.save(update_fields=["template"])

        with force_check_outcome(self.botch) as capture:
            told = self.telnet(self.ysmay, "sacrifice weathervane pin")

        self.assertIn("requested 3", told)
        self.assertIn("asked for: weathervane pin", told)
        self.assertIsNotNone(capture.check_type)
        offering = CeremonyOffering.objects.get()
        self.assertEqual(offering.outcome_tier, self.failure)  # a Critical Failure lands as Failure
        (signal,) = offering.signals.all()
        self.assertEqual(
            (signal.kind, signal.requested_item), (MeaningSignalKind.REQUESTED, request)
        )
        after = self.telnet(self.ysmay, "pledge")
        self.assertIn("weathervane pin: 1 of 1 given", after)

    def test_the_same_pin_when_nothing_asked_for_it_is_given_up_for_nothing(self) -> None:
        self.telnet(self.ysmay, "pledge Ombrin/Keep the lamp")
        pin = _carry(self.ysmay, "weathervane pin", days=1, value=2)

        with force_check_outcome(self.success) as capture:
            told = self.telnet(self.ysmay, "sacrifice weathervane pin")

        self.assertIn("No meaning points: given up, no roll, no favor", told)
        self.assertIsNone(capture.check_type)
        self.assertIsNotNone(ItemInstance.objects.get(pk=pin.pk).destroyed_at)
