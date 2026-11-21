"""Journeys for magical gear that puts a condition on its wearer (#5074).

Staff author two kinds of gear (the names, conditions and numbers here are invented):

- **Shadowed Cloak** gives its wearer **Shadowed**: a permanent condition that raises
  ``traversal`` by 10 and carries the property ``teleport``. Staff set Shadowed's per-use
  anima cost to 3.
- **Ember Mantle** is a mantle with five levels. Its item gives **Ember-touched** to a wearer
  attuned to level 1 and **Kindled Stride** to a wearer attuned to level 3.

Wearing is typed (``wear``, ``remove``, ``give``); the condition list is read over
``/api/conditions/character/``. A mantle level is reached through the Rite of Imbuing
service, the one writer that raises a thread's level.

- Wearing the cloak gives her Shadowed in her condition list, labelled with the cloak; taking
  it off ends it; handing it to Hobb gives it to him when he puts it on and to nobody else.
- An enemy's dispel takes Shadowed off her. It stays off through an unrelated wear and remove,
  and returns once she takes the cloak off and puts it back on. A condition staff made
  undispellable is never taken.
- Two cloaks that give the same condition give one condition; taking one off keeps it.
- A mantle at attunement level 1 gives Ember-touched only; raising the thread to level 3
  (mantle still worn) adds Kindled Stride; retiring the thread takes both away. A stranger
  who puts the mantle on gets neither.
- In a fight the cloak's blink is offered ("Blink to Stage (3 anima)") and used for its 3
  anima; with 1 anima the blink still goes through and her Soulfray grows. Dodging with it
  charges the same 3 anima. Without the cloak there is no blink.
- Others looking at her conditions in a fight never see the cloak's name; she does.

Expected values come from the spec (#5074 decisions 1 to 4, the scenarios), the mantle rule
that a thread's stored level runs ten to one with a mantle level (a thread at 30 has reached
mantle level 3), and the field defaults.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from django.test import override_settings
from evennia.objects.models import ObjectDB

from actions.player_interface import get_player_actions
from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.checks.factories import CheckTypeFactory
from world.classes.factories import CharacterClassLevelFactory
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
from world.combat.models import CombatParticipant
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.constants import DurationType, FoundationalCapability
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionCategoryFactory,
    ConditionTemplateFactory,
    SoulfrayTemplateFactory,
)
from world.conditions.models import CapabilityType, ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition, has_condition
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    ItemWornConditionFactory,
    MantleFactory,
    TemplateSlotFactory,
)
from world.items.models import ItemInstance
from world.items.services.mantle import grant_mantle_clearance
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
    ThreadFactory,
    ensure_soulfray_config,
)
from world.magic.models import ThreadLevelUnlock
from world.magic.models.anima import CharacterAnima
from world.magic.services import spend_resonance_for_imbuing
from world.magic.services.condition_application import remove_technique_conditions
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

SHADOWED = "Shadowed"
CLOAK = "Shadowed Cloak"
CLOAK_ANIMA = 3
BLINK_VALUE = 10
EXTRA_MOVEMENT = 5  # baseline 5 + 5 = 10 movement = 2 hops a round
BLINK_TO_STAGE = f"Blink to Stage ({CLOAK_ANIMA} anima)"
MANTLE_LEVELS_TO_THREAD_LEVEL = 10


def wearable(holder: ObjectDB, name: str, *, region: str = BodyRegion.TORSO) -> ItemInstance:
    """A held item whose template has one slot, authored before the item exists."""
    template = ItemTemplateFactory(name=name)
    TemplateSlotFactory(template=template, body_region=region, equipment_layer=EquipmentLayer.BASE)
    template.__dict__.pop("cached_slots", None)
    return ItemInstanceFactory(
        template=template,
        game_object=ObjectDBFactory(db_key=name, location=holder),
        holder_character_sheet=holder.sheet_data,
    )


def gear_condition(name: str, **fields: Any) -> ConditionTemplate:
    """A permanent condition, as staff author one for gear."""
    return ConditionTemplateFactory(
        name=name,
        category=ConditionCategoryFactory(name="Gear", is_negative=False),
        default_duration_type=DurationType.PERMANENT,
        default_duration_value=0,
        **fields,
    )


def conditions_of(case: JourneyCase, character: ObjectDB) -> list[dict[str, Any]]:
    """The condition list the web client shows this character."""
    response = case.api(case.account_of(character)).get(
        "/api/conditions/character/", HTTP_X_CHARACTER_ID=str(character.pk)
    )
    case.assertEqual(response.status_code, 200, response.content)
    return response.json()


def names_of(case: JourneyCase, character: ObjectDB) -> list[str]:
    return sorted(row["name"] for row in conditions_of(case, character))


class _TheCloakRoom(JourneyCase):
    """Ysmay and Hobb in a room, and a Shadowed Cloak in Ysmay's hands."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Wardrobe")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.traversal = CapabilityTypeFactory(name="traversal", innate_baseline=0)
        self.teleport = PropertyFactory(name="teleport")
        self.shadowed = gear_condition(SHADOWED, reactive_anima_cost=CLOAK_ANIMA)
        ConditionCapabilityEffectFactory(
            condition=self.shadowed, capability=self.traversal, value=BLINK_VALUE
        )
        self.shadowed.properties.add(self.teleport)
        self.cloak = wearable(self.ysmay, CLOAK)
        ItemWornConditionFactory(item_instance=self.cloak, condition=self.shadowed)


class AnEnchantedCloak(_TheCloakRoom):
    def test_wearing_it_gives_the_condition_and_taking_it_off_ends_it(self) -> None:
        self.assertEqual(names_of(self, self.ysmay), [])

        self.assertIn(f"You equip {CLOAK}.", self.telnet(self.ysmay, f"wear {CLOAK}"))

        rows = conditions_of(self, self.ysmay)
        self.assertEqual([row["name"] for row in rows], [SHADOWED])
        self.assertEqual(rows[0]["source_description"], CLOAK)
        self.assertEqual(rows[0]["duration_type"], DurationType.PERMANENT)

        self.assertIn(f"You remove {CLOAK}.", self.telnet(self.ysmay, f"remove {CLOAK}"))
        self.assertEqual(names_of(self, self.ysmay), [])

    def test_handing_it_on_gives_it_to_the_one_who_wears_it(self) -> None:
        self.telnet(self.ysmay, f"wear {CLOAK}")
        self.telnet(self.ysmay, f"remove {CLOAK}")
        self.telnet(self.ysmay, f"give {CLOAK} to Hobb")

        self.assertEqual(names_of(self, self.hobb), [])
        self.telnet(self.hobb, f"wear {CLOAK}")

        self.assertEqual(names_of(self, self.hobb), [SHADOWED])
        self.assertEqual(names_of(self, self.ysmay), [])

    def test_a_cloak_given_away_while_worn_leaves_her(self) -> None:
        self.telnet(self.ysmay, f"wear {CLOAK}")

        self.telnet(self.ysmay, f"give {CLOAK} to Hobb")

        self.assertEqual(names_of(self, self.ysmay), [])

    def test_two_cloaks_giving_one_condition_give_one_condition(self) -> None:
        second = wearable(self.ysmay, "Shadowed Hood", region=BodyRegion.HEAD)
        ItemWornConditionFactory(item_instance=second, condition=self.shadowed)
        self.telnet(self.ysmay, f"wear {CLOAK}")
        self.telnet(self.ysmay, "wear Shadowed Hood")
        self.assertEqual(names_of(self, self.ysmay), [SHADOWED])

        self.telnet(self.ysmay, f"remove {CLOAK}")

        row = conditions_of(self, self.ysmay)[0]
        self.assertEqual((row["name"], row["source_description"]), (SHADOWED, "Shadowed Hood"))
        self.telnet(self.ysmay, "remove Shadowed Hood")
        self.assertEqual(names_of(self, self.ysmay), [])

    def test_a_condition_she_already_holds_from_elsewhere_is_left_alone(self) -> None:
        apply_condition(self.ysmay, self.shadowed)

        self.telnet(self.ysmay, f"wear {CLOAK}")
        self.telnet(self.ysmay, f"remove {CLOAK}")

        self.assertTrue(has_condition(self.ysmay, self.shadowed))


class ADispelledGearCondition(_TheCloakRoom):
    """An enemy's dispel takes the condition off her. It is a cross-system journey: the
    dispel is the service both the combat resolver and a scene cast call
    (``remove_technique_conditions``), and the assertions are on what she then sees."""

    def dispel(self, condition: ConditionTemplate) -> bool:
        technique = TechniqueFactory(name="Unravel")
        TechniqueRemovedConditionFactory(technique=technique, condition=condition)
        results = remove_technique_conditions(
            technique=technique,
            success_level=1,
            eff_intensity=1,
            targets_by_kind={"enemy": [self.ysmay]},
            source_character=self.hobb,
        )
        return any(result.success for result in results)

    def test_it_stays_off_until_she_takes_the_cloak_off_and_puts_it_on_again(self) -> None:
        self.telnet(self.ysmay, f"wear {CLOAK}")
        self.assertTrue(self.dispel(self.shadowed))
        self.assertEqual(names_of(self, self.ysmay), [])

        wearable(self.ysmay, "Linen Shirt", region=BodyRegion.HEAD)
        self.telnet(self.ysmay, "wear Linen Shirt")
        self.telnet(self.ysmay, "remove Linen Shirt")
        self.assertEqual(names_of(self, self.ysmay), [])

        self.telnet(self.ysmay, f"remove {CLOAK}")
        self.telnet(self.ysmay, f"wear {CLOAK}")

        self.assertEqual(names_of(self, self.ysmay), [SHADOWED])

    def test_a_condition_staff_made_undispellable_is_never_taken(self) -> None:
        self.shadowed.can_be_dispelled = False
        self.shadowed.save(update_fields=["can_be_dispelled"])
        self.telnet(self.ysmay, f"wear {CLOAK}")

        self.assertFalse(self.dispel(self.shadowed))

        self.assertEqual(names_of(self, self.ysmay), [SHADOWED])


class AMantleAtLevelThree(JourneyCase):
    """Ysmay is attuned to level 1 of the Ember Mantle (a thread at 19, level cap 100)."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Reliquary")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterClassLevelFactory(character=self.sheet, level=10, is_primary=True)
        self.item = wearable(self.ysmay, "Ember Mantle")
        self.mantle = MantleFactory(name="Ember", item_instance=self.item, max_level=5)
        self.ember = gear_condition("Ember-touched")
        self.stride = gear_condition("Kindled Stride")
        ItemWornConditionFactory(item_instance=self.item, condition=self.ember, mantle_level=1)
        ItemWornConditionFactory(item_instance=self.item, condition=self.stride, mantle_level=3)
        for level in (1, 2, 3):
            grant_mantle_clearance(self.sheet, self.mantle, level)
        self.resonance = ResonanceFactory(name="Kindling")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance, balance=10)
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.MANTLE,
            target_mantle=self.mantle,
            target_trait=None,
            level=19,
            developed_points=100_000,
        )
        for boundary in range(10, 40, 10):
            ThreadLevelUnlock.objects.create(
                thread=self.thread, unlocked_level=boundary, xp_spent=0
            )

    def test_the_second_condition_arrives_when_attunement_reaches_its_level(self) -> None:
        self.telnet(self.ysmay, "wear Ember Mantle")
        self.assertEqual(names_of(self, self.ysmay), ["Ember-touched"])

        spend_resonance_for_imbuing(self.sheet, self.thread, self.resonance, 0)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.level, 3 * MANTLE_LEVELS_TO_THREAD_LEVEL)
        self.assertEqual(names_of(self, self.ysmay), ["Ember-touched", "Kindled Stride"])

    def test_a_raise_with_the_mantle_in_her_pack_gives_nothing_until_she_wears_it(self) -> None:
        spend_resonance_for_imbuing(self.sheet, self.thread, self.resonance, 0)
        self.assertEqual(names_of(self, self.ysmay), [])

        self.telnet(self.ysmay, "wear Ember Mantle")

        self.assertEqual(names_of(self, self.ysmay), ["Ember-touched", "Kindled Stride"])

    def test_retiring_the_thread_takes_the_levels_with_it(self) -> None:
        self.telnet(self.ysmay, "wear Ember Mantle")
        self.assertEqual(names_of(self, self.ysmay), ["Ember-touched"])

        retired = self.api(self.account_of(self.ysmay)).delete(
            f"/api/magic/threads/{self.thread.pk}/", HTTP_X_CHARACTER_ID=str(self.ysmay.pk)
        )

        self.assertEqual(retired.status_code, 204, retired.content)
        self.assertEqual(names_of(self, self.ysmay), [])

    def test_a_stranger_wearing_the_mantle_gets_neither(self) -> None:
        self.telnet(self.ysmay, "wear Ember Mantle")
        self.telnet(self.ysmay, "remove Ember Mantle")
        self.telnet(self.ysmay, "give Ember Mantle to Hobb")

        self.telnet(self.hobb, "wear Ember Mantle")

        self.assertEqual(names_of(self, self.hobb), [])


class _TheCellar(_TheCloakRoom):
    """The hedged cellar and a fight in DECLARING round 1, the cloak on Ondrelle."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):
            ensure_foundational_capabilities()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.doorway = PositionFactory(room=self.room, name="Doorway")
        self.floor = PositionFactory(room=self.room, name="Floor")
        self.gallery = PositionFactory(room=self.room, name="Gallery")
        self.stage = PositionFactory(room=self.room, name="Stage")
        connect_positions(self.doorway, self.floor)
        connect_positions(self.floor, self.gallery)
        connect_positions(self.gallery, self.stage)
        hedge = ChallengeInstanceFactory(
            template=ChallengeTemplateFactory(name="Thorn Hedge"), location=self.room
        )
        connect_positions(self.doorway, self.stage, is_passable=False, gating_challenge=hedge)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.room,
            risk_level=RiskLevel.LETHAL,
        )
        self.defense = CheckTypeFactory(name="Evade")
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
        self.soulfray = SoulfrayTemplateFactory()
        ensure_soulfray_config()
        self.ondrelle = self.fighter("Ondrelle", anima=20)

    def fighter(self, name: str, *, anima: int) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=anima, maximum=20)
        CharacterEngagementFactory(character=sheet)
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        target, _ = ModifierTarget.objects.get_or_create(
            name=f"capability_{movement.pk}",
            category=ModifierCategoryFactory(name="capability"),
            defaults={
                "description": "",
                "display_order": 0,
                "is_active": True,
                "target_capability": movement,
            },
        )
        CharacterModifier.objects.create(
            character=sheet,
            target=target,
            value=EXTRA_MOVEMENT,
            source=ModifierSource.objects.create(),
        )
        place_in_position(character, self.doorway)
        self.watch(character)
        return character

    def put_on_cloak(self, character: ObjectDB) -> None:
        """Hand the character a Shadowed Cloak of their own and wear it."""
        cloak = wearable(character, CLOAK)
        ItemWornConditionFactory(item_instance=cloak, condition=self.shadowed)
        self.telnet(character, f"wear {CLOAK}")

    def anima(self, character: ObjectDB) -> int:
        return CharacterAnima.objects.get(character_id=character.sheet_data.pk).current

    def moves(self, character: ObjectDB) -> dict[str, Any]:
        return {action.display_name: action for action in get_player_actions(character)}

    def soulfray_on(self, character: ObjectDB) -> ConditionInstance | None:
        return ConditionInstance.objects.filter(target=character, condition=self.soulfray).first()


class TheCloakBlinks(_TheCellar):
    def test_without_the_cloak_there_is_no_blink(self) -> None:
        self.assertFalse([name for name in self.moves(self.ondrelle) if name.startswith("Blink")])

    def test_with_it_the_blink_is_offered_at_its_anima_cost_and_used(self) -> None:
        self.put_on_cloak(self.ondrelle)
        self.assertIn(BLINK_TO_STAGE, self.moves(self.ondrelle))

        result = self.web(self.ondrelle, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, f"You blink to Stage for {CLOAK_ANIMA} anima.")
        self.assertEqual(position_of(self.ondrelle), self.stage)
        self.assertEqual(self.anima(self.ondrelle), 20 - CLOAK_ANIMA)

    def test_with_one_anima_the_blink_still_goes_through_and_costs_soulfray(self) -> None:
        tired = self.fighter("Tamsin", anima=1)
        self.put_on_cloak(tired)
        entry = self.moves(tired)[BLINK_TO_STAGE]
        self.assertTrue(entry.prerequisite_met)
        self.assertEqual(entry.prerequisite_reasons, [])

        result = self.web(tired, "move_to_position", position_id=self.stage.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, f"You blink to Stage for {CLOAK_ANIMA} anima.")
        self.assertEqual(position_of(tired), self.stage)
        self.assertEqual(self.anima(tired), 0)
        self.assertIsNotNone(self.soulfray_on(tired))

    def test_a_dodge_with_it_charges_the_same_anima(self) -> None:
        self.put_on_cloak(self.ondrelle)
        self.web(self.ondrelle, "combat_dodge", position_id=self.gallery.pk)
        pool = ThreatPoolFactory(name="Archer attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Archer shot",
            base_damage=10,
            delivery=StrikeDelivery.MISSILE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
        )
        template = CreatureTemplateFactory(
            name="Archer", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
        )
        spawn_from_creature_template(self.encounter, template, position=self.floor)
        extras: list[int] = []

        def defence(*_args: object, **kwargs: Any) -> MagicMock:
            extras.append(kwargs["extra_modifiers"])
            return MagicMock(success_level=1, outcome=None)

        with patch("world.combat.services.movement_use.roll_technique"):
            resolve_round(
                self.encounter,
                defense_check_fn=defence,
                offense_check_fn=lambda *_a, **_k: MagicMock(success_level=2, outcome=None),
            )

        self.assertEqual(extras, [BLINK_VALUE])
        self.assertEqual(position_of(self.ondrelle), self.gallery)
        self.assertEqual(self.anima(self.ondrelle), 20 - CLOAK_ANIMA)


class WhoSeesTheCloaksName(_TheCellar):
    """The fight's payload shows the cloak's name to the one who wears it and to nobody else."""

    def seen_by(self, viewer: ObjectDB, wearer: ObjectDB) -> list[str]:
        response = self.api(self.account_of(viewer)).get(
            f"/api/combat/{self.encounter.pk}/", HTTP_X_CHARACTER_ID=str(viewer.pk)
        )
        self.assertEqual(response.status_code, 200, response.content)
        participant = CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=wearer.sheet_data
        )
        seat = next(row for row in response.json()["participants"] if row["id"] == participant.pk)
        return [row["source_description"] for row in seat["active_conditions"]]

    def test_she_sees_it_and_another_fighter_does_not(self) -> None:
        self.shadowed.is_visible_to_others = True
        self.shadowed.save(update_fields=["is_visible_to_others"])
        self.put_on_cloak(self.ondrelle)
        hobb = self.fighter("Brannoch", anima=20)

        self.assertEqual(self.seen_by(self.ondrelle, self.ondrelle), [CLOAK])
        self.assertEqual(self.seen_by(hobb, self.ondrelle), [""])
