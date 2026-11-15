"""Journeys for earning a resonance by acting on a kindling situation (#5124).

Mira is a played character on "The Overseers' Gate" mission with Tomas in the room. Her
Domination is kindled by the mission's theme (people held captive) for any option that
carries the theme. Staff authored the strength rows (Faint earns half of a deed's award,
Strong all of it) and what a deed earns at each roll result: a Success earns 10.

Hand-worked numbers: a Success on a Faint-kindled option earns 10 x 50 / 100 = 5; on a
Strong-kindled option 10 x 100 / 100 = 10; a Partial Success has no award row and earns
nothing. Only Mira is told "You earned ..."; Tomas is told nothing.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from integration_tests.test_strike_journeys import _StrikeField
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.covenants.perks.constants import Situation
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
    kindle_resonance,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterResonance,
    DriftConversionOffer,
    KindlingSituation,
    ResonanceGrant,
)
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
    MissionThemeFactory,
)
from world.missions.services.run import staff_assign_mission
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome

SUCCESS_AWARD = 10


class _Gate(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Overseers' Gate")
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.watch(self.mira, self.tomas)
        self.connect_telnet(self.mira)
        self.connect_telnet(self.tomas)
        self.sheet = self.mira.sheet_data
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        KindledDeedAwardFactory(outcome_tier=self.success, amount=SUCCESS_AWARD)
        self.faint = KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=50)
        self.strong = KindledStrengthTierFactory(rank=2, name="Strong", earn_percent=100)
        self.domination = ResonanceFactory(name="Domination")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.domination)
        self.sheet.__dict__.pop("cached_resonances", None)
        self.captives = MissionThemeFactory(name="Held captive")
        self.mission_template = MissionTemplateFactory(name="Bar the door")
        self.entry = MissionNodeFactory(template=self.mission_template, key="entry", is_entry=True)
        self.done = MissionNodeFactory(template=self.mission_template, key="done")

    def theme_row(self, theme, strength: int, resonance=None):
        return KindlingSituationFactory(
            resonance=resonance or self.domination,
            situation=Situation.MISSION_THEME,
            mission_theme=theme,
            strength=strength,
        )

    def check_option(self, *themes, order: int = 0):
        option = MissionOptionFactory(
            node=self.entry,
            order=order,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name=f"Presence {order}"),
            authored_ic_framing=f"[check option {order}]",
        )
        option.themes.add(*themes)
        for outcome in (self.success, self.partial):
            MissionOptionRouteFactory(
                option=option,
                outcome_tier=outcome,
                target_node=self.done,
                consequence=ConsequenceFactory(outcome_tier=outcome),
            )
        return option

    def branch_option(self, *themes, order: int = 1):
        option = MissionOptionFactory(
            node=self.entry,
            order=order,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="[branch option]",
            branch_target=self.done,
        )
        option.themes.add(*themes)
        return option

    def take(self, number: int, outcome=None) -> str:
        """Mira takes option ``number`` of the beat, her roll forced to ``outcome``."""
        instance = self.mission
        with self.captureOnCommitCallbacks(execute=True):
            if outcome is None:
                return self.telnet(self.mira, f"mission resolve {instance.pk} {number}")
            with force_check_outcome(outcome):
                return self.telnet(self.mira, f"mission resolve {instance.pk} {number}")

    def start(self) -> None:
        self.mission = staff_assign_mission(self.mission_template, self.mira)

    def balance(self) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=self.sheet, resonance=self.domination
        ).first()
        return row.balance if row else 0

    def deeds(self):
        return ResonanceGrant.objects.filter(source=GainSource.KINDLED_DEED)


class EarningFromAMissionOption(_Gate):
    def test_a_themed_option_earns_the_resonance_scaled_by_award_and_strength(self) -> None:
        row = self.theme_row(self.captives, strength=1)
        self.check_option(self.captives)
        self.start()

        self.take(1, self.success)

        grant = self.deeds().get()
        self.assertEqual((grant.amount, grant.resonance), (5, self.domination))
        self.assertEqual(grant.source_kindling_situation, row)
        self.assertEqual(self.balance(), 5)
        self.assertTold(self.mira, "You earned 5 Domination.")

    def test_only_the_actor_is_told(self) -> None:
        self.theme_row(self.captives, strength=2)
        self.check_option(self.captives)
        self.start()

        self.take(1, self.success)

        self.assertTold(self.mira, "You earned 10 Domination.")
        self.assertNotTold(self.tomas, "You earned")

    def test_an_option_without_the_theme_earns_nothing(self) -> None:
        self.theme_row(self.captives, strength=2)
        self.check_option()
        self.start()

        self.take(1, self.success)

        self.assertFalse(self.deeds().exists())
        self.assertNotTold(self.mira, "You earned")

    def test_a_roll_result_with_no_award_row_earns_nothing(self) -> None:
        self.theme_row(self.captives, strength=2)
        self.check_option(self.captives)
        self.start()

        self.take(1, self.partial)

        self.assertFalse(self.deeds().exists())

    def test_an_outcome_with_no_act_earns_nothing(self) -> None:
        # A branch option rolls nothing: it is a choice, not a roll, so no deed is earned.
        self.theme_row(self.captives, strength=2)
        self.branch_option(self.captives, order=0)
        self.start()

        self.take(1)

        self.assertFalse(self.deeds().exists())

    def test_two_rows_feeding_one_resonance_earn_one_grant_at_the_strongest(self) -> None:
        other = MissionThemeFactory(name="Cowed overseers")
        self.theme_row(self.captives, strength=1)
        strongest = self.theme_row(other, strength=2)
        self.check_option(self.captives, other)
        self.start()

        self.take(1, self.success)

        grant = self.deeds().get()
        self.assertEqual((grant.amount, grant.source_kindling_situation), (10, strongest))

    def test_the_option_names_the_resonance_it_would_feed(self) -> None:
        from world.missions.services.play import beat_for

        self.theme_row(self.captives, strength=2)
        self.check_option(self.captives, order=0)
        self.check_option(order=1)
        self.start()

        options = beat_for(self.mission, self.mira).options

        self.assertEqual(
            [(feed.resonance_name, feed.strength_name) for feed in options[0].feeds],
            [("Domination", "Strong")],
        )
        self.assertEqual(options[1].feeds, ())


class ADeedOnTheMainAffinityOpensTheChanceToAtone(_Gate):
    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.celestial, _primal, self.abyssal = ensure_conversion_pairs()
        self.dawnlight = ResonanceFactory(name="Dawnlight", affinity=self.celestial)
        self.dread = ResonanceFactory(name="Dread", affinity=self.abyssal)
        SceneFactory(room=self.room)
        invalidate_active_scene_cache(self.room)
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="100", primal="0", abyssal="0")
        for resonance, lifetime in ((self.dawnlight, 170), (self.dread, 30)):
            CharacterResonance.objects.create(
                character_sheet=self.sheet,
                resonance=resonance,
                balance=0,
                lifetime_earned=lifetime,
            )
        self.sheet.__dict__.pop("cached_resonances", None)

    def test_a_kindled_deed_in_a_live_scene_opens_the_offer(self) -> None:
        self.theme_row(self.captives, strength=2, resonance=self.dawnlight)
        self.check_option(self.captives)
        self.start()

        self.take(1, self.success)

        self.assertEqual(self.deeds().get().resonance, self.dawnlight)
        self.assertEqual(DriftConversionOffer.objects.get().character_sheet, self.sheet)


class EarningFromACombatStrike(_StrikeField):
    """Hobb's Wrath is kindled by a feeling he carries; a Strike earns it."""

    def setUp(self) -> None:
        super().setUp()
        self.watch(self.hobb)
        self.connect_telnet(self.hobb)
        KindledDeedAwardFactory(outcome_tier=CheckOutcome.objects.get(name="Success"), amount=10)
        faint = KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=50)
        self.wrath = ResonanceFactory(name="Wrath")
        # Wrath is kindled by a feeling he carries; any act feeds a feeling.
        kindle_resonance(self.sheet, self.wrath, faint)
        self.row = KindlingSituation.objects.get(resonance=self.wrath)

    def test_a_strike_earns_the_kindled_resonance_scaled_by_its_hit_roll(self) -> None:
        self.equip_sword()

        with self.captureOnCommitCallbacks(execute=True):
            self.strike_and_resolve("Success", "Success")

        grant = ResonanceGrant.objects.get(source=GainSource.KINDLED_DEED)
        self.assertEqual((grant.amount, grant.resonance), (5, self.wrath))
        self.assertEqual(grant.source_kindling_situation, self.row)
        self.assertTold(self.hobb, "You earned 5 Wrath.")
