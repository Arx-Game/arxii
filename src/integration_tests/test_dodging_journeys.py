"""Journeys for dodging attacks and getting clear of area attacks (#4676, slice 4 of #4651).

The cellar is four places in a row, Doorway - Floor - Stage - Gallery, joined by open edges.
Ondrelle has a teleport capability (reach: any place, costs anima) at 4 above its baseline;
Malvaine has acrobatics (reach: an adjacent place, costs fatigue) at 3; Bram has neither.
Blades are spawned beside them with a 10-damage strike that carries a defence check.

- Shot at three times in one round, Ondrelle dodges each time automatically: each dodge costs
  2 anima, adds her teleport (4) to the roll, and each one after the first is 2 harder
  (bonus 4, then 2, then 0). No cap: all three fire.
- She sets where to land while declaring ("If you're attacked, you'll dodge to Gallery."),
  and a dodge that at least partly succeeds puts her there; a failed one leaves her in place.
  Turned off ("You won't dodge this round.") she pays nothing and gets no bonus. The plan
  resets each round.
- Her plan can only name a place her capability reaches: Malvaine (adjacent) cannot plan the
  Gallery from the Doorway ("Your dodge can't reach Gallery."). Bram cannot plan at all
  ("Nothing you have lets you dodge.").
- Malvaine's acrobatic dodge costs fatigue, not anima.
- Typed on telnet: ``combat dodge Gallery``, ``combat dodge off``.
- The plan is private: the encounter payload shows it to its owner only.
- A wound-up fire flask covering the Floor shows a round ahead, with its place in the
  encounter payload. When it lands, Malvaine, who planned to leap to the Stage, is not hit
  and stands on the Stage; Bram, who braced, is hit. Someone who walked out of the Floor on
  their turn is not hit; dodging in place does not escape it.

Expected values come from the spec (#4651 decisions 5 to 8, assumptions C and D) and the
MovementConfig field defaults: 2 anima or 1 base fatigue per dodge, a step of 2 per reaction.
A recording defence roll stands in for perform_check, so the bonus and penalty it was handed
can be read back.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import override_settings

from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import ReactionCostKind, ReactionReach
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
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
from world.combat.models import CombatParticipant, PendingOpponentAttack
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.factories import CapabilityTypeFactory
from world.fatigue.models import FatiguePool
from world.magic.factories import CharacterAnimaFactory
from world.magic.models.anima import CharacterAnima
from world.mechanics.factories import CharacterEngagementFactory, ModifierCategoryFactory
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

STRIKE = 10
DODGED_TO = "If you're attacked, you'll dodge to {place}."
DODGE_IN_PLACE = "If you're attacked, you'll dodge in place."
DODGE_OFF = "You won't dodge this round."
CANNOT_REACH = "Your dodge can't reach {place}."
NO_DODGE = "Nothing you have lets you dodge."


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
    """Doorway - Floor - Stage - Gallery, open edges, a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):
            ensure_foundational_capabilities()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.room = self.make_room("The Cellar")
        self.doorway = PositionFactory(room=self.room, name="Doorway")
        self.floor = PositionFactory(room=self.room, name="Floor")
        self.stage = PositionFactory(room=self.room, name="Stage")
        self.gallery = PositionFactory(room=self.room, name="Gallery")
        connect_positions(self.doorway, self.floor)
        connect_positions(self.floor, self.stage)
        connect_positions(self.stage, self.gallery)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.defense = CheckTypeFactory(name="Evade")
        self.teleport = CapabilityTypeFactory(
            name="teleport",
            innate_baseline=0,
            reaction_reach=ReactionReach.ANY_PLACE,
            reaction_cost_kind=ReactionCostKind.ANIMA,
        )
        self.acrobatics = CapabilityTypeFactory(
            name="acrobatics",
            innate_baseline=0,
            reaction_reach=ReactionReach.ADJACENT,
            reaction_cost_kind=ReactionCostKind.FATIGUE,
        )
        self.participants: dict[int, CombatParticipant] = {}

    def fighter(self, name: str, *, at, capability=None, value: int = 0):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        self.participants[character.pk] = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        place_in_position(character, at)
        if capability is not None:
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
                character=sheet, target=target, value=value, source=ModifierSource.objects.create()
            )
        self.watch(character)
        return character

    def blade(self, name: str, *, at, **entry_kwargs: object):
        pool = ThreatPoolFactory(name=f"{name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=entry_kwargs.pop("attack_name", f"{name} strike"),
            base_damage=STRIKE,
            delivery=StrikeDelivery.MISSILE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
            **entry_kwargs,
        )
        template = CreatureTemplateFactory(
            name=name, tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def resolve(self, roll: RecordingRoll) -> None:
        resolve_round(self.encounter, defense_check_fn=roll, offense_check_fn=_clean_hit)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(pk=self.participants[character.pk].pk)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def anima(self, character) -> int:
        return CharacterAnima.objects.get(character_id=character.sheet_data.pk).current


class DodgingAutomatically(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.ondrelle = self.fighter("Ondrelle", at=self.stage, capability=self.teleport, value=4)

    def test_three_shots_three_dodges_each_paid_and_harder(self) -> None:
        for name in ("Archer", "Bowman", "Slinger"):
            self.blade(name, at=self.gallery)
        roll = RecordingRoll(2, 2, 2)

        self.resolve(roll)

        self.assertEqual(roll.extras(), [4, 2, 0])
        self.assertEqual(self.participant(self.ondrelle).reactions_used, 3)
        self.assertEqual(self.anima(self.ondrelle), 20 - 3 * 2)
        self.assertEqual(position_of(self.ondrelle), self.stage)  # no landing set: in place

    def test_a_planned_landing_is_where_a_good_dodge_puts_her(self) -> None:
        told = self.web(self.ondrelle, "combat_dodge", position_id=self.gallery.pk)
        self.assertTrue(told.detail.success)
        self.assertEqual(told.detail.message, DODGED_TO.format(place="Gallery"))
        self.blade("Archer", at=self.doorway)

        self.resolve(RecordingRoll(1))

        self.assertEqual(position_of(self.ondrelle), self.gallery)

    def test_a_failed_dodge_leaves_her_where_she_was(self) -> None:
        self.web(self.ondrelle, "combat_dodge", position_id=self.gallery.pk)
        self.blade("Archer", at=self.doorway)

        self.resolve(RecordingRoll(0))

        self.assertEqual(position_of(self.ondrelle), self.stage)
        self.assertEqual(self.anima(self.ondrelle), 18)  # the attempt was still paid

    def test_turned_off_she_pays_nothing_and_gets_no_bonus(self) -> None:
        told = self.web(self.ondrelle, "combat_dodge", dodge=False)
        self.assertEqual(told.detail.message, DODGE_OFF)
        self.blade("Archer", at=self.doorway)
        roll = RecordingRoll(0)

        self.resolve(roll)

        self.assertEqual(roll.extras(), [0])
        self.assertEqual(self.anima(self.ondrelle), 20)
        self.assertEqual(self.participant(self.ondrelle).reactions_used, 0)

    def test_the_plan_resets_each_round(self) -> None:
        self.blade("Archer", at=self.gallery)  # the fight goes on to round 2
        self.web(self.ondrelle, "combat_dodge", dodge=False)
        self.resolve(RecordingRoll())
        begin_declaration_phase(self.encounter)

        plan = self.participant(self.ondrelle)
        self.assertTrue(plan.dodge_enabled)
        self.assertIsNone(plan.dodge_landing)
        self.assertEqual(plan.reactions_used, 0)

    def test_typed_on_telnet(self) -> None:
        self.assertIn(
            DODGED_TO.format(place="Gallery"), self.telnet(self.ondrelle, "combat dodge Gallery")
        )
        self.assertEqual(self.participant(self.ondrelle).dodge_landing, self.gallery)
        self.assertIn(DODGE_IN_PLACE, self.telnet(self.ondrelle, "combat dodge here"))
        self.assertIsNone(self.participant(self.ondrelle).dodge_landing)
        self.assertIn(DODGE_OFF, self.telnet(self.ondrelle, "combat dodge off"))
        self.assertFalse(self.participant(self.ondrelle).dodge_enabled)

    def test_the_plan_reaches_its_owner_only(self) -> None:
        self.web(self.ondrelle, "combat_dodge", position_id=self.gallery.pk)
        bram = self.fighter("Bram", at=self.floor)
        url = f"/api/combat/{self.encounter.pk}/"

        mine = self.api(self.account_of(self.ondrelle)).get(url).json()
        theirs = self.api(self.account_of(bram)).get(url).json()

        def plan_of(payload: dict, character) -> Any:
            row = next(
                p for p in payload["participants"] if p["character_sheet_id"] == character.pk
            )
            return row["dodge_plan"]

        own = plan_of(mine, self.ondrelle)
        self.assertTrue(own["enabled"])
        self.assertEqual(own["landing_id"], self.gallery.pk)
        self.assertEqual(
            {o["name"] for o in own["options"]}, {"Stage", "Doorway", "Floor", "Gallery"}
        )
        self.assertEqual(
            own["cost_line"],
            "Each dodge costs 2 anima. Each dodge after the first this round is harder.",
        )
        self.assertIsNone(plan_of(theirs, self.ondrelle))


class ReachAndCost(_TheCellar):
    def test_an_adjacent_dodge_cannot_plan_a_far_place(self) -> None:
        malvaine = self.fighter("Malvaine", at=self.doorway, capability=self.acrobatics, value=3)

        told = self.web(malvaine, "combat_dodge", position_id=self.gallery.pk)

        self.assertFalse(told.detail.success)
        self.assertEqual(told.detail.message, CANNOT_REACH.format(place="Gallery"))

    def test_no_capability_no_plan_and_a_plain_roll(self) -> None:
        bram = self.fighter("Bram", at=self.floor)
        told = self.web(bram, "combat_dodge")
        self.assertEqual(told.detail.message, NO_DODGE)
        self.blade("Archer", at=self.stage)
        roll = RecordingRoll(0)

        self.resolve(roll)

        self.assertEqual(roll.extras(), [0])
        self.assertEqual(self.anima(bram), 20)

    def test_an_acrobatic_dodge_costs_fatigue_not_anima(self) -> None:
        malvaine = self.fighter("Malvaine", at=self.floor, capability=self.acrobatics, value=3)
        self.blade("Archer", at=self.gallery)
        before = FatiguePool.objects.filter(character_sheet=malvaine.sheet_data).first()
        before_total = 0 if before is None else before.physical_current

        self.resolve(RecordingRoll(2))

        after = FatiguePool.objects.get(character_sheet=malvaine.sheet_data)
        self.assertGreater(after.physical_current, before_total)
        self.assertEqual(self.anima(malvaine), 20)


class GettingClearOfAnAreaAttack(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.malvaine = self.fighter("Malvaine", at=self.floor, capability=self.acrobatics, value=3)
        self.bram = self.fighter("Bram", at=self.floor)
        self.captain = self.blade(
            "Captain",
            at=self.doorway,
            attack_name="Holy fire",
            covers_place=True,
            windup_rounds=1,
        )

    def test_the_flask_shows_a_round_ahead_and_only_leaving_escapes_it(self) -> None:
        self.resolve(RecordingRoll())  # round 1: the captain winds up
        pending = PendingOpponentAttack.objects.get(encounter=self.encounter)
        self.assertEqual(pending.covered_position, self.floor)
        url = f"/api/combat/{self.encounter.pk}/"
        row = self.api(self.account_of(self.bram)).get(url).json()["pending_attacks"][0]
        self.assertEqual(row["covered_position_name"], "Floor")
        self.assertEqual(row["attack_name"], "Holy fire")

        begin_declaration_phase(self.encounter)
        self.web(self.malvaine, "combat_dodge", position_id=self.stage.pk)
        self.resolve(RecordingRoll(1, 0))  # round 2: it lands

        self.assertEqual(position_of(self.malvaine), self.stage)
        self.assertEqual(self.health(self.malvaine), 100)
        self.assertLess(self.health(self.bram), 100)

    def test_walking_out_on_your_turn_escapes_it(self) -> None:
        self.resolve(RecordingRoll())
        begin_declaration_phase(self.encounter)
        self.web(self.bram, "move_to_position", position_id=self.doorway.pk)
        self.web(self.malvaine, "combat_dodge", dodge=False)

        self.resolve(RecordingRoll(0))

        self.assertEqual(self.health(self.bram), 100)
        self.assertLess(self.health(self.malvaine), 100)

    def test_dodging_in_place_does_not_escape_it(self) -> None:
        self.resolve(RecordingRoll())
        begin_declaration_phase(self.encounter)
        roll = RecordingRoll(0, 0)

        self.resolve(roll)

        self.assertLess(self.health(self.malvaine), 100)
        self.assertEqual(self.participant(self.malvaine).reactions_used, 0)  # no dodge, no cost
