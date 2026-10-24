"""Journeys for cover, the waiting strike and grounding (#4608, slice 3 of #4576).

The steading is five positions in a row, Lane - Barn - Yard - Hall - Tower, joined by open
edges. The Barn has a roof. Hobb fights there or at the Yard's edge; enemies are spawned from
bestiary entries the way staff spawn them (``spawn_from_creature_template`` with a position).

- A roof stops every strike between the air and the Barn, both ways, though the air above
  the Barn is joined to it. A hawk over the Barn cannot strike Hobb in it; with two hops it
  lands in the Yard beside the Barn and bites from there. Hobb's lunge at a hawk over the
  Barn is refused. A flying archer comes down to shoot.
- A screened Yard: an archer across the room cannot shoot into it and walks closer; an
  archer beside it shoots.
- Hobb waits for an opening (``combat await Lunge``, or the web action). A wolf that
  attacks him takes his strike first; a wolf that walks into reach takes it on arrival and
  it is not repeated on its bite; a second wolf draws nothing; a wolf his strike drops is
  stopped before striking; an assassin that strikes and blinks away is answered first; a
  round where nothing comes says so and costs nothing.
- A hawk whose bite knocks fliers down grounds Hobb in the air: he falls, a bystander has
  the chance to catch him, and at the end of the round he hits the ground. A clash Hobb's
  technique opened that grounds a flying hawk drops it at once, with fall damage on its
  health and no catch.

Expected values are the rows built here and the spec (#4576 slice 3): a mortal has 1 hop a
round; MELEE reaches the same or an adjacent position, MISSILE anywhere in the room; a roof
stops every strike between the air and the roofed position; a screen lets a missile in only
from the same or an adjacent position; the bite does 10; a fall's impact is the Plummeting
condition's severity (it starts at 1 and gains 1 per level, one level from the air) times
``FALL_IMPACT_PER_LEVEL``; the copy strings "{name} meets {mover} with a waiting strike.",
"{name} waited for an opening that never came.", "{name} is stopped before striking.",
"{name} moves to {position}." and "{name} slams into the ground.".
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.conf import settings
from django.test import override_settings

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory, ConsequencePoolEntryFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CATCH_THE_FALLER_NAME, CreatureTraversal
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import Position
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import (
    connect_positions,
    enter_aerial,
    is_aerial,
    materialize_aerial_layer,
    place_in_position,
    position_of,
    position_reachable,
    set_position_cover,
)
from world.checks.constants import EffectTarget, EffectType, PositionDestination
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.combat.clash import _resolution_to_check_outcome, resolve_clash
from world.combat.constants import (
    ActionCategory,
    ClashResolution,
    CombatManeuver,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.models import FatiguePool
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterAnima
from world.mechanics.factories import AerialPropertyFactory, CharacterEngagementFactory
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

FULL_HEALTH = 100
BITE = 10
WAITING_STRIKE = "{name} meets {mover} with a waiting strike."
NEVER_CAME = "{name} waited for an opening that never came."
STOPPED = "{name} is stopped before striking."
MOVES_TO = "{name} moves to {position}."
SLAMS = "{name} slams into the ground."
# Plummeting starts at severity 1 and gains 1 for the one level down from the air.
FALL_FROM_THE_AIR = 2 * settings.FALL_IMPACT_PER_LEVEL


def _full_strength(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll at success level 0, which takes the blow at full strength."""
    return MagicMock(success_level=0)


def _clean_hit(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands a PC's strike."""
    return MagicMock(success_level=2)


class _TheSteading(JourneyCase):
    """Lane - Barn - Yard - Hall - Tower, open edges, a roofed Barn, round 1 declaring."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # movement, the fall content
            ensure_foundational_capabilities()
            ensure_fall_content()
        AerialPropertyFactory()
        DamageSuccessLevelMultiplierFactory(min_success_level=0, multiplier=1)
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.room = self.make_room("The Steading")
        self.lane = PositionFactory(room=self.room, name="Lane")
        self.barn = PositionFactory(room=self.room, name="Barn")
        self.yard = PositionFactory(room=self.room, name="Yard")
        self.hall = PositionFactory(room=self.room, name="Hall")
        self.tower = PositionFactory(room=self.room, name="Tower")
        connect_positions(self.lane, self.barn)
        connect_positions(self.barn, self.yard)
        connect_positions(self.yard, self.hall)
        connect_positions(self.hall, self.tower)
        set_position_cover(self.barn, roofed=True, screens_ranged=False)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.participants: dict[int, CombatParticipant] = {}

    # -- the people in the fight ----------------------------------------------

    def fighter(self, name: str, *, at, health: int = FULL_HEALTH):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=health, max_health=FULL_HEALTH, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        self.participants[character.pk] = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        place_in_position(character, at)
        self.watch(character)
        return character

    def technique(self, character, name: str, *, reach: str = TechniqueReach.ADJACENT):
        """A known physical strike for 10 at one target."""
        technique = TechniqueFactory(
            name=name,
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name=name, base_power=20),
            action_category=ActionCategory.PHYSICAL,
            reach=reach,
            anima_cost=3,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)
        CharacterTechniqueFactory(character=character.sheet_data, technique=technique)
        return technique

    def creature(
        self,
        name: str,
        *,
        at,
        hops: int = 1,
        traversal: str = CreatureTraversal.WALKS,
        delivery: str = StrikeDelivery.MELEE,
        **entry_kwargs: object,
    ) -> CombatOpponent:
        """An enemy spawned from its bestiary entry at ``at``, with one attack of 10."""
        pool = ThreatPoolFactory(name=f"{name} attacks")
        entry_kwargs.setdefault("target_selection", TargetSelection.HIGHEST_THREAT)
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{name} strike",
            base_damage=BITE,
            delivery=delivery,
            targeting_mode=TargetingMode.SINGLE,
            **entry_kwargs,
        )
        template = CreatureTemplateFactory(
            name=name,
            tier=OpponentTier.MOOK,
            threat_pool=pool,
            speed_hops=hops,
            traversal=traversal,
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def airborne(self, opponent: CombatOpponent) -> None:
        """Take a flier up into the air over where it stands (its own flight)."""
        enter_aerial(opponent.objectdb)

    def above(self, position: Position) -> Position:
        materialize_aerial_layer(self.room)
        return Position.objects.get(room=self.room, elevation_anchor=position)

    # -- what happened ----------------------------------------------------------

    def resolve(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_strength, offense_check_fn=_clean_hit)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def opponent_health(self, opponent: CombatOpponent) -> int:
        return CombatOpponent.objects.get(pk=opponent.pk).health

    def where(self, opponent: CombatOpponent):
        return position_of(opponent.objectdb)

    def declare_strike(self, character, technique, opponent: CombatOpponent):
        return dispatch_player_action(
            character,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
            ),
            {"effort_level": "medium", "focused_opponent_target_id": opponent.pk},
        )

    def row_index(self, character, needle: str) -> int:
        rows = self.mailbox(character).rows
        for index, row in enumerate(rows):
            if needle in row:
                return index
        self.fail(f"{character.key} was never pushed a row with {needle!r}. Rows:\n{rows}")
        return -1

    def rows_with(self, character, needle: str) -> list[str]:
        return [row for row in self.mailbox(character).rows if needle in row]


class ARoofStopsAFlier(_TheSteading):
    """No strike passes between the air and the roofed Barn, though they are joined."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.barn)

    def test_the_roof_cuts_reach_across_the_joined_edge(self) -> None:
        over_barn = self.above(self.barn)
        # The air over the Barn is joined to it, yet adjacent reach is refused both ways.
        self.assertFalse(position_reachable(over_barn, self.barn, TechniqueReach.ADJACENT))
        self.assertFalse(position_reachable(self.barn, over_barn, TechniqueReach.ANY))
        # The unroofed Yard keeps the ordinary rule with the air above it.
        self.assertTrue(
            position_reachable(self.above(self.yard), self.yard, TechniqueReach.ADJACENT)
        )

    def test_a_hawk_over_the_barn_cannot_strike_down_through_the_roof(self) -> None:
        hawk = self.creature("Hawk", at=self.barn, traversal=CreatureTraversal.FLIES)
        self.airborne(hawk)

        self.resolve()

        # Its one hop takes it over the Lane or the Yard: still in the air, still no strike.
        self.assertIn(self.where(hawk).name, {"Above Lane", "Above Yard"})
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertFalse(self.rows_with(self.hobb, "strikes Hobb"))

    def test_with_two_hops_the_hawk_lands_beside_the_barn_and_bites(self) -> None:
        hawk = self.creature("Hawk", at=self.barn, hops=2, traversal=CreatureTraversal.FLIES)
        self.airborne(hawk)

        self.resolve()

        # Across the air beside the Barn, then down onto the ground there (the Lane or the
        # Yard, both beside the Barn): two hops, then the bite.
        landed = self.where(hawk)
        self.assertIn(landed, {self.lane, self.yard})
        self.assertFalse(is_aerial(hawk.objectdb))
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Hawk", position=landed.name))

    def test_a_flying_archer_comes_down_to_shoot(self) -> None:
        archer = self.creature(
            "Sky Archer",
            at=self.yard,
            traversal=CreatureTraversal.FLIES,
            delivery=StrikeDelivery.MISSILE,
        )
        self.airborne(archer)

        self.resolve()

        # Nothing it looses from the air reaches the Barn, so it lands in the Yard and shoots.
        self.assertEqual(self.where(archer), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)

    def test_hobbs_lunge_at_a_hawk_over_the_barn_is_refused(self) -> None:
        lunge = self.technique(self.hobb, "Lunge")
        hawk = self.creature("Hawk", at=self.barn, traversal=CreatureTraversal.FLIES)
        self.airborne(hawk)

        with self.assertRaises(ActionDispatchError) as refused:
            self.declare_strike(self.hobb, lunge, hawk)

        self.assertEqual(refused.exception.code, ActionDispatchError.TARGET_OUT_OF_REACH)
        self.assertFalse(CombatRoundAction.objects.filter(participant__encounter=self.encounter))

    def test_a_flier_over_the_barn_cannot_drop_through_the_roof(self) -> None:
        brenna = self.fighter("Brenna", at=self.barn)
        enter_aerial(brenna)

        told = self.telnet(brenna, "position Barn")

        self.assertIn("A roof is in the way.", told)
        self.assertEqual(position_of(brenna).name, "Above Barn")


class AScreenedLane(_TheSteading):
    """A screen lets a missile in only from the same position or the one beside it."""

    def setUp(self) -> None:
        super().setUp()
        set_position_cover(self.lane, roofed=False, screens_ranged=True)
        self.hobb = self.fighter("Hobb", at=self.lane)

    def test_an_archer_across_the_room_walks_closer_instead_of_shooting(self) -> None:
        archer = self.creature("Bandit Archer", at=self.tower, delivery=StrikeDelivery.MISSILE)

        self.resolve()

        # From the Tower nothing reaches the screened Lane; only the Barn beside it does,
        # three hops away. One hop takes the archer to the Hall, and no shot is loosed.
        self.assertEqual(self.where(archer), self.hall)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Bandit Archer", position="Hall"))

    def test_an_archer_beside_the_screen_shoots(self) -> None:
        archer = self.creature("Bandit Archer", at=self.barn, delivery=StrikeDelivery.MISSILE)

        self.resolve()

        self.assertEqual(self.where(archer), self.barn)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)

    def test_hobbs_room_wide_strike_at_a_screened_foe_is_refused_from_afar(self) -> None:
        brenna = self.fighter("Brenna", at=self.tower)
        sling = self.technique(brenna, "Sling Stone", reach=TechniqueReach.ANY)
        wolf = self.creature("Grey Wolf", at=self.lane)

        with self.assertRaises(ActionDispatchError) as refused:
            self.declare_strike(brenna, sling, wolf)

        self.assertEqual(refused.exception.code, ActionDispatchError.TARGET_OUT_OF_REACH)


class HobbWaitsForAnOpening(_TheSteading):
    """Hobb holds the Barn's doorway with a lunge ready for the first enemy to come at him."""

    def setUp(self) -> None:
        super().setUp()
        set_position_cover(self.barn, roofed=False, screens_ranged=False)
        self.hobb = self.fighter("Hobb", at=self.barn)
        self.lunge = self.technique(self.hobb, "Lunge")

    def wait_on_telnet(self) -> str:
        return self.telnet(self.hobb, "combat await Lunge")

    def waiting_row(self) -> CombatRoundAction:
        return CombatRoundAction.objects.get(
            participant=self.participants[self.hobb.pk], round_number=1
        )

    def anima(self) -> int:
        return CharacterAnima.objects.get(character=self.hobb.sheet_data).current

    def fatigue(self) -> int:
        pool = FatiguePool.objects.filter(character_sheet=self.hobb.sheet_data).first()
        return pool.physical_current if pool else 0

    def test_waiting_is_declared_from_telnet_and_from_the_web(self) -> None:
        told = self.wait_on_telnet()
        self.assertIn("You wait for an opening, ready with Lunge.", told)
        row = self.waiting_row()
        self.assertEqual(row.maneuver, CombatManeuver.AWAIT_OPENING)
        self.assertEqual(row.focused_action, self.lunge)
        self.assertIsNone(row.focused_opponent_target)

        result = self.web(self.hobb, "combat_await_opening", technique_id=self.lunge.pk).detail
        self.assertTrue(result.success, result.message)
        self.assertEqual(
            CombatRoundAction.objects.filter(participant__encounter=self.encounter).count(), 1
        )

    def test_a_ranged_technique_cannot_be_held(self) -> None:
        self.technique(self.hobb, "Sling Stone", reach=TechniqueReach.ANY)

        told = self.telnet(self.hobb, "combat await Sling Stone")

        self.assertIn("A waiting strike needs a strike that reaches", told)
        self.assertFalse(CombatRoundAction.objects.filter(participant__encounter=self.encounter))

    def test_a_wolf_that_attacks_him_takes_his_strike_first(self) -> None:
        self.wait_on_telnet()
        wolf = self.creature("Grey Wolf", at=self.yard)

        self.resolve()

        strike_line = WAITING_STRIKE.format(name="Hobb", mover="Grey Wolf")
        first = self.row_index(self.hobb, strike_line)
        bite = self.row_index(self.hobb, "strikes Hobb for")
        self.assertLess(first, bite)
        self.assertLess(self.opponent_health(wolf), 30)
        # The wolf lived, so its bite still lands after the exchange.
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertEqual(self.waiting_row().focused_opponent_target_id, wolf.pk)
        self.assertFalse(self.rows_with(self.hobb, "never came"))

    def test_a_wolf_that_walks_into_reach_takes_it_on_arrival_and_only_once(self) -> None:
        self.wait_on_telnet()
        wolf = self.creature("Grey Wolf", at=self.hall)

        self.resolve()

        moved = self.row_index(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Yard"))
        strike = self.row_index(self.hobb, WAITING_STRIKE.format(name="Hobb", mover="Grey Wolf"))
        bite = self.row_index(self.hobb, "strikes Hobb for")
        self.assertLess(moved, strike)
        self.assertLess(strike, bite)
        self.assertEqual(len(self.rows_with(self.hobb, "with a waiting strike")), 1)
        self.assertEqual(self.where(wolf), self.yard)

    def test_a_second_wolf_draws_no_second_strike(self) -> None:
        self.wait_on_telnet()
        first = self.creature("Grey Wolf", at=self.yard)
        second = self.creature("Black Wolf", at=self.lane)

        self.resolve()

        self.assertEqual(len(self.rows_with(self.hobb, "with a waiting strike")), 1)
        struck = [o for o in (first, second) if self.opponent_health(o) < 30]
        self.assertEqual(len(struck), 1)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - 2 * BITE)

    def test_a_wolf_his_strike_drops_is_stopped_before_striking(self) -> None:
        self.wait_on_telnet()
        wolf = self.creature("Grey Wolf", at=self.yard)
        wolf.health = 1
        wolf.save(update_fields=["health"])

        self.resolve()

        self.assertShownRow(self.hobb, STOPPED.format(name="Grey Wolf"))
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)

    def test_an_assassin_that_strikes_and_blinks_away_is_answered_first(self) -> None:
        self.wait_on_telnet()
        blink_out = ConsequenceFactory(label="Blinks away")
        ConsequenceEffectFactory(
            consequence=blink_out,
            effect_type=EffectType.MOVE_TO_POSITION,
            target=EffectTarget.SELF,
            position_destination=PositionDestination.NAMED,
            position_name="Tower",
        )
        entry = ConsequencePoolEntryFactory(consequence=blink_out)
        assassin = self.creature("Shade Assassin", at=self.yard, on_hit_consequence_pool=entry.pool)

        self.resolve()

        strike = self.row_index(
            self.hobb, WAITING_STRIKE.format(name="Hobb", mover="Shade Assassin")
        )
        stab = self.row_index(self.hobb, "strikes Hobb for")
        self.assertLess(strike, stab)
        self.assertLess(self.opponent_health(assassin), 30)
        # It ended the action far out of reach, but it was beside him when it struck.
        self.assertEqual(self.where(assassin), self.tower)

    def test_when_nothing_comes_it_says_so_and_costs_nothing(self) -> None:
        self.wait_on_telnet()
        self.creature("Grey Wolf", at=self.tower)  # one hop a round: two short of the Barn
        anima, fatigue = self.anima(), self.fatigue()

        self.resolve()

        self.assertShownRow(self.hobb, NEVER_CAME.format(name="Hobb"))
        self.assertEqual(self.anima(), anima)
        self.assertEqual(self.fatigue(), fatigue)
        self.assertIsNone(self.waiting_row().focused_opponent_target)


class KnockedOutOfTheAir(_TheSteading):
    """Grounding is a fall, not a landing."""

    def setUp(self) -> None:
        super().setUp()
        set_position_cover(self.barn, roofed=False, screens_ranged=False)

    def grounding_pool(self):
        grounds = ConsequenceFactory(label="Knocked out of the air")
        ConsequenceEffectFactory(
            consequence=grounds, effect_type=EffectType.REMOVE_FLIGHT, target=EffectTarget.TARGET
        )
        return ConsequencePoolEntryFactory(consequence=grounds).pool

    def test_a_hawk_grounds_a_flying_hobb_who_falls_while_brenna_could_catch(self) -> None:
        hobb = self.fighter("Hobb", at=self.barn)
        self.fighter("Brenna", at=self.lane)  # someone there to catch him
        enter_aerial(hobb)
        hawk = self.creature(
            "Hawk",
            at=self.yard,
            traversal=CreatureTraversal.FLIES,
            on_hit_consequence_pool=self.grounding_pool(),
        )
        self.airborne(hawk)

        self.resolve()

        catch = ChallengeInstance.objects.filter(
            template__name=CATCH_THE_FALLER_NAME, target_object=hobb
        )
        self.assertTrue(catch.exists())  # the catch window opened
        self.assertFalse(catch.filter(is_active=True).exists())  # and closed at impact
        # Uncaught, he hit the ground at the end of the round: the bite, then the fall.
        self.assertEqual(position_of(hobb), self.barn)
        self.assertFalse(is_aerial(hobb))
        self.assertEqual(self.health(hobb), FULL_HEALTH - BITE - FALL_FROM_THE_AIR)
        self.assertTold(hobb, SLAMS.format(name="Hobb"))

    def test_a_clash_hobbs_technique_opened_drops_a_flying_hawk_at_once(self) -> None:
        self.fighter("Hobb", at=self.barn)
        hawk = self.creature("Hawk", at=self.yard, traversal=CreatureTraversal.FLIES)
        self.airborne(hawk)
        before = self.opponent_health(hawk)
        pool = self.grounding_pool()
        # The technique's clash resolution pool answers a decisive win with the grounding.
        consequence = pool.entries.get().consequence
        consequence.outcome_tier = _resolution_to_check_outcome(ClashResolution.PC_DECISIVE)
        consequence.save(update_fields=["outcome_tier"])
        clash = ClashFactory(
            encounter=self.encounter, npc_opponent=hawk, resolution_consequence_pool=pool
        )

        resolve_clash(clash=clash, resolution=ClashResolution.PC_DECISIVE, round_number=1)

        self.assertEqual(self.where(hawk), self.yard)
        self.assertFalse(is_aerial(hawk.objectdb))
        self.assertEqual(self.opponent_health(hawk), before - FALL_FROM_THE_AIR)
        self.assertFalse(
            ChallengeInstance.objects.filter(
                template__name=CATCH_THE_FALLER_NAME, target_object=hawk.objectdb
            ).exists()
        )
        # The empty sky layer comes down with it.
        self.assertFalse(Position.objects.filter(room=self.room, name__startswith="Above"))
