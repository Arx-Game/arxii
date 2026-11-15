"""Journeys for a resonance kindled by an opponent a thread is tied to (#5124).

Brannoc fights a bandit on "The Ford". The bandit is Overseer Kell, a person Brannoc's Wrath
thread is bonded to (a tie of tier 3). Staff authored one kindling situation on Wrath, "a
person a thread is tied to stands against you" (opponents only), and a strength row that the
bond's tier 3 reaches. That strength reads a pull 20 levels higher, lets a character give in
to depth 2 (the "Give in" step, not Unbound) and doubles a Dig deep surge.

Hand-worked numbers. A level-0 thread's perk of 3 reads at a multiplier of 1; the strength's
20 levels read it at a multiplier of 2, so 6. Giving in at "Give in" (depth 2, 8 control
surrendered) at a Success (75%): 8 x 1.5 x 1.2 = 14.4 full, floor(10.8) = 10 bought.
Dig deep: a Success band of 5 is 10 with the strength's 100% uplift.
"""

from __future__ import annotations

from django.urls import reverse

from integration_tests.test_dig_deep_journeys import SUCCESS_DIG_DEEP, _DigDeepField
from integration_tests.test_surrendering_control_to_fury_journeys import _AtTheFord
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import CombatOpponentFactory
from world.covenants.perks.constants import Situation
from world.magic.factories import (
    CharacterResonanceFactory,
    FuryTierFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import KindledStrengthTier, Kindling

PANEL = "/api/magic/kindled-resonances/"
GIVE_IN_SURRENDERS = 8


def tie_a_thread_to(owner_sheet, resonance, other_sheet, *, tier: int):
    """A thread of ``owner_sheet`` bonded to ``other_sheet`` with a tie of ``tier``."""
    thread = ThreadFactory(owner=owner_sheet, resonance=resonance, level=0, as_track_thread=True)
    side = thread.target_relationship
    side.target = other_sheet
    side.tier = tier
    side.save()
    return thread


class _OpponentBonded(_AtTheFord):
    """The Ford, with the bandit as Overseer Kell, whom Brannoc's Wrath thread is tied to."""

    def setUp(self) -> None:
        super().setUp()
        Kindling.objects.all().delete()
        blazing = KindledStrengthTier.objects.get(rank=3)
        blazing.min_bond_tier = 3
        blazing.pull_levels = 20
        blazing.save()
        self.kell = CharacterSheetFactory()
        # The bandit is Kell himself: a persona-backed opponent, not a throwaway.
        pool = self.bandit.threat_pool
        self.bandit.delete()
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter,
            name="Bandit",
            persona=self.kell.primary_persona,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet = self.brannoc.sheet_data
        self.thread = tie_a_thread_to(sheet, self.wrath, self.kell, tier=3)
        KindlingSituationFactory(
            resonance=self.wrath,
            situation=Situation.THREAD_ANCHOR_PRESENT,
            enemies_only=True,
            strength=None,
        )
        self.reason = f"{self.kell.character.db_key} stands against you here"


class SeeingTheBondKindleItAndDrawingOnIt(_OpponentBonded):
    def test_the_panel_reads_wrath_blazing_with_the_reason_on_the_web_and_telnet(self) -> None:
        response = self.api(self.account_of(self.brannoc)).get(
            PANEL, {"character_sheet": self.brannoc.sheet_data.pk}
        )

        rows = {row["name"]: row for row in response.json()["results"]}
        self.assertTrue(rows["Wrath"]["kindled"])
        self.assertEqual(rows["Wrath"]["strength_name"], "Blazing")
        self.assertEqual(rows["Wrath"]["reasons"], [self.reason])
        self.assertFalse(rows["Calm"]["kindled"])
        lines = self.telnet(self.brannoc, "resonances").splitlines()
        self.assertIn(f"  {self.reason}", lines)
        self.assertTrue(any("Wrath" in line and "Kindled, blazing" in line for line in lines))

    def test_paying_a_pull_with_it_reads_the_perk_at_the_larger_level(self) -> None:
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        ThreadPullEffectFactory(
            target_kind=self.thread.target_kind,
            resonance=self.wrath,
            tier=1,
            flat_bonus_amount=3,
        )

        response = self.api(self.account_of(self.brannoc)).post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.brannoc.sheet_data.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        (pulled,) = response.json()["per_thread"]
        options = {row["resonance_name"]: row for row in pulled["options"]}
        self.assertEqual(options["Wrath"]["kindled_strength"], "Blazing")
        # The perk is authored at 3; the blazing strength makes the same perk read 6.
        self.assertEqual([e["authored_value"] for e in options["Wrath"]["effects"]], [3])
        self.assertEqual([e["scaled_value"] for e in options["Wrath"]["effects"]], [6])
        self.assertIsNone(options["Calm"]["kindled_strength"])
        # The thread itself did not move, and no number of the strength is on the wire.
        self.assertEqual(options["Wrath"]["level_read"], 0)


class GivingInToTheBondedRage(_OpponentBonded):
    def setUp(self) -> None:
        super().setUp()
        self.give_in = FuryTierFactory(
            name="Give in", depth=2, control_surrendered=GIVE_IN_SURRENDERS
        )

    def declare_give_in(self, resonance_name: str) -> str:
        # A tier name with a space is typed with an underscore.
        return self.telnet(
            self.brannoc,
            f"cast {self.technique.name} at {self.bandit.name} givein={resonance_name}:Give_in",
        )

    def test_she_gives_in_up_to_give_in_and_the_trade_is_bought(self) -> None:
        self.declare_give_in("Wrath")

        casts = self.resolve_with("Success")

        engagement = self.engagement_now()
        self.assertEqual(engagement.control_modifier, -GIVE_IN_SURRENDERS)
        self.assertEqual(engagement.intensity_modifier, 10)
        self.assertEqual(casts, [20 + 10])

    def test_the_deeper_step_is_refused_and_so_is_a_resonance_the_bond_does_not_kindle(
        self,
    ) -> None:
        told = self.declare_fury(self.unbound)
        self.assertIn("Your Wrath is not kindled enough to give in as far as Unbound.", told)

        told = self.declare_give_in("Calm")
        self.assertIn("Your Calm is not kindled right now, so you cannot give in to it.", told)


class DiggingDeepOnTheBondedRage(_DigDeepField):
    """Mira's Fury thread is tied to the brigand she fights; the surge reads that bond."""

    def setUp(self) -> None:
        super().setUp()
        self.fury = ResonanceFactory(name="Fury")
        CharacterResonanceFactory(character_sheet=self.mira.sheet_data, resonance=self.fury)
        self.mira.sheet_data.__dict__.pop("cached_resonances", None)
        KindledStrengthTierFactory(rank=1, name="Faint", min_bond_tier=1)
        KindledStrengthTierFactory(
            rank=2, name="Blazing", min_bond_tier=3, dig_deep_scale_percent=100
        )
        brigand = CharacterSheetFactory()
        CombatOpponentFactory(encounter=self.encounter, persona=brigand.primary_persona)
        tie_a_thread_to(self.mira.sheet_data, self.fury, brigand, tier=3)
        KindlingSituationFactory(
            resonance=self.fury,
            situation=Situation.THREAD_ANCHOR_PRESENT,
            enemies_only=True,
            strength=None,
        )

    def test_a_blazing_bond_doubles_the_surge_and_names_the_resonance(self) -> None:
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            told = self.telnet(self.mira, "combat digdeep fury")

        self.assertIn("Your Fury is kindled, so the surge is larger.", told)
        self.assertEqual(self.intensity(self.mira), 2 * SUCCESS_DIG_DEEP)
        self.assertIn("Fury", self.records(SurgeTriggerKind.DUG_DEEP).latest("pk").cause)
