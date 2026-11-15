"""Level on both sides of a check (#5093).

With the standard ladder (baseline 18 + 8 x (level - 1), one level 8 points wide) and a level
share of 0.5, a level-11 character's level term is 49 of level 11's 98-point baseline, and a
level-11 NPC opposes with the whole 98. A debuff on the NPC lowers it by the derived value of
the debuff, and a player character who is the obstacle counts as her full check total.
"""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.factories import (
    CheckTypeAspectFactory,
    CheckTypeCapabilityModifierFactory,
    CheckTypeFactory,
)
from world.checks.modifier_models import ModifierSizeFraction
from world.checks.modifier_values import load_value_table
from world.checks.scale_config import CheckScaleConfig
from world.checks.services import (
    compute_check_rating,
    compute_obstacle_rating,
    level_opposition,
    level_points,
    preview_check_difficulty,
)
from world.checks.test_helpers import make_player_character
from world.classes.factories import (
    AspectFactory,
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathAspectFactory,
    PathFactory,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import caster_opposition
from world.mechanics.factories import CharacterModifierFactory, ModifierTargetFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.traits.factories import ensure_level_ladder
from world.traits.models import CheckRank


class LevelTermTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})

    def test_the_level_term_is_the_share_of_the_levels_baseline(self) -> None:
        # Baseline at level 11 is 18 + 8 x 10 = 98; half of it is 49. Level 1: half of 18.
        self.assertEqual(level_points(11), 49)
        self.assertEqual(level_points(1), 9)

    def test_the_share_is_a_row(self) -> None:
        config = CheckScaleConfig.get_singleton()
        config.level_share = Decimal("0.25")
        config.save()
        # A quarter of 98 is 24.5, rounded half up.
        self.assertEqual(level_points(11), 25)

    def test_level_zero_adds_nothing(self) -> None:
        self.assertEqual(level_points(0), 0)

    def test_a_level_above_the_top_row_reuses_the_top_baseline(self) -> None:
        # The level-30 baseline is 18 + 8 x 29 = 250; half is 125.
        self.assertEqual(level_points(30), 125)
        self.assertEqual(level_points(33), 125)


class LevelOnBothSidesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})
        ModifierSizeFraction.objects.create(
            lane=ModifierLane.CHECK, size=ModifierSize.LARGE, fraction=Decimal("0.5")
        )
        cls.check_type = CheckTypeFactory(name="LevelBothSidesCheck")
        character_class = CharacterClassFactory()

        cls.level_eleven_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=cls.level_eleven_sheet,
            character_class=character_class,
            level=11,
            is_primary=True,
        )
        cls.level_eleven = cls.level_eleven_sheet.character

        cls.level_three_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=cls.level_three_sheet,
            character_class=character_class,
            level=3,
            is_primary=True,
        )
        cls.level_three = cls.level_three_sheet.character

    def test_a_level_eleven_roller_meets_a_level_eleven_npc_evenly(self) -> None:
        # Her level term is 49. With skills and stats adding the other 49 she totals 98,
        # exactly level 11's baseline: rank 11 against a rank-11 opponent.
        rating = compute_check_rating(self.level_eleven, self.check_type, extra_modifiers=49)
        opposition = level_opposition(self.check_type, level=11)

        self.assertEqual(rating, 98)
        self.assertEqual(opposition, 98)
        self.assertEqual(CheckRank.get_rank_difference(rating, opposition), 0)
        self.assertEqual(
            preview_check_difficulty(
                self.level_eleven, self.check_type, target_difficulty=opposition, extra_modifiers=49
            ),
            0,
        )

    def test_a_large_buff_moves_her_half_a_rank(self) -> None:
        # One Large buff is half of level 11's 8-point width: 4 points of the 8-point band.
        buff = load_value_table(ModifierLane.CHECK).value(11, ModifierSize.LARGE)
        self.assertEqual(buff, 4)
        opposition = level_opposition(self.check_type, level=11)
        plain = compute_check_rating(self.level_eleven, self.check_type, extra_modifiers=49)
        buffed = compute_check_rating(self.level_eleven, self.check_type, extra_modifiers=49 + buff)
        self.assertEqual(buffed - plain, 4)
        self.assertEqual(CheckRank.get_rank_difference(buffed, opposition), 0)

    def test_a_large_debuff_lowers_the_npc_by_the_same_share(self) -> None:
        opponent = ObjectDBFactory(db_key="LevelBothSidesOpponent")
        weakened = ConditionTemplateFactory(name="LevelBothSidesWeakened")
        ConditionCheckModifierFactory(
            condition=weakened, check_type=self.check_type, modifier_value=-1
        )
        undebuffed = level_opposition(self.check_type, level=11, character=opponent)

        ConditionInstanceFactory(
            target=opponent,
            condition=weakened,
            modifier_level=11,
            modifier_size=ModifierSize.LARGE,
        )
        debuffed = level_opposition(self.check_type, level=11, character=opponent)

        self.assertEqual(undebuffed, 98)
        self.assertEqual(undebuffed - debuffed, 4)

    def test_an_opposing_aspect_match_is_sized_as_a_modifier_at_the_level(self) -> None:
        path = PathFactory(name="LevelBothSidesPath")
        aspect = AspectFactory(name="LevelBothSidesAspect")
        PathAspectFactory(character_path=path, aspect=aspect, weight=2)
        CheckTypeAspectFactory(check_type=self.check_type, aspect=aspect, weight=Decimal("1.0"))
        defender = CharacterSheetFactory().character
        CharacterPathHistoryFactory(character=defender.sheet_data, path=path)

        # The match is 1.0 x 2 = 2 shares of level 11's 8-point width: 16 on top of 98.
        self.assertEqual(level_opposition(self.check_type, level=11, character=defender), 98 + 16)
        # No character, no aspect term.
        self.assertEqual(level_opposition(self.check_type, level=11), 98)

    def test_no_level_is_no_opposition(self) -> None:
        self.assertEqual(level_opposition(self.check_type, level=0), 0)


class PlayerCharacterAsObstacleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})
        cls.check_type = CheckTypeFactory(name="ObstacleCheck")
        character_class = CharacterClassFactory()
        cls.sheet = make_player_character(CharacterSheetFactory())
        CharacterClassLevelFactory(
            character=cls.sheet, character_class=character_class, level=11, is_primary=True
        )
        cls.character = cls.sheet.character
        # A named NPC has a sheet too, but no tenure: it is a level, not a rating.
        cls.npc_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=cls.npc_sheet, character_class=character_class, level=11, is_primary=True
        )

    def test_she_counts_as_her_full_check_total(self) -> None:
        # Her level term is 49; no traits, no modifiers.
        self.assertEqual(compute_obstacle_rating(self.character, self.check_type), 49)

    def test_what_she_carries_on_the_check_counts_once(self) -> None:
        template = ConditionTemplateFactory(name="ObstacleCarriedBonus")
        ConditionCheckModifierFactory(
            condition=template, check_type=self.check_type, modifier_value=6
        )
        ConditionInstanceFactory(target=self.character, condition=template)

        self.assertEqual(compute_obstacle_rating(self.character, self.check_type), 49 + 6)

    def test_a_capability_deviation_counts_once(self) -> None:
        # Baseline 5, effective 10 after her +5 modifier, weight 2.0: +10, counted by the
        # rating and left out of the gathered modifiers, so 49 + 10 and not 49 + 20.
        capability = CapabilityTypeFactory(name="ObstacleFireControl", innate_baseline=5)
        target = ModifierTargetFactory(target_capability=capability)
        CharacterModifierFactory(character=self.sheet, target=target, value=5)
        CheckTypeCapabilityModifierFactory(
            check_type=self.check_type, capability=capability, weight=Decimal("2.0")
        )

        self.assertEqual(compute_obstacle_rating(self.character, self.check_type), 49 + 10)

    def test_a_named_npc_with_a_sheet_counts_as_its_levels_baseline(self) -> None:
        # Level 11 with a sheet but no tenure: 98, the whole baseline, never her 49.
        self.assertEqual(compute_obstacle_rating(self.npc_sheet.character, self.check_type), 98)

    def test_a_rostered_player_character_counts_her_full_total(self) -> None:
        self.assertEqual(compute_obstacle_rating(self.character, self.check_type), 49)

    def test_an_obstacle_with_no_sheet_counts_as_its_levels_baseline(self) -> None:
        npc = ObjectDBFactory(db_key="ObstacleSheetlessNpc")

        # An NPC has a level and no points: level 11's whole baseline, never half of it.
        self.assertEqual(compute_obstacle_rating(npc, self.check_type, level_override=11), 98)
        # With no authored level it is level 1, like any character with no class level.
        self.assertEqual(compute_obstacle_rating(npc, self.check_type), 18)

    def test_a_sheetless_obstacles_debuff_lowers_it(self) -> None:
        ModifierSizeFraction.objects.get_or_create(
            lane=ModifierLane.CHECK, size=ModifierSize.LARGE, defaults={"fraction": Decimal("0.5")}
        )
        npc = ObjectDBFactory(db_key="ObstacleDebuffedNpc")
        weakened = ConditionTemplateFactory(name="ObstacleWeakened")
        ConditionCheckModifierFactory(
            condition=weakened, check_type=self.check_type, modifier_value=-1
        )
        ConditionInstanceFactory(
            target=npc, condition=weakened, modifier_level=11, modifier_size=ModifierSize.LARGE
        )

        self.assertEqual(compute_obstacle_rating(npc, self.check_type, level_override=11), 94)

    def test_an_authored_level_substitutes_for_her_own(self) -> None:
        # A bond-adjusted combat level of 3: the level term at level 3 is half of 34 = 17.
        self.assertEqual(
            compute_obstacle_rating(self.character, self.check_type, level_override=3), 17
        )

    def test_a_penalty_never_takes_her_below_nothing(self) -> None:
        template = ConditionTemplateFactory(name="ObstacleCrushingPenalty")
        ConditionCheckModifierFactory(
            condition=template, check_type=self.check_type, modifier_value=-500
        )
        ConditionInstanceFactory(target=self.character, condition=template)

        self.assertEqual(compute_obstacle_rating(self.character, self.check_type), 0)


class CasterOppositionTests(TestCase):
    """The caster's share of reading, rallying against or breaking a hold (#5093)."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        CheckScaleConfig.objects.update_or_create(pk=1, defaults={"level_share": Decimal("0.5")})
        cls.check_type = CheckTypeFactory(name="CasterOppositionCheck")
        cls.character_class = CharacterClassFactory()
        cls.template = ConditionTemplateFactory(name="CasterOppositionHold")

    def _caster(self, level: int):
        sheet = make_player_character(CharacterSheetFactory())
        CharacterClassLevelFactory(
            character=sheet, character_class=self.character_class, level=level, is_primary=True
        )
        return sheet.character

    def test_a_caster_is_her_full_check_total(self) -> None:
        caster = self._caster(11)
        hold = ConditionInstanceFactory(
            condition=self.template, source_character=caster, target=self._caster(1)
        )

        # Her level-11 term is 49.
        self.assertEqual(caster_opposition(hold, self.check_type), 49)

    def test_a_hold_with_no_caster_adds_nothing(self) -> None:
        hold = ConditionInstanceFactory(condition=self.template, target=self._caster(1))

        self.assertEqual(caster_opposition(hold, self.check_type), 0)

    def test_a_hold_put_on_herself_counts_her_levels_baseline_not_her_rating(self) -> None:
        caster = self._caster(11)
        hold = ConditionInstanceFactory(
            condition=self.template, source_character=caster, target=caster
        )

        # Level 11's baseline is 98: nobody else opposes it, and her rating would cancel
        # against the roll she makes to break it.
        self.assertEqual(caster_opposition(hold, self.check_type), 98)
