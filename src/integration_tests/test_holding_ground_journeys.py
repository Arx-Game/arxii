"""Journeys for held ground (#4663, slice 2 of #4651).

A ready enemy holds the place it stands in. A walker who steps into a held place stops
there for the round; one who starts the round there may walk out. A flier passes over it,
and so does a leaper. NPCs obey the same rule when they route toward player characters.

The causeway is five positions in a row, Lane - Gate - Yard - Hall - Tower, joined by open
edges, with a fight in DECLARING round 1.

- Kit has three hops a round (movement 5 + 10 = 15, five points a hop). A Bandit stands in
  the Yard. Kit walks from the Gate into the Yard and is told "You are stopped by Bandit.";
  she has no hops left, and a step on to the Hall is refused.
- A Bandit already DEFEATED holds nothing: Kit walks into the Yard and keeps two hops.
- Kit starting the round in the Yard beside the Bandit walks out to the Hall for one hop.
- Kit in the air above the Gate flies on above the Yard and is not stopped.
- Kit's move list marks the Yard: "Held by Bandit: you'd stop there."
- Kit climbs a Thorn Hedge (a 2-hop crossing) onto the Ledge the Bandit holds: her
  three hops are spent once, all of them, not two and then three more.
- A Bandit fighting on Kit's side (ALLY) holds nothing against her.
- A Grey Wolf (three hops) at the Tower goes for Wren at the Lane. Hobb stands in the
  Yard between them: the walking wolf stops in the Yard. A leaping wolf goes past him to
  the Gate, beside Wren. With Hobb unconscious, the walking wolf goes past him too. A
  Bandit fighting on the players' side in the Yard stops the walking wolf the same way.
- A broken Bandit in the Yard backs away from Hobb in the Hall. The far end past Hobb
  (Tower - Spire - Peak - Summit) is farther, but Hobb holds the way: it heads for the
  Lane instead of being cornered.

Expected values are the rows built here; "You are stopped by {name}." and
"Held by {name}: you'd stop there." are the spec's copy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.player_interface import get_player_actions
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.combat.constants import (
    CombatAllegiance,
    OpponentMoveKind,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatOpponentMove,
    CombatParticipant,
    MovementConfig,
)
from world.combat.services import resolve_round, select_npc_actions
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.combat.services.movement_budget import hops_left
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.magic.factories import CharacterAnimaFactory
from world.mechanics.factories import (
    AerialPropertyFactory,
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
    ModifierCategoryFactory,
)
from world.mechanics.models import (
    ChallengeInstance,
    CharacterModifier,
    ModifierSource,
    ModifierTarget,
)
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities, ensure_unconscious_condition
from world.vitals.services import can_act

FULL_HEALTH = 100
BITE = 10
EXTRA_MOVEMENT = 10  # baseline 5 + 10 = 15 movement = 3 hops a round
CAPABILITY_RAISE = 3
STOPPED_BY = "You are stopped by {name}."
HELD_BY = "Held by {name}: you'd stop there."
NO_MOVEMENT_LEFT = "You have no movement left this round."
GOT_PAST = "You get past {name}."
GOT_PAST_PARTLY = "You get past {name}, but not cleanly."
STOPS_YOU = "{name} stops you."
NO_WAY_PAST = "There is no way past them."
GET_PAST_ENTRY = "Get past {name} into {place}"
STUMBLE = 5  # the partial pass's authored strike, below the interpose threshold (10)
CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"


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
        with override_settings(SEED_SAMPLE_CONTENT=True):  # movement and awareness
            ensure_foundational_capabilities()
        AerialPropertyFactory()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.flight = CapabilityTypeFactory(
            name="winged flight", innate_baseline=0, traversal=CreatureTraversal.FLIES
        )
        self.climbing = CapabilityTypeFactory(
            name="climbing", innate_baseline=0, traversal=CreatureTraversal.CLIMBS
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

    def raise_capability(self, character, capability: CapabilityType, value: int) -> None:
        """A modifier on the sheet (the species/distinction shape) raising ``capability``."""
        target, _ = ModifierTarget.objects.get_or_create(
            name=f"capability_{capability.pk}",
            category=ModifierCategoryFactory(name="capability"),
            defaults={
                "description": "",
                "display_order": 0,
                "is_active": True,
                "target_capability": capability,
            },
        )
        CharacterModifier.objects.create(
            character=character.sheet_data,
            target=target,
            value=value,
            source=ModifierSource.objects.create(),
        )

    def fighter(self, name: str, *, at, flies: bool = False, climbs: bool = False):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=FULL_HEALTH, max_health=FULL_HEALTH, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        self.raise_capability(character, movement, EXTRA_MOVEMENT)
        if flies:
            self.raise_capability(character, self.flight, CAPABILITY_RAISE)
        if climbs:
            self.raise_capability(character, self.climbing, CAPABILITY_RAISE)
        place_in_position(character, at)
        return character

    def creature(
        self, name: str, *, at, hops: int = 1, traversal: str = CreatureTraversal.WALKS
    ) -> CombatOpponent:
        """An enemy spawned from its bestiary entry at ``at``, with one bite of 10."""
        pool = ThreatPoolFactory(name=f"{name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{name} strike",
            base_damage=BITE,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        template = CreatureTemplateFactory(
            name=name,
            tier=OpponentTier.MOOK,
            threat_pool=pool,
            speed_hops=hops,
            traversal=traversal,
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=character.sheet_data
        )

    def on_our_side(self, opponent: CombatOpponent) -> CombatOpponent:
        opponent.allegiance = CombatAllegiance.ALLY
        opponent.save(update_fields=["allegiance"])
        return opponent

    def resolve(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_strength, offense_check_fn=_clean_hit)


class AWalkerStopsInHeldGround(_TheCauseway):
    def test_walker_entering_held_ground_stops(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate)

        result = self.web(kit, "move_to_position", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("stopped", result.detail.message)
        self.assertIn(STOPPED_BY.format(name="Bandit"), result.detail.message)
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(hops_left(self.participant(kit)), 0)

        onward = self.web(kit, "move_to_position", position_id=self.hall.pk)

        self.assertFalse(onward.detail.success)
        self.assertEqual(position_of(kit), self.yard)

    def test_defeated_or_unconscious_holder_holds_nothing(self) -> None:
        bandit = self.creature("Bandit", at=self.yard)
        bandit.status = OpponentStatus.DEFEATED
        bandit.save(update_fields=["status"])
        kit = self.fighter("Kit", at=self.gate)

        result = self.web(kit, "move_to_position", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertNotIn("stopped", result.detail.message or "")
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(hops_left(self.participant(kit)), 2)

    def test_starting_in_held_ground_can_leave(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.yard)

        result = self.web(kit, "move_to_position", position_id=self.hall.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(kit), self.hall)
        self.assertEqual(self.participant(kit).hops_used, 1)

    def test_aerial_mover_is_not_stopped(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate, flies=True)
        self.telnet(kit, "position/fly")
        above_yard = self.room.positions.get(kind=PositionKind.AERIAL, elevation_anchor=self.yard)

        result = self.web(kit, "move_to_position", position_id=above_yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertNotIn("stopped", result.detail.message or "")
        self.assertEqual(position_of(kit), above_yard)
        self.assertEqual(self.participant(kit).hops_used, 2)

    def test_a_climb_into_held_ground_spends_the_hops_once(self) -> None:
        ledge = PositionFactory(room=self.room, name="Ledge")
        hedge = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name="Thorn Hedge"), location=self.room
        )
        connect_positions(self.gate, ledge, is_passable=False, gating_challenge=hedge)
        self.creature("Bandit", at=ledge)
        kit = self.fighter("Kit", at=self.gate, climbs=True)

        result = self.web(kit, "move_to_position", position_id=ledge.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, STOPPED_BY.format(name="Bandit"))
        self.assertEqual(position_of(kit), ledge)
        self.assertEqual(self.participant(kit).hops_used, 3)  # all three, spent once
        self.assertEqual(hops_left(self.participant(kit)), 0)

    def test_an_opponent_on_her_side_holds_nothing(self) -> None:
        self.on_our_side(self.creature("Bandit", at=self.yard))
        kit = self.fighter("Kit", at=self.gate)

        result = self.web(kit, "move_to_position", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertNotIn("stopped", result.detail.message or "")
        self.assertEqual(self.participant(kit).hops_used, 1)

    def test_move_list_marks_held_places(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate)

        moves = {action.display_name: action for action in get_player_actions(kit)}

        self.assertEqual(moves["Move to Yard"].description, HELD_BY.format(name="Bandit"))
        self.assertNotEqual(moves["Move to Lane"].description, HELD_BY.format(name="Bandit"))


class AnNpcStopsInHeldGround(_TheCauseway):
    """A wolf at the Tower goes for Wren at the Lane; Hobb stands in the Yard between."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.yard)
        self.wren = self.fighter("Wren", at=self.lane)

    def wolf_going_for_wren(self, traversal: str) -> CombatOpponent:
        wolf = self.creature("Grey Wolf", at=self.tower, hops=3, traversal=traversal)
        bite = CombatOpponentAction.objects.create(
            opponent=wolf, round_number=1, threat_entry=wolf.threat_pool.entries.get()
        )
        bite.targets.set([self.participant(self.wren)])
        return wolf

    def test_npc_walker_stops_at_a_pc_holding_the_way(self) -> None:
        wolf = self.wolf_going_for_wren(CreatureTraversal.WALKS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.yard)

    def test_npc_leaper_passes_held_ground(self) -> None:
        wolf = self.wolf_going_for_wren(CreatureTraversal.LEAPS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.gate)

    def test_a_planning_pass_reads_held_ground_once_for_every_opponent(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for index in range(3):
            self.creature(f"Grey Wolf {index}", at=self.tower, hops=3)

        with CaptureQueriesContext(connection) as queries:
            select_npc_actions(self.encounter)

        # The one read of where each side's opponents stand (it selects their allegiance
        # beside their places), shared by all three wolves' plans.
        reads = [
            q["sql"]
            for q in queries.captured_queries
            if "objectposition" in q["sql"].lower()
            and "combatopponent" in q["sql"].lower()
            and '"allegiance"' in q["sql"].lower()
        ]
        self.assertEqual(len(reads), 1, reads)

    def test_an_unconscious_pc_holds_nothing(self) -> None:
        with override_settings(SEED_SAMPLE_CONTENT=True):
            unconscious = ensure_unconscious_condition()
        apply_condition(self.hobb, unconscious)
        self.assertFalse(can_act(self.hobb.sheet_data))
        wolf = self.wolf_going_for_wren(CreatureTraversal.WALKS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.gate)


class AnAllyHoldsTheWay(_TheCauseway):
    """No player stands between: a Bandit fighting on the players' side holds the Yard."""

    def test_an_ally_opponent_stops_an_enemy_walker(self) -> None:
        wren = self.fighter("Wren", at=self.lane)
        bandit = self.on_our_side(self.creature("Bandit", at=self.yard))
        wolf = self.creature("Grey Wolf", at=self.tower, hops=3)
        bite = CombatOpponentAction.objects.create(
            opponent=wolf, round_number=1, threat_entry=wolf.threat_pool.entries.get()
        )
        bite.targets.set([self.participant(wren)])

        self.resolve()

        # The bandit may step up to meet it first; wherever it stands, the wolf stops there
        # and never reaches the Gate beside Wren.
        self.assertEqual(position_of(wolf.objectdb), position_of(bandit.objectdb))
        self.assertNotEqual(position_of(wolf.objectdb), self.gate)


class ABrokenBanditBacksAwayPastHeldGround(_TheCauseway):
    def test_a_broken_walker_heads_for_the_farthest_place_it_can_reach(self) -> None:
        spire = PositionFactory(room=self.room, name="Spire")
        peak = PositionFactory(room=self.room, name="Peak")
        summit = PositionFactory(room=self.room, name="Summit")
        connect_positions(self.tower, spire)
        connect_positions(spire, peak)
        connect_positions(peak, summit)
        self.fighter("Hobb", at=self.hall)
        bandit = self.creature("Bandit", at=self.yard)
        bandit.morale = 20  # at or below BREAK_MORALE_THRESHOLD (25)
        bandit.save(update_fields=["morale"])

        self.resolve()

        # From the Hall the Summit is four away and the Lane three; Hobb holds the way to
        # the Summit, so the bandit backs off toward the Lane rather than being cornered.
        plan = CombatOpponentMove.objects.get(opponent=bandit, round_number=1)
        self.assertEqual(plan.kind, OpponentMoveKind.RETREAT)
        self.assertEqual(plan.goal_position, self.lane)


class AnAcrobatGetsPast(_TheCauseway):
    """Kit, tumbling by a Tumbler's Poise condition, rolls to get past the Bandit in the Yard.

    The pass challenge is "Slip Past", designated on MovementConfig, with one approach by
    acrobatics. Its partial outcome carries a 5-point stumble (DEAL_DAMAGE on the roller).
    Kit has three hops; the pass costs one, and being stopped spends them all.
    """

    def setUp(self) -> None:
        super().setUp()
        self.acrobatics = CapabilityTypeFactory(name="acrobatics", innate_baseline=0)
        self.slip_past = ChallengeTemplateFactory(name="Slip Past")
        ChallengeApproachFactory(
            challenge_template=self.slip_past,
            application=ApplicationFactory(name="Tumble", capability=self.acrobatics),
            display_name="Tumble past",
        )
        self.clean = CheckOutcomeFactory(name="Slip-Clean", success_level=1)
        self.partly = CheckOutcomeFactory(name="Slip-Partial", success_level=0)
        self.stopped = CheckOutcomeFactory(name="Slip-Stopped", success_level=-1)
        stumble = ConsequenceFactory(outcome_tier=self.partly, label="Stumble past")
        ConsequenceEffectFactory(
            consequence=stumble,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=STUMBLE,
            damage_type=DamageTypeFactory(name="blunt"),
            target="self",
        )
        ChallengeTemplateConsequenceFactory(challenge_template=self.slip_past, consequence=stumble)
        self.poise = ConditionTemplateFactory(name="Tumbler's Poise")
        ConditionCapabilityEffectFactory(condition=self.poise, capability=self.acrobatics, value=10)
        self.bandit = self.creature("Bandit", at=self.yard)

    def designate(self) -> None:
        MovementConfig.objects.create(pk=1, held_ground_challenge=self.slip_past)

    def acrobat(self, name: str = "Kit"):
        character = self.fighter(name, at=self.gate)
        apply_condition(character, self.poise)
        return character

    def roll(self, outcome):
        def forced(_character, check_type, *_args: object, **_kwargs: object) -> CheckResult:
            return CheckResult(
                check_type=check_type,
                outcome=outcome,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        return patch(CHALLENGE_PERFORM_CHECK, side_effect=forced)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def test_acrobat_passes_held_ground_cleanly(self) -> None:
        self.designate()
        kit = self.acrobat()

        with self.roll(self.clean):
            result = self.web(kit, "pass_held_ground", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, GOT_PAST.format(name="Bandit"))
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(self.health(kit), FULL_HEALTH)
        # One-shot: the minted pass challenge is spent.
        minted = ChallengeInstance.objects.get(template=self.slip_past)
        self.assertEqual(minted.target_object, self.bandit.objectdb)
        self.assertFalse(minted.is_active)

        onward = self.web(kit, "move_to_position", position_id=self.hall.pk)

        self.assertTrue(onward.detail.success, onward.detail.message)
        self.assertEqual(position_of(kit), self.hall)

    def test_acrobat_passes_held_ground_partially(self) -> None:
        self.designate()
        kit = self.acrobat()

        with self.roll(self.partly):
            result = self.web(kit, "pass_held_ground", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, GOT_PAST_PARTLY.format(name="Bandit"))
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(self.health(kit), FULL_HEALTH - STUMBLE)

    def test_acrobat_is_stopped(self) -> None:
        self.designate()
        kit = self.acrobat()

        with self.roll(self.stopped):
            result = self.web(kit, "pass_held_ground", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, STOPS_YOU.format(name="Bandit"))
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 3)
        self.assertEqual(hops_left(self.participant(kit)), 0)

    def test_no_pass_offered_without_config(self) -> None:
        kit = self.acrobat()

        moves = [action.display_name for action in get_player_actions(kit)]
        result = self.web(kit, "pass_held_ground", position_id=self.yard.pk)

        self.assertFalse([name for name in moves if name.startswith("Get past")], moves)
        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, NO_WAY_PAST)
        self.assertEqual(position_of(kit), self.gate)
        self.assertEqual(self.participant(kit).hops_used, 0)

    def test_pass_is_offered_by_capability(self) -> None:
        self.designate()
        kit = self.acrobat()
        wren = self.fighter("Wren", at=self.gate)

        kit_moves = {action.display_name: action for action in get_player_actions(kit)}
        wren_moves = [action.display_name for action in get_player_actions(wren)]

        entry = kit_moves[GET_PAST_ENTRY.format(name="Bandit", place="Yard")]
        self.assertEqual(entry.ref.registry_key, "pass_held_ground")
        self.assertEqual(entry.ref.position_id, self.yard.pk)
        self.assertTrue(entry.prerequisite_met)
        self.assertFalse([name for name in wren_moves if name.startswith("Get past")], wren_moves)

    def test_pass_by_telnet(self) -> None:
        self.designate()
        kit = self.acrobat()

        with self.roll(self.clean):
            said = self.telnet(kit, "position/pass Yard")

        self.assertIn(GOT_PAST.format(name="Bandit"), said)
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 1)
