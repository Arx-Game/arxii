"""Journeys for a rank meaning a level, with level on both sides of a check (#5093).

Hobb is a level-11 character at the Steading. He Strikes a level-11 bandit with his bare
hands through the web dispatch (``combat_strike``), and the round resolves with the real
rolls: nothing is forced, only the hit roll's standing is read back. On the seeded ladder
(rank N starts at 18 + 8 x (N - 1), so one level is 8 points wide) and a level share of 0.5:

* Level 11's baseline is 98 and the seeded tiers (levels 6 and 11, 24 points each) add 48, so
  a level-11 strength is 146 and rank 17 starts there. The bandit is a level, not a pile of
  points, so it opposes with 146. Hobb's level term is half of the baseline plus the tier
  bonus, 49 + 48 = 97, and his Unarmed Combat of 49 (one point a level on the seeded
  conversion) is the other half of the baseline: his total is 146, the start of rank 17 against
  rank 17. The even chart, with no slide.
* An ally's Large buff is half of a level's 8 points: 4. Hobb rolls 150, half way through
  rank 17, so the even chart slides half way toward the next.
* A Large debuff on the bandit lowers it by the same 4, to 142, half way through rank 16:
  the same half-rank gain from the other side.
* The tier jump: a level-6 Hobb with ordinary skills Strikes a level-5 bandit four ranks above
  it, while a level-5 Hobb Strikes a level-4 bandit one rank above.

Expected totals come from the spec's numbers (baseline 18 + 8 per level, level share 0.5, a
Large modifier at fraction 0.5 of an 8-point level, tiers of 24 points from level 6, 11, ...),
not from the code.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierSize
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check, perform_check_with_modifiers
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.maneuver_effects import ensure_maneuver_effects
from world.room_features.factories import TrapFactory
from world.room_features.trap_services import search_room_traps
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.factories import (
    CharacterTraitValueFactory,
    SkillTraitFactory,
    StatTraitFactory,
)
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from collections.abc import Iterator

LEVEL = 11
LEVEL_ELEVEN_BASELINE = 98  # 18 + 8 x 10
LEVEL_ELEVEN_TIERS = 48  # the tiers starting at levels 6 and 11, 24 points each
LEVEL_ELEVEN_STRENGTH = LEVEL_ELEVEN_BASELINE + LEVEL_ELEVEN_TIERS  # rank 17 starts here
LEVEL_ELEVEN_RANK = 17  # (146 - 18) / 8 + 1
UNARMED_COMBAT = 49  # half of the baseline: the level term is the other half
LARGE_BUFF = 4  # Large is 0.5 of an 8-point level


class _LevelElevenField(JourneyCase):
    """Hobb (level 11, Unarmed Combat 49) and a level-11 bandit at the Steading."""

    hobb_level = LEVEL
    bandit_level = LEVEL
    unarmed_value = UNARMED_COMBAT

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        ensure_maneuver_effects()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )
        strength = StatTraitFactory(name="strength")
        StatTraitFactory(name="agility")
        unarmed_skill = SkillTraitFactory(name="Unarmed Combat")
        self.unarmed = CheckTypeFactory(name="Unarmed Attack")
        CheckTypeTraitFactory(check_type=self.unarmed, trait=strength, weight=1)
        CheckTypeTraitFactory(check_type=self.unarmed, trait=unarmed_skill, weight=1)

        self.steading = self.make_room("The Steading")
        SceneFactory(room=self.steading)
        self.hobb = self.make_player("Hobb", room=self.steading)
        self.maren = self.make_player("Maren", room=self.steading)
        sheet = self.hobb.sheet_data
        CharacterClassLevelFactory(
            character=sheet,
            character_class=CharacterClassFactory(),
            level=self.hobb_level,
            is_primary=True,
        )
        CharacterTraitValueFactory(character=sheet, trait=unarmed_skill, value=self.unarmed_value)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )

    # -- the fight ------------------------------------------------------------------

    def open_the_fight(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS, round_number=0, room=self.steading
        )
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.hobb.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter,
            name="Bandit",
            health=200,
            max_health=200,
            level=self.bandit_level,
        )
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

    @contextmanager
    def real_rolls(self) -> Iterator[list[tuple[CheckResult, dict[str, Any]]]]:
        """Every roll the round makes, as (the real result, the keywords it was rolled with)."""
        rolled: list[tuple[CheckResult, dict[str, Any]]] = []

        def spy(character, check_type, *args, **kwargs):
            result = perform_check(character, check_type, *args, **kwargs)
            rolled.append((result, kwargs))
            return result

        with patch("world.combat.services.perform_check", side_effect=spy):
            yield rolled

    def hit_roll(self) -> tuple[CheckResult, dict[str, Any]]:
        """Hobb Strikes the bandit bare-handed and the round resolves; the hit roll comes back."""
        declared = self.web(self.hobb, "combat_strike", opponent_id=self.bandit.pk)
        self.assertTrue(declared.detail.success, declared.detail.message)
        with self.real_rolls() as rolled:
            resolve_round(self.encounter)
        return rolled[0]


class ALevelElevenPCMeetsALevelElevenNPCEvenly(_LevelElevenField):
    def test_her_total_is_the_start_of_the_rank_her_opponent_stands_at(self) -> None:
        self.open_the_fight()

        hit, rolled_with = self.hit_roll()

        # The bandit has a level and no points: level 11's baseline plus its tier bonus.
        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_STRENGTH)
        # Hobb's level term (49 + the tiers' 48) and his Unarmed Combat (49) make the whole.
        self.assertEqual(hit.level_points, UNARMED_COMBAT + LEVEL_ELEVEN_TIERS)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_STRENGTH)
        self.assertEqual(hit.standing.roller.rank.rank, LEVEL_ELEVEN_RANK)
        self.assertEqual(hit.standing.target.rank.rank, LEVEL_ELEVEN_RANK)
        # The even chart, with no slide toward the next.
        self.assertEqual(hit.rank_difference, 0)
        self.assertEqual(hit.standing.slid.share, 0)

    def test_one_allys_large_buff_moves_him_about_half_a_rank(self) -> None:
        self.maren_buffs_hobb()
        self.open_the_fight()

        hit, rolled_with = self.hit_roll()

        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_STRENGTH)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_STRENGTH + LARGE_BUFF)
        self.assertEqual(hit.rank_difference, 0)
        self.assertGreaterEqual(hit.standing.slid.share, 0.4)
        self.assertLessEqual(hit.standing.slid.share, 0.6)

    def test_a_large_debuff_on_the_bandit_moves_him_the_same_from_its_side(self) -> None:
        self.open_the_fight()
        self.weaken_the_bandit()

        hit, rolled_with = self.hit_roll()

        # The bandit acts as a level lower by half a level: 146 less the Large value, 4.
        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_STRENGTH - LARGE_BUFF)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_STRENGTH)
        self.assertEqual(hit.rank_difference, 0)
        self.assertGreaterEqual(hit.standing.slid.share, 0.4)
        self.assertLessEqual(hit.standing.slid.share, 0.6)

    # -- the ally's buff and the bandit's debuff ---------------------------------------

    def maren_buffs_hobb(self) -> None:
        """Maren casts a Large Unarmed Attack buff on Hobb the way the web client does."""
        technique = TechniqueFactory(
            name="Iron Knuckle",
            gift=GiftFactory(),
            intensity=20,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Casting")),
        )
        condition = ConditionTemplateFactory(name="Iron Knuckle")
        ConditionCheckModifierFactory(
            condition=condition, check_type=self.unarmed, check_category=None, modifier_value=5
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            modifier_size=ModifierSize.LARGE,
        )
        sheet = self.maren.sheet_data
        CharacterClassLevelFactory(
            character=sheet, character_class=CharacterClassFactory(), level=LEVEL, is_primary=True
        )
        grant_technique(sheet.primary_persona, technique)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            cast = self.web(
                self.maren,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=self.hobb.sheet_data.primary_persona.pk,
            )
        self.assertTrue(cast.detail.success, cast.detail.message)

    def weaken_the_bandit(self) -> None:
        """A Large debuff to Unarmed Attack on the bandit, applied at level 11."""
        weakened = ConditionTemplateFactory(name="Hamstrung")
        ConditionCheckModifierFactory(
            condition=weakened, check_type=self.unarmed, check_category=None, modifier_value=-1
        )
        ConditionInstanceFactory(
            target=self.bandit.objectdb,
            condition=weakened,
            modifier_level=LEVEL,
            modifier_size=ModifierSize.LARGE,
        )


class _TierJumpField(_LevelElevenField):
    """Hobb with ordinary skills at one level strikes a bandit one level lower."""

    def ordinary_skill(self, level: int) -> int:
        """The half of the level's baseline the level term leaves, one point a skill level."""
        return (18 + 8 * (level - 1)) // 2


class CrossingIntoTheSecondTierIsWorthFourRanks(_TierJumpField):
    """Level 6 starts the second tier: 24 more points, three ranks, on top of the level step."""

    hobb_level = 6
    bandit_level = 5
    unarmed_value = 29  # half of level 6's baseline of 58

    def test_a_level_six_pc_is_four_ranks_above_a_level_five_bandit(self) -> None:
        self.open_the_fight()

        hit, rolled_with = self.hit_roll()

        # Level 5 is 50 points with no tier; level 6 is 58 plus 24 and her skills add 29 of it.
        self.assertEqual(rolled_with["target_difficulty"], 50)
        self.assertEqual(hit.level_points, 29 + 24)
        self.assertEqual(hit.total_points, 82)
        self.assertEqual(hit.standing.target.rank.rank, 5)
        self.assertEqual(hit.standing.roller.rank.rank, 9)
        self.assertEqual(hit.rank_difference, 4)


class StayingInTheFirstTierIsWorthOneRank(_TierJumpField):
    """Level 5 is still in the first tier: stepping up a level is one rank."""

    hobb_level = 5
    bandit_level = 4
    unarmed_value = 25  # half of level 5's baseline of 50

    def test_a_level_five_pc_is_one_rank_above_a_level_four_bandit(self) -> None:
        self.open_the_fight()

        hit, rolled_with = self.hit_roll()

        self.assertEqual(rolled_with["target_difficulty"], 42)
        self.assertEqual(hit.level_points, 25)
        self.assertEqual(hit.total_points, 50)
        self.assertEqual(hit.standing.target.rank.rank, 4)
        self.assertEqual(hit.standing.roller.rank.rank, 5)
        self.assertEqual(hit.rank_difference, 1)


LOCK_LEVEL = 8
LOCK_BASELINE = 74  # 18 + 8 x 7
LOCK_STRENGTH = 98  # plus the tiers starting at levels 6: 24 points
LOCK_RANK = 11  # (98 - 18) / 8 + 1


class ALockAuthoredAtLevelEightIsRolledAtItsLevelsRank(JourneyCase):
    """A hidden trap authored at ``detect_difficulty_level=8`` with no owner (#5093).

    The room-feature seam is ``search_room_traps``, the roll the Search action makes against
    every hidden trap. The lock has a level and no points, so it asks the strength of level 8
    (its baseline plus the level-6 tier), and a level-8 searcher whose skill is half of the
    baseline rolls on the even chart.
    """

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        room = self.make_room("The Vault Corridor")
        self.mira = self.make_player("Mira", room=room)
        sheet = self.mira.sheet_data
        CharacterClassLevelFactory(
            character=sheet,
            character_class=CharacterClassFactory(),
            level=LOCK_LEVEL,
            is_primary=True,
        )
        search_skill = SkillTraitFactory(name="Search")
        # Half the baseline is her level term; the skill makes the other half, one point each.
        CharacterTraitValueFactory(character=sheet, trait=search_skill, value=LOCK_BASELINE // 2)
        self.search = CheckTypeFactory(name="Search the Vault")
        CheckTypeTraitFactory(check_type=self.search, trait=search_skill, weight=1)
        self.lock = TrapFactory(
            room_profile=room.room_profile,
            detect_check_type=self.search,
            detect_difficulty_level=LOCK_LEVEL,
        )

    def test_the_lock_is_rolled_against_its_levels_rank_with_no_rank_difference(self) -> None:
        rolled: list[tuple[CheckResult, dict[str, Any]]] = []

        def spy(character, check_type, *args, **kwargs):
            result = perform_check_with_modifiers(character, check_type, *args, **kwargs)
            rolled.append((result, kwargs))
            return result

        with patch("world.checks.services.perform_check_with_modifiers", side_effect=spy):
            search_room_traps(self.mira, self.mira.location.room_profile)

        result, rolled_with = rolled[0]
        self.assertEqual(rolled_with["target_difficulty"], LOCK_STRENGTH)
        self.assertEqual(result.total_points, LOCK_STRENGTH)
        self.assertEqual(result.standing.roller.rank.rank, LOCK_RANK)
        self.assertEqual(result.standing.target.rank.rank, LOCK_RANK)
        self.assertEqual(result.rank_difference, 0)
