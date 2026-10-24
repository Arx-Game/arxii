"""Journeys for how enemies fight by their wits (#4609, slice 4 of #4576).

Enemies are spawned from bestiary entries the way staff spawn them
(``spawn_from_creature_template`` with a position); each entry says how cleverly the
creature fights (mindless, cunning, tactical), how far it moves and how it crosses
ground. The players act through the seams they use: the web client's combat action,
telnet ``position`` and ``combat await``.

- A wall splits a pack (Scenario 1). Two cunning wolves and a mindless brute batter a
  conjured wall the three of them can bring down in time; it gives way in the first
  round and the pack is on Hobb next round. A wall too strong for them sends a cunning
  wolf the long way round, while the mindless brute batters it anyway.
- An archer in the air shoots an ogre that cannot hit back (Scenario 5): the ogre runs
  for the roofed barn, and so does a mindless construct, since cover is instinct. With
  no roof anywhere, the unanswered arrow costs the ogre the tuning row's morale and
  nothing else, and a blow it can answer costs none.
- A cunning ogre with a net brings the flying archer down with it; a mindless construct
  with the same net never throws it.
- At a wall too strong for it with no way round, a cunning wolf waits once, then batters
  the wall anyway; a mindless brute batters it at once.
- Shut away behind a wall nothing can break, a cunning wolf waits for an opening once,
  then strains against the wall; a mindless construct never waits.
- A wolf shut in a pen it cannot climb out of waits for an opening, and meets Hobb's
  mounted charge with its own waiting strike before his blow lands.
- Hobb holds a screened gate (Scenario 7). Archers who cannot see him walk out into the
  open within two rounds, and the first to arrive takes his waiting strike.
- A broken bandit backs away over the map, a hop a round, and leaves after two rounds of
  it; a broken bandit with nowhere farther to go is cornered and fights.

Expected values come from the rows built here and the spec (#4576 slice 4): a mortal
has 1 hop a round; MELEE reaches the same or an adjacent position over an open edge and
MISSILE anywhere in the room unless a roof or screen stops it; a group bashes when the
wall's integrity is at most ``bash_rounds_limit`` (3) times its summed best melee chips;
a broken opponent leaves after ``retreat_rounds_limit`` (2) rounds of retreating; an
unanswered hit takes ``unanswered_hit_morale`` (10); the copy strings "{name} batters
{barrier}.", "{barrier} gives way.", "{name} waits for an opening.", "{name} strains
against {barrier}.", "{name} flees the fight." and "{name} moves to {position}.".
"""

from __future__ import annotations

from itertools import pairwise
from unittest.mock import MagicMock

from django.test import override_settings

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory, ConsequencePoolEntryFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import Position, PositionEdge
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    enter_aerial,
    is_aerial,
    place_in_position,
    position_of,
    set_position_cover,
    strike_reaches,
)
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.combat.constants import (
    ActionCategory,
    CreatureTactics,
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
    CombatOpponentMove,
    CombatParticipant,
    NpcTacticsConfig,
    PendingOpponentAttack,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.companions.mount_content import MOUNTED_CONDITION_NAME, ensure_mount_conditions
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.mechanics.factories import (
    AerialPropertyFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
)
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

FULL_HEALTH = 100
BARRIER = "Conjured Barrier"
BATTERS = "{name} batters {barrier}."
GIVES_WAY = "{barrier} gives way."
WAITS = "{name} waits for an opening."
STRAINS = "{name} strains against {barrier}."
FLEES = "{name} flees the fight."
MOVES_TO = "{name} moves to {position}."
WAITING_STRIKE = "{name} meets {mover} with a waiting strike."
UNANSWERED = 10  # NpcTacticsConfig.unanswered_hit_morale's starting value


def _full_strength(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll at success level 0, which takes the blow at full strength."""
    return MagicMock(success_level=0)


def _clean_hit(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands a PC's strike."""
    return MagicMock(success_level=2)


class _TheField(JourneyCase):
    """A room with no positions yet, a fight in DECLARING round 1, and its people."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # movement, the fall content
            ensure_foundational_capabilities()
            ensure_fall_content()
        AerialPropertyFactory()
        DamageSuccessLevelMultiplierFactory(min_success_level=0, multiplier=1)
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=60, base_soak=0)
        self.room = self.make_room("The Field")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )

    def places(self, *names: str) -> list[Position]:
        """Positions named ``names``, joined in a row by open edges."""
        made = [PositionFactory(room=self.room, name=name) for name in names]
        for here, there in pairwise(made):
            connect_positions(here, there)
        return made

    def fighter(self, name: str, *, at: Position):
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

    def creature(  # noqa: PLR0913 - one keyword per bestiary column a journey varies
        self,
        name: str,
        *,
        at: Position,
        tactics: str = CreatureTactics.CUNNING,
        hops: int = 1,
        traversal: str = CreatureTraversal.WALKS,
        bite: int = 10,
        delivery: str = StrikeDelivery.MELEE,
        windup_rounds: int = 0,
        extra_entry: dict | None = None,
    ) -> CombatOpponent:
        """An enemy spawned from its bestiary entry at ``at``, with one attack of ``bite``."""
        pool = ThreatPoolFactory(name=f"{name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{name} strike",
            base_damage=bite,
            delivery=delivery,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            weight=1,
            windup_rounds=windup_rounds,
        )
        if extra_entry is not None:
            ThreatPoolEntryFactory(
                pool=pool,
                targeting_mode=TargetingMode.SINGLE,
                target_selection=TargetSelection.HIGHEST_THREAT,
                **extra_entry,
            )
        template = CreatureTemplateFactory(
            name=name,
            tier=OpponentTier.MOOK,
            threat_pool=pool,
            tactics=tactics,
            speed_hops=hops,
            traversal=traversal,
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def conjured_wall(self, a: Position, b: Position, *, integrity: int) -> PositionEdge:
        """A conjured wall with a climb past it, as a Barricade leaves one."""
        gate = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name=BARRIER),
            location=self.room,
            target_object=self.room,
        )
        return create_conjured_obstacle(
            a, b, caster_sheet=None, integrity=integrity, gating_challenge=gate
        )

    def declare_strike(self, character, technique, opponent: CombatOpponent) -> None:
        declared = dispatch_player_action(
            character,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
            ),
            {"effort_level": "medium", "focused_opponent_target_id": opponent.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def resolve(self):
        return resolve_round(
            self.encounter, defense_check_fn=_full_strength, offense_check_fn=_clean_hit
        )

    def next_round(self) -> None:
        begin_declaration_phase(self.encounter)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def where(self, opponent: CombatOpponent) -> Position | None:
        return position_of(opponent.objectdb)

    def fresh(self, opponent: CombatOpponent) -> CombatOpponent:
        opponent.refresh_from_db()
        return opponent

    def edge(self, a: Position, b: Position) -> PositionEdge:
        lo, hi = (a, b) if a.pk < b.pk else (b, a)
        return PositionEdge.objects.get(position_a=lo, position_b=hi)

    def plan(self, opponent: CombatOpponent, round_number: int = 1) -> CombatOpponentMove:
        return CombatOpponentMove.objects.get(opponent=opponent, round_number=round_number)

    def rows_with(self, character, needle: str) -> list[str]:
        return [row for row in self.mailbox(character).rows if needle in row]

    def row_index(self, character, needle: str) -> int:
        rows = self.mailbox(character).rows
        for index, row in enumerate(rows):
            if needle in row:
                return index
        self.fail(f"{character.key} was never pushed a row with {needle!r}. Rows:\n{rows}")
        return -1


class AWallSplitsAPack(_TheField):
    """Scenario 1: West - Middle - East, Hobb at West, the pack at East, a wall at Middle-East."""

    def setUp(self) -> None:
        super().setUp()
        self.west, self.middle, self.east = self.places("West", "Middle", "East")
        self.hobb = self.fighter("Hobb", at=self.west)
        self.grey = self.creature("Grey Wolf", at=self.east, hops=2, bite=4)
        self.brute = self.creature(
            "Hulking Brute", at=self.east, tactics=CreatureTactics.MINDLESS, bite=9
        )

    def test_the_pack_batters_the_wall_down_in_one_round_and_is_on_hobb_the_next(self) -> None:
        self.dun = self.creature("Dun Wolf", at=self.east, hops=2, bite=4)
        # 4 + 4 + 9 = 17 a round against 12: well inside three rounds, so all three bash.
        self.conjured_wall(self.middle, self.east, integrity=12)

        self.resolve()

        wall = self.edge(self.middle, self.east)
        self.assertTrue(wall.is_passable)
        self.assertIsNone(wall.integrity)
        self.assertShownRow(self.hobb, GIVES_WAY.format(barrier=BARRIER))
        battered = [
            name
            for name in ("Grey Wolf", "Dun Wolf", "Hulking Brute")
            if self.rows_with(self.hobb, BATTERS.format(name=name, barrier=BARRIER))
        ]
        # Whoever was still to act when it fell walked on through the gap instead.
        self.assertGreaterEqual(len(battered), 2, battered)
        for opponent in (self.grey, self.dun, self.brute):
            name = opponent.name
            did_something = self.rows_with(
                self.hobb, BATTERS.format(name=name, barrier=BARRIER)
            ) or self.rows_with(self.hobb, f"{name} moves to")
            self.assertTrue(did_something, f"{name} idled. Rows:\n{self.mailbox(self.hobb).rows}")

        self.next_round()
        self.resolve()

        # The wall bought one round. Every one of them now stands beside Hobb at the Middle.
        for opponent in (self.grey, self.dun, self.brute):
            self.assertEqual(self.where(opponent), self.middle, opponent.name)
        self.assertLess(self.health(self.hobb), FULL_HEALTH)

    def test_a_wall_too_strong_sends_a_wolf_round_while_the_brute_batters_it(self) -> None:
        # The Grey Wolf and the Brute at the wall chip 4 + 9 = 13 a round: 39 in three
        # rounds, short of 40. A way round runs East - Bank - Ford - West.
        bank, ford = (
            PositionFactory(room=self.room, name="Bank"),
            PositionFactory(room=self.room, name="Ford"),
        )
        connect_positions(self.east, bank)
        connect_positions(bank, ford)
        connect_positions(ford, self.west)
        self.conjured_wall(self.middle, self.east, integrity=40)

        self.resolve()

        # The wolf goes the long way: two hops to the Ford, beside Hobb, and bites.
        self.assertEqual(self.where(self.grey), ford)
        self.assertShownRow(self.hobb, MOVES_TO.format(name="Grey Wolf", position="Ford"))
        self.assertFalse(self.rows_with(self.hobb, "Grey Wolf batters"))
        # The brute batters it anyway, though it cannot bring it down in time.
        self.assertShownRow(self.hobb, BATTERS.format(name="Hulking Brute", barrier=BARRIER))
        self.assertEqual(self.edge(self.middle, self.east).integrity, 40 - 9)
        self.assertEqual(self.where(self.brute), self.east)


class AWallTooStrongWithNoWayRound(_TheField):
    """West - Middle - East and a 40-strength wall at Middle-East, the only way to Hobb."""

    def setUp(self) -> None:
        super().setUp()
        self.west, self.middle, self.east = self.places("West", "Middle", "East")
        self.hobb = self.fighter("Hobb", at=self.west)
        self.conjured_wall(self.middle, self.east, integrity=40)

    def test_a_cunning_wolf_waits_once_then_batters_the_wall_anyway(self) -> None:
        # Alone it chips 4 a round: 12 in three rounds, far short of 40, and there is no
        # way round. It judges the wall unbreakable and waits for an opening first.
        wolf = self.creature("Grey Wolf", at=self.east, hops=2, bite=4)

        self.resolve()

        self.assertEqual(self.plan(wolf).kind, OpponentMoveKind.WAIT)
        self.assertShownRow(self.hobb, WAITS.format(name="Grey Wolf"))
        self.assertEqual(self.edge(self.middle, self.east).integrity, 40)

        self.next_round()
        self.resolve()

        # It cannot wait twice running, so it batters the wall it could not break in time.
        self.assertEqual(self.plan(wolf, 2).kind, OpponentMoveKind.BASH)
        self.assertShownRow(self.hobb, BATTERS.format(name="Grey Wolf", barrier=BARRIER))
        self.assertEqual(self.edge(self.middle, self.east).integrity, 40 - 4)

    def test_a_mindless_brute_batters_it_at_once(self) -> None:
        brute = self.creature(
            "Hulking Brute", at=self.east, tactics=CreatureTactics.MINDLESS, bite=9
        )

        self.resolve()

        self.assertEqual(self.plan(brute).kind, OpponentMoveKind.BASH)
        self.assertFalse(self.rows_with(self.hobb, "waits for an opening"))
        self.assertEqual(self.edge(self.middle, self.east).integrity, 40 - 9)


class AnArcherThatCannotBeAnswered(_TheField):
    """Scenario 5: Lane - Yard - Field - Meadow - Moor, a roofed Barn off the Yard."""

    def setUp(self) -> None:
        super().setUp()
        self.lane, self.yard, self.field, self.meadow, self.moor = self.places(
            "Lane", "Yard", "Field", "Meadow", "Moor"
        )
        self.wren = self.fighter("Wren", at=self.moor)
        enter_aerial(self.wren)
        self.bow = self.technique(self.wren, "Longshot", reach=TechniqueReach.ANY)

    def roofed_barn(self) -> Position:
        barn = PositionFactory(room=self.room, name="Barn")
        connect_positions(self.yard, barn)
        set_position_cover(barn, roofed=True, screens_ranged=False)
        return barn

    def assert_runs_for_the_barn(self, tactics: str) -> None:
        barn = self.roofed_barn()
        ogre = self.creature("Ogre", at=self.yard, tactics=tactics)
        self.declare_strike(self.wren, self.bow, ogre)

        self.resolve()

        self.assertEqual(self.plan(ogre).kind, OpponentMoveKind.SHELTER)
        self.assertEqual(self.where(ogre), barn)
        self.assertShownRow(self.wren, MOVES_TO.format(name="Ogre", position="Barn"))
        # Under the roof, nothing Wren looses from the air reaches it.
        self.assertFalse(strike_reaches(position_of(self.wren), barn, StrikeDelivery.MISSILE))

    def test_a_cunning_ogre_runs_for_the_roofed_barn(self) -> None:
        self.assert_runs_for_the_barn(CreatureTactics.CUNNING)

    def test_a_mindless_construct_runs_for_cover_too(self) -> None:
        self.assert_runs_for_the_barn(CreatureTactics.MINDLESS)

    def test_an_unanswered_arrow_costs_morale_and_an_answered_blow_does_not(self) -> None:
        # No roof anywhere: the ogre at the Lane is four hops short of answering Wren.
        hobb = self.fighter("Hobb", at=self.lane)
        lunge = self.technique(hobb, "Lunge")
        ogre = self.creature("Ogre", at=self.lane)
        before = ogre.morale
        self.declare_strike(self.wren, self.bow, ogre)
        self.declare_strike(hobb, lunge, ogre)

        self.resolve()

        ogre = self.fresh(ogre)
        self.assertLess(ogre.health, ogre.max_health)  # both blows landed
        self.assertEqual(before - ogre.morale, UNANSWERED)
        self.assertEqual(NpcTacticsConfig.load().unanswered_hit_morale, UNANSWERED)

    def test_a_duel_mirror_and_a_pool_less_opponent_keep_their_morale(self) -> None:
        # Neither has a threat pool to answer with, so the tactics ladder never judges
        # them: arrows they cannot return shake neither of them.
        hobb = self.fighter("Hobb", at=self.lane)
        mirror = CombatOpponentFactory(
            encounter=self.encounter,
            name="Hobb's Reflection",
            threat_pool=None,
            mirrors_participant_id=CombatParticipant.objects.get(
                character_sheet=hobb.sheet_data
            ).pk,
        )
        spirit = CombatOpponentFactory(
            encounter=self.encounter, name="Thorn Spirit", threat_pool=None
        )
        for opponent in (mirror, spirit):
            place_in_position(opponent.objectdb, self.lane)
        before = {o.pk: o.morale for o in (mirror, spirit)}

        # Four rounds: Wren shoots each of them twice from the air.
        for round_index, opponent in enumerate((mirror, spirit, mirror, spirit)):
            if round_index:
                self.next_round()
            self.declare_strike(self.wren, self.bow, opponent)
            self.resolve()
        for shot in (self.fresh(mirror), self.fresh(spirit)):
            self.assertLess(shot.health, shot.max_health, shot.name)  # the arrows landed
            self.assertEqual(shot.morale, before[shot.pk], shot.name)


class BringingDownAFlier(_TheField):
    """A net that knocks fliers down is a cunning ogre's answer and never a construct's."""

    def setUp(self) -> None:
        super().setUp()
        self.lane, self.yard, self.field, self.meadow, self.moor = self.places(
            "Lane", "Yard", "Field", "Meadow", "Moor"
        )
        self.wren = self.fighter("Wren", at=self.moor)
        enter_aerial(self.wren)
        self.bow = self.technique(self.wren, "Longshot", reach=TechniqueReach.ANY)

    def net(self) -> dict:
        grounds = ConsequenceFactory(label="Tangled and dragged down")
        ConsequenceEffectFactory(
            consequence=grounds, effect_type=EffectType.REMOVE_FLIGHT, target=EffectTarget.TARGET
        )
        pool = ConsequencePoolEntryFactory(consequence=grounds).pool
        return {
            "name": "Weighted Net",
            "base_damage": 2,
            "delivery": StrikeDelivery.MISSILE,
            "on_hit_consequence_pool": pool,
            "weight": 1,
        }

    def test_a_cunning_ogre_throws_its_net_and_wren_falls(self) -> None:
        ogre = self.creature("Ogre", at=self.lane, extra_entry=self.net())
        self.declare_strike(self.wren, self.bow, ogre)

        self.resolve()

        thrown = CombatOpponentAction.objects.get(opponent=ogre, round_number=1)
        self.assertEqual(thrown.threat_entry.name, "Weighted Net")
        self.assertFalse(is_aerial(self.wren))

    def test_a_mindless_construct_never_throws_the_net(self) -> None:
        construct = self.creature(
            "Iron Construct",
            at=self.lane,
            tactics=CreatureTactics.MINDLESS,
            extra_entry=self.net(),
        )
        self.declare_strike(self.wren, self.bow, construct)

        self.resolve()

        self.assertFalse(CombatOpponentAction.objects.filter(opponent=construct).exists())
        self.assertTrue(is_aerial(self.wren))
        # It walks toward her instead.
        self.assertEqual(self.where(construct), self.yard)


class ShutAwayBehindAWall(_TheField):
    """A Pen joined to the Yard only by a staff-built wall nothing can break."""

    def setUp(self) -> None:
        super().setUp()
        (self.yard,) = self.places("Yard")
        self.pen = PositionFactory(room=self.room, name="Pen")
        connect_positions(self.pen, self.yard, is_passable=False)
        self.hobb = self.fighter("Hobb", at=self.yard)

    def test_a_cunning_wolf_waits_once_then_strains_against_the_wall(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.pen)

        self.resolve()

        self.assertEqual(self.plan(wolf).kind, OpponentMoveKind.WAIT)
        self.assertShownRow(self.hobb, WAITS.format(name="Grey Wolf"))

        self.next_round()
        self.resolve()

        # Never twice running: the second round it has nothing left but to strain.
        self.assertEqual(self.plan(wolf, 2).kind, OpponentMoveKind.ADVANCE)
        self.assertShownRow(self.hobb, STRAINS.format(name="Grey Wolf", barrier="the wall"))
        self.assertEqual(len(self.rows_with(self.hobb, WAITS.format(name="Grey Wolf"))), 1)

    def test_a_mindless_construct_never_waits(self) -> None:
        construct = self.creature("Iron Construct", at=self.pen, tactics=CreatureTactics.MINDLESS)

        self.resolve()

        self.assertEqual(self.plan(construct).kind, OpponentMoveKind.ADVANCE)
        self.assertFalse(self.rows_with(self.hobb, "waits for an opening"))
        self.assertShownRow(self.hobb, STRAINS.format(name="Iron Construct", barrier="the wall"))


class AWaitingWolfMeetsACharge(_TheField):
    """Yard - Ledge - Pen. The Pen's edge has a climb on it: a rider can charge across,
    a walking wolf cannot climb out."""

    def setUp(self) -> None:
        super().setUp()
        self.yard, self.ledge = self.places("Yard", "Ledge")
        self.pen = PositionFactory(room=self.room, name="Pen")
        climb = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name="Sheer Rock"),
            location=self.room,
            target_object=self.room,
        )
        connect_positions(self.ledge, self.pen, gating_challenge=climb)
        self.hobb = self.fighter("Hobb", at=self.yard)
        self.lunge = self.technique(self.hobb, "Lunge")
        ensure_mount_conditions()
        apply_condition(self.hobb, ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME))

    def test_the_wolf_holds_its_bite_and_meets_hobbs_charge_first(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.pen)
        told = self.telnet(self.hobb, "combat charge Grey Wolf with Lunge")
        self.assertIn("You spur your mount into a charge!", told)

        self.resolve()

        # No one in its reach and no way out of the Pen: it waited for an opening, and
        # Hobb's charge brought him into it.
        plan = self.plan(wolf)
        self.assertEqual(plan.kind, OpponentMoveKind.WAIT)
        self.assertTrue(plan.fired)
        self.assertEqual(position_of(self.hobb), self.pen)
        met = WAITING_STRIKE.format(name="Grey Wolf", mover="Hobb")
        self.assertShownRow(self.hobb, met)
        # The wolf's strike comes before the charge's own blow ("Hobb's Lunge strikes Grey
        # Wolf for ...").
        self.assertLess(
            self.row_index(self.hobb, met), self.row_index(self.hobb, "strikes Grey Wolf for")
        )
        self.assertEqual(self.health(self.hobb), FULL_HEALTH - 10)
        self.assertLess(self.fresh(wolf).health, self.fresh(wolf).max_health)


class AStandoffAtTheScreenedGate(_TheField):
    """Scenario 7: Lane - Gate - Yard - Hall - Tower; the Gate breaks line of sight."""

    def setUp(self) -> None:
        super().setUp()
        self.lane, self.gate, self.yard, self.hall, self.tower = self.places(
            "Lane", "Gate", "Yard", "Hall", "Tower"
        )
        set_position_cover(self.gate, roofed=False, screens_ranged=True)
        self.hobb = self.fighter("Hobb", at=self.gate)
        self.lunge = self.technique(self.hobb, "Lunge")
        self.archers = [
            self.creature(
                name,
                at=self.tower,
                tactics=CreatureTactics.TACTICAL,
                delivery=StrikeDelivery.MISSILE,
            )
            for name in ("Red Archer", "Black Archer")
        ]

    def test_the_archers_walk_into_the_open_and_the_first_takes_hobbs_waiting_strike(
        self,
    ) -> None:
        self.resolve()

        # No line of sight from the Tower: they come a hop closer and loose nothing.
        for archer in self.archers:
            self.assertEqual(self.where(archer), self.hall)
        self.assertEqual(self.health(self.hobb), FULL_HEALTH)

        self.next_round()
        told = self.telnet(self.hobb, "combat await Lunge")
        self.assertNotIn("cannot", told.lower(), told)
        self.resolve()

        # Within two rounds they stand in the open Yard beside the Gate.
        for archer in self.archers:
            self.assertEqual(self.where(archer), self.yard)
        struck = [
            a.name
            for a in self.archers
            if self.rows_with(self.hobb, WAITING_STRIKE.format(name="Hobb", mover=a.name))
        ]
        self.assertEqual(len(struck), 1, struck)
        self.assertLess(
            self.row_index(self.hobb, WAITING_STRIKE.format(name="Hobb", mover=struck[0])),
            self.row_index(self.hobb, f"{struck[0]}’s "),
        )


class ABrokenBandit(_TheField):
    """Lane - Gate - Yard - Hall - Tower; a bandit at the end of its nerve."""

    def setUp(self) -> None:
        super().setUp()
        self.lane, self.gate, self.yard, self.hall, self.tower, self.moor = self.places(
            "Lane", "Gate", "Yard", "Hall", "Tower", "Moor"
        )

    def broken(self, name: str, *, at: Position) -> CombatOpponent:
        bandit = self.creature(name, at=at)
        bandit.morale = 20  # at or below BREAK_MORALE_THRESHOLD (25)
        bandit.save(update_fields=["morale"])
        return bandit

    def test_it_backs_away_a_hop_a_round_and_leaves_after_two_rounds(self) -> None:
        hobb = self.fighter("Hobb", at=self.lane)
        bandit = self.broken("Bandit", at=self.gate)
        # Hobb steps up to it as the round is declared.
        self.telnet(hobb, "position Gate")

        self.resolve()

        # It heads for the Moor, the far end from Hobb, one hop: the Yard, still beside him.
        self.assertEqual(self.plan(bandit).kind, OpponentMoveKind.RETREAT)
        self.assertEqual(self.where(bandit), self.yard)
        self.assertShownRow(hobb, MOVES_TO.format(name="Bandit", position="Yard"))
        self.assertEqual(self.fresh(bandit).status, OpponentStatus.ACTIVE)

        self.next_round()
        self.telnet(hobb, "position Yard")
        self.resolve()

        # Its second round backing away: it leaves, though Hobb still reaches the Hall.
        self.assertShownRow(hobb, MOVES_TO.format(name="Bandit", position="Hall"))
        self.assertEqual(self.fresh(bandit).status, OpponentStatus.FLED)
        self.assertShownRow(hobb, FLEES.format(name="Bandit"))
        self.assertEqual(self.health(hobb), FULL_HEALTH)  # it never struck while backing off

    def test_it_leaves_at_once_when_one_hop_takes_it_out_of_reach(self) -> None:
        hobb = self.fighter("Hobb", at=self.gate)
        bandit = self.broken("Bandit", at=self.yard)

        self.resolve()

        # One hop, to the Hall, puts it out of Hobb's reach at the Gate: it is gone.
        self.assertShownRow(hobb, MOVES_TO.format(name="Bandit", position="Hall"))
        self.assertEqual(self.fresh(bandit).status, OpponentStatus.FLED)
        self.assertShownRow(hobb, FLEES.format(name="Bandit"))

    def test_a_bandit_that_breaks_mid_wind_up_lands_the_blow_then_backs_away(self) -> None:
        # Its one attack takes a round to wind up. The telegraph is its action: a broken
        # opponent winding up stands still and writes no plan until the blow lands.
        hobb = self.fighter("Hobb", at=self.gate)
        bandit = self.creature("Bandit", at=self.yard, windup_rounds=1)
        self.resolve()  # round 1: beside Hobb, it winds up
        self.assertTrue(PendingOpponentAttack.objects.filter(opponent=bandit).exists())
        bandit = self.fresh(bandit)
        bandit.morale = 20  # it breaks before the blow lands
        bandit.save(update_fields=["morale"])

        self.next_round()
        self.resolve()  # round 2: the blow lands; no retreat plan, no move, still here

        self.assertEqual(self.health(hobb), FULL_HEALTH - 10)
        self.assertFalse(CombatOpponentMove.objects.filter(opponent=bandit, round_number=2))
        self.assertEqual(self.where(bandit), self.yard)
        self.assertEqual(self.fresh(bandit).status, OpponentStatus.ACTIVE)

        self.next_round()
        self.resolve()  # round 3: the telegraph is spent, so it backs away and is gone

        self.assertEqual(self.plan(bandit, 3).kind, OpponentMoveKind.RETREAT)
        self.assertShownRow(hobb, MOVES_TO.format(name="Bandit", position="Hall"))
        self.assertEqual(self.fresh(bandit).status, OpponentStatus.FLED)
        self.assertEqual(self.health(hobb), FULL_HEALTH - 10)

    def test_a_cornered_bandit_fights(self) -> None:
        # Hobb at the Gate and Wren at the Tower: nowhere on the line is farther from both
        # than the Hall, a hop from each of them.
        hobb = self.fighter("Hobb", at=self.gate)
        wren = self.fighter("Wren", at=self.tower)
        bandit = self.broken("Bandit", at=self.hall)

        self.resolve()

        self.assertEqual(self.fresh(bandit).status, OpponentStatus.ACTIVE)
        self.assertNotEqual(self.plan(bandit).kind, OpponentMoveKind.RETREAT)
        self.assertFalse(self.rows_with(hobb, "Bandit flees"))
        # It fights: one of them takes its blow.
        self.assertLess(self.health(hobb) + self.health(wren), 2 * FULL_HEALTH)
