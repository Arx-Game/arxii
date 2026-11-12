"""Journeys: a vow holder chooses their own focus picks (#4929, slice 6 of #4844).

Ysmay holds the Quicksilver vow at vow level 20. She reads every pick her vow offers
by level from the sheet's endpoint and through ``vow picks``, chooses within each
level's budget from the web and through ``vow pick``, and is refused a pick over
budget, a pick above her level, and a pick she already chose. The expected numbers
come from the rules the covenants doc states: a pick's price is
``max(1, value x frequency / 10 - reductions)``, and a level's chosen picks may
cost no more than ``VowFocusPickConfig.budget_per_level`` (4 by default).

Imbuing her vow thread into a new level tells her how many points of new picks it
opened, on telnet and on the web; a joiner whose vow thread already stands at a
level is told the same on joining.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from integration_tests import test_vow_focus_picks_in_combat_journeys as combat_journeys
from integration_tests.harness import JourneyCase
from integration_tests.test_thread_level_cap_journeys import imbue_cost
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.classes.factories import CharacterClassFactory
from world.classes.services import set_primary_class_level
from world.covenants.constants import CovenantType, FocusPickLimitKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
    CovenantRoleFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
    engage_vow_with_thread,
)
from world.covenants.models import CharacterCovenantRole, CharacterVowFocusPick, VowFocusPick
from world.magic.constants import IMBUING_SERVICE_PATH, TargetKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CovenantInductionRitualFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    RitualFactory,
    ThreadFactory,
)
from world.magic.models import CharacterResonance, Thread, ThreadLevelUnlock

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

CHOOSE = "choose_vow_focus_pick"
CATALOG_URL = "/api/covenants/character-roles/vow-picks/"


class _VowHolderCase(JourneyCase):
    """Ysmay, in the Quicksilver covenant, holding its vow at vow level 20."""

    vow_level = 20

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Fencing Hall")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        self.covenant = CovenantFactory(name="The Quicksilver Hall")
        self.vow = CovenantRoleFactory(name="Quicksilver", covenant_type=CovenantType.DURANCE)
        self.membership = engage_vow_with_thread(
            self.sheet, self.vow, covenant=self.covenant, thread_level=self.vow_level
        )
        # Level 10: prices 2, 2 and 4. The Target limit met 5 times in 10 halves 4 to 2.
        self.flank = self.pick("Strike from the Flank", level=10, value=4)
        VowFocusPickLimitFactory(
            pick=self.flank,
            kind=FocusPickLimitKind.TARGET,
            frequency_tenths=5,
            description="an ally is engaging them",
        )
        self.recovery = self.pick("Quick Recovery", level=10, value=2)
        self.light = self.pick("Light on Your Feet", level=10, value=4)
        # Level 20: prices 3, 1 and 4.
        self.bleeding = self.pick("Bleeding Cut", level=20, value=3)
        self.feint = self.pick("Read the Feint", level=20, value=1)
        self.gap = self.pick("Through the Gap", level=20, value=4)
        # Level 30: above her vow level.
        self.stand = self.pick("Last Stand", level=30, value=2)

    def pick(self, name: str, *, level: int, value: int, role: object = None) -> VowFocusPick:
        return VowFocusPickFactory(
            covenant_role=role or self.vow, name=name, pick_level=level, value=value
        )

    def catalog(self, character: ObjectDB | None = None) -> list[dict]:
        character = character or self.ysmay
        response = self.api(self.account_of(character)).get(
            CATALOG_URL, {"character_sheet": character.sheet_data.pk}
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def level(catalog: dict, number: int) -> dict:
        return next(row for row in catalog["levels"] if row["level"] == number)

    @staticmethod
    def entry(level: dict, name: str) -> dict:
        return next(row for row in level["picks"] if row["name"] == name)

    def chosen_names(self) -> set[str]:
        return set(
            CharacterVowFocusPick.objects.filter(character_role=self.membership).values_list(
                "pick__name", flat=True
            )
        )


class ReadingTheCatalog(_VowHolderCase):
    def test_every_pick_by_level_with_the_locked_ones_saying_why(self) -> None:
        (quicksilver,) = self.catalog()

        self.assertEqual((quicksilver["vow"], quicksilver["vow_level"]), ("Quicksilver", 20))
        first, second, third = (self.level(quicksilver, n) for n in (10, 20, 30))
        self.assertEqual((first["is_open"], first["budget"], first["spent"]), (True, 4, 0))
        self.assertTrue(second["is_open"])
        self.assertFalse(third["is_open"])
        flank = self.entry(first, "Strike from the Flank")
        self.assertEqual(flank["price"], 2)
        self.assertEqual(
            flank["limits"], "Target limit: an ally is engaging them, met 5 times in 10"
        )
        self.assertTrue(flank["choosable"])
        self.assertEqual(self.entry(first, "Light on Your Feet")["limits"], "no limits")
        stand = self.entry(third, "Last Stand")
        self.assertEqual(stand["locked_reason"], "opens at vow level 30")
        self.assertFalse(stand["choosable"])

    def test_telnet_lists_the_same_catalog(self) -> None:
        told = self.telnet(self.ysmay, "vow picks")

        self.assertIn("Quicksilver|n, vow level 20.", told)
        self.assertIn("Level 10: 0 of 4.", told)
        self.assertIn("Strike from the Flank, 2 pts.", told)
        self.assertIn("Level 30: opens at vow level 30.", told)
        self.assertIn("Last Stand, 2 pts. |x(opens at vow level 30)|n", told)

    def test_another_account_cannot_read_her_catalog(self) -> None:
        hobb = self.make_player("Hobb", room=self.room)
        response = self.api(self.account_of(hobb)).get(
            CATALOG_URL, {"character_sheet": self.sheet.pk}
        )

        self.assertEqual(response.status_code, 404)

    def test_a_missing_or_malformed_sheet_id_is_refused(self) -> None:
        client = self.api(self.account_of(self.ysmay))

        for query in ({}, {"character_sheet": "abc"}, {"character_sheet": "\u00b2"}):
            with self.subTest(query=query):
                response = client.get(CATALOG_URL, query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": "character_sheet is required."})


class ChoosingWithinTheBudget(_VowHolderCase):
    def test_she_fills_level_one_and_the_next_pick_is_refused(self) -> None:
        taken = self.web(self.ysmay, CHOOSE, pick_id=self.flank.pk)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertEqual(taken.detail.message, "You take Strike from the Flank. Level 10: 2 of 4.")

        told = self.telnet(self.ysmay, "vow pick Quick Recovery")
        self.assertIn("You take Quick Recovery. Level 10: 4 of 4.", told)

        refused = self.web(self.ysmay, CHOOSE, pick_id=self.light.pk)
        self.assertFalse(refused.detail.success)
        self.assertEqual(
            refused.detail.message,
            "'Light on Your Feet' costs 4, and this character has already spent 4 of the "
            "4 points for level 10 picks.",
        )
        first = self.level(self.catalog()[0], 10)
        self.assertEqual(first["spent"], 4)
        self.assertEqual(
            self.entry(first, "Light on Your Feet")["locked_reason"], ("costs more than is left")
        )
        self.assertTrue(self.entry(first, "Quick Recovery")["chosen"])
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Quick Recovery"})

    def test_unspent_budget_waits_for_a_second_pick_at_the_same_level(self) -> None:
        self.telnet(self.ysmay, "vow pick bleeding cut")

        second = self.level(self.catalog()[0], 20)
        self.assertEqual((second["spent"], second["left"]), (3, 1))
        self.assertTrue(self.entry(second, "Read the Feint")["choosable"])
        self.assertEqual(
            self.entry(second, "Through the Gap")["locked_reason"], "costs more than is left"
        )

        told = self.telnet(self.ysmay, "vow pick Read the Feint")
        self.assertIn("You take Read the Feint. Level 20: 4 of 4.", told)
        self.assertEqual(self.chosen_names(), {"Bleeding Cut", "Read the Feint"})

    def test_a_pick_with_in_in_its_name_and_a_named_covenant(self) -> None:
        self.pick("Cut in Two", level=20, value=1)

        told = self.telnet(self.ysmay, "vow pick Cut in Two")
        self.assertIn("You take Cut in Two. Level 20: 1 of 4.", told)
        told = self.telnet(self.ysmay, "vow pick Bleeding Cut in The Quicksilver Hall")
        self.assertIn("You take Bleeding Cut. Level 20: 4 of 4.", told)

    def test_a_pick_above_her_level_or_chosen_twice_is_refused(self) -> None:
        above = self.web(self.ysmay, CHOOSE, pick_id=self.stand.pk)
        self.assertEqual(
            above.detail.message,
            "'Last Stand' is a level 30 pick, and this character's vow is at level 20.",
        )
        self.web(self.ysmay, CHOOSE, pick_id=self.flank.pk)
        again = self.telnet(self.ysmay, "vow pick Strike from the Flank")
        self.assertIn("You have already chosen Strike from the Flank.", again)
        missing = self.telnet(self.ysmay, "vow pick Dance of Knives")
        self.assertIn("Your vow offers no pick named Dance of Knives.", missing)
        self.assertEqual(self.chosen_names(), {"Strike from the Flank"})

    def test_another_vows_pick_cannot_be_named_from_the_wire(self) -> None:
        other = self.pick("Shield Wall", level=10, value=1, role=CovenantRoleFactory())

        refused = self.web(self.ysmay, CHOOSE, pick_id=other.pk)

        self.assertEqual(refused.detail.message, "Your vow offers no pick.")
        self.assertFalse(CharacterVowFocusPick.objects.filter(pick=other).exists())


class ASubRoleHoldersPicksInOnePlace(_VowHolderCase):
    def test_the_anchor_and_sub_role_picks_are_listed_and_choosable_together(self) -> None:
        sub_role = CovenantRoleFactory(
            name="Quicksilver Duelist", covenant_type=CovenantType.DURANCE, parent_role=self.vow
        )
        self.membership.covenant_role = sub_role
        self.membership.save(update_fields=["covenant_role"])
        self.pick("Riposte", level=10, value=1, role=sub_role)

        (catalog,) = self.catalog()
        self.assertEqual(catalog["vows"], ["Quicksilver", "Quicksilver Duelist"])
        first = self.level(catalog, 10)
        self.assertEqual(
            [(row["vow"], row["name"]) for row in first["picks"]],
            [
                ("Quicksilver", "Light on Your Feet"),
                ("Quicksilver", "Quick Recovery"),
                ("Quicksilver", "Strike from the Flank"),
                ("Quicksilver Duelist", "Riposte"),
            ],
        )
        told = self.telnet(self.ysmay, "vow pick Riposte")
        self.assertIn("You take Riposte. Level 10: 1 of 4.", told)
        # One budget per level for the membership, whichever vow's catalog a pick is from.
        told = self.telnet(self.ysmay, "vow pick Quick Recovery")
        self.assertIn("You take Quick Recovery. Level 10: 3 of 4.", told)
        first = self.level(self.catalog()[0], 10)
        self.assertEqual((first["spent"], first["left"]), (3, 1))
        self.assertEqual(
            self.entry(first, "Light on Your Feet")["locked_reason"], "costs more than is left"
        )

        listed = self.telnet(self.ysmay, "vow picks")
        level_one = listed[listed.index("Level 10: 3 of 4.") : listed.index("Level 20:")]
        self.assertLess(level_one.index(" Quicksilver:"), level_one.index("Strike from the Flank"))
        self.assertLess(
            level_one.index("Strike from the Flank"), level_one.index(" Quicksilver Duelist:")
        )
        self.assertLess(level_one.index(" Quicksilver Duelist:"), level_one.index("Riposte"))
        self.assertEqual(level_one.count("of 4."), 1)

    def test_a_holder_of_the_anchor_alone_sees_no_vow_headings(self) -> None:
        listed = self.telnet(self.ysmay, "vow picks")

        self.assertEqual(self.catalog()[0]["vows"], ["Quicksilver"])
        self.assertNotIn(" Quicksilver:", listed)


class ASecondaryOrLeftVowIsRefused(_VowHolderCase):
    def test_a_secondary_vow_gets_no_picks(self) -> None:
        other_covenant = CovenantFactory(name="The Ember Court")
        ember = CovenantRoleFactory(name="Ember", covenant_type=CovenantType.DURANCE)
        ember_pick = self.pick("Cinder Step", level=10, value=1, role=ember)
        engage_vow_with_thread(
            self.sheet, ember, covenant=other_covenant, thread_level=20, is_secondary=True
        )

        refused = self.web(self.ysmay, CHOOSE, pick_id=ember_pick.pk, covenant_id=other_covenant.pk)

        self.assertEqual(
            refused.detail.message,
            "This is a secondary vow, and a secondary vow gets no focus picks.",
        )
        self.assertEqual([row["vow"] for row in self.catalog()], ["Quicksilver"])

    def test_a_vow_she_has_left_offers_nothing(self) -> None:
        from django.utils import timezone

        self.membership.engaged = False
        self.membership.left_at = timezone.now()
        self.membership.save(update_fields=["engaged", "left_at"])

        refused = self.web(self.ysmay, CHOOSE, pick_id=self.flank.pk, covenant_id=self.covenant.pk)

        self.assertEqual(refused.detail.message, "You hold no vow in that covenant.")
        self.assertEqual(self.catalog(), [])
        self.assertIn("You hold no vow with focus picks.", self.telnet(self.ysmay, "vow picks"))


class AChosenPickCountsInAFight(combat_journeys.AFocusPickRidesOnlyItsChoosersHold):
    """The combat journey of #4806, with Ysmay choosing Binding Grip herself on the web."""

    def setUp(self) -> None:
        super().setUp()
        CharacterVowFocusPick.objects.filter(pick=self.grip).delete()
        chosen = self.web(self.ysmay, CHOOSE, pick_id=self.grip.pk)
        self.assertTrue(chosen.detail.success, chosen.detail.message)


class _ImbuingCase(JourneyCase):
    """Ysmay holds the Quicksilver vow with resonance to spend and the Rite of Imbuing known."""

    def setUp(self) -> None:
        super().setUp()
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.ritual = ImbuingRitualFactory()
        self.room = self.make_room("The Loom Room")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        set_primary_class_level(self.ysmay, CharacterClassFactory(), 5)
        CharacterAuraFactory(character=self.sheet)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance, balance=0)
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 500
        pool.maximum = 500
        pool.save()
        self.covenant = CovenantFactory(name="The Quicksilver Hall", level=5)
        self.vow = CovenantRoleFactory(name="Quicksilver", covenant_type=CovenantType.DURANCE)

    def vow_thread(self, level: int) -> Thread:
        engage_vow_with_thread(
            self.sheet,
            self.vow,
            covenant=self.covenant,
            thread_level=level,
            resonance=self.resonance,
        )
        return Thread.objects.get(owner=self.sheet, target_kind=TargetKind.COVENANT_ROLE)

    def ready(self, thread: Thread, start: int, end: int) -> int:
        """Pay the XP boundaries and fund the imbue from stored ``start`` to ``end``."""
        for boundary in range(10, end + 1, 10):
            ThreadLevelUnlock.objects.get_or_create(
                thread=thread, unlocked_level=boundary, defaults={"xp_spent": 0}
            )
        amount = imbue_cost(start, end)
        row = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        row.balance = amount
        row.save(update_fields=["balance"])
        return amount

    def imbue_by_telnet(self, thread: Thread, amount: int) -> str:
        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        return self.telnet(self.ysmay, f"imbue thread={thread.pk} amount={amount}")


class ImbuingOpensNewPicks(_ImbuingCase):
    def test_imbuing_the_vow_thread_into_level_twenty_says_so(self) -> None:
        thread = self.vow_thread(10)

        told = self.imbue_by_telnet(thread, self.ready(thread, 10, 20))

        thread.refresh_from_db()
        self.assertEqual(thread.level, 20)
        # The level the thread now stands at, never the climb of 10.
        self.assertIn(f"{thread.name} is now level 20.", told)
        self.assertIn("Vow level 20: 4 pts of new picks.", told)

    def test_an_imbue_within_a_pick_level_names_the_level_and_opens_no_picks(self) -> None:
        thread = self.vow_thread(10)

        told = self.imbue_by_telnet(thread, self.ready(thread, 10, 15))

        thread.refresh_from_db()
        self.assertEqual(thread.level, 15)
        self.assertIn(f"You complete the rite, imbuing {thread.name}.", told)
        # A climb says where the thread now stands, but 15 opens no pick level.
        self.assertIn(f"{thread.name} is now level 15.", told)
        self.assertNotIn("new picks", told)

    def test_the_web_finisher_says_so_and_names_the_level(self) -> None:
        thread = self.vow_thread(10)
        amount = self.ready(thread, 10, 20)

        response = self.api(self.account_of(self.ysmay)).post(
            "/api/magic/rituals/perform/",
            {
                "ritual_id": self.ritual.pk,
                "character_sheet_id": self.sheet.pk,
                "kwargs": {"thread_id": thread.pk, "amount": amount},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Vow level 20: 4 pts of new picks.", response.json()["message"])
        self.assertIn(f"{thread.name} is now level 20.", response.json()["message"])
        self.assertEqual(response.json()["opened_pick_levels"], [20])
        self.assertEqual(response.json()["new_picks"], [{"level": 20, "points": 4}])

    def test_a_service_imbuing_rite_says_so_on_telnet_and_the_web(self) -> None:
        """A staff-authored SERVICE variant of the rite carries the same line on both."""
        quick = RitualFactory(name="Quick Imbuing", service_function_path=IMBUING_SERVICE_PATH)
        thread = self.vow_thread(10)

        told = self.telnet(
            self.ysmay,
            f"ritual Quick Imbuing thread={thread.pk} amount={self.ready(thread, 10, 15)}",
        )
        self.assertNotIn("new picks", told)
        response = self.api(self.account_of(self.ysmay)).post(
            "/api/magic/rituals/perform/",
            {
                "ritual_id": quick.pk,
                "character_sheet_id": self.sheet.pk,
                "kwargs": {"thread_id": thread.pk, "amount": self.ready(thread, 15, 20)},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Vow level 20: 4 pts of new picks.", response.json()["message"])
        self.assertEqual(response.json()["opened_pick_levels"], [20])
        self.assertEqual(response.json()["new_picks"], [{"level": 20, "points": 4}])

        told = self.telnet(
            self.ysmay,
            f"ritual Quick Imbuing thread={thread.pk} amount={self.ready(thread, 20, 30)}",
        )
        self.assertIn("Vow level 30: 4 pts of new picks.", told)

    def test_imbuing_past_level_thirty_opens_nothing_more(self) -> None:
        thread = self.vow_thread(30)

        told = self.imbue_by_telnet(thread, self.ready(thread, 30, 40))

        thread.refresh_from_db()
        self.assertEqual(thread.level, 40)
        self.assertNotIn("new picks", told)

    def test_a_thread_on_anything_else_opens_nothing(self) -> None:
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=10,
            developed_points=0,
            _trait_value=200,
        )

        told = self.imbue_by_telnet(thread, self.ready(thread, 10, 20))

        thread.refresh_from_db()
        self.assertEqual(thread.level, 20)
        self.assertNotIn("new picks", told)


class JoiningWithAVowAlreadyWoven(JourneyCase):
    """Wren inducts Ysmay into the Silver Circle as a Warden through the induction rite."""

    def setUp(self) -> None:
        super().setUp()
        CovenantInductionRitualFactory()
        self.room = self.make_room("The Silver Hall")
        self.wren = self.make_player("Wren", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.covenant = CovenantFactory(name="Silver Circle", covenant_type=CovenantType.DURANCE)
        elder = CovenantManagerRankFactory(covenant=self.covenant, name="Elder", can_invite=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.wren.sheet_data,
            covenant=self.covenant,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            rank=elder,
        )
        self.warden = CovenantRoleFactory(name="Warden", covenant_type=CovenantType.DURANCE)
        self.connect_telnet(self.ysmay)

    def induct(self) -> None:
        from world.magic.models.sessions import RitualSession

        self.telnet(
            self.wren, "ritual draft Covenant Induction invite=Ysmay covenant=Silver Circle"
        )
        session = RitualSession.objects.get()
        self.telnet(self.ysmay, f"ritual join {session.pk} role=Warden")
        # The joining line is sent once the rite's transaction commits.
        with self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.wren, f"ritual fire {session.pk}")
        self.assertTrue(
            CharacterCovenantRole.objects.filter(
                character_sheet=self.ysmay.sheet_data, covenant_role=self.warden
            ).exists()
        )

    def test_a_joiner_whose_thread_stands_at_level_twenty_is_told_both_levels(self) -> None:
        ThreadFactory(
            owner=self.ysmay.sheet_data,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=self.warden,
            level=20,
        )

        self.induct()

        self.assertTold(self.ysmay, "Vow level 10: 4 pts of new picks.")
        self.assertTold(self.ysmay, "Vow level 20: 4 pts of new picks.")

    def test_a_fresh_joiner_is_told_nothing_of_picks(self) -> None:
        self.induct()

        self.assertNotTold(self.ysmay, "new picks")
