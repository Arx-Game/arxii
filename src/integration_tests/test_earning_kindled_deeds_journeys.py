"""Journeys for what an act pays and what it only suggests (#5124, #5327).

Mira is a played character on "The Overseers' Gate" mission with Tomas in the room. Her
Domination is kindled by the mission's theme (people held captive) for any option that
carries the theme, and an option whose theme names a resonance pays it at once, scaled by the
roll. Staff authored the strength rows (Faint earns half of a deed's award, Strong all of it)
and what a deed earns at each roll result: a Success earns 10.

Hand-worked numbers: a Success on a Faint-kindled option earns 10 x 50 / 100 = 5; on a
Strong-kindled option 10 x 100 / 100 = 10; a Partial Success has no award row and earns
nothing. Only Mira is told "You earned ..."; Tomas is told nothing.

Every other situation (a feeling she carries, someone in trouble, a Rally or a GM's
kindling) only suggests: the act is written down for her player to mark, with the resonance
the situation reached, and nothing is paid until a mark is made.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from integration_tests.harness import JourneyCase
from integration_tests.test_kindled_dig_deep_and_rally_journeys import _KindledField
from integration_tests.test_strike_journeys import SWORD_DAMAGE, _StrikeField
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentStatus, ParticipantStatus, SurgeTriggerKind
from world.combat.factories import CombatParticipantFactory, SocialManeuverConfigFactory
from world.combat.models import CombatOpponent
from world.combat.services import resolve_round
from world.combat.tests.test_mounted_combat import _equip_weapon
from world.conditions.factories import ConditionTemplateFactory
from world.covenants.perks.constants import Situation
from world.items.constants import GearArchetype
from world.magic.constants import GainSource, KindlingSource
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingFactory,
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
    RecordedAct,
    ResonanceGrant,
)
from world.magic.services.kindling import kindled_resonances_now
from world.mechanics.constants import EngagementType
from world.mechanics.factories import ChallengeApproachFactory, ChallengeTemplateFactory
from world.mechanics.services import begin_engagement
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
    MissionThemeFactory,
)
from world.missions.services.play import _kindled_feeds, beat_for
from world.missions.services.resolution import build_option_list, resolve_option
from world.missions.services.run import staff_assign_mission
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

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

    def theme_row(self, theme, strength: int, resonance=None, theme_text: str = ""):
        if theme_text:
            theme.player_text = theme_text
            theme.save(update_fields=["player_text"])
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
        # The grant records what she did, in the option's own title.
        self.assertEqual(grant.deed_label, "[check option 0]")
        self.assertEqual(self.balance(), 5)
        self.assertTold(self.mira, "You earned 5 Domination.")

    def test_a_better_roll_earns_more_of_the_same_resonance(self) -> None:
        great = CheckOutcomeFactory(name="Great Success", success_level=2)
        KindledDeedAwardFactory(outcome_tier=great, amount=25)
        self.theme_row(self.captives, strength=2)
        option = self.check_option(self.captives)
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=great,
            target_node=self.done,
            consequence=ConsequenceFactory(outcome_tier=great),
        )
        self.start()

        self.take(1, great)

        # 25 at a Strong strength (all of the award), against the Success's 10.
        self.assertEqual(self.deeds().get().amount, 25)
        self.assertTold(self.mira, "You earned 25 Domination.")

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


class TheTelnetBeat(_Gate):
    def test_the_telnet_beat_says_what_each_option_pays_at_once_and_never_an_amount(self) -> None:
        self.theme_row(self.captives, strength=2, theme_text="The captives are held here.")
        self.check_option(self.captives, order=0)
        self.check_option(order=1)
        self.start()

        told = self.telnet(self.mira, f"mission beat {self.mission.pk}")

        self.assertIn("Pays you Domination at once: The captives are held here.", told)
        self.assertEqual(told.count("at once"), 1)
        self.assertNotIn("kindled", told)


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


class AStrikeIsRecordedNotPaid(_StrikeField):
    """Hobb's Wrath is kindled by a feeling he carries; a Strike writes the act down with Wrath
    as a suggestion and pays nothing, because a situation only suggests (#5327)."""

    def setUp(self) -> None:
        super().setUp()
        self.watch(self.hobb)
        self.connect_telnet(self.hobb)
        KindledDeedAwardFactory(outcome_tier=CheckOutcome.objects.get(name="Success"), amount=10)
        self.faint = KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=50)
        self.wrath = ResonanceFactory(name="Wrath")
        # Wrath is kindled by a feeling he carries; any act feeds a feeling.
        kindle_resonance(self.sheet, self.wrath, self.faint)

    def test_a_strike_is_recorded_with_the_suggestion_and_pays_nothing(self) -> None:
        self.equip_sword()

        with self.captureOnCommitCallbacks(execute=True):
            self.strike_and_resolve("Success", "Success")

        # The act is written down in his own words, naming the opponent he struck.
        act = RecordedAct.objects.get(character_sheet=self.sheet)
        self.assertEqual((act.label, act.outcome.name), ("Struck Bandit", "Success"))
        suggestion = act.suggestions.get()
        self.assertEqual((suggestion.resonance, suggestion.strength), (self.wrath, self.faint))
        self.assertFalse(ResonanceGrant.objects.exists())
        self.assertNotTold(self.hobb, "You earned")
        # Her player reads the act and what the situation suggested for it.
        listed = self.telnet(self.hobb, "acts")
        self.assertIn(f"{act.pk}. Struck Bandit (", listed)
        self.assertIn("Wrath: You carry ", listed)


class AnOutcomeNoActOfHersWasAimedAt(_StrikeField):
    """Hobb's Abyssal Cruelty is kindled, and he stands in the fight while Tomas kills the bandit.

    Hobb declares nothing: the bandit's death is an outcome, not an act of his, so it earns him
    nothing and leaves no act of his to mark, however kindled his Cruelty is.
    """

    def setUp(self) -> None:
        super().setUp()
        self.watch(self.hobb)
        self.connect_telnet(self.hobb)
        KindledDeedAwardFactory(outcome_tier=CheckOutcome.objects.get(name="Success"), amount=10)
        faint = KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=50)
        abyssal = AffinityFactory(name="Abyssal")
        self.cruelty = ResonanceFactory(name="Cruelty", affinity=abyssal)
        kindle_resonance(self.sheet, self.cruelty, faint)
        self.assertEqual(
            [e.tier.name for e in kindled_resonances_now(self.sheet) if e.tier is not None],
            ["Faint"],
        )

        self.tomas = self.make_player("Tomas", room=self.steading)
        self.watch(self.tomas)
        CharacterVitals.objects.create(
            character_sheet=self.tomas.sheet_data, health=100, max_health=100, base_max_health=100
        )
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        begin_engagement(self.tomas, EngagementType.COMBAT, source=self.encounter)
        self.sword = _equip_weapon(
            self.tomas, archetype=GearArchetype.MELEE_ONE_HAND, damage=SWORD_DAMAGE
        )

    def test_a_captor_killed_by_someone_elses_strike_earns_the_kindled_bystander_nothing(
        self,
    ) -> None:
        self.bandit.health = 1
        self.bandit.save(update_fields=["health"])
        result = self.web(self.tomas, "combat_strike", opponent_id=self.bandit.pk)
        self.assertTrue(result.detail.success, result.detail.message)

        with self.captureOnCommitCallbacks(execute=True), self.forced_rolls("Success", "Success"):
            resolve_round(self.encounter)

        self.assertEqual(
            CombatOpponent.objects.get(pk=self.bandit.pk).status, OpponentStatus.DEFEATED
        )
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=self.sheet).exists())
        # Nor is there an act of his to point a mark at: the death was an outcome, not an act.
        self.assertFalse(RecordedAct.objects.filter(character_sheet=self.sheet).exists())
        self.assertNotTold(self.hobb, "You earned")
        self.assertEqual(
            CharacterResonance.objects.get(
                character_sheet=self.sheet, resonance=self.cruelty
            ).lifetime_earned,
            0,
        )


class WhatEarnsAndWhatIsPromised(_Gate):
    """Only authored situations earn, and an option promises what its act would pay."""

    def kindle_by_a_gm(self, strength: int) -> None:
        scene = SceneFactory(room=self.room)
        invalidate_active_scene_cache(self.room)
        KindlingFactory(
            character_sheet=self.sheet,
            resonance=self.domination,
            strength=strength,
            source=KindlingSource.GM,
            encounter=None,
            scene=scene,
        )

    def test_a_gm_kindling_alone_earns_nothing(self) -> None:
        self.kindle_by_a_gm(2)
        self.check_option(self.captives)
        self.start()

        self.take(1, self.success)

        self.assertFalse(self.deeds().exists())

    def test_a_gm_kindling_does_not_raise_the_share_or_the_promise(self) -> None:
        self.theme_row(self.captives, strength=1, theme_text="The captives are held here.")
        self.kindle_by_a_gm(2)
        self.check_option(self.captives)
        self.start()

        (feed,) = beat_for(self.mission, self.mira).options[0].feeds
        self.take(1, self.success)

        self.assertEqual(
            (feed.strength_name, feed.reason), ("Faint", "The captives are held here.")
        )
        self.assertEqual(self.deeds().get().amount, 5)  # the Faint share, not the GM's Strong

    def test_an_auto_succeeding_approach_earns_at_the_plainest_success_and_says_so(self) -> None:
        top = CheckOutcomeFactory(name="Critical", success_level=5)
        KindledDeedAwardFactory(outcome_tier=top, amount=99)
        self.theme_row(self.captives, strength=2)
        challenge = ChallengeTemplateFactory(name="The barred door", severity_level=0)
        approach = ChallengeApproachFactory(
            challenge_template=challenge,
            check_type=CheckTypeFactory(name="Walk through"),
            auto_succeeds=True,
            is_default=True,
        )
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.CHALLENGE,
            challenge=challenge,
        )
        option.themes.add(self.captives)
        MissionOptionRouteFactory(option=option, outcome_tier=top, target_node=self.done)
        self.start()
        participant = self.mission.participants.get(character=self.sheet)
        presented = next(
            p
            for p in build_option_list(self.mission, self.entry, participant)
            if p.approach == approach
        )

        (feed,) = _kindled_feeds(self.mission, [presented], self.mira)[0]
        resolve_option(self.mission, self.entry, option, participant, chosen_approach=approach)

        self.assertEqual((feed.resonance_name, feed.strength_name), ("Domination", "Strong"))
        self.assertEqual(self.deeds().get().amount, SUCCESS_AWARD)  # not the top tier's 99


class AnActForAnAllyInTroubleIsRecordedNotPaid(_KindledField):
    """Mira is badly hurt; Tomas holds Mercy, kindled whenever someone is in trouble, and
    Fury, kindled by a feeling he carries (any act feeds it). What Tomas does for her is
    written down with those resonances as suggestions, and pays nothing (#5327)."""

    def setUp(self) -> None:
        super().setUp()
        self.connect_telnet(self.mira)
        self.connect_telnet(self.tomas)
        great = CheckOutcomeFactory(name="Great Success", success_level=2)
        KindledDeedAwardFactory(outcome_tier=self.success, amount=10)
        KindledDeedAwardFactory(outcome_tier=great, amount=99)
        sheet = self.tomas.sheet_data
        mercy = ResonanceFactory(name="Mercy of Tomas")
        CharacterResonanceFactory(character_sheet=sheet, resonance=mercy)
        sheet.__dict__.pop("cached_resonances", None)
        self.trouble = KindlingSituationFactory(
            resonance=mercy, situation=Situation.SOMEONE_IN_TROUBLE, strength=1
        )
        self.mercy = mercy
        vitals = CharacterVitals.objects.get(character_sheet=self.mira.sheet_data)
        vitals.health = 10
        vitals.save(update_fields=["health"])

    def tomas_act(self) -> RecordedAct:
        return RecordedAct.objects.get(character_sheet=self.tomas.sheet_data)

    def assert_nothing_paid(self) -> None:
        self.assertFalse(ResonanceGrant.objects.exists())
        self.assertNotTold(self.tomas, "You earned")
        self.assertNotTold(self.mira, "You earned")

    def test_covering_an_ally_in_trouble_is_recorded_at_the_plainest_success(self) -> None:
        self.telnet(self.tomas, "combat cover Mira")

        self.resolve(self.success)

        act = self.tomas_act()
        # Cover rolls nothing: it is recorded at the lowest successful tier (so it is worth 10
        # when marked), never at the Great's 99.
        self.assertEqual(act.outcome, self.success)
        self.assertEqual({row.resonance for row in act.suggestions.all()}, {self.mercy})
        self.assert_nothing_paid()
        listed = self.telnet(self.tomas, "acts")
        self.assertIn(f"{act.pk}. Covered Mira (", listed)
        self.assertIn("Mercy of Tomas", listed)

    def test_a_rally_is_recorded_with_a_resonance_kindled_by_a_feeling_he_carries(self) -> None:
        SocialManeuverConfigFactory(
            rally_success_condition=ConditionTemplateFactory(name="Heartened")
        )
        self.author_tuning(SurgeTriggerKind.RALLIED, "Rally", partial=1, success=4)
        kindle_resonance(self.tomas.sheet_data, self.fury, self.faint)
        self.telnet(self.tomas, "combat rally Mira")

        self.resolve(self.success)

        act = self.tomas_act()
        self.assertEqual(act.outcome, self.success)
        self.assertIn(self.fury, {row.resonance for row in act.suggestions.all()})
        self.assert_nothing_paid()
        listed = self.telnet(self.tomas, "acts")
        self.assertIn(f"{act.pk}. Rallied Mira (", listed)
        self.assertIn("Fury", listed)

    def test_a_reaction_that_answers_for_an_ally_in_trouble_is_recorded(self) -> None:
        """Through the shared reaction spine (Succor, Interpose, Cover, catching a faller).

        The spine's two seams, which pick the reaction and roll the challenge, are the only
        doubles: the capability content that offers a real Succor or Interpose is PostgreSQL
        only. Deleting the spine's act hook turns this red.
        """
        from world.checks.types import CheckResult
        from world.mechanics.reactions import dispatch_capability_reaction
        from world.mechanics.types import ChallengeResolutionResult

        check = CheckResult(
            check_type=CheckTypeFactory(name="Guard"),
            outcome=self.success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        result = ChallengeResolutionResult(
            challenge_instance_id=0,
            challenge_name="Interpose",
            approach_name="Step in",
            check_result=check,
            consequence=None,
            applied_effects=[],
            resolution_type="",
            challenge_deactivated=False,
            display_consequences=[],
        )
        instance = SimpleNamespace(target_object_id=self.mira.pk)
        offered = SimpleNamespace(
            challenge_name="Interpose",
            resolved_challenge_instance=instance,
            resolved_challenge_approach=SimpleNamespace(),
            capability_source=SimpleNamespace(),
        )

        with (
            patch("world.mechanics.services.get_available_actions", return_value=[offered]),
            patch("world.mechanics.reactions._fresh_reaction_instance", return_value=instance),
            patch("world.mechanics.challenge_resolution.resolve_challenge", return_value=result),
            self.captureOnCommitCallbacks(execute=True),
        ):
            dispatch_capability_reaction(
                self.tomas,
                self.mira,
                challenge_name="Interpose",
                approach=None,
                error_msg="",
                outcome_fn=lambda _result: None,
            )

        act = self.tomas_act()
        self.assertEqual({row.resonance for row in act.suggestions.all()}, {self.mercy})
        self.assert_nothing_paid()
        listed = self.telnet(self.tomas, "acts")
        self.assertIn(f"{act.pk}. Interpose Mira (", listed)
        self.assertIn("Mercy of Tomas", listed)
