"""Journeys for enemies that close in on the battle map (#4607, slice 2 of #4576).

The causeway is five positions in a row, Lane - Gate - Yard - Hall - Tower, joined by open
edges. Hobb holds the Gate. Enemies are spawned from bestiary entries the way staff spawn
them (``spawn_from_creature_template`` with a position), each entry carrying its hop budget
and how it crosses the map.

- A wolf with 2 hops at the Tower runs to the Yard, beside the Gate, and bites Hobb in the
  same round. The room is told "Grey Wolf moves to Yard."
- A wolf whose only bite is on cooldown still closes in. A wolf staff gave a bite before the
  round resolved still moves first.
- A bite does not carry across the room: a 1-hop wolf two positions short comes one closer
  and does not bite. An archer shoots Hobb from the Tower without moving.
- Hobb moves one hop a round, only while the round is being declared: by typing
  ``position <name>`` and by the web client's move action, which say the same things.
- Hobb's strike at an archer who is no longer beside him finds no one, and costs him nothing.
- A brute's telegraphed blow that matures after Hobb stepped out of its reach lands on the
  weakest fighter still in reach, or is called off when nobody is. A brute winding up does
  not move.
- A wall makes a walker go around, or stops it. A climber goes over a wall with a way past
  it at one extra hop. A flier goes over a hard seal, unless the wall also blocks flight.
- Hobb cannot step up into the air above the Gate: "You cannot fly."

Expected values are the rows built here and the spec (#4576 slice 2): a mortal (movement 5)
has 1 hop a round; MELEE reaches the same or an adjacent position over an open edge and
MISSILE reaches anywhere in the room; a climber pays 2 hops for a wall with a way past it;
the bite does 10; the copy strings "{name} moves to {position}.", "{name} cannot reach
anyone.", "{name}'s strike finds no one in reach.", "You have no movement left this
round.", "Wait for the round to resolve.", "You can move when the next round opens.",
"1 hop left this round." and "You cannot fly.".

``defense_check_fn`` returning success level 0 is the established stand-in for a defence that
takes the blow at full strength (the crossing-a-wall journeys use it the same way).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import override_settings

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action, get_player_actions
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    force_move_to_position,
    materialize_aerial_layer,
    place_in_position,
    position_of,
)
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    PendingOpponentAttack,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.conditions.models import CapabilityType
from world.fatigue.constants import EffortLevel
from world.fatigue.models import FatiguePool
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterAnima
from world.mechanics.factories import (
    AerialPropertyFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
)
from world.scenes.constants import RoundStatus
from world.scenes.services import active_persona_for_sheet
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

FULL_HEALTH = 100
BITE = 10
MOVES_TO = "{name} moves to {position}."
CANNOT_REACH = "{name} cannot reach anyone."
FIZZLES = "{name}'s strike finds no one in reach."
NO_MOVEMENT_LEFT = "You have no movement left this round."
WAIT_FOR_RESOLUTION = "Wait for the round to resolve."
WAIT_FOR_NEXT_ROUND = "You can move when the next round opens."
ONE_HOP_LEFT = "1 hop left this round."
CANNOT_FLY = "You cannot fly."


def _full_strength(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll at success level 0, which takes the blow at full strength."""
    return MagicMock(success_level=0)


def _clean_hit(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands a PC's strike."""
    return MagicMock(success_level=2)


class _TheCauseway(JourneyCase):
    """Lane - Gate - Yard - Hall - Tower, open edges, and a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        self.mook_tier = OpponentTierTemplateFactory(
            tier=OpponentTier.MOOK, base_health=30, base_soak=0
        )
        self.room = self.make_room("The Causeway")
        self.lane = PositionFactory(room=self.room, name="Lane")
        self.gate = PositionFactory(room=self.room, name="Gate")
        self.yard = PositionFactory(room=self.room, name="Yard")
        self.hall = PositionFactory(room=self.room, name="Hall")
        self.tower = PositionFactory(room=self.room, name="Tower")
        connect_positions(self.lane, self.gate)
        connect_positions(self.gate, self.yard)
        connect_positions(self.yard, self.hall)
        connect_positions(self.hall, self.tower)
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

    # -- what happened ----------------------------------------------------------

    def resolve(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_strength, offense_check_fn=_clean_hit)

    def next_round(self) -> None:
        begin_declaration_phase(self.encounter)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def where(self, opponent: CombatOpponent):
        return position_of(opponent.objectdb)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(pk=self.participants[character.pk].pk)

    def assertNoMoveRow(self, character, name: str) -> None:  # noqa: N802
        """``character`` was never shown "{name} moves to ..." (the enemy stood still)."""
        rows = self.mailbox(character).rows
        self.assertFalse([row for row in rows if f"{name} moves to" in row], rows)

    def assertStrikeRow(self, character, name: str, target: str) -> None:  # noqa: N802
        """``character`` was shown "{name}\u2019s ... strikes {target} for ... damage"."""
        rows = self.mailbox(character).rows
        self.assertTrue(
            [
                row
                for row in rows
                if row.startswith(f"{name}\u2019s ") and f"strikes {target} for" in row
            ],
            rows,
        )

    def assertNotRefused(self, told: str) -> None:  # noqa: N802
        """A move that worked told the player none of the refusals (it says nothing at all)."""
        for refusal in (NO_MOVEMENT_LEFT, WAIT_FOR_RESOLUTION, WAIT_FOR_NEXT_ROUND, CANNOT_FLY):
            self.assertNotIn(refusal, told)
        self.assertNotIn("Crossing that requires", told)

    def edge_sealed_between_gate_and_yard(self, **kwargs: object) -> None:
        create_conjured_obstacle(self.gate, self.yard, caster_sheet=None, integrity=12, **kwargs)


class AnEnemyClosesIn(_TheCauseway):
    """Enemies move on the map before they strike, and strike only what they reach."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.gate)

    def test_a_fast_wolf_runs_up_and_bites_in_the_same_round(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.tower, hops=2)

        self.resolve()

        # Two hops from the Tower is the Yard, beside the Gate; a bite reaches from there.
        self.assertEqual(self.where(wolf), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Yard"))
        # The bite names the wolf as the room knows it, never its tier.
        bite = [row for row in self.mailbox(self.hobb).rows if "strikes" in row]
        self.assertTrue(bite)
        self.assertTrue(all(row.startswith("Grey Wolf\u2019s ") for row in bite), bite)

    def test_a_wolf_whose_bite_is_on_cooldown_still_closes_in(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.yard, cooldown_rounds=2)
        self.resolve()  # round 1: the wolf is beside Hobb already and bites from the Yard
        self.assertEqual(self.where(wolf), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)

        self.next_round()
        told = self.telnet(self.hobb, "position Lane")
        self.assertNotRefused(told)
        self.assertEqual(position_of(self.hobb), self.lane)
        self.resolve()  # round 2: no bite to use, so the wolf only follows him

        self.assertEqual(self.where(wolf), self.gate)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Gate"))

    def test_a_wolf_staff_gave_a_bite_still_moves_before_it_bites(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.hall)
        # Staff (or a simulation) chose the wolf's bite before the round resolved, and wrote
        # no movement for it.
        bite = CombatOpponentAction.objects.create(
            opponent=wolf,
            round_number=1,
            threat_entry=wolf.threat_pool.entries.get(),
        )
        bite.targets.set([self.participant(self.hobb)])

        self.resolve()

        self.assertEqual(self.where(wolf), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertEqual(CombatOpponentAction.objects.filter(opponent=wolf).count(), 1)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Yard"))

    def test_a_bite_does_not_carry_across_the_room(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.tower)

        self.resolve()

        # One hop from the Tower is the Hall, still two positions from the Gate.
        self.assertEqual(self.where(wolf), self.hall)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Hall"))

    def test_a_creature_with_two_actions_closes_in_once_then_strikes_twice(self) -> None:
        # The tier row staff authored gives its creatures two actions a round.
        self.mook_tier.base_actions_per_round = 2
        self.mook_tier.save()
        ogre = self.creature("Ogre", at=self.hall)
        self.assertEqual(ogre.actions_per_round, 2)

        self.resolve()

        # One hop from the Hall is the Yard, beside the Gate: both blows land from there.
        self.assertEqual(self.where(ogre), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - 2 * BITE)
        rows = self.mailbox(self.hobb).rows
        self.assertEqual([r for r in rows if "Ogre moves to" in r], ["Ogre moves to Yard."])
        # Each blow is its own row, naming Hobb once, for one bite each.
        blows = [r for r in rows if r.startswith("Ogre\u2019s ") and "strikes" in r]
        self.assertEqual(blows, [f"Ogre\u2019s Ogre strike strikes Hobb for {BITE} damage."] * 2)

    def test_an_archer_shoots_across_the_room_without_moving(self) -> None:
        archer = self.creature("Bandit Archer", at=self.tower, delivery=StrikeDelivery.MISSILE)

        self.resolve()

        self.assertEqual(self.where(archer), self.tower)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertNotIn("Bandit Archer moves to", "\n".join(self.mailbox(self.hobb).rows))


class HobbMovesOneHopARound(_TheCauseway):
    """A mortal moves one hop a round, only while the round is being declared."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.gate)
        # Someone to fight, who never acts, so the fight goes on between rounds.
        CombatOpponentFactory(encounter=self.encounter, name="Watcher", threat_pool=None)

    def move_on_the_web(self, position):
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="move_to_position",
            position_id=position.pk,
        )
        return dispatch_player_action(self.hobb, ref, {}).detail

    def moves_listed(self) -> dict[str, object]:
        return {
            action.display_name: action
            for action in get_player_actions(self.hobb)
            if action.ref.registry_key == "move_to_position"
        }

    def hops_used(self) -> int:
        return self.participant(self.hobb).hops_used

    def test_one_move_while_declaring_then_no_movement_left(self) -> None:
        listed = self.moves_listed()
        self.assertTrue(listed["Move to Yard"].prerequisite_met)
        self.assertEqual(listed["Move to Yard"].description, ONE_HOP_LEFT)

        result = self.move_on_the_web(self.yard)

        self.assertTrue(result.success, result.message)
        self.assertEqual(position_of(self.hobb), self.yard)
        self.assertEqual(self.hops_used(), 1)

        self.assertIn(NO_MOVEMENT_LEFT, self.telnet(self.hobb, "position Hall"))
        refused = self.move_on_the_web(self.gate)
        self.assertFalse(refused.success)
        self.assertEqual(refused.message, NO_MOVEMENT_LEFT)
        self.assertEqual(position_of(self.hobb), self.yard)
        self.assertEqual(self.hops_used(), 1)
        listed = self.moves_listed()
        self.assertEqual(set(listed), {"Move to Gate", "Move to Hall"})
        for action in listed.values():
            self.assertFalse(action.prerequisite_met)
            self.assertEqual(action.prerequisite_reasons, [NO_MOVEMENT_LEFT])

    def test_the_first_move_typed_in_telnet_spends_the_hop_too(self) -> None:
        told = self.telnet(self.hobb, "position Yard")
        self.assertNotRefused(told)

        self.assertEqual(position_of(self.hobb), self.yard)
        self.assertEqual(self.hops_used(), 1)
        self.assertEqual(self.move_on_the_web(self.hall).message, NO_MOVEMENT_LEFT)

    def test_no_move_while_the_round_resolves(self) -> None:
        self.encounter.status = RoundStatus.RESOLVING
        self.encounter.save(update_fields=["status"])

        self.assertIn(WAIT_FOR_RESOLUTION, self.telnet(self.hobb, "position Yard"))
        self.assertEqual(self.move_on_the_web(self.yard).message, WAIT_FOR_RESOLUTION)
        self.assertEqual(position_of(self.hobb), self.gate)
        self.assertEqual(self.hops_used(), 0)
        self.assertEqual(
            self.moves_listed()["Move to Yard"].prerequisite_reasons, [WAIT_FOR_RESOLUTION]
        )

    def test_no_move_between_rounds_and_the_hop_comes_back_next_round(self) -> None:
        told = self.telnet(self.hobb, "position Yard")
        self.assertNotRefused(told)
        self.resolve()
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)

        self.assertIn(WAIT_FOR_NEXT_ROUND, self.telnet(self.hobb, "position Hall"))
        self.assertEqual(self.move_on_the_web(self.hall).message, WAIT_FOR_NEXT_ROUND)
        self.assertEqual(
            self.moves_listed()["Move to Hall"].prerequisite_reasons, [WAIT_FOR_NEXT_ROUND]
        )
        self.assertEqual(position_of(self.hobb), self.yard)

        self.next_round()

        listed = self.moves_listed()
        self.assertTrue(listed["Move to Hall"].prerequisite_met)
        self.assertEqual(listed["Move to Hall"].description, ONE_HOP_LEFT)
        self.assertTrue(self.move_on_the_web(self.hall).success)
        self.assertEqual(position_of(self.hobb), self.hall)

    def test_moving_is_free_once_the_fight_is_over(self) -> None:
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])

        self.telnet(self.hobb, "position Yard")
        self.assertTrue(self.move_on_the_web(self.hall).success)
        self.telnet(self.hobb, "position Tower")

        self.assertEqual(position_of(self.hobb), self.tower)
        self.assertEqual(self.hops_used(), 0)


class HobbMovesTwoHops(_TheCauseway):
    """A mortal's movement is 5; a known technique granting 5 more makes 10, two hops a round."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.lane)
        # Someone to fight, who never acts, so the fight goes on between rounds.
        CombatOpponentFactory(encounter=self.encounter, name="Watcher", threat_pool=None)
        sprint = TechniqueFactory(damage_profile=False)
        TechniqueCapabilityGrantFactory(
            technique=sprint,
            capability=CapabilityType.objects.get(name="movement"),
            base_value=5,
        )
        CharacterTechniqueFactory(character=self.hobb.sheet_data, technique=sprint)

    def move_descriptions(self) -> dict[str, str]:
        return {
            action.display_name: action.description
            for action in get_player_actions(self.hobb)
            if action.ref.registry_key == "move_to_position"
        }

    def test_two_moves_in_a_round_and_the_third_is_refused(self) -> None:
        self.assertEqual(self.move_descriptions()["Move to Gate"], "2 hops left this round.")

        self.assertNotRefused(self.telnet(self.hobb, "position Gate"))
        self.assertEqual(self.move_descriptions()["Move to Yard"], ONE_HOP_LEFT)
        self.assertNotRefused(self.telnet(self.hobb, "position Yard"))
        self.assertEqual(position_of(self.hobb), self.yard)

        self.assertIn(NO_MOVEMENT_LEFT, self.telnet(self.hobb, "position Hall"))
        self.assertEqual(position_of(self.hobb), self.yard)
        self.assertEqual(self.participant(self.hobb).hops_used, 2)


class HobbsStrikeFindsNoOne(_TheCauseway):
    """A strike whose target is no longer in reach when its turn comes fizzles for free."""

    def setUp(self) -> None:
        super().setUp()
        DamageSuccessLevelMultiplierFactory(min_success_level=0, multiplier=1)
        self.hobb = self.fighter("Hobb", at=self.gate)
        self.lunge = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="Lunge", base_power=20),
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.ADJACENT,
            anima_cost=3,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=self.lunge, base_damage=10)
        CharacterTechniqueFactory(character=self.hobb.sheet_data, technique=self.lunge)

    def test_a_lunge_at_an_archer_who_slipped_away_costs_nothing(self) -> None:
        archer = self.creature("Bandit Archer", at=self.yard, delivery=StrikeDelivery.MISSILE)
        declared = dispatch_player_action(
            self.hobb,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=self.lunge.pk, action_slot="focused"
            ),
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": archer.pk},
        )
        self.assertTrue(declared.deferred, declared)
        # The archer falls back to the Tower before Hobb's turn. Nothing in slice 2 walks an
        # enemy away (retreat is slice 4), so a force-move stands in for the step back.
        force_move_to_position(archer.objectdb, self.tower)
        archer_health = CombatOpponent.objects.get(pk=archer.pk).health
        anima = CharacterAnima.objects.get(character=self.hobb.sheet_data).current
        fatigue = self.fatigue()

        self.resolve()

        self.assertEqual(CombatOpponent.objects.get(pk=archer.pk).health, archer_health)
        self.assertEqual(CharacterAnima.objects.get(character=self.hobb.sheet_data).current, anima)
        self.assertEqual(self.fatigue(), fatigue)
        name = active_persona_for_sheet(self.hobb.sheet_data).name
        self.assertShownRow(self.hobb, FIZZLES.format(name=name))

    def fatigue(self) -> int:
        pool = FatiguePool.objects.filter(character_sheet=self.hobb.sheet_data).first()
        return pool.physical_current if pool else 0


class ABruteWindsUp(_TheCauseway):
    """A telegraphed blow lands on whoever is still in reach when it matures, or on no one.

    The brute's only attack takes a round to wind up and picks the lowest-health fighter.
    A brute winding up stands still: the telegraph is its action.
    """

    def brute(self, *, at) -> CombatOpponent:
        return self.creature(
            "Brute", at=at, windup_rounds=1, target_selection=TargetSelection.LOWEST_HEALTH
        )

    def test_a_brute_winding_up_does_not_move(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        brute = self.brute(at=self.yard)  # beside Hobb: its blow reaches from where it stands

        self.resolve()

        self.assertTrue(PendingOpponentAttack.objects.filter(opponent=brute).exists())
        self.assertEqual(self.where(brute), self.yard)
        self.assertNotIn("Brute moves to", "\n".join(self.mailbox(hobb).rows))

    def test_a_brute_out_of_reach_closes_in_then_winds_up_then_lands_the_blow(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        brute = self.brute(at=self.hall)  # two hops from Hobb: a wind-up cannot reach him

        self.resolve()  # round 1: it walks up instead of winding up at nobody
        self.assertEqual(self.where(brute), self.yard)
        self.assertFalse(PendingOpponentAttack.objects.filter(opponent=brute).exists())
        self.assertShownRow(hobb, "Brute moves to Yard.")

        self.next_round()
        self.resolve()  # round 2: beside Hobb now, it winds up and stands still
        self.assertEqual(self.where(brute), self.yard)
        self.assertEqual(self.health(hobb), FULL_HEALTH)

        self.next_round()
        self.resolve()  # round 3: Hobb stayed put, so the blow lands
        self.assertEqual(self.health(hobb), FULL_HEALTH - BITE)
        self.assertStrikeRow(hobb, "Brute", "Hobb")

    def test_the_blow_lands_on_the_weakest_still_in_reach_after_hobb_steps_away(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate, health=60)
        brenna = self.fighter("Brenna", at=self.hall)
        corwin = self.fighter("Corwin", at=self.hall, health=80)
        brute = self.brute(at=self.yard)
        self.resolve()  # round 1: the brute winds up at Hobb, the weakest
        self.assertEqual(
            PendingOpponentAttack.objects.get(opponent=brute).target, self.participant(hobb)
        )

        self.next_round()
        self.telnet(hobb, "position Lane")  # out of reach of a blow from the Yard
        self.resolve()

        self.assertEqual(self.where(brute), self.yard)
        self.assertEqual(self.health(hobb), 60)
        self.assertEqual(self.health(corwin), 80 - BITE)
        self.assertEqual(self.health(brenna), FULL_HEALTH)
        self.assertStrikeRow(hobb, "Brute", "Corwin")
        self.assertFalse([r for r in self.mailbox(hobb).rows if "strikes Hobb" in r])

    def test_the_blow_is_called_off_when_nobody_is_in_reach(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        brute = self.brute(at=self.yard)
        self.resolve()  # round 1: the brute winds up at Hobb

        self.next_round()
        self.telnet(hobb, "position Lane")
        self.resolve()

        self.assertEqual(self.where(brute), self.yard)
        self.assertEqual(self.health(hobb), FULL_HEALTH)
        self.assertShownRow(hobb, CANNOT_REACH.format(name="Brute"))


class TwoEnemiesOnHobb(_TheCauseway):
    """Two enemies whose attacks name the same fighter each keep their own target (#4607)."""

    def test_the_brute_calls_off_while_the_wolf_still_bites(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        brute = self.creature(
            "Brute", at=self.yard, windup_rounds=1, target_selection=TargetSelection.LOWEST_HEALTH
        )
        self.resolve()  # round 1: the brute winds up at Hobb, beside it
        wolf = self.creature("Grey Wolf", at=self.hall, hops=2)

        self.next_round()
        self.telnet(hobb, "position Lane")  # two from the brute; the wolf can still follow
        self.resolve()

        self.assertEqual(self.where(brute), self.yard)
        self.assertEqual(self.where(wolf), self.gate)
        self.assertShownRow(hobb, CANNOT_REACH.format(name="Brute"))
        bites = [r for r in self.mailbox(hobb).rows if "strikes Hobb" in r]
        self.assertEqual(
            bites, [f"Grey Wolf\u2019s Grey Wolf strike strikes Hobb for {BITE} damage."]
        )
        self.assertEqual(self.health(hobb), FULL_HEALTH - BITE)


class WallsOnTheCauseway(_TheCauseway):
    """A wall between the Gate and the Yard; Hobb holds the Gate, the enemy is in the Yard."""

    def setUp(self) -> None:
        super().setUp()
        AerialPropertyFactory()
        self.hobb = self.fighter("Hobb", at=self.gate)

    def test_a_wolf_goes_around_a_wall(self) -> None:
        self.edge_sealed_between_gate_and_yard()
        connect_positions(self.yard, self.lane)  # the way round
        wolf = self.creature("Grey Wolf", at=self.yard)

        self.resolve()

        self.assertEqual(self.where(wolf), self.lane)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Lane"))

    def test_a_wolf_with_no_way_round_stays_behind_the_wall(self) -> None:
        self.edge_sealed_between_gate_and_yard()
        wolf = self.creature("Grey Wolf", at=self.yard)

        self.resolve()

        self.assertEqual(self.where(wolf), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertNoMoveRow(self.hobb, "Grey Wolf")

    def climbable_wall(self) -> None:
        hedge = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name="Thorn Hedge"), location=self.room
        )
        self.edge_sealed_between_gate_and_yard(gating_challenge=hedge)

    def test_a_climber_goes_over_a_wall_with_a_way_past_at_one_extra_hop(self) -> None:
        self.climbable_wall()
        lizard = self.creature(
            "Wall Lizard", at=self.yard, hops=2, traversal=CreatureTraversal.CLIMBS
        )

        self.resolve()

        self.assertEqual(self.where(lizard), self.gate)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Wall Lizard", position="Gate"))

    def test_a_climber_with_one_hop_cannot_get_over(self) -> None:
        self.climbable_wall()
        lizard = self.creature("Wall Lizard", at=self.yard, traversal=CreatureTraversal.CLIMBS)

        self.resolve()

        self.assertEqual(self.where(lizard), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertNoMoveRow(self.hobb, "Wall Lizard")

    def test_a_walker_cannot_climb_the_same_wall(self) -> None:
        self.climbable_wall()
        wolf = self.creature("Grey Wolf", at=self.yard, hops=2)

        self.resolve()

        self.assertEqual(self.where(wolf), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertNoMoveRow(self.hobb, "Grey Wolf")

    def test_a_hawk_flies_over_a_hard_seal(self) -> None:
        self.edge_sealed_between_gate_and_yard()
        hawk = self.creature("Hawk", at=self.yard, hops=2, traversal=CreatureTraversal.FLIES)

        self.resolve()

        # Up from the Yard, then across above the wall: the air over the Gate is beside it.
        self.assertEqual(self.where(hawk).name, "Above Gate")
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - BITE)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Hawk", position="Above Gate"))

    def test_a_wall_that_blocks_flight_stops_the_hawk(self) -> None:
        self.edge_sealed_between_gate_and_yard(blocks_flight=True)
        hawk = self.creature("Hawk", at=self.yard, hops=2, traversal=CreatureTraversal.FLIES)

        self.resolve()

        self.assertEqual(self.where(hawk), self.yard)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)
        self.assertNoMoveRow(self.hobb, "Hawk")


class HobbCannotFly(_TheCauseway):
    def test_hobb_cannot_step_up_into_the_air(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        materialize_aerial_layer(self.room)

        self.assertIn(CANNOT_FLY, self.telnet(hobb, "position Above Gate"))

        self.assertEqual(position_of(hobb), self.gate)
        self.assertEqual(self.participant(hobb).hops_used, 0)
        # His move list offers the ground on either side and never the air above him.
        moves = {
            action.display_name
            for action in get_player_actions(hobb)
            if action.ref.registry_key == "move_to_position"
        }
        self.assertEqual(moves, {"Move to Lane", "Move to Yard"})
