"""Journeys for one blink power used two ways: a dodge and a move on her turn (#5019, #5066).

The cellar is four places: Doorway - Floor - Gallery - Stage in a ring, every edge open but
Doorway - Stage, which a Thorn Hedge (an active gating challenge) closes. Staff have authored
two applications of the capability ``traversal`` that need the ``teleport`` property:
**Evade** (dodges, landing by blinking) and **Blink** (on her turn she moves by blinking).
Nobody authored a blink capability. Ondrelle knows Blink Step, a technique marked
``teleport`` that grants traversal 10 and costs 2 anima. Her movement is raised to two hops
a round. Every technique roll is forced to a bare success, so each use's strength is 10:
anywhere in the room by the MovementConfig bands (1 / 5 / 10).

- Shot at, she dodges with it to her planned Gallery: a cast of Blink Step, 2 anima, and the
  roll gets her strength 10.
- On her turn the move list offers "Blink to Stage (2 anima)", past the hedge. Taken by web
  dispatch or telnet ``position Stage``, it is a cast of Blink Step: she is on the Stage,
  2 anima and one hop poorer, her reaction count and her declared action untouched, so a
  dodge later that round still gets the full 10.
- A failed technique roll leaves her where she is, paid, with the hop spent.
- Too little anima never stops her (owner ruling 2026-11-08): with 1 anima in a lethal fight
  the entry stays open and she blinks; her pool runs to 0 and the 1 she lacked is drawn as
  Soulfray through the cast's own path. Already frayed, her entry carries her Soulfray stage
  warning, as a cast does.
- Where walking reaches (the Floor), the list offers a walk, not a blink, and it is free.
- Hobb, who walks, keeps "Move to Stage (blocked: Thorn Hedge)" and no blink entries; a
  dodger whose source matches only a dodging application gets no blink entries either.
- Blinking into the Gallery while a Bandit holds it stops her there with no hops left.
- The room is told "Ondrelle blinks to Stage."
- Outside a fight a blink is still a cast of her technique (#5066 decision 9): her control is
  higher out of combat, so it costs nothing ("Blink to Stage"); once she is engaged (intensity
  raised) the same blink costs its 2 anima again.
- Staff authoring an application are offered Blinks and Phases as its way of moving; a
  bestiary entry is offered neither.

Expected values come from the spec (#5019 owner answers 1 to 4; #5066 decisions 3, 4, 9,
11) and the field defaults: one hop per blink; reactions are not counted; the out-of-combat
control bonus is SoulfrayConfig.social_safety_bonus's default 10.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from actions.factories import ActionTemplateFactory
from actions.player_interface import get_player_actions
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
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
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    SoulfrayTemplateFactory,
)
from world.conditions.models import CapabilityType, ConditionInstance
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    ensure_soulfray_config,
)
from world.magic.models.anima import CharacterAnima
from world.mechanics.factories import (
    ChallengeInstanceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
    ModifierCategoryFactory,
    MovementApplicationFactory,
    PropertyFactory,
)
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

HEDGE = "Thorn Hedge"
BLINK_VALUE = 10
EXTRA_MOVEMENT = 5  # baseline 5 + 5 = 10 movement = 2 hops a round
BLINK_TO_STAGE = "Blink to Stage (2 anima)"
EMPTY_POOL_SEVERITY = 10  # SoulfrayConfigFactory: severity_scale 10 at anima 0
DEFICIT_SEVERITY = 5  # deficit_scale 5 x the 1 anima she lacked


class RecordingRoll:
    """A defence roll that returns the given success levels in turn and keeps its kwargs."""

    def __init__(self, *levels: int) -> None:
        self.levels = list(levels)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *_args: object, **kwargs: Any) -> MagicMock:
        self.calls.append(kwargs)
        level = self.levels.pop(0) if self.levels else 0
        return MagicMock(success_level=level)

    def extras(self) -> list[int]:
        return [call["extra_modifiers"] for call in self.calls]


def _clean_hit(*args: object, **kwargs: object) -> MagicMock:
    return MagicMock(success_level=2)


class _TheCellar(JourneyCase):
    """The hedged cellar and a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):
            ensure_foundational_capabilities()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.room = self.make_room("The Cellar")
        self.doorway = PositionFactory(room=self.room, name="Doorway")
        self.floor = PositionFactory(room=self.room, name="Floor")
        self.gallery = PositionFactory(room=self.room, name="Gallery")
        self.stage = PositionFactory(room=self.room, name="Stage")
        connect_positions(self.doorway, self.floor)
        connect_positions(self.floor, self.gallery)
        connect_positions(self.gallery, self.stage)
        hedge = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name=HEDGE), location=self.room
        )
        connect_positions(self.doorway, self.stage, is_passable=False, gating_challenge=hedge)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.defense = CheckTypeFactory(name="Evade")
        self.traversal = CapabilityTypeFactory(name="traversal", innate_baseline=0)
        self.teleport = PropertyFactory(name="teleport")
        MovementApplicationFactory(
            name="Evade",
            capability=self.traversal,
            required_effect_property=self.teleport,
            dodges=True,
            way_of_moving=CreatureTraversal.BLINKS,
        )
        MovementApplicationFactory(
            name="Blink",
            capability=self.traversal,
            required_effect_property=self.teleport,
            way_of_moving=CreatureTraversal.BLINKS,
        )
        self.blink_step = TechniqueFactory(
            name="Blink Step",
            anima_cost=2,
            intensity=1,
            control=1,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Blink Cast")),
        )
        self.blink_step.properties.add(self.teleport)
        TechniqueCapabilityGrantFactory(
            technique=self.blink_step,
            capability=self.traversal,
            base_value=BLINK_VALUE,
            intensity_multiplier=0,
        )
        self.technique_roll = MagicMock(success_level=1)
        patcher = patch(
            "world.combat.services.movement_use.roll_technique",
            side_effect=lambda *_a, **_k: self.technique_roll,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def raise_capability(self, character, capability: CapabilityType, value: int) -> None:
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

    def fighter(  # noqa: PLR0913 - one fighter, her switches
        self, name: str, *, at, blinks: bool = True, in_fight: bool = True, anima=20, engaged=True
    ):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=anima, maximum=20)
        if engaged:
            CharacterEngagementFactory(character=sheet)
        if in_fight:
            CombatParticipantFactory(
                encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
            )
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        self.raise_capability(character, movement, EXTRA_MOVEMENT)
        if blinks:
            CharacterTechniqueFactory(character=sheet, technique=self.blink_step)
        place_in_position(character, at)
        self.watch(character)
        return character

    def enemy(self, name: str, *, at):
        pool = ThreatPoolFactory(name=f"{name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{name} shot",
            base_damage=10,
            delivery=StrikeDelivery.MISSILE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
        )
        template = CreatureTemplateFactory(
            name=name, tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=character.sheet_data
        )

    def anima(self, character) -> int:
        return CharacterAnima.objects.get(character_id=character.sheet_data.pk).current

    def moves(self, character) -> dict[str, Any]:
        return {action.display_name: action for action in get_player_actions(character)}


class OnePowerTwoUses(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.ondrelle = self.fighter("Ondrelle", at=self.doorway)

    def test_she_dodges_with_it_to_her_planned_place(self) -> None:
        self.web(self.ondrelle, "combat_dodge", position_id=self.gallery.pk)
        self.enemy("Archer", at=self.floor)
        roll = RecordingRoll(1)

        resolve_round(self.encounter, defense_check_fn=roll, offense_check_fn=_clean_hit)

        self.assertEqual(roll.extras(), [BLINK_VALUE])
        self.assertEqual(position_of(self.ondrelle), self.gallery)
        self.assertEqual(self.anima(self.ondrelle), 18)

    def test_her_move_list_offers_the_blink_past_the_hedge(self) -> None:
        entry = self.moves(self.ondrelle)[BLINK_TO_STAGE]

        self.assertTrue(entry.prerequisite_met)
        self.assertEqual(entry.ref.registry_key, "move_to_position")
        self.assertEqual(entry.ref.position_id, self.stage.pk)

    def test_blinking_on_her_turn_costs_a_hop_and_anima_and_nothing_else(self) -> None:
        result = self.web(self.ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You blink to Stage for 2 anima.")
        self.assertEqual(position_of(self.ondrelle), self.stage)
        self.assertEqual(self.anima(self.ondrelle), 18)
        seat = self.participant(self.ondrelle)
        self.assertEqual(seat.hops_used, 1)
        self.assertEqual(seat.reactions_used, 0)
        self.assertFalse(CombatRoundAction.objects.filter(participant=seat).exists())

    def test_a_dodge_after_her_blink_is_no_harder(self) -> None:
        self.web(self.ondrelle, "move_to_position", position_id=self.stage.pk)
        self.enemy("Archer", at=self.floor)
        roll = RecordingRoll(1)

        resolve_round(self.encounter, defense_check_fn=roll, offense_check_fn=_clean_hit)

        self.assertEqual(roll.extras(), [BLINK_VALUE])
        self.assertEqual(self.anima(self.ondrelle), 16)  # the blink, then the dodge

    def test_typed_on_telnet(self) -> None:
        told = self.telnet(self.ondrelle, "position Stage")

        self.assertIn("You blink to Stage for 2 anima.", told)
        self.assertEqual(position_of(self.ondrelle), self.stage)
        self.assertEqual(self.anima(self.ondrelle), 18)

    def test_the_room_sees_her_blink(self) -> None:
        hobb = self.fighter("Hobb", at=self.floor, blinks=False)

        self.web(self.ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTold(hobb, "Ondrelle blinks to Stage.")

    def test_where_she_can_walk_she_walks_for_free(self) -> None:
        moves = self.moves(self.ondrelle)
        self.assertIn("Move to Floor", moves)
        self.assertNotIn("Blink to Floor (2 anima)", moves)

        result = self.web(self.ondrelle, "move_to_position", position_id=self.floor.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(self.ondrelle), self.floor)
        self.assertEqual(self.anima(self.ondrelle), 20)

    def test_blinking_into_held_ground_stops_her_there(self) -> None:
        self.enemy("Bandit", at=self.gallery)

        result = self.web(self.ondrelle, "move_to_position", position_id=self.gallery.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(
            result.detail.message, "You blink to Gallery for 2 anima. You are stopped by Bandit."
        )
        self.assertEqual(position_of(self.ondrelle), self.gallery)
        self.assertEqual(self.participant(self.ondrelle).hops_used, 2)


class TheRollSetsHowFar(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.ondrelle = self.fighter("Ondrelle", at=self.doorway)

    def test_a_failed_roll_leaves_her_in_place_paid(self) -> None:
        self.technique_roll = MagicMock(success_level=0)

        result = self.web(self.ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(
            result.detail.message, "Your blink fails; you stay where you are (2 anima)."
        )
        self.assertEqual(position_of(self.ondrelle), self.doorway)
        self.assertEqual(self.anima(self.ondrelle), 18)
        self.assertEqual(self.participant(self.ondrelle).hops_used, 1)


class TooLittleAnima(_TheCellar):
    """Lack of anima never greys out or refuses a blink; it pays through Soulfray."""

    def setUp(self) -> None:
        super().setUp()
        self.soulfray = SoulfrayTemplateFactory()
        ensure_soulfray_config()
        self.encounter.risk_level = RiskLevel.LETHAL
        self.encounter.save(update_fields=["risk_level"])

    def soulfray_on(self, character) -> ConditionInstance | None:
        return ConditionInstance.objects.filter(target=character, condition=self.soulfray).first()

    def test_with_one_anima_she_blinks_and_pays_in_soulfray(self) -> None:
        ondrelle = self.fighter("Ondrelle", at=self.doorway, anima=1)

        entry = self.moves(ondrelle)[BLINK_TO_STAGE]
        self.assertTrue(entry.prerequisite_met)
        self.assertEqual(entry.prerequisite_reasons, [])

        result = self.web(ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You blink to Stage for 2 anima.")
        self.assertEqual(position_of(ondrelle), self.stage)
        self.assertEqual(self.anima(ondrelle), 0)
        self.assertEqual(self.participant(ondrelle).hops_used, 1)
        frayed = self.soulfray_on(ondrelle)
        self.assertIsNotNone(frayed)
        self.assertEqual(frayed.severity, EMPTY_POOL_SEVERITY + DEFICIT_SEVERITY)

    def test_typed_on_telnet_with_one_anima(self) -> None:
        ondrelle = self.fighter("Ondrelle", at=self.doorway, anima=1)

        told = self.telnet(ondrelle, "position Stage")

        self.assertIn("You blink to Stage for 2 anima.", told)
        self.assertEqual(position_of(ondrelle), self.stage)
        self.assertIsNotNone(self.soulfray_on(ondrelle))

    def test_already_frayed_her_blink_carries_the_stage_warning(self) -> None:
        stage = ConditionStageFactory(
            condition=self.soulfray, stage_order=1, name="Fraying", severity_threshold=1
        )
        ondrelle = self.fighter("Ondrelle", at=self.doorway, anima=1)
        ConditionInstanceFactory(
            target=ondrelle, condition=self.soulfray, current_stage=stage, severity=1
        )

        entry = self.moves(ondrelle)[BLINK_TO_STAGE]

        self.assertTrue(entry.prerequisite_met)
        self.assertEqual(entry.soulfray_warning.stage_name, "Fraying")


class OthersDoNotBlink(_TheCellar):
    def test_a_walker_still_sees_the_hedge_block(self) -> None:
        hobb = self.fighter("Hobb", at=self.doorway, blinks=False)

        moves = self.moves(hobb)

        self.assertIn(f"Move to Stage (blocked: {HEDGE})", moves)
        self.assertFalse([name for name in moves if name.startswith("Blink to")])
        refused = self.web(hobb, "move_to_position", position_id=self.stage.pk)
        self.assertFalse(refused.detail.success)
        self.assertEqual(position_of(hobb), self.doorway)

    def test_a_dodge_that_does_not_blink_gives_no_turn_blink(self) -> None:
        """Trained dodging matches a dodging application that needs no property; it gives
        her no turn blink (Blink needs teleport, which training does not carry)."""
        MovementApplicationFactory(
            name="Sidestep",
            capability=self.traversal,
            dodges=True,
            way_of_moving=CreatureTraversal.BLINKS,
        )
        dodger = self.fighter("Malvaine", at=self.doorway, blinks=False)
        self.raise_capability(dodger, self.traversal, BLINK_VALUE)

        moves = self.moves(dodger)

        self.assertFalse([name for name in moves if name.startswith("Blink to")])


class StaffAuthoring(_TheCellar):
    def test_applications_offer_blinks_and_phases_and_bestiary_entries_do_not(self) -> None:
        staff = get_user_model().objects.create_superuser("staff5019", "s@example.com", "pw-5019")
        client = Client()
        client.force_login(staff)

        application = client.get("/admin/arxii/application/add/")
        capability = client.get("/admin/arxii/capabilitytype/add/")
        bestiary = client.get("/admin/arxii/creaturetemplate/add/")

        self.assertEqual(application.status_code, 200)
        self.assertIn('value="blinks"', application.content.decode())
        self.assertIn('value="phases"', application.content.decode())
        self.assertEqual(capability.status_code, 200)
        self.assertNotIn('value="blinks"', capability.content.decode())
        self.assertEqual(bestiary.status_code, 200)
        self.assertNotIn('value="blinks"', bestiary.content.decode())
        self.assertNotIn('value="phases"', bestiary.content.decode())


class OutsideAFight(_TheCellar):
    def test_in_a_calm_scene_her_control_makes_the_cast_free(self) -> None:
        ondrelle = self.fighter("Ondrelle", at=self.doorway, in_fight=False, engaged=False)

        self.assertIn("Blink to Stage", self.moves(ondrelle))
        result = self.web(ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You blink to Stage.")
        self.assertEqual(position_of(ondrelle), self.stage)
        self.assertEqual(self.anima(ondrelle), 20)

    def test_when_the_scene_heats_up_the_same_blink_costs_again(self) -> None:
        """Engaged (a duel of wits, a competition), she loses the out-of-combat control."""
        ondrelle = self.fighter("Ondrelle", at=self.doorway, in_fight=False, engaged=True)

        self.assertIn(BLINK_TO_STAGE, self.moves(ondrelle))
        result = self.web(ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You blink to Stage for 2 anima.")
        self.assertEqual(self.anima(ondrelle), 18)
