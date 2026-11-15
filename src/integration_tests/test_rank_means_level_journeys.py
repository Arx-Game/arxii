"""Journeys for a rank meaning a level, with level on both sides of a check (#5093).

Hobb is a level-11 character at the Steading. He Strikes a level-11 bandit with his bare
hands through the web dispatch (``combat_strike``), and the round resolves with the real
rolls: nothing is forced, only the hit roll's standing is read back. On the seeded ladder
(rank N starts at 18 + 8 x (N - 1), so one level is 8 points wide) and a level share of 0.5:

* Level 11's baseline is 98 and rank 11 starts there. The bandit is a level, not a pile of
  points, so it opposes with 98. Hobb's level term is half of the baseline, 49, and his
  Unarmed Combat of 49 (one point a level on the seeded conversion) is the other half: his
  total is 98, the start of rank 11 against rank 11. The even chart, with no slide.
* An ally's Large buff is half of a level's 8 points: 4. Hobb rolls 102, half way through
  rank 11, so the even chart slides half way toward the next.
* A Large debuff on the bandit lowers it by the same 4, to 94, half way through rank 10:
  the same half-rank gain from the other side.

Expected totals come from the spec's numbers (baseline 18 + 8 per level, level share 0.5, a
Large modifier at fraction 0.5 of an 8-point level), not from the code.
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
from world.checks.services import perform_check
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
UNARMED_COMBAT = 49  # half of the baseline: the level term is the other half
LARGE_BUFF = 4  # Large is 0.5 of an 8-point level


class _LevelElevenField(JourneyCase):
    """Hobb (level 11, Unarmed Combat 49) and a level-11 bandit at the Steading."""

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
            character=sheet, character_class=CharacterClassFactory(), level=LEVEL, is_primary=True
        )
        CharacterTraitValueFactory(character=sheet, trait=unarmed_skill, value=UNARMED_COMBAT)
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
            encounter=self.encounter, name="Bandit", health=200, max_health=200, level=LEVEL
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

        # The bandit has a level and no points: level 11's baseline.
        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_BASELINE)
        # Hobb's level term (49) and his Unarmed Combat (49) make the other half and the whole.
        self.assertEqual(hit.level_points, UNARMED_COMBAT)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_BASELINE)
        self.assertEqual(hit.standing.roller.rank.rank, LEVEL)
        self.assertEqual(hit.standing.target.rank.rank, LEVEL)
        # The even chart, with no slide toward the next.
        self.assertEqual(hit.rank_difference, 0)
        self.assertEqual(hit.standing.slid.share, 0)

    def test_one_allys_large_buff_moves_him_about_half_a_rank(self) -> None:
        self.maren_buffs_hobb()
        self.open_the_fight()

        hit, rolled_with = self.hit_roll()

        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_BASELINE)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_BASELINE + LARGE_BUFF)
        self.assertEqual(hit.rank_difference, 0)
        self.assertGreaterEqual(hit.standing.slid.share, 0.4)
        self.assertLessEqual(hit.standing.slid.share, 0.6)

    def test_a_large_debuff_on_the_bandit_moves_him_the_same_from_its_side(self) -> None:
        self.open_the_fight()
        self.weaken_the_bandit()

        hit, rolled_with = self.hit_roll()

        # The bandit acts as a level lower by half a level: 98 less the Large value, 4.
        self.assertEqual(rolled_with["target_difficulty"], LEVEL_ELEVEN_BASELINE - LARGE_BUFF)
        self.assertEqual(hit.total_points, LEVEL_ELEVEN_BASELINE)
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
