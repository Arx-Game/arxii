"""Tests for action points models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.action_points.factories import ActionPointConfigFactory, ActionPointPoolFactory
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction, DistinctionEffect
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
from world.mechanics.services import create_distinction_modifiers


class ActionPointPoolTestCase(TestCase):
    """Base test case that clears SharedMemoryModel cache between tests."""

    def setUp(self):
        """Clear ActionPointPool cache to avoid cross-test pollution."""
        ActionPointPool.flush_instance_cache()


class ActionPointConfigModelTests(TestCase):
    """Tests for ActionPointConfig model."""

    def test_str_representation(self):
        """ActionPointConfig string shows name and active status."""
        config = ActionPointConfigFactory(name="Default", is_active=True)
        assert str(config) == "Default (Active)"

    def test_str_inactive(self):
        """Inactive config shows just the name."""
        config = ActionPointConfigFactory(name="Old Config", is_active=False)
        assert str(config) == "Old Config"

    def test_name_unique(self):
        """ActionPointConfig names must be unique."""
        ActionPointConfigFactory(name="Unique Name")
        with self.assertRaises(IntegrityError):
            ActionPointConfig.objects.create(name="Unique Name")

    def test_get_active_returns_active_config(self):
        """get_active returns the active configuration."""
        ActionPointConfigFactory(name="Inactive", is_active=False)
        active = ActionPointConfigFactory(name="Active", is_active=True)

        result = ActionPointConfig.get_active()
        assert result == active

    def test_get_active_returns_none_when_no_active(self):
        """get_active returns None when no config is active."""
        ActionPointConfigFactory(is_active=False)

        result = ActionPointConfig.get_active()
        assert result is None

    def test_get_default_maximum_from_active(self):
        """get_default_maximum returns value from active config."""
        ActionPointConfigFactory(default_maximum=300, is_active=True)

        assert ActionPointConfig.get_default_maximum() == 300

    def test_get_default_maximum_fallback(self):
        """get_default_maximum returns fallback when no active config."""
        assert ActionPointConfig.get_default_maximum() == 200

    def test_get_daily_regen_from_active(self):
        """get_daily_regen returns value from active config."""
        ActionPointConfigFactory(daily_regen=10, is_active=True)

        assert ActionPointConfig.get_daily_regen() == 10

    def test_get_daily_regen_fallback(self):
        """get_daily_regen returns fallback when no active config."""
        assert ActionPointConfig.get_daily_regen() == 5

    def test_get_weekly_regen_from_active(self):
        """get_weekly_regen returns value from active config."""
        ActionPointConfigFactory(weekly_regen=150, is_active=True)

        assert ActionPointConfig.get_weekly_regen() == 150

    def test_get_weekly_regen_fallback(self):
        """get_weekly_regen returns fallback when no active config."""
        assert ActionPointConfig.get_weekly_regen() == 100


class ActionPointPoolModelTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_str_representation(self):
        """ActionPointPool string shows character and values."""
        pool = ActionPointPoolFactory(
            character=self.character,
            current=150,
            maximum=200,
            banked=25,
        )
        assert "150/200" in str(pool)
        assert "banked: 25" in str(pool)

    def test_one_pool_per_character(self):
        """Each character can only have one pool."""
        ActionPointPoolFactory(character=self.character)
        with self.assertRaises(IntegrityError):
            ActionPointPoolFactory(character=self.character)


class ActionPointPoolSpendTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.spend method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_spend_success(self):
        """spend deducts from current when sufficient."""
        pool = ActionPointPoolFactory(character=self.character, current=100)

        result = pool.spend(30)

        assert result is True
        pool.refresh_from_db()
        assert pool.current == 70

    def test_spend_insufficient_fails(self):
        """spend returns False when insufficient AP."""
        pool = ActionPointPoolFactory(character=self.character, current=20)

        result = pool.spend(30)

        assert result is False
        pool.refresh_from_db()
        assert pool.current == 20

    def test_spend_exact_amount(self):
        """spend works when spending exact amount available."""
        pool = ActionPointPoolFactory(character=self.character, current=50)

        result = pool.spend(50)

        assert result is True
        pool.refresh_from_db()
        assert pool.current == 0

    def test_spend_negative_fails(self):
        """spend returns False for negative amounts."""
        pool = ActionPointPoolFactory(character=self.character, current=100)

        result = pool.spend(-10)

        assert result is False
        pool.refresh_from_db()
        assert pool.current == 100


class ActionPointPoolBankTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.bank method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_bank_success(self):
        """bank moves AP from current to banked."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=0)

        result = pool.bank(30)

        assert result is True
        pool.refresh_from_db()
        assert pool.current == 70
        assert pool.banked == 30

    def test_bank_insufficient_fails(self):
        """bank returns False when insufficient current AP."""
        pool = ActionPointPoolFactory(character=self.character, current=20, banked=0)

        result = pool.bank(30)

        assert result is False
        pool.refresh_from_db()
        assert pool.current == 20
        assert pool.banked == 0

    def test_bank_adds_to_existing_banked(self):
        """bank adds to existing banked amount."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=50)

        result = pool.bank(30)

        assert result is True
        pool.refresh_from_db()
        assert pool.current == 70
        assert pool.banked == 80

    def test_bank_negative_fails(self):
        """bank returns False for negative amounts."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=0)

        result = pool.bank(-10)

        assert result is False
        pool.refresh_from_db()
        assert pool.current == 100
        assert pool.banked == 0


class ActionPointPoolUnbankTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.unbank method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_unbank_full_restore(self):
        """unbank restores full amount when space available."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200, banked=50)

        restored = pool.unbank(50)

        assert restored == 50
        pool.refresh_from_db()
        assert pool.current == 150
        assert pool.banked == 0

    def test_unbank_capped_at_maximum(self):
        """unbank caps restoration at maximum, excess is lost."""
        pool = ActionPointPoolFactory(character=self.character, current=180, maximum=200, banked=50)

        restored = pool.unbank(50)

        # Only 20 space available, so only 20 restored
        assert restored == 20
        pool.refresh_from_db()
        assert pool.current == 200
        # Full amount left banked (50) but was removed
        assert pool.banked == 0

    def test_unbank_at_maximum_loses_all(self):
        """unbank loses all when already at maximum."""
        pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200, banked=50)

        restored = pool.unbank(50)

        assert restored == 0
        pool.refresh_from_db()
        assert pool.current == 200
        assert pool.banked == 0

    def test_unbank_partial_amount(self):
        """unbank can restore partial amount."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200, banked=50)

        restored = pool.unbank(20)

        assert restored == 20
        pool.refresh_from_db()
        assert pool.current == 120
        assert pool.banked == 30

    def test_unbank_more_than_banked(self):
        """unbank only unbanks what's actually banked."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200, banked=30)

        restored = pool.unbank(50)

        assert restored == 30
        pool.refresh_from_db()
        assert pool.current == 130
        assert pool.banked == 0

    def test_unbank_negative_returns_zero(self):
        """unbank returns 0 for negative amounts."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200, banked=50)

        restored = pool.unbank(-10)

        assert restored == 0
        pool.refresh_from_db()
        assert pool.current == 100
        assert pool.banked == 50


class ActionPointPoolConsumeBankedTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.consume_banked method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_consume_banked_success(self):
        """consume_banked removes from banked without affecting current."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=50)

        result = pool.consume_banked(30)

        assert result is True
        pool.refresh_from_db()
        assert pool.current == 100  # Unchanged
        assert pool.banked == 20

    def test_consume_banked_insufficient_fails(self):
        """consume_banked returns False when insufficient banked AP."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=20)

        result = pool.consume_banked(30)

        assert result is False
        pool.refresh_from_db()
        assert pool.current == 100
        assert pool.banked == 20

    def test_consume_banked_exact_amount(self):
        """consume_banked works for exact banked amount."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=50)

        result = pool.consume_banked(50)

        assert result is True
        pool.refresh_from_db()
        assert pool.banked == 0

    def test_consume_banked_negative_fails(self):
        """consume_banked returns False for negative amounts."""
        pool = ActionPointPoolFactory(character=self.character, current=100, banked=50)

        result = pool.consume_banked(-10)

        assert result is False
        pool.refresh_from_db()
        assert pool.banked == 50


class ActionPointPoolRegenerateTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.regenerate method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_regenerate_adds_to_current(self):
        """regenerate adds AP to current."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        added = pool.regenerate(50)

        assert added == 50
        pool.refresh_from_db()
        assert pool.current == 150

    def test_regenerate_capped_at_maximum(self):
        """regenerate caps at maximum."""
        pool = ActionPointPoolFactory(character=self.character, current=180, maximum=200)

        added = pool.regenerate(50)

        assert added == 20
        pool.refresh_from_db()
        assert pool.current == 200

    def test_regenerate_at_maximum_adds_nothing(self):
        """regenerate adds nothing when already at maximum."""
        pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)

        added = pool.regenerate(50)

        assert added == 0
        pool.refresh_from_db()
        assert pool.current == 200

    def test_regenerate_negative_returns_zero(self):
        """regenerate returns 0 for negative amounts."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        added = pool.regenerate(-10)

        assert added == 0
        pool.refresh_from_db()
        assert pool.current == 100

    def test_regenerate_ignores_banked(self):
        """regenerate fills current regardless of banked amount."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200, banked=50)

        added = pool.regenerate(100)

        assert added == 100
        pool.refresh_from_db()
        assert pool.current == 200
        assert pool.banked == 50  # Unchanged


class ActionPointPoolHelperTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool helper methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_can_afford_true(self):
        """can_afford returns True when sufficient AP."""
        pool = ActionPointPoolFactory(character=self.character, current=100)
        assert pool.can_afford(50) is True

    def test_can_afford_false(self):
        """can_afford returns False when insufficient AP."""
        pool = ActionPointPoolFactory(character=self.character, current=30)
        assert pool.can_afford(50) is False

    def test_can_afford_exact(self):
        """can_afford returns True for exact amount."""
        pool = ActionPointPoolFactory(character=self.character, current=50)
        assert pool.can_afford(50) is True

    def test_can_bank_true(self):
        """can_bank returns True when sufficient AP."""
        pool = ActionPointPoolFactory(character=self.character, current=100)
        assert pool.can_bank(50) is True

    def test_can_bank_false(self):
        """can_bank returns False when insufficient AP."""
        pool = ActionPointPoolFactory(character=self.character, current=30)
        assert pool.can_bank(50) is False


class ActionPointPoolGetOrCreateTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.get_or_create_for_character."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_creates_new_pool(self):
        """get_or_create_for_character creates pool if none exists."""
        pool = ActionPointPool.get_or_create_for_character(self.character)

        assert pool.character == self.character
        assert pool.current == 200  # Default
        assert pool.maximum == 200  # Default

    def test_returns_existing_pool(self):
        """get_or_create_for_character returns existing pool."""
        existing = ActionPointPoolFactory(character=self.character, current=50, maximum=200)

        pool = ActionPointPool.get_or_create_for_character(self.character)

        assert pool == existing
        assert pool.current == 50

    def test_uses_active_config_defaults(self):
        """get_or_create_for_character uses active config for defaults."""
        ActionPointConfigFactory(default_maximum=300, is_active=True)
        character = CharacterFactory()

        pool = ActionPointPool.get_or_create_for_character(character)

        assert pool.maximum == 300
        assert pool.current == 300


class ActionPointPoolApplyDailyRegenTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.apply_daily_regen method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_apply_daily_regen_adds_ap(self):
        """apply_daily_regen adds configured daily amount."""
        ActionPointConfigFactory(daily_regen=10, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        old_timestamp = pool.last_daily_regen

        added = pool.apply_daily_regen()

        assert added == 10
        pool.refresh_from_db()
        assert pool.current == 110
        assert pool.last_daily_regen > old_timestamp

    def test_apply_daily_regen_capped_at_maximum(self):
        """apply_daily_regen caps at maximum."""
        ActionPointConfigFactory(daily_regen=10, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=195, maximum=200)

        added = pool.apply_daily_regen()

        assert added == 5
        pool.refresh_from_db()
        assert pool.current == 200

    def test_apply_daily_regen_at_maximum(self):
        """apply_daily_regen adds nothing when at maximum but still updates timestamp."""
        ActionPointConfigFactory(daily_regen=10, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)
        old_timestamp = pool.last_daily_regen

        added = pool.apply_daily_regen()

        assert added == 0
        pool.refresh_from_db()
        assert pool.current == 200
        assert pool.last_daily_regen > old_timestamp

    def test_apply_daily_regen_uses_fallback(self):
        """apply_daily_regen uses fallback when no active config."""
        # No active config, fallback is 5
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        added = pool.apply_daily_regen()

        assert added == 5
        pool.refresh_from_db()
        assert pool.current == 105


class ActionPointPoolApplyWeeklyRegenTests(ActionPointPoolTestCase):
    """Tests for ActionPointPool.apply_weekly_regen method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_apply_weekly_regen_adds_ap(self):
        """apply_weekly_regen adds configured weekly amount."""
        ActionPointConfigFactory(weekly_regen=100, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=50, maximum=200)

        added = pool.apply_weekly_regen()

        assert added == 100
        pool.refresh_from_db()
        assert pool.current == 150

    def test_apply_weekly_regen_capped_at_maximum(self):
        """apply_weekly_regen caps at maximum."""
        ActionPointConfigFactory(weekly_regen=100, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=150, maximum=200)

        added = pool.apply_weekly_regen()

        assert added == 50
        pool.refresh_from_db()
        assert pool.current == 200

    def test_apply_weekly_regen_uses_fallback(self):
        """apply_weekly_regen uses fallback when no active config."""
        # No active config, fallback is 100
        pool = ActionPointPoolFactory(character=self.character, current=50, maximum=200)

        added = pool.apply_weekly_regen()

        assert added == 100
        pool.refresh_from_db()
        assert pool.current == 150


class ActionPointPoolModifierTests(ActionPointPoolTestCase):
    """Tests for AP regen with character modifiers (e.g., Indolent distinction)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data including character with sheet and Indolent distinction."""
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Create the Indolent distinction with its effects
        category = DistinctionCategoryFactory(slug="personality", name="Personality")
        cls.indolent = DistinctionFactory(
            slug="indolent",
            name="Indolent",
            category=category,
            cost_per_rank=-15,
            max_rank=1,
        )

        # Create modifier types for AP regen
        ap_category = ModifierCategoryFactory(name="action_points")
        daily_regen = ModifierTypeFactory(category=ap_category, name="ap_daily_regen")
        weekly_regen = ModifierTypeFactory(category=ap_category, name="ap_weekly_regen")

        # Create effects for Indolent: -2 daily, -40 weekly
        DistinctionEffect.objects.create(
            distinction=cls.indolent,
            target=daily_regen,
            value_per_rank=-2,
            description="Reduces daily AP regeneration by 2",
        )
        DistinctionEffect.objects.create(
            distinction=cls.indolent,
            target=weekly_regen,
            value_per_rank=-40,
            description="Reduces weekly AP regeneration by 40",
        )

        # Create Tireless distinction: +1 daily, +20 weekly
        cls.tireless = DistinctionFactory(
            slug="tireless",
            name="Tireless",
            category=category,
            cost_per_rank=15,
            max_rank=1,
        )
        DistinctionEffect.objects.create(
            distinction=cls.tireless,
            target=daily_regen,
            value_per_rank=1,
            description="Increases daily AP regeneration by 1",
        )
        DistinctionEffect.objects.create(
            distinction=cls.tireless,
            target=weekly_regen,
            value_per_rank=20,
            description="Increases weekly AP regeneration by 20",
        )

        # Create Efficient distinction: +100 effective maximum
        ap_max = ModifierTypeFactory(category=ap_category, name="ap_maximum")
        cls.efficient = DistinctionFactory(
            slug="efficient",
            name="Efficient",
            category=category,
            cost_per_rank=20,
            max_rank=1,
        )
        DistinctionEffect.objects.create(
            distinction=cls.efficient,
            target=ap_max,
            value_per_rank=100,
            description="Increases effective AP maximum by 100",
        )

    def _grant_indolent(self):
        """Helper to grant Indolent distinction and create modifiers."""
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.indolent,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)
        return char_distinction

    def test_daily_regen_with_indolent_modifier(self):
        """Indolent reduces daily regen by 2."""
        ActionPointConfigFactory(daily_regen=5, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        self._grant_indolent()

        added = pool.apply_daily_regen()

        # 5 base - 2 from Indolent = 3
        assert added == 3
        pool.refresh_from_db()
        assert pool.current == 103

    def test_weekly_regen_with_indolent_modifier(self):
        """Indolent reduces weekly regen by 40."""
        ActionPointConfigFactory(weekly_regen=100, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=50, maximum=200)
        self._grant_indolent()

        added = pool.apply_weekly_regen()

        # 100 base - 40 from Indolent = 60
        assert added == 60
        pool.refresh_from_db()
        assert pool.current == 110

    def test_regen_modifier_floors_at_zero(self):
        """Regen cannot go negative even with large penalties."""
        ActionPointConfigFactory(daily_regen=1, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        self._grant_indolent()  # -2 modifier, but base is only 1

        added = pool.apply_daily_regen()

        # max(0, 1 - 2) = 0
        assert added == 0
        pool.refresh_from_db()
        assert pool.current == 100

    def test_regen_without_sheet_uses_base(self):
        """Characters without a CharacterSheet regenerate at base rate."""
        ActionPointConfigFactory(daily_regen=5, is_active=True)
        character_no_sheet = CharacterFactory()
        pool = ActionPointPoolFactory(character=character_no_sheet, current=100, maximum=200)

        added = pool.apply_daily_regen()

        # No sheet means no modifiers, so full base rate
        assert added == 5
        pool.refresh_from_db()
        assert pool.current == 105

    def test_regen_without_distinction_uses_base(self):
        """Characters with sheet but no Indolent regenerate at base rate."""
        ActionPointConfigFactory(daily_regen=5, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        # Don't grant Indolent

        added = pool.apply_daily_regen()

        assert added == 5
        pool.refresh_from_db()
        assert pool.current == 105

    def test_daily_regen_with_tireless_modifier(self):
        """Tireless increases daily regen by 1."""
        ActionPointConfigFactory(daily_regen=5, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.tireless,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        added = pool.apply_daily_regen()

        # 5 base + 1 from Tireless = 6
        assert added == 6
        pool.refresh_from_db()
        assert pool.current == 106

    def test_weekly_regen_with_tireless_modifier(self):
        """Tireless increases weekly regen by 20."""
        ActionPointConfigFactory(weekly_regen=100, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=50, maximum=200)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.tireless,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        added = pool.apply_weekly_regen()

        # 100 base + 20 from Tireless = 120
        assert added == 120
        pool.refresh_from_db()
        assert pool.current == 170

    def test_effective_maximum_with_efficient(self):
        """Efficient increases effective maximum by 100."""
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.efficient,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        effective_max = pool.get_effective_maximum()

        # 200 base + 100 from Efficient = 300
        assert effective_max == 300

    def test_regenerate_respects_effective_maximum(self):
        """Regenerate caps at effective maximum, not stored maximum."""
        pool = ActionPointPoolFactory(character=self.character, current=190, maximum=200)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.efficient,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Without Efficient, only 10 space. With Efficient, 110 space.
        added = pool.regenerate(50)

        assert added == 50
        pool.refresh_from_db()
        assert pool.current == 240

    def test_unbank_respects_effective_maximum(self):
        """Unbank caps at effective maximum, not stored maximum."""
        pool = ActionPointPoolFactory(character=self.character, current=195, maximum=200, banked=50)
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.efficient,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Without Efficient, only 5 space. With Efficient, 105 space.
        restored = pool.unbank(50)

        assert restored == 50
        pool.refresh_from_db()
        assert pool.current == 245
        assert pool.banked == 0

    def test_stacking_tireless_and_indolent(self):
        """Tireless and Indolent modifiers stack (net -1 daily, -20 weekly)."""
        ActionPointConfigFactory(daily_regen=5, is_active=True)
        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        # Grant both
        for distinction in [self.tireless, self.indolent]:
            char_distinction = CharacterDistinction.objects.create(
                character=self.character,
                distinction=distinction,
                rank=1,
            )
            create_distinction_modifiers(char_distinction)

        added = pool.apply_daily_regen()

        # 5 base + 1 (Tireless) - 2 (Indolent) = 4
        assert added == 4
        pool.refresh_from_db()
        assert pool.current == 104
