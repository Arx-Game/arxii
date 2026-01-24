"""Tests for action points models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.action_points.factories import ActionPointConfigFactory, ActionPointPoolFactory
from world.action_points.models import ActionPointConfig, ActionPointPool


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


class ActionPointPoolModelTests(TestCase):
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


class ActionPointPoolSpendTests(TestCase):
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


class ActionPointPoolBankTests(TestCase):
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


class ActionPointPoolUnbankTests(TestCase):
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


class ActionPointPoolConsumeBankedTests(TestCase):
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


class ActionPointPoolRegenerateTests(TestCase):
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


class ActionPointPoolHelperTests(TestCase):
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


class ActionPointPoolGetOrCreateTests(TestCase):
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
