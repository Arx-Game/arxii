"""Journeys through moving a thread to another resonance (slice 6 of #4672).

Ysmay is a Celestial character with a thread on Bene (Celestial), anchored to a trait, holding
40 developed points. Staff have authored the retune rite: a SERVICE ritual found by its service
path, whose offering must tie to the resonance the thread moves to.

The pair rates are the ones ``ensure_conversion_pairs`` authors (the production values):
Celestial -> Primal is a Fall at 1.20, Celestial -> Abyssal a Fall at 1.50, Abyssal ->
Celestial a Redemption at 0.50. Expected numbers are worked out by hand from those rows:

* Within Celestial (Bene -> Lumen) the 40 points stay 40.
* Bene -> Praedari (Primal) is a Fall: int(40 x 1.20) = 48.
* Bene -> Ruin (Abyssal) is a Fall: int(40 x 1.50) = 60.
* A 1-point Ruin thread redeemed to Bene: int(1 x 0.50) = 0, floored to 1.
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from integration_tests.harness import JourneyCase
from web.admin.tuning.required_content import (
    _probe_single_thread_resonance_ritual,
    _probe_thread_resonance_ritual,
    _probe_thread_resonance_ritual_web_payable,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.constants import GainSource, RitualExecutionKind, SanctumSlotKind, TargetKind
from world.magic.exceptions import ThreadAnchorTakenError
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualFactory,
    SignatureMotifBonusFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadRetuneRiteFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import (
    CharacterAnima,
    CharacterResonance,
    FallRedemptionRecord,
    ResonanceConversion,
    RitualComponentRequirement,
    SanctumDetails,
    SanctumOwnerMode,
    Thread,
)
from world.magic.services import conversion
from world.magic.services.resonance import grant_resonance
from world.magic.services.thread_resonance import (
    NO_RITE_MESSAGE,
    SANCTUM_THREAD_MESSAGE,
    SIGNATURE_THREAD_MESSAGE,
)
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

PERFORM_URL = "/api/magic/rituals/perform/"
OPTIONS_URL = "/api/magic/threads/{}/resonance-options/"
RITE = "Rite of Retuning"
NO_THREAD = "You have no active thread with that id."


def consumed(pk: int) -> bool:
    """Whether the offered item is used up. Takes the pk: a delete clears ``item.pk``."""
    row = ItemInstance.objects.filter(pk=pk).values("destroyed_at", "quantity").first()
    return row is None or row["destroyed_at"] is not None or row["quantity"] <= 0


def stored(thread: Thread) -> dict:
    """The thread's row as the database holds it (the identity map may lag)."""
    return Thread.objects.filter(pk=thread.pk).values(
        "resonance_id", "developed_points", "level", "retired_at"
    )[0]


class ThreadRetuneCase(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        self.bene = ResonanceFactory(name="Bene", affinity=self.celestial)
        self.lumen = ResonanceFactory(name="Lumen", affinity=self.celestial)
        self.praedari = ResonanceFactory(name="Praedari", affinity=self.primal)
        self.sylvan = ResonanceFactory(name="Sylvan", affinity=self.primal)
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        for source, target_affinity, target in (
            (self.bene, self.primal, self.praedari),
            (self.bene, self.abyssal, self.ruin),
            (self.ruin, self.celestial, self.bene),
        ):
            ResonanceConversion.objects.create(
                source_resonance=source, target_affinity=target_affinity, target_resonance=target
            )
        self.rite = ThreadRetuneRiteFactory()

        self.room = self.make_room("The Loom Hall")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.sheet = self.ysmay.sheet_data
        for character in (self.ysmay, self.hobb):
            set_aura_split(
                CharacterAuraFactory(character=character.sheet_data),
                celestial="80",
                primal="10",
                abyssal="10",
            )
        self.thread = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=40)

    def carry(self, character, resonance, name: str) -> int:
        """Put an item tied to ``resonance`` in ``character``'s hands; return its pk."""
        template = ItemTemplateFactory(
            name=name, tied_resonance=resonance, resonance_tier=ResonanceTierFactory()
        )
        item = ItemInstanceFactory(template=template, holder_character_sheet=character.sheet_data)
        materialize_item_game_object(item, character.sheet_data)
        return item.pk

    def retune(self, thread: Thread, resonance=None, character=None) -> str:
        line = f"ritual {RITE} thread={thread.pk}"
        if resonance is not None:
            line += f" resonance={resonance.pk}"
        return strip_ansi(self.telnet(character or self.ysmay, line))


class RetuningAtTheKeyboard(ThreadRetuneCase):
    def test_a_retune_within_her_affinity_keeps_every_point(self) -> None:
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(self.thread, self.lumen)
        trait = self.thread.target_trait.name
        self.assertIn(
            f"You perform {RITE}. Your {trait} thread left Bene and now channels Lumen "
            "(40 points, now 40).",
            told,
        )
        row = stored(self.thread)
        self.assertEqual(row["resonance_id"], self.lumen.pk)
        self.assertEqual(row["developed_points"], 40)
        self.assertIsNone(row["retired_at"])
        self.assertTrue(consumed(candle))

    def test_a_fall_converts_her_points_at_the_pair_rate(self) -> None:
        fang = self.carry(self.ysmay, self.praedari, "Praedari Fang")
        self.thread.name = "Mercy of the Healer"
        self.thread.save(update_fields=["name"])
        told = self.retune(self.thread, self.praedari)
        self.assertIn(
            "Mercy of the Healer left Bene and now channels Praedari (40 points, now 48).", told
        )
        row = stored(self.thread)
        self.assertEqual(row["resonance_id"], self.praedari.pk)
        self.assertEqual(row["developed_points"], 48)
        self.assertTrue(consumed(fang))

    def test_a_redemption_shrinks_a_thread_but_never_empties_it(self) -> None:
        thin = ThreadFactory(owner=self.sheet, resonance=self.ruin, developed_points=1)
        self.carry(self.ysmay, self.bene, "Bene Lamp")
        self.retune(thin, self.bene)
        row = stored(thin)
        self.assertEqual(row["resonance_id"], self.bene.pk)
        self.assertEqual(row["developed_points"], 1)

    def test_moving_onto_a_thread_she_already_holds_there_merges_the_two(self) -> None:
        held = ThreadFactory(
            owner=self.sheet,
            resonance=self.lumen,
            target_trait=self.thread.target_trait,
            developed_points=10,
        )
        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(self.thread, self.lumen)
        self.assertIn(
            f"Your {self.thread.target_trait.name} thread left Bene and merged into your Lumen "
            "thread on the same anchor: its 40 points brought 40, and that thread now holds 50.",
            told,
        )
        self.assertEqual(stored(held)["developed_points"], 50)
        source = stored(self.thread)
        self.assertIsNotNone(source["retired_at"])
        self.assertEqual(source["resonance_id"], self.bene.pk)

    def test_a_merged_thread_can_move_back_onto_the_place_the_retired_one_left(self) -> None:
        # The merge leaves the old Bene thread retired on the same trait. A retired thread
        # holds no place, so the survivor can move to Bene.
        held = ThreadFactory(
            owner=self.sheet,
            resonance=self.lumen,
            target_trait=self.thread.target_trait,
            developed_points=10,
        )
        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        self.retune(self.thread, self.lumen)
        lamp = self.carry(self.ysmay, self.bene, "Bene Lamp")
        told = self.retune(held, self.bene)
        self.assertIn(f"You perform {RITE}.", told)
        self.assertEqual(stored(held)["resonance_id"], self.bene.pk)
        self.assertEqual(stored(held)["developed_points"], 50)
        self.assertIsNone(stored(held)["retired_at"])
        self.assertTrue(consumed(lamp))

    def test_naming_no_resonance_lists_where_the_thread_can_go(self) -> None:
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(self.thread)
        self.assertIn("Name the resonance to move it to: resonance=<id>.", told)
        self.assertIn(
            f"It can move to: Lumen ({self.lumen.pk}, same affinity), "
            f"Ruin ({self.ruin.pk}, Fall), Praedari ({self.praedari.pk}, Fall).",
            told,
        )
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)
        self.assertFalse(consumed(candle))

    def test_a_resonance_the_thread_cannot_reach_is_refused_and_nothing_is_spent(self) -> None:
        # Sylvan is Primal, but Bene's Primal counterpart is Praedari: no route to Sylvan.
        moss = self.carry(self.ysmay, self.sylvan, "Sylvan Moss")
        told = self.retune(self.thread, self.sylvan)
        self.assertIn("This thread cannot move to Sylvan.", told)
        self.assertFalse(consumed(moss))
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)
        self.assertEqual(stored(self.thread)["developed_points"], 40)

    def test_its_own_resonance_is_not_a_target(self) -> None:
        told = self.retune(self.thread, self.bene)
        self.assertIn("This thread cannot move to Bene.", told)

    def test_an_offering_that_does_not_count_is_refused(self) -> None:
        moss = self.carry(self.ysmay, self.sylvan, "Sylvan Moss")
        told = self.retune(self.thread, self.lumen)
        self.assertIn(f"Ritual '{RITE}' requires 1x offering for Lumen", told)
        self.assertFalse(consumed(moss))
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)

    def test_another_characters_thread_is_refused(self) -> None:
        hers = ThreadFactory(owner=self.hobb.sheet_data, resonance=self.bene, developed_points=9)
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(hers, self.lumen)
        self.assertIn(NO_THREAD, told)
        self.assertEqual(stored(hers)["resonance_id"], self.bene.pk)
        self.assertFalse(consumed(candle))

    def test_a_resonance_that_is_not_a_number_is_refused_plainly(self) -> None:
        told = strip_ansi(
            self.telnet(self.ysmay, f"ritual {RITE} thread={self.thread.pk} resonance=abc")
        )
        self.assertIn("Ritual parameter 'resonance' must be a number.", told)
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)

    def test_a_refused_retune_leaves_her_anima_and_a_good_one_spends_it(self) -> None:
        self.rite.anima_requirement = 4
        self.rite.save(update_fields=["anima_requirement"])
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)

        def anima() -> int:
            return CharacterAnima.objects.filter(character=self.sheet).values_list(
                "current", flat=True
            )[0]

        self.carry(self.ysmay, self.sylvan, "Sylvan Moss")
        told = self.retune(self.thread, self.sylvan)
        self.assertIn("This thread cannot move to Sylvan.", told)
        self.assertEqual(anima(), 10)

        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(self.thread, self.lumen)
        self.assertIn(f"You perform {RITE}.", told)
        self.assertEqual(anima(), 6)

    def test_naming_no_thread_tells_her_what_to_type(self) -> None:
        told = strip_ansi(self.telnet(self.ysmay, f"ritual {RITE} resonance={self.lumen.pk}"))
        self.assertIn("Name the thread to move: thread=<id>.", told)

    def test_an_unknown_resonance_id_is_refused_plainly(self) -> None:
        told = strip_ansi(
            self.telnet(self.ysmay, f"ritual {RITE} thread={self.thread.pk} resonance=999999")
        )
        self.assertIn("No resonance with id 999999.", told)


class ARetuneRefusedAfterItsOfferingIsSpent(ThreadRetuneCase):
    """The rite spends its offering and anima, then the re-anchor is refused (#4735).

    Another process wove a live Lumen thread on the same trait after the lookup ran: the
    lookup misses it (patched to, as that race does), the unique index refuses the move, and
    the whole perform rolls back. The offering must still be in her hands, in the database
    and in every later read in this process, so the next retune can pay with it.
    """

    def refused_then_retried(self, candle: int) -> None:
        held = ThreadFactory(
            owner=self.sheet,
            resonance=self.lumen,
            target_trait=self.thread.target_trait,
            developed_points=3,
        )
        with mock.patch(
            "world.magic.services.conversion._find_existing_target_thread", return_value=None
        ):
            told = self.retune(self.thread, self.lumen)

        self.assertIn(ThreadAnchorTakenError.user_message, told)
        row = ItemInstance.objects.filter(pk=candle).values("quantity", "destroyed_at")[0]
        self.assertEqual(row, {"quantity": 1, "destroyed_at": None})
        cached = ItemInstance.objects.get(pk=candle)
        self.assertEqual(cached.quantity, 1)
        self.assertIsNone(cached.destroyed_at)
        self.assertEqual(cached.holder_character_sheet_id, self.sheet.pk)
        self.assertIn("Lumen Candle", strip_ansi(self.telnet(self.ysmay, "inventory")))
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)

        # The lookup finds the Lumen thread now: the retune merges into it, paying with the
        # same candle the refused one spent and gave back.
        told = self.retune(self.thread, self.lumen)
        self.assertIn(f"You perform {RITE}.", told)
        self.assertEqual(stored(held)["developed_points"], 43)
        self.assertTrue(consumed(candle))
        self.assertNotIn("Lumen Candle", strip_ansi(self.telnet(self.ysmay, "inventory")))

    def test_a_plain_offering_is_given_back_and_pays_for_the_next_retune(self) -> None:
        # A template-identical candle: consuming it hard-deletes the row and its game object.
        self.rite.anima_requirement = 4
        self.rite.save(update_fields=["anima_requirement"])
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")

        self.refused_then_retried(candle)

        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 6)

    def test_the_anima_a_refused_retune_channelled_is_hers_again(self) -> None:
        self.rite.anima_requirement = 4
        self.rite.save(update_fields=["anima_requirement"])
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        ThreadFactory(
            owner=self.sheet,
            resonance=self.lumen,
            target_trait=self.thread.target_trait,
            developed_points=3,
        )
        with mock.patch(
            "world.magic.services.conversion._find_existing_target_thread", return_value=None
        ):
            self.retune(self.thread, self.lumen)

        # The row as stored, then the identity-mapped object every later read gets.
        stored_anima = CharacterAnima.objects.filter(character=self.sheet).values("current")[0]
        self.assertEqual(stored_anima["current"], 10)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 10)

    def test_a_named_offering_is_given_back_and_pays_for_the_next_retune(self) -> None:
        # A candle with a name of its own is kept on consumption: soft-deleted, its game
        # object taken out of play rather than deleted.
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        item = ItemInstance.objects.get(pk=candle)
        item.custom_name = "Lumen Candle"
        item.save(update_fields=["custom_name"])
        self.assertTrue(item.differs_from_template)

        self.refused_then_retried(candle)

        self.assertIsNotNone(ItemInstance.objects.get(pk=candle).destroyed_at)


class RetuningThroughTheWebClient(ThreadRetuneCase):
    def post(self, character, data: dict):
        return self.api(self.account_of(character)).post(PERFORM_URL, data, format="json")

    def perform(self, thread: Thread, resonance, components: list[int]):
        return self.post(
            self.ysmay,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.rite.pk,
                "kwargs": {"thread_id": thread.pk, "target_resonance": resonance.pk},
                "components": components,
            },
        )

    def test_the_spellbook_retunes_a_thread_through_the_ritual_endpoint(self) -> None:
        fang = self.carry(self.ysmay, self.ruin, "Ruin Shard")
        response = self.perform(self.thread, self.ruin, [fang])
        self.assertEqual(response.status_code, 200, response.content)
        result = response.data["result"]
        self.assertEqual(result["thread_id"], self.thread.pk)
        self.assertEqual(result["to_resonance_id"], self.ruin.pk)
        self.assertEqual(result["points_after"], 60)
        self.assertEqual(result["conversion_type"], "FALL")
        self.assertFalse(result["merged"])
        self.assertEqual(response.data["message"], f"You perform {RITE}. {result['message']}")
        self.assertIn("left Bene and now channels Ruin (40 points, now 60).", result["message"])
        self.assertEqual(stored(self.thread)["developed_points"], 60)
        self.assertTrue(consumed(fang))

    def test_the_web_client_is_refused_a_target_and_spends_nothing(self) -> None:
        moss = self.carry(self.ysmay, self.sylvan, "Sylvan Moss")
        response = self.perform(self.thread, self.sylvan, [moss])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("This thread cannot move to Sylvan.", response.data["detail"])
        self.assertFalse(consumed(moss))

    def test_ids_that_are_not_numbers_are_a_plain_400(self) -> None:
        for kwargs, detail in (
            (
                {"thread_id": self.thread.pk, "target_resonance": "abc"},
                "No resonance with id abc.",
            ),
            (
                {"thread_id": "abc", "target_resonance": self.lumen.pk},
                "You have no active thread with that id.",
            ),
            ({"thread_id": True, "target_resonance": self.lumen.pk}, NO_THREAD),
        ):
            with self.subTest(kwargs=kwargs):
                response = self.post(
                    self.ysmay,
                    {
                        "character_sheet_id": self.sheet.pk,
                        "ritual_id": self.rite.pk,
                        "kwargs": kwargs,
                    },
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.data["detail"], detail)
        # A list is not a primitive: the request serializer refuses it before the resolver.
        response = self.post(
            self.ysmay,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.rite.pk,
                "kwargs": {"thread_id": self.thread.pk, "target_resonance": [1]},
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(stored(self.thread)["resonance_id"], self.bene.pk)

    def test_the_web_client_is_refused_another_characters_thread(self) -> None:
        hers = ThreadFactory(owner=self.hobb.sheet_data, resonance=self.bene, developed_points=9)
        response = self.perform(hers, self.lumen, [])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(stored(hers)["resonance_id"], self.bene.pk)

    def options(self, thread: Thread):
        response = self.api(self.account_of(self.ysmay)).get(OPTIONS_URL.format(thread.pk))
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_the_options_list_where_the_thread_can_go_and_what_pays_for_it(self) -> None:
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        held = ThreadFactory(
            owner=self.sheet,
            resonance=self.ruin,
            target_trait=self.thread.target_trait,
            developed_points=5,
        )
        data = self.options(self.thread)
        self.assertEqual(data["ritual_id"], self.rite.pk)
        self.assertTrue(data["offering_required"])
        self.assertEqual(data["offering_count"], 1)
        self.assertEqual(data["unavailable_reason"], "")
        shown = {
            option["resonance_name"]: (
                option["affinity_name"],
                option["conversion_type"],
                option["projected_points"],
                option["merges_into_thread_id"],
                [(item["item_id"], item["mode"]) for item in option["qualifying"]],
            )
            for option in data["options"]
        }
        self.assertEqual(
            shown,
            {
                "Lumen": ("Celestial", None, 40, None, [(candle, "material")]),
                "Ruin": ("Abyssal", "FALL", 60, held.pk, []),
                "Praedari": ("Primal", "FALL", 48, None, []),
            },
        )

    def test_a_rite_that_asks_no_offering_lists_none_to_pick(self) -> None:
        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        self.rite.requirements.all().delete()
        data = self.options(self.thread)
        self.assertFalse(data["offering_required"])
        self.assertEqual(data["offering_count"], 0)
        self.assertEqual([o["qualifying"] for o in data["options"]], [[], [], []])
        response = self.perform(self.thread, self.lumen, [])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(stored(self.thread)["resonance_id"], self.lumen.pk)

    def test_a_rite_asking_two_offerings_says_so(self) -> None:
        for requirement in self.rite.requirements.all():
            requirement.quantity = 2
            requirement.save(update_fields=["quantity"])
        data = self.options(self.thread)
        self.assertTrue(data["offering_required"])
        self.assertEqual(data["offering_count"], 2)

    def test_with_no_rite_the_options_say_why(self) -> None:
        self.rite.delete()
        data = self.options(self.thread)
        self.assertIsNone(data["ritual_id"])
        self.assertEqual(data["options"], [])
        self.assertEqual(data["unavailable_reason"], NO_RITE_MESSAGE)

    def test_a_missing_target_is_refused_without_telnet_syntax(self) -> None:
        response = self.post(
            self.ysmay,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.rite.pk,
                "kwargs": {"thread_id": self.thread.pk},
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.data["detail"],
            "Name the resonance to move it to. It can move to: Lumen (same affinity), "
            "Ruin (Fall), Praedari (Fall).",
        )

    def test_a_merge_returns_the_thread_that_survives(self) -> None:
        held = ThreadFactory(
            owner=self.sheet,
            resonance=self.lumen,
            target_trait=self.thread.target_trait,
            developed_points=10,
        )
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        response = self.perform(self.thread, self.lumen, [candle])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["result"]["merged"])
        self.assertEqual(response.data["result"]["thread_id"], held.pk)

    def test_the_options_cost_the_same_queries_however_many_there_are(self) -> None:
        for requirement in self.rite.requirements.all():
            requirement.min_item_meaning = 1
            requirement.save(update_fields=["min_item_meaning"])
        self.carry(self.ysmay, self.lumen, "Lumen Candle")
        self.carry(self.ysmay, self.ruin, "Ruin Shard")
        client = self.api(self.account_of(self.ysmay))
        url = f"/api/magic/threads/{self.thread.pk}/resonance-options/"
        # Warm the per-process caches (pair rates, devotion config, session) first.
        client.get(url)
        client.get(url)
        with CaptureQueriesContext(connection) as three:
            response = client.get(url)
        self.assertEqual(len(response.data["options"]), 3)

        for name in ("Aurum", "Candor", "Dulcis", "Fides"):
            ResonanceFactory(name=name, affinity=self.celestial)
        with self.assertNumQueries(len(three.captured_queries)):
            response = client.get(url)
        self.assertEqual(len(response.data["options"]), 7)

    def test_the_options_of_another_characters_thread_are_hidden(self) -> None:
        hers = ThreadFactory(owner=self.hobb.sheet_data, resonance=self.bene, developed_points=9)
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/magic/threads/{hers.pk}/resonance-options/"
        )
        self.assertEqual(response.status_code, 404, response.content)


class TheRiteOnTheRequiredContentDashboard(ThreadRetuneCase):
    def test_the_dashboard_lists_the_rite_until_staff_author_it(self) -> None:
        self.assertTrue(_probe_thread_resonance_ritual().present)
        self.rite.delete()
        result = _probe_thread_resonance_ritual()
        self.assertFalse(result.present)
        self.assertIn("No ritual changes a thread's resonance", result.detail)
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/magic/threads/{self.thread.pk}/resonance-options/"
        )
        self.assertIsNone(response.data["ritual_id"])


class TheDashboardFlagsARiteTheWebCannotPay(ThreadRetuneCase):
    def test_a_template_component_on_the_rite_is_listed(self) -> None:
        self.assertTrue(_probe_thread_resonance_ritual_web_payable().present)
        RitualComponentRequirement.objects.create(
            ritual=self.rite, item_template=ItemTemplateFactory(name="Tuning Fork"), quantity=1
        )
        result = _probe_thread_resonance_ritual_web_payable()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, (RITE,))


class AnchorsThatHoldAResonance(ThreadRetuneCase):
    """Gift, sanctum and signed technique threads follow the rules weaving set for them."""

    def options(self, thread: Thread):
        response = self.api(self.account_of(self.ysmay)).get(OPTIONS_URL.format(thread.pk))
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_a_gift_thread_moves_only_within_its_gifts_resonances(self) -> None:
        gift = GiftFactory(name="Gift of the Long Dark")
        gift.resonances.add(self.bene, self.ruin)
        woven = ThreadFactory(
            owner=self.sheet,
            resonance=self.bene,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=gift,
            developed_points=20,
        )
        data = self.options(woven)
        self.assertEqual([o["resonance_name"] for o in data["options"]], ["Ruin"])

        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        told = self.retune(woven, self.lumen)
        self.assertIn("This thread cannot move to Lumen. It can move to: Ruin (Fall).", told)
        self.assertFalse(consumed(candle))
        self.assertEqual(stored(woven)["resonance_id"], self.bene.pk)

        shard = self.carry(self.ysmay, self.ruin, "Ruin Shard")
        self.assertIn(f"You perform {RITE}.", self.retune(woven, self.ruin))
        self.assertEqual(stored(woven)["resonance_id"], self.ruin.pk)
        self.assertTrue(consumed(shard))

    def test_a_gift_that_names_no_resonance_does_not_narrow_the_options(self) -> None:
        woven = ThreadFactory(
            owner=self.sheet,
            resonance=self.bene,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=GiftFactory(name="Gift of Open Hands"),
            developed_points=20,
        )
        self.assertEqual(len(self.options(woven)["options"]), 3)

    def test_a_sanctum_thread_is_sent_to_the_ritual_of_purging(self) -> None:
        sanctum = SanctumDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=RoomFeatureKindFactory(), level=2
            ),
            resonance_type=self.bene,
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        woven = ThreadFactory(
            owner=self.sheet,
            resonance=self.bene,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            developed_points=20,
        )
        data = self.options(woven)
        self.assertEqual(data["options"], [])
        self.assertEqual(data["unavailable_reason"], SANCTUM_THREAD_MESSAGE)
        self.assertIn("Ritual of Purging", SANCTUM_THREAD_MESSAGE)

        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        self.assertIn(SANCTUM_THREAD_MESSAGE, self.retune(woven, self.lumen))
        self.assertIn(SANCTUM_THREAD_MESSAGE, self.retune(woven))
        self.assertFalse(consumed(candle))
        self.assertEqual(stored(woven)["resonance_id"], self.bene.pk)

    def test_a_signed_technique_thread_moves_once_the_signature_is_cleared(self) -> None:
        technique = TechniqueFactory(name="Dawnstrike")
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        woven = ThreadFactory(
            owner=self.sheet,
            resonance=self.bene,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
            signature_bonus=SignatureMotifBonusFactory(required_resonance=self.bene),
            developed_points=20,
        )
        self.assertEqual(self.options(woven)["unavailable_reason"], SIGNATURE_THREAD_MESSAGE)
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        self.assertIn(SIGNATURE_THREAD_MESSAGE, self.retune(woven, self.lumen))
        self.assertFalse(consumed(candle))

        self.telnet(self.ysmay, "signature clear technique=Dawnstrike")
        self.assertIn(f"You perform {RITE}.", self.retune(woven, self.lumen))
        self.assertEqual(stored(woven)["resonance_id"], self.lumen.pk)


class TheDashboardFlagsASecondRetuneRite(ThreadRetuneCase):
    def test_a_second_rite_on_the_retune_path_is_listed(self) -> None:
        self.assertTrue(_probe_single_thread_resonance_ritual().present)
        ThreadRetuneRiteFactory(name="Rite of Second Tuning")
        result = _probe_single_thread_resonance_ritual()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Rite of Second Tuning",))
        self.assertIn(f"the Spellbook offers only {RITE}", result.detail)


class AFallAfterAMergeReanchorsOntoTheRetiredPlace(JourneyCase):
    """The full Fall re-anchors every thread; a retired thread in the target holds no place."""

    def test_the_fall_moves_her_thread_where_a_retired_one_sits(self) -> None:
        celestial, primal, _abyssal = ensure_conversion_pairs()
        bene = ResonanceFactory(name="Bene", affinity=celestial)
        praedari = ResonanceFactory(name="Praedari", affinity=primal)
        ResonanceConversion.objects.create(
            source_resonance=bene, target_affinity=primal, target_resonance=praedari
        )
        RitualFactory(
            name="Ritual of Falling",
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.fall_redemption.perform_fall",
        )
        room = self.make_room("The Threshold")
        ysmay = self.make_player("Ysmay", room=room)
        sheet = ysmay.sheet_data
        set_aura_split(
            CharacterAuraFactory(character=sheet), celestial="50", primal="45", abyssal="5"
        )
        grant_resonance(sheet, bene, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, praedari, 100, source=GainSource.STAFF_GRANT)
        live = ThreadFactory(owner=sheet, resonance=bene, developed_points=10)
        retired = ThreadFactory(
            owner=sheet,
            resonance=praedari,
            target_trait=live.target_trait,
            developed_points=5,
            retired_at=timezone.now(),
        )

        told = self.telnet(ysmay, f"ritual Ritual of Falling target_affinity={primal.pk}")

        self.assertIn("You perform Ritual of Falling.", told)
        row = stored(live)
        self.assertEqual(row["resonance_id"], praedari.pk)
        # Celestial -> Primal is a Fall at 1.20: int(10 x 1.20) = 12.
        self.assertEqual(row["developed_points"], 12)
        self.assertIsNone(row["retired_at"])
        self.assertEqual(stored(retired)["developed_points"], 5)


class AFallRefusedPartWayLeavesHerThreadsWhereTheyWere(JourneyCase):
    """The full Fall re-anchors her threads one by one; the second is refused (#4735).

    Another process wove a live Praedari thread on the second thread's trait just before it
    moved: the unique index refuses, and the whole Fall rolls back. The thread that moved
    first and the resonance balances the Fall zeroed must read back as stored, in memory too.
    """

    def test_the_thread_that_moved_first_is_back_on_bene(self) -> None:
        celestial, primal, _abyssal = ensure_conversion_pairs()
        bene = ResonanceFactory(name="Bene", affinity=celestial)
        praedari = ResonanceFactory(name="Praedari", affinity=primal)
        ResonanceConversion.objects.create(
            source_resonance=bene, target_affinity=primal, target_resonance=praedari
        )
        RitualFactory(
            name="Ritual of Falling",
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.fall_redemption.perform_fall",
        )
        room = self.make_room("The Threshold")
        ysmay = self.make_player("Ysmay", room=room)
        sheet = ysmay.sheet_data
        set_aura_split(
            CharacterAuraFactory(character=sheet), celestial="50", primal="45", abyssal="5"
        )
        grant_resonance(sheet, bene, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, praedari, 100, source=GainSource.STAFF_GRANT)
        first = ThreadFactory(owner=sheet, resonance=bene, developed_points=10)
        second = ThreadFactory(owner=sheet, resonance=bene, developed_points=20)

        real_reanchor = conversion._reanchor_thread
        moved: list[int] = []

        def the_second_collides(thread: Thread, target_resonance_id: int, new_points: int):
            moved.append(thread.pk)
            if len(moved) == 2:
                ThreadFactory(
                    owner=sheet,
                    resonance=praedari,
                    target_trait=thread.target_trait,
                    developed_points=1,
                )
            return real_reanchor(thread, target_resonance_id, new_points)

        with (
            mock.patch.object(conversion, "_find_existing_target_thread", return_value=None),
            mock.patch.object(conversion, "_reanchor_thread", side_effect=the_second_collides),
        ):
            told = self.telnet(ysmay, f"ritual Ritual of Falling target_affinity={primal.pk}")

        self.assertIn(ThreadAnchorTakenError.user_message, told)
        self.assertEqual(len(moved), 2)
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=sheet).exists())
        for thread, points in ((first, 10), (second, 20)):
            self.assertEqual(stored(thread)["resonance_id"], bene.pk)
            cached = Thread.objects.get(pk=thread.pk)
            self.assertEqual(cached.resonance_id, bene.pk)
            self.assertEqual(cached.resonance, bene)
            self.assertEqual(cached.developed_points, points)
        self.assertEqual(
            sorted(t.pk for t in ysmay.threads.all() if t.resonance_id == bene.pk),
            sorted([first.pk, second.pk]),
        )
        for resonance in (bene, praedari):
            self.assertEqual(
                CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance).balance,
                100,
            )

        # Nothing in the way now: the same Fall goes through from the stored state.
        told = self.telnet(ysmay, f"ritual Ritual of Falling target_affinity={primal.pk}")
        self.assertIn("You perform Ritual of Falling.", told)
        self.assertEqual(stored(first)["developed_points"], 12)
        self.assertEqual(stored(second)["developed_points"], 24)
