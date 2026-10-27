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

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from integration_tests.harness import JourneyCase
from web.admin.tuning.required_content import (
    _probe_single_thread_resonance_ritual,
    _probe_thread_resonance_ritual,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.constants import GainSource, RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualFactory,
    ThreadFactory,
    ThreadRetuneRiteFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import CharacterAnima, ResonanceConversion, Thread
from world.magic.services.resonance import grant_resonance

PERFORM_URL = "/api/magic/rituals/perform/"
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

    def test_an_unknown_resonance_id_is_refused_plainly(self) -> None:
        told = strip_ansi(
            self.telnet(self.ysmay, f"ritual {RITE} thread={self.thread.pk} resonance=999999")
        )
        self.assertIn("No resonance with id 999999.", told)


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

    def test_the_options_list_where_the_thread_can_go_and_what_pays_for_it(self) -> None:
        candle = self.carry(self.ysmay, self.lumen, "Lumen Candle")
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/magic/threads/{self.thread.pk}/resonance-options/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["ritual_id"], self.rite.pk)
        shown = {
            option["resonance_name"]: (
                option["affinity_name"],
                option["conversion_type"],
                option["projected_points"],
                [(item["item_id"], item["mode"]) for item in option["qualifying"]],
            )
            for option in response.data["options"]
        }
        self.assertEqual(
            shown,
            {
                "Lumen": ("Celestial", None, 40, [(candle, "material")]),
                "Ruin": ("Abyssal", "FALL", 60, []),
                "Praedari": ("Primal", "FALL", 48, []),
            },
        )

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
