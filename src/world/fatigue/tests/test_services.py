"""Tests for fatigue service functions."""

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.constants import (
    CAPACITY_STAT_MULTIPLIER,
    CAPACITY_WILLPOWER_MULTIPLIER,
    MIN_FATIGUE_COST,
    REST_AP_COST,
    WELL_RESTED_MULTIPLIER,
    EffortLevel,
    FatigueCategory,
    FatigueZone,
)
from world.fatigue.models import FatiguePool
from world.fatigue.services import (
    apply_fatigue,
    get_fatigue_capacity,
    get_fatigue_penalty,
    get_fatigue_percentage,
    get_fatigue_zone,
    get_or_create_fatigue_pool,
    reset_fatigue,
    rest,
    should_check_collapse,
)
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import TraitCategory


def _setup_stat(character, stat_name, internal_value, category=TraitCategory.PHYSICAL):
    """Helper to create a stat trait and assign a value to a character.

    Args:
        character: ObjectDB character instance.
        stat_name: Name of the stat (e.g. "stamina").
        internal_value: Internal scale value (e.g. 30 for display value 3).
        category: TraitCategory for the stat.
    """
    trait = StatTraitFactory(name=stat_name, category=category)
    CharacterTraitValueFactory(character=character, trait=trait, value=internal_value)
    # Clear trait handler cache so it picks up the new value
    if hasattr(character, "traits") and character.traits.initialized:
        character.traits.clear_cache()


class GetOrCreateFatiguePoolTests(TestCase):
    """Tests for get_or_create_fatigue_pool."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_creates_pool_if_none_exists(self):
        """Should create a new pool with defaults."""
        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.physical_current == 0
        assert pool.social_current == 0
        assert pool.mental_current == 0
        assert pool.well_rested is False

    def test_returns_existing_pool(self):
        """Should return existing pool without creating a new one."""
        existing = FatiguePool.objects.create(character=self.sheet, physical_current=5)
        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.pk == existing.pk
        assert pool.physical_current == 5


class GetFatigueCapacityTests(TestCase):
    """Tests for get_fatigue_capacity."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_capacity_from_stats(self):
        """Capacity = endurance * 10 + willpower * 3 (display values)."""
        char = self.sheet.character
        # stamina display 3 (internal 30), willpower display 2 (internal 20)
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

        capacity = get_fatigue_capacity(self.sheet, FatigueCategory.PHYSICAL)
        expected = 3 * CAPACITY_STAT_MULTIPLIER + 2 * CAPACITY_WILLPOWER_MULTIPLIER
        assert capacity == expected

    def test_capacity_social_uses_composure(self):
        """Social fatigue capacity uses composure as the endurance stat."""
        char = self.sheet.character
        _setup_stat(char, "composure", 40, TraitCategory.SOCIAL)
        _setup_stat(char, "willpower", 10, TraitCategory.META)

        capacity = get_fatigue_capacity(self.sheet, FatigueCategory.SOCIAL)
        expected = 4 * CAPACITY_STAT_MULTIPLIER + 1 * CAPACITY_WILLPOWER_MULTIPLIER
        assert capacity == expected

    def test_capacity_mental_uses_stability(self):
        """Mental fatigue capacity uses stability as the endurance stat."""
        char = self.sheet.character
        _setup_stat(char, "stability", 50, TraitCategory.MENTAL)
        _setup_stat(char, "willpower", 30, TraitCategory.META)

        capacity = get_fatigue_capacity(self.sheet, FatigueCategory.MENTAL)
        expected = 5 * CAPACITY_STAT_MULTIPLIER + 3 * CAPACITY_WILLPOWER_MULTIPLIER
        assert capacity == expected

    def test_well_rested_multiplier(self):
        """Well-rested characters get 1.5x capacity."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

        pool = get_or_create_fatigue_pool(self.sheet)
        pool.well_rested = True
        pool.save()

        capacity = get_fatigue_capacity(self.sheet, FatigueCategory.PHYSICAL)
        base = 3 * CAPACITY_STAT_MULTIPLIER + 2 * CAPACITY_WILLPOWER_MULTIPLIER
        expected = int(base * WELL_RESTED_MULTIPLIER)
        assert capacity == expected

    def test_zero_stats_gives_zero_capacity(self):
        """Characters with no stats have 0 capacity."""
        capacity = get_fatigue_capacity(self.sheet, FatigueCategory.PHYSICAL)
        assert capacity == 0


class GetFatigueZoneTests(TestCase):
    """Tests for get_fatigue_zone."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def _set_fatigue_and_capacity(self, current, stamina_internal=30, willpower_internal=20):
        """Helper to set up fatigue level with known capacity."""
        char = self.sheet.character
        _setup_stat(char, "stamina", stamina_internal, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", willpower_internal, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", current)
        pool.save()

    def test_fresh_zone(self):
        """0-40% fatigue is FRESH."""
        # Capacity = 3*10 + 2*3 = 36. 0% fatigue.
        self._set_fatigue_and_capacity(0)
        assert get_fatigue_zone(self.sheet, FatigueCategory.PHYSICAL) == FatigueZone.FRESH

    def test_strained_zone(self):
        """41-60% fatigue is STRAINED."""
        # Capacity = 36. 50% = 18
        self._set_fatigue_and_capacity(18)
        zone = get_fatigue_zone(self.sheet, FatigueCategory.PHYSICAL)
        assert zone == FatigueZone.STRAINED

    def test_tired_zone(self):
        """61-80% fatigue is TIRED."""
        # Capacity = 36. ~72% = 26
        self._set_fatigue_and_capacity(26)
        zone = get_fatigue_zone(self.sheet, FatigueCategory.PHYSICAL)
        assert zone == FatigueZone.TIRED

    def test_overexerted_zone(self):
        """81-99% fatigue is OVEREXERTED."""
        # Capacity = 36. ~92% = 33
        self._set_fatigue_and_capacity(33)
        zone = get_fatigue_zone(self.sheet, FatigueCategory.PHYSICAL)
        assert zone == FatigueZone.OVEREXERTED

    def test_exhausted_zone(self):
        """100%+ fatigue is EXHAUSTED."""
        # Capacity = 36. Over 100% = 40
        self._set_fatigue_and_capacity(40)
        zone = get_fatigue_zone(self.sheet, FatigueCategory.PHYSICAL)
        assert zone == FatigueZone.EXHAUSTED


class GetFatiguePenaltyTests(TestCase):
    """Tests for get_fatigue_penalty."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_fresh_no_penalty(self):
        """FRESH zone has 0 penalty."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

        assert get_fatigue_penalty(self.sheet, FatigueCategory.PHYSICAL) == 0

    def test_strained_penalty(self):
        """STRAINED zone has -1 penalty."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 18)  # ~50% of 36 capacity
        pool.save()

        assert get_fatigue_penalty(self.sheet, FatigueCategory.PHYSICAL) == -1

    def test_exhausted_penalty(self):
        """EXHAUSTED zone has -4 penalty."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 40)  # >100% of 36 capacity
        pool.save()

        assert get_fatigue_penalty(self.sheet, FatigueCategory.PHYSICAL) == -4


class ApplyFatigueTests(TestCase):
    """Tests for apply_fatigue."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_medium_effort_full_cost(self):
        """Medium effort applies base cost * 1.0."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.MEDIUM)
        assert cost == 10

        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.get_current("physical") == 10

    def test_very_low_effort_reduced_cost(self):
        """Very low effort applies base cost * 0.1 but at least MIN_FATIGUE_COST."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.VERY_LOW)
        # int(10 * 0.1) = 1, which equals MIN_FATIGUE_COST
        assert cost == MIN_FATIGUE_COST

    def test_low_effort_half_cost(self):
        """Low effort applies base cost * 0.5."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.LOW)
        assert cost == 5

    def test_high_effort_double_cost(self):
        """High effort applies base cost * 2.0."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.HIGH)
        assert cost == 20

    def test_extreme_effort_triple_plus_cost(self):
        """Extreme effort applies base cost * 3.5."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.EXTREME)
        assert cost == 35

    def test_min_fatigue_cost_enforced(self):
        """Even very low effort on a tiny base cost returns at least MIN_FATIGUE_COST."""
        cost = apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 1, EffortLevel.VERY_LOW)
        # int(1 * 0.1) = 0, but MIN_FATIGUE_COST = 1
        assert cost == MIN_FATIGUE_COST

    def test_fatigue_accumulates(self):
        """Multiple applications stack."""
        apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 10, EffortLevel.MEDIUM)
        apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 5, EffortLevel.MEDIUM)

        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.get_current("physical") == 15

    def test_fatigue_can_exceed_capacity(self):
        """Fatigue is not capped at capacity."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 10, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 10, TraitCategory.META)
        # Capacity = 1*10 + 1*3 = 13

        apply_fatigue(self.sheet, FatigueCategory.PHYSICAL, 20, EffortLevel.MEDIUM)
        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.get_current("physical") == 20  # Exceeds capacity of 13


class ShouldCheckCollapseTests(TestCase):
    """Tests for should_check_collapse."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def _setup_overexerted(self):
        """Put the character into the overexerted zone."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 33)  # ~92% of 36
        pool.save()

    def test_very_low_always_safe(self):
        """Very low effort never triggers collapse check."""
        self._setup_overexerted()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.VERY_LOW)
        assert result is False

    def test_low_always_safe(self):
        """Low effort never triggers collapse check."""
        self._setup_overexerted()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.LOW)
        assert result is False

    def test_medium_safe_when_overexerted(self):
        """Medium effort does NOT trigger collapse when overexerted."""
        self._setup_overexerted()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.MEDIUM)
        assert result is False

    def test_medium_collapses_when_exhausted(self):
        """Medium effort DOES trigger collapse when exhausted (100%+)."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        # capacity = 30*10 + 20*3 = 360... wait, that's display scale
        # stamina display=3, so capacity = 3*10 + 2*3 = 36
        pool.set_current("physical", 40)  # 111% of 36 → exhausted
        pool.save()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.MEDIUM)
        assert result is True

    def test_high_when_overexerted(self):
        """High effort triggers collapse when overexerted."""
        self._setup_overexerted()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.HIGH)
        assert result is True

    def test_extreme_when_overexerted(self):
        """Extreme effort triggers collapse when overexerted."""
        self._setup_overexerted()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.EXTREME)
        assert result is True

    def test_high_when_fresh(self):
        """High effort does not trigger collapse when fresh."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.HIGH)
        assert result is False

    def test_high_when_strained(self):
        """High effort does not trigger collapse when strained."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 18)  # ~50%
        pool.save()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.HIGH)
        assert result is False

    def test_high_when_tired(self):
        """High effort does not trigger collapse when tired."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 26)  # ~72%
        pool.save()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.HIGH)
        assert result is False

    def test_extreme_when_exhausted(self):
        """Extreme effort triggers collapse when exhausted."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 40)  # >100%
        pool.save()
        result = should_check_collapse(self.sheet, FatigueCategory.PHYSICAL, EffortLevel.EXTREME)
        assert result is True


class ResetFatigueTests(TestCase):
    """Tests for reset_fatigue."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_resets_all_pools_to_zero(self):
        """All three fatigue pools should be set to 0."""
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.physical_current = 20
        pool.social_current = 15
        pool.mental_current = 10
        pool.well_rested = True
        pool.rested_today = True
        pool.dawn_deferred = True
        pool.save()

        reset_fatigue(self.sheet)

        pool.refresh_from_db()
        assert pool.physical_current == 0
        assert pool.social_current == 0
        assert pool.mental_current == 0
        assert pool.well_rested is False
        assert pool.rested_today is False
        assert pool.dawn_deferred is False


class RestTests(TestCase):
    """Tests for rest service function."""

    def setUp(self):
        FatiguePool.flush_instance_cache()
        ActionPointPool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_rest_sets_flags(self):
        """Resting sets well_rested and rested_today."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )

        result = rest(self.sheet)

        assert result.success is True
        pool = get_or_create_fatigue_pool(self.sheet)
        assert pool.well_rested is True
        assert pool.rested_today is True

    def test_rest_spends_ap(self):
        """Resting costs the configured AP amount."""
        ap_pool = ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )

        rest(self.sheet)

        ap_pool.refresh_from_db()
        assert ap_pool.current == 200 - REST_AP_COST

    def test_rest_fails_if_already_rested(self):
        """Cannot rest twice in one day."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=200,
            maximum=200,
        )

        pool = get_or_create_fatigue_pool(self.sheet)
        pool.rested_today = True
        pool.save()

        result = rest(self.sheet)
        assert result.success is False
        assert "already rested" in result.message.lower()

    def test_rest_fails_if_insufficient_ap(self):
        """Cannot rest without enough AP."""
        ActionPointPool.objects.create(
            character=self.sheet.character,
            current=REST_AP_COST - 1,
            maximum=200,
        )

        result = rest(self.sheet)
        assert result.success is False
        assert "action points" in result.message.lower()


class GetFatiguePercentageTests(TestCase):
    """Tests for get_fatigue_percentage."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_zero_fatigue_is_zero_percent(self):
        """No fatigue accumulated returns 0%."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)

        pct = get_fatigue_percentage(self.sheet, FatigueCategory.PHYSICAL)
        assert pct == 0.0

    def test_half_capacity(self):
        """50% of capacity returns 50%."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        # Capacity = 36
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 18)
        pool.save()

        pct = get_fatigue_percentage(self.sheet, FatigueCategory.PHYSICAL)
        assert pct == 50.0

    def test_over_capacity(self):
        """Fatigue over capacity returns >100%."""
        char = self.sheet.character
        _setup_stat(char, "stamina", 30, TraitCategory.PHYSICAL)
        _setup_stat(char, "willpower", 20, TraitCategory.META)
        # Capacity = 36
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 72)
        pool.save()

        pct = get_fatigue_percentage(self.sheet, FatigueCategory.PHYSICAL)
        assert pct == 200.0

    def test_zero_capacity_no_fatigue_returns_zero(self):
        """Zero capacity with no fatigue returns 0%."""
        pct = get_fatigue_percentage(self.sheet, FatigueCategory.PHYSICAL)
        assert pct == 0.0

    def test_zero_capacity_with_fatigue_returns_hundred(self):
        """Zero capacity with accumulated fatigue returns 100%."""
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.set_current("physical", 5)
        pool.save()

        pct = get_fatigue_percentage(self.sheet, FatigueCategory.PHYSICAL)
        assert pct == 100.0
