"""Journeys for crossing a wall (#4606, slice 1 of #4576).

Every conjured wall has a strength, a wall raised with a way past it can be got past, and a
Rampart that falls opens the edges it sealed. The yard has three positions in a row, West -
Middle - East, joined by open edges.

- Maren casts Barricade on the West - Middle edge during a combat round (``cast`` typed in
  the round). Hobb at West is told "Crossing that requires getting past Conjured Barrier."
  and sees the blocked move in his action list. He climbs it through the challenge dispatch
  the web client sends (the roll forced to Success, whose consequence resolves the
  challenge for everyone), and then walks to Middle.
- A sealed edge with no challenge is a hard seal: "The way is blocked."
- A Stone Rampart of integrity 10 at Middle seals both edges. A brute's swing of 12 at Brenna
  standing on it collapses it, and both edges open, except one a later Barricade took over.
- The same Rampart drained to nothing by a ward clash, expired after its one round, or torn
  down when the scene finishes opens its edges each time.

A mortal moves one hop a round and only while a round is open (#4607), so Brenna's walk across
the yard takes three rounds.

Expected values are the rows built here: the Rampart's integrity 10, the swing 12, the clash
pressure 5 against 3 integrity, the Rampart's duration of 1 round, and the challenge name
"Conjured Barrier" the spell wall's gate is minted from (``CONJURED_BARRIER_CHALLENGE_NAME``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action, get_player_actions
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.barrier_content import ensure_conjured_barrier_content
from world.areas.positioning.constants import (
    CONJURED_BARRIER_CHALLENGE_NAME,
    CONJURED_WALL_BASE_INTEGRITY,
)
from world.areas.positioning.factories import PositionFactory, RampartElementProfileFactory
from world.areas.positioning.models import PositionEdge, Rampart
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    place_in_position,
    position_of,
    raise_rampart,
)
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.clash import run_clash_round
from world.combat.constants import ParticipantStatus, TargetingMode, TargetSelection
from world.combat.factories import (
    ClashConfigFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    WardClashFactory,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import ConditionCapabilityEffectFactory, ConditionTemplateFactory
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.magic.effect_palette_content import OBSTACLE_TECHNIQUE_NAME, ensure_obstacle_content
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.mechanics.factories import (
    CharacterEngagementFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.models import ChallengeApproach, ChallengeInstance, ModifierTarget
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneOwnerParticipationFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.security_checks import seed_security_check_content
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

RAMPART_INTEGRITY = 10
BRUTE_SWING = 12
CLASH_PRESSURE = 5
CLASH_RAMPART_INTEGRITY = 3
WALL_RUNNER = 4  # traversal from the Wall-Runner distinction at rank 1
SURE_GRIP = 2  # traversal from the Sure Grip condition
CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"
BLOCKED = "The way is blocked."
GATED = f"Crossing that requires getting past {CONJURED_BARRIER_CHALLENGE_NAME}."


def _full_swing(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


def _clean_cast(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands the Barricade."""
    return MagicMock(success_level=2)


class _TheYard(JourneyCase):
    """West - Middle - East, open edges, and a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        self.yard = self.make_room("The Yard")
        self.west = PositionFactory(room=self.yard, name="West")
        self.middle = PositionFactory(room=self.yard, name="Middle")
        self.east = PositionFactory(room=self.yard, name="East")
        self.west_middle = connect_positions(self.west, self.middle)
        self.middle_east = connect_positions(self.middle, self.east)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )

    def fighter(self, name: str, *, at) -> object:
        character = self.make_player(name, room=self.yard)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        place_in_position(character, at)
        return character

    def next_round(self) -> None:
        """Open the next declaration phase. A mortal moves one hop a round, and only then."""
        begin_declaration_phase(self.encounter)

    def edge(self, a, b) -> PositionEdge:
        lo, hi = (a, b) if a.pk < b.pk else (b, a)
        return PositionEdge.objects.get(position_a=lo, position_b=hi)

    def stone_rampart(self, *, integrity: int = RAMPART_INTEGRITY, **kwargs) -> Rampart:
        return raise_rampart(
            self.middle,
            caster_sheet=None,
            element_profile=RampartElementProfileFactory(name="Stone"),
            integrity=integrity,
            **kwargs,
        )


@override_settings(SEED_SAMPLE_CONTENT=True)  # the Conjured Barrier content gates on it
class ClimbingABarricade(_TheYard):
    """Maren's Barricade seals West - Middle with a climb; Hobb climbs it and walks on."""

    def setUp(self) -> None:
        super().setUp()
        seed_security_check_content()
        ensure_conjured_barrier_content()
        ensure_obstacle_content()
        self.maren = self.fighter("Maren", at=self.middle)
        self.hobb = self.fighter("Hobb", at=self.west)
        CharacterTechniqueFactory(
            character=self.maren.sheet_data,
            technique=Technique.objects.get(name=OBSTACLE_TECHNIQUE_NAME),
        )
        self.let_hobb_climb()

    def let_hobb_climb(self) -> None:
        """A known technique grants Hobb the traversal capability "Climb Over" matches on."""
        climbing = TechniqueFactory(damage_profile=False)
        TechniqueCapabilityGrantFactory(
            technique=climbing,
            capability=CapabilityType.objects.get(name="traversal"),
            base_value=5,
        )
        CharacterTechniqueFactory(character=self.hobb.sheet_data, technique=climbing)

    def raise_the_barricade(self) -> None:
        told = self.telnet(self.maren, "cast Barricade position_a=West,position_b=Middle")
        self.assertNotIn("Could not", told)
        resolve_round(self.encounter, offense_check_fn=_clean_cast)

    def test_a_barricade_is_a_wall_with_a_strength_and_a_way_over(self) -> None:
        self.raise_the_barricade()

        wall = self.edge(self.west, self.middle)
        self.assertFalse(wall.is_passable)
        self.assertGreaterEqual(wall.integrity, CONJURED_WALL_BASE_INTEGRITY)
        self.assertEqual(wall.integrity, wall.max_integrity)
        self.assertEqual(wall.gating_challenge.template.name, CONJURED_BARRIER_CHALLENGE_NAME)

        told = self.telnet(self.hobb, "position Middle")
        self.assertIn(GATED, told)
        self.assertEqual(position_of(self.hobb), self.west)

        names = [action.display_name for action in get_player_actions(self.hobb)]
        self.assertIn(f"Move to Middle (blocked: {CONJURED_BARRIER_CHALLENGE_NAME})", names)

    def test_hobb_climbs_the_barricade_and_walks_through(self) -> None:
        self.raise_the_barricade()
        gate = self.edge(self.west, self.middle).gating_challenge
        climb = ChallengeApproach.objects.get(
            challenge_template=gate.template, display_name="Climb Over"
        )

        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            dispatch_player_action(
                self.hobb,
                ActionRef(
                    backend=ActionBackend.CHALLENGE,
                    challenge_instance_id=gate.pk,
                    approach_id=climb.pk,
                ),
                {},
            )

        self.assertFalse(ChallengeInstance.objects.get(pk=gate.pk).is_active)
        told = self.telnet(self.hobb, "position Middle")
        self.assertNotIn(GATED, told)
        self.assertEqual(position_of(self.hobb), self.middle)


class ADistinctionClimbsTheBarricade(ClimbingABarricade):
    """Hobb climbs by a Wall-Runner distinction, not a technique, and is offered Climb Over.

    The distinction's one effect raises traversal by 4 at rank 1 through the capability's
    modifier target, the way a species gift or worn gear raises a capability.
    """

    def let_hobb_climb(self) -> None:
        traversal = CapabilityType.objects.get(name="traversal")
        target = ModifierTarget.objects.filter(target_capability=traversal).first()
        if target is None:
            target = ModifierTargetFactory(
                name="traversal",
                category=ModifierCategoryFactory(name="capability"),
                target_capability=traversal,
            )
        wall_runner = DistinctionFactory(name="Wall-Runner")
        DistinctionEffectFactory(distinction=wall_runner, target=target, value_per_rank=WALL_RUNNER)
        grant_distinction(self.hobb.sheet_data, wall_runner, origin=DistinctionOrigin.GM_AWARD)

    def test_a_distinction_climber_is_offered_climb_over(self) -> None:
        self.raise_the_barricade()
        gate = self.edge(self.west, self.middle).gating_challenge
        climb = ChallengeApproach.objects.get(
            challenge_template=gate.template, display_name="Climb Over"
        )

        offered = [
            action
            for action in get_player_actions(self.hobb)
            if action.ref.backend == ActionBackend.CHALLENGE and action.ref.approach_id == climb.pk
        ]

        self.assertEqual(len(offered), 1, [a.display_name for a in offered])
        self.assertEqual(offered[0].ref.challenge_instance_id, gate.pk)

    def test_two_ways_to_climb_offer_one_climb_rolled_with_the_stronger(self) -> None:
        """A Sure Grip condition (+2 traversal) beside Wall-Runner (+4): one entry, rolls 4."""
        sure_grip = ConditionTemplateFactory(name="Sure Grip")
        ConditionCapabilityEffectFactory(
            condition=sure_grip,
            capability=CapabilityType.objects.get(name="traversal"),
            value=SURE_GRIP,
        )
        apply_condition(self.hobb, sure_grip)
        self.raise_the_barricade()
        gate = self.edge(self.west, self.middle).gating_challenge
        climb = ChallengeApproach.objects.get(
            challenge_template=gate.template, display_name="Climb Over"
        )

        names = [action.display_name for action in get_player_actions(self.hobb)]
        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            patch(CHALLENGE_PERFORM_CHECK, wraps=perform_check) as rolled,
        ):
            dispatch_player_action(
                self.hobb,
                ActionRef(
                    backend=ActionBackend.CHALLENGE,
                    challenge_instance_id=gate.pk,
                    approach_id=climb.pk,
                ),
                {},
            )

        self.assertEqual(names.count("Climb Over"), 1, names)
        self.assertEqual(rolled.call_args.kwargs["extra_modifiers"], WALL_RUNNER)
        self.assertFalse(ChallengeInstance.objects.get(pk=gate.pk).is_active)


class AHardSeal(_TheYard):
    """A sealed edge with no challenge is shut to anyone on foot."""

    def test_a_sealed_edge_with_no_way_over_stays_shut(self) -> None:
        hobb = self.fighter("Hobb", at=self.west)
        create_conjured_obstacle(self.west, self.middle, caster_sheet=hobb.sheet_data, integrity=12)

        self.assertIn(BLOCKED, self.telnet(hobb, "position Middle"))
        self.assertEqual(position_of(hobb), self.west)


class ARampartFalls(_TheYard):
    """A Stone Rampart at Middle seals both of its edges; however it ends, they open."""

    def setUp(self) -> None:
        super().setUp()
        self.brenna = self.fighter("Brenna", at=self.middle)

    def assertSealed(self, a, b) -> None:  # noqa: N802 - unittest style
        self.assertFalse(self.edge(a, b).is_passable)

    def brute_swings_at_brenna(self) -> None:
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            base_damage=BRUTE_SWING,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        CombatOpponentFactory(
            encounter=self.encounter, threat_pool=pool, health=50, max_health=50, soak_value=0
        )
        resolve_round(self.encounter, defense_check_fn=_full_swing)

    def test_a_brutes_swing_breaks_the_rampart_and_brenna_walks_out(self) -> None:
        rampart = self.stone_rampart()
        self.assertSealed(self.west, self.middle)
        self.assertSealed(self.middle, self.east)
        self.assertIn(BLOCKED, self.telnet(self.brenna, "position West"))

        self.brute_swings_at_brenna()

        self.assertFalse(Rampart.objects.filter(pk=rampart.pk).exists())
        self.next_round()
        # Both edges the Rampart sealed are open moves in her list; she has one hop to spend.
        open_moves = {
            action.display_name
            for action in get_player_actions(self.brenna)
            if action.ref.registry_key == "move_to_position" and action.prerequisite_met
        }
        self.assertEqual(open_moves, {"Move to West", "Move to East"})
        self.telnet(self.brenna, "position West")
        self.assertEqual(position_of(self.brenna), self.west)

    def test_an_edge_a_later_barricade_took_stays_sealed_when_the_rampart_falls(self) -> None:
        self.stone_rampart()
        create_conjured_obstacle(
            self.middle, self.east, caster_sheet=self.brenna.sheet_data, integrity=12
        )

        self.brute_swings_at_brenna()
        self.next_round()

        self.assertIn(BLOCKED, self.telnet(self.brenna, "position East"))
        self.assertEqual(position_of(self.brenna), self.middle)
        self.telnet(self.brenna, "position West")
        self.assertEqual(position_of(self.brenna), self.west)

    def test_a_ward_clash_that_drains_the_rampart_opens_its_edges(self) -> None:
        rampart = self.stone_rampart(integrity=CLASH_RAMPART_INTEGRITY)
        clash = WardClashFactory(
            encounter=self.encounter,
            progress=rampart.integrity,
            pc_win_threshold=20,
            triggering_threat_entry=ThreatPoolEntryFactory(clash_npc_pressure=CLASH_PRESSURE),
            rampart=rampart,
            started_round=1,
        )

        run_clash_round(
            clash=clash,
            round_number=2,
            pc_contributions=[],
            config_clash=ClashConfigFactory(),
            config_strain=StrainConfigFactory(),
        )

        self.assertFalse(Rampart.objects.filter(pk=rampart.pk).exists())
        self.telnet(self.brenna, "position East")
        self.assertEqual(position_of(self.brenna), self.east)

    def test_a_rampart_that_runs_out_its_rounds_opens_its_edges(self) -> None:
        hobb = self.fighter("Hobb", at=self.west)
        self.stone_rampart(duration_rounds=1)
        self.assertIn(BLOCKED, self.telnet(hobb, "position Middle"))

        resolve_round(self.encounter)

        self.assertFalse(Rampart.objects.filter(position=self.middle).exists())
        self.telnet(hobb, "position Middle")
        self.assertEqual(position_of(hobb), self.middle)

    def test_finishing_the_scene_tears_the_rampart_down(self) -> None:
        self.stone_rampart()
        # The fight's scene is the one running here; Brenna started it, so she owns it.
        SceneOwnerParticipationFactory(
            scene=self.encounter.scene, account=self.account_of(self.brenna)
        )

        self.assertIn("The scene comes to a close.", self.telnet(self.brenna, "scene finish"))

        self.assertFalse(Rampart.objects.filter(position=self.middle).exists())
        self.telnet(self.brenna, "position West")
        self.assertEqual(position_of(self.brenna), self.west)
