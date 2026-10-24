"""Journeys for rolls that gather every modifier (#4629).

Ysmay climbs at the Old Quarry. She wears Chalked Gloves (+5 to Climbing, an item check
modifier) and Maren casts Sure Grip on her (+5 to Climbing, a technique buff that lands
as a condition). Her own Climbing total is 5 points: Incompetent (rank 0), 50% toward
Novice (rank 1), on the seeded rank ladder. With the gloves and the buff it is 15:
Novice (rank 1), 33% toward Competent (rank 2).

Every way she rolls Climbing counts both: her own ``check`` by telnet and from the web,
answering a GM's call, a Senior GM's ``gm check`` on her, and a challenge she takes on
(the plain path and the action-template path). A challenge's stored breakdown, read
back from the REST endpoint, is the one the roll used. Her capability from the approach
counts once, and so does a capability staff linked to the check.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.checks import services as check_services
from world.checks.factories import CheckTypeCapabilityModifierFactory, CheckTypeFactory
from world.checks.models import CheckCall
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.constants import DurationType
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import ItemCheckModifier
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import CheckOutcome, ResultChart
from world.vitals.models import CharacterVitals

# Her own total, and her total with the gloves and the buff (5 each).
OWN = 5
GEARED = 15
OWN_STANDING = "Incompetent (rank 0), 50% toward Novice (rank 1)"
GEARED_STANDING = "Novice (rank 1), 33% toward Competent (rank 2)"
# Trivial is 15 points: Novice (rank 1), a third of its band.
AGAINST_TRIVIAL = "against Novice (rank 1), 33% toward Competent (rank 2)"
# Her capability from the approach's technique, and the gloves and the buff.
CAPABILITY = 5
GLOVES = ("equipment", "Equipped: Chalked Gloves", 5)
BUFF = ("condition", "Sure Grip", 5)


@contextmanager
def rolls_seen() -> Iterator[list[CheckResult]]:
    """Every check the game rolls inside the block, as the roller's results.

    Wraps the real ``perform_check``; the dice, the points and the outcome are the
    game's own. Used where the only reader of the total is the GM's graded line.
    """
    seen: list[CheckResult] = []
    real = check_services.perform_check

    def spy(*args, **kwargs) -> CheckResult:
        result = real(*args, **kwargs)
        seen.append(result)
        return result

    with patch("world.checks.services.perform_check", side_effect=spy):
        yield seen


class _TheOldQuarry(JourneyCase):
    """Ysmay, geared for the climb; Maren, who buffs her; Ravenna, who runs the scene."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ResultChart.clear_cache()
        self.climbing = CheckTypeFactory(name="Climbing", description="Scale a wall or a cliff.")
        self.room = self.make_room("The Old Quarry")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.maren = self.make_player("Maren", room=self.room)
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.telnet(self.ravenna, "scene start")

    # -- what she brings ----------------------------------------------------------

    def gloves(self) -> None:
        """Chalked Gloves (+5 to Climbing), put on with the real ``wear`` command."""
        template = ItemTemplateFactory(name="Chalked Gloves")
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.LEFT_HAND, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        ItemCheckModifier.objects.create(
            template=template, check_type=self.climbing, modifier_value=5
        )
        obj = ObjectDBFactory(db_key="Chalked Gloves", location=self.ysmay)
        ItemInstanceFactory(
            template=template, game_object=obj, holder_character_sheet=self.ysmay.sheet_data
        )
        self.assertIn("You equip Chalked Gloves.", self.telnet(self.ysmay, "wear Chalked Gloves"))

    def buff(self) -> None:
        """Maren casts Sure Grip (+5 to Climbing) on Ysmay, the way the web client does."""
        technique = TechniqueFactory(
            name="Sure Grip",
            gift=GiftFactory(),
            intensity=20,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Casting")),
        )
        condition = ConditionTemplateFactory(name="Sure Grip")
        ConditionCheckModifierFactory(
            condition=condition, check_type=self.climbing, check_category=None, modifier_value=5
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        sheet = self.maren.sheet_data
        CharacterClassLevelFactory(
            character=sheet, character_class=CharacterClassFactory(), level=1, is_primary=True
        )
        grant_technique(sheet.primary_persona, technique)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            result = self.web(
                self.maren,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=self.ysmay.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.ysmay, condition=condition).exists()
        )

    def gear_up(self) -> None:
        self.gloves()
        self.buff()


class HerOwnCheckCountsHerGear(_TheOldQuarry):
    """``check <name>`` and answering a call read her gloves and her buff."""

    def test_by_telnet_her_standing_counts_the_gloves_and_the_buff(self) -> None:
        told = self.telnet(self.ysmay, "check Climbing at trivial")
        self.assertIn(f"Your standing: {OWN_STANDING} {AGAINST_TRIVIAL}.", told)

        self.gear_up()

        told = self.telnet(self.ysmay, "check Climbing at trivial")
        self.assertIn("Ysmay attempts Climbing (Trivial) and", told)
        self.assertIn(f"Your standing: {GEARED_STANDING} {AGAINST_TRIVIAL}.", told)

    def test_from_the_web_her_standing_counts_them_too(self) -> None:
        self.gear_up()

        result = self.web(
            self.ysmay, "scene_self_check", check_type_ref="Climbing", difficulty="trivial"
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn(f"Your standing: {GEARED_STANDING} {AGAINST_TRIVIAL}.", result.detail.message)

    def test_answering_a_gms_call_counts_them(self) -> None:
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.JUNIOR)
        self.gear_up()
        self.telnet(self.ravenna, "callcheck Climbing=Ysmay at trivial")
        call = CheckCall.objects.get(check_type=self.climbing)

        told = self.telnet(self.ysmay, f"check answer {call.pk}")

        self.assertIn("Ysmay attempts Climbing (Trivial) and", told)
        self.assertIn(f"Your standing: {GEARED_STANDING} {AGAINST_TRIVIAL}.", told)


class AGmCheckCountsHerGear(_TheOldQuarry):
    """A Senior GM's ``gm check`` on her reads the same gear; the GM still sees no number."""

    def test_the_gm_check_rolls_her_geared_total(self) -> None:
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.SENIOR)
        self.gear_up()

        with rolls_seen() as rolls:
            told = self.telnet(self.ravenna, "gm check Ysmay Climbing=trivial")

        self.assertIn("Ysmay: Climbing (Trivial) -> ", told)
        (roll,) = rolls
        self.assertEqual(roll.total_points, GEARED)
        self.assertEqual(roll.standing_text, f"{GEARED_STANDING} {AGAINST_TRIVIAL}")

    def test_an_edge_still_moves_only_the_band(self) -> None:
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.SENIOR)
        self.gear_up()

        with rolls_seen() as rolls:
            told = self.telnet(
                self.ravenna, "gm check Ysmay Climbing=easy edge=a rope is already rigged"
            )

        self.assertIn("Ysmay: Climbing (Easy) [edge -> Trivial: a rope is already rigged]", told)
        (roll,) = rolls
        self.assertEqual(roll.total_points, GEARED)


class AChallengeCountsHerGear(_TheOldQuarry):
    """Ysmay climbs the quarry face: a challenge whose approach her technique opens."""

    def setUp(self) -> None:
        super().setUp()
        self.scaling = CapabilityTypeFactory(name="Scaling")
        prop = PropertyFactory(name="sheer")
        template = ChallengeTemplateFactory(
            name="The Quarry Face", severity=DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL]
        )
        template.properties.add(prop)
        self.approach = ChallengeApproachFactory(
            challenge_template=template,
            application=ApplicationFactory(
                name="Scale It", capability=self.scaling, target_property=prop
            ),
            check_type=self.climbing,
            display_name="Climb the face",
            action_template=None,
        )
        wall = ObjectDBFactory(db_key="the quarry face", location=self.room)
        self.face = ChallengeInstance.objects.create(
            template=template,
            location=self.room,
            target_object=wall,
            is_active=True,
            is_revealed=True,
        )
        climber = TechniqueFactory(name="Spider Step", damage_profile=False)
        # No sensitivity to power, so the grant is its authored 5 at any intensity.
        TechniqueCapabilityGrantFactory(
            technique=climber,
            capability=self.scaling,
            base_value=CAPABILITY,
            intensity_multiplier=Decimal(0),
        )
        grant_technique(self.ysmay.sheet_data.primary_persona, climber)

    def climb(self) -> CheckResult:
        """Take the approach the way the web client does."""
        result = dispatch_player_action(
            self.ysmay,
            ActionRef(
                backend=ActionBackend.CHALLENGE,
                challenge_instance_id=self.face.pk,
                approach_id=self.approach.pk,
            ),
            {},
        )
        return result.detail.check_result

    def stored(self) -> dict:
        """Her challenge's stored outcome, read back from the REST endpoint."""
        response = self.api(self.account_of(self.ysmay)).get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200, response.content)
        (outcome,) = response.json()["results"]
        return outcome

    @staticmethod
    def rows(outcome: dict) -> list[tuple[str, str, int]]:
        """Every stored row, sorted; a row stored twice shows up twice."""
        return sorted(
            (m["source_kind"], m["source_label"], m["value"]) for m in outcome["modifiers"]
        )

    def test_the_roll_and_the_stored_breakdown_count_the_gloves_and_the_buff(self) -> None:
        self.gear_up()

        roll = self.climb()

        # Her own 5, the gloves' 5, the buff's 5 and her capability's 5, each once.
        self.assertEqual(roll.total_points, GEARED + CAPABILITY)
        # 20 points: Novice (rank 1), two thirds of its band.
        self.assertEqual(
            roll.standing_text,
            "Novice (rank 1), 67% toward Competent (rank 2) " + AGAINST_TRIVIAL,
        )
        outcome = self.stored()
        self.assertEqual(
            self.rows(outcome),
            sorted([GLOVES, BUFF, ("capability", "Scaling: Spider Step", CAPABILITY)]),
        )
        self.assertEqual(outcome["modifier_total"], 15)

    def test_without_gear_the_stored_breakdown_holds_only_her_capability(self) -> None:
        roll = self.climb()

        self.assertEqual(roll.total_points, OWN + CAPABILITY)
        outcome = self.stored()
        self.assertEqual(self.rows(outcome), [("capability", "Scaling: Spider Step", CAPABILITY)])
        self.assertEqual(outcome["modifier_total"], CAPABILITY)

    def test_a_capability_staff_linked_to_the_check_counts_once(self) -> None:
        # Staff linked Scaling to Climbing: her 5 Scaling adds 5 through that link, on
        # top of the approach's own 5 (ADR-0145's two channels), and never a third time.
        CheckTypeCapabilityModifierFactory(check_type=self.climbing, capability=self.scaling)
        self.gear_up()

        roll = self.climb()

        self.assertEqual(roll.total_points, GEARED + CAPABILITY + CAPABILITY)
        outcome = self.stored()
        self.assertEqual(
            self.rows(outcome),
            sorted(
                [
                    GLOVES,
                    BUFF,
                    ("capability", "Scaling: Spider Step", CAPABILITY),
                    ("capability", "Capability: Scaling", CAPABILITY),
                ]
            ),
        )
        self.assertEqual(outcome["modifier_total"], 20)

    def test_an_approach_with_an_action_template_counts_them_too(self) -> None:
        self.approach.action_template = ActionTemplateFactory(
            name="Climb the face", check_type=self.climbing, consequence_pool=None
        )
        self.approach.save(update_fields=["action_template"])
        self.gear_up()

        roll = self.climb()

        self.assertEqual(roll.total_points, GEARED + CAPABILITY)
        outcome = self.stored()
        self.assertEqual(
            self.rows(outcome),
            sorted([GLOVES, BUFF, ("capability", "Scaling: Spider Step", CAPABILITY)]),
        )
        self.assertEqual(outcome["modifier_total"], 15)

    def test_a_once_only_blessing_helps_one_climb_and_is_spent(self) -> None:
        word = ConditionTemplateFactory(
            name="Steadying Word", default_duration_type=DurationType.UNTIL_USED
        )
        ConditionCheckModifierFactory(
            condition=word, check_type=self.climbing, check_category=None, modifier_value=3
        )
        ConditionInstanceFactory(target=self.ysmay, condition=word)

        roll = self.climb()

        self.assertEqual(roll.total_points, OWN + CAPABILITY + 3)
        self.assertFalse(
            ConditionInstance.objects.filter(target=self.ysmay, condition=word).exists()
        )
        self.assertEqual(
            self.rows(self.stored()),
            sorted(
                [
                    ("capability", "Scaling: Spider Step", CAPABILITY),
                    ("condition", "Steadying Word", 3),
                ]
            ),
        )
