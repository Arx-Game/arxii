"""#3066: check-based development points accrue through the real combat
offense-check path (``CombatTechniqueResolver._roll_check`` -- the method
``resolve_combat_technique``/``_run_combat_technique_pipeline`` actually call
during round resolution), not just when ``perform_check`` is called directly.

Before #3066, ``_roll_check`` folded ``EFFORT_CHECK_MODIFIER`` into a labeled
``ModifierContribution`` and always called ``perform_check`` with
``effort_level=None`` -- so a PC's declared combat effort shifted the roll but
never awarded check-based development points, exactly the #3048 audit's
criticism (green suite, dead feature) applied to the combat production path.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import CombatTechniqueResolver
from world.fatigue.constants import EffortLevel
from world.progression.models import DevelopmentPoints, WeeklySkillUsage
from world.progression.services.skill_development import calculate_check_dev_points
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


class CombatOffenseCheckDevelopmentAwardTests(TestCase):
    """A PC's offense roll, resolved through the real production call
    (``CombatTechniqueResolver._roll_check``), must award WeeklySkillUsage +
    DevelopmentPoints rows for the actor when they declare an effort level."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        cls.trait, _ = Trait.objects.get_or_create(
            name="combat_dp_test_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        cls.category = CheckCategoryFactory(name="combat_dp_test_category")
        cls.check_type = CheckTypeFactory(name="combat_dp_test_strike", category=cls.category)
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.trait, weight=1)

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        WeeklySkillUsage.flush_instance_cache()
        DevelopmentPoints.flush_instance_cache()
        ResultChart.clear_cache()

        self.sheet = CharacterSheetFactory()
        WeeklySkillUsage.objects.filter(character_sheet=self.sheet).delete()
        DevelopmentPoints.objects.filter(character_sheet=self.sheet).delete()
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=30)

        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        self.opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        self.participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        self.action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_opponent_target=self.opponent,
            effort_level=EffortLevel.HIGH,
        )

    def _build_resolver(self) -> CombatTechniqueResolver:
        return CombatTechniqueResolver(
            participant=self.participant,
            action=self.action,
            pull_flat_bonus=0,
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=self.check_type,
            offense_check_fn=None,
        )

    def test_offense_roll_awards_development_points(self):
        resolver = self._build_resolver()

        resolver._roll_check()

        expected_dp = calculate_check_dev_points(EffortLevel.HIGH, path_level=1)
        self.assertGreater(expected_dp, 0)

        usage = WeeklySkillUsage.objects.get(character_sheet=self.sheet, trait=self.trait)
        self.assertEqual(usage.check_count, 1)
        self.assertEqual(usage.points_earned, expected_dp)

        dev = DevelopmentPoints.objects.get(character_sheet=self.sheet, trait=self.trait)
        self.assertEqual(dev.total_earned, expected_dp)
