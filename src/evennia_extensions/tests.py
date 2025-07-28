"""
Tests for evennia_extensions models.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerAllowList, PlayerBlockList, PlayerData


class PlayerDataTestCase(TestCase):
    """Test PlayerData model and its methods"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account1 = AccountDB.objects.create_user(
            username="ee_player1", email="ee_player1@test.com", password="testpass"
        )
        cls.account2 = AccountDB.objects.create_user(
            username="ee_player2", email="ee_player2@test.com", password="testpass"
        )
        cls.staff_account = AccountDB.objects.create_user(
            username="ee_staff",
            email="ee_staff@test.com",
            password="testpass",
            is_staff=True,
        )

        cls.player_data1 = PlayerData.objects.create(account=cls.account1)
        cls.player_data2 = PlayerData.objects.create(account=cls.account2)
        cls.staff_data = PlayerData.objects.create(account=cls.staff_account)

    def test_player_data_str_representation(self):
        """Test PlayerData string representation"""
        expected = "PlayerData for ee_player1"
        self.assertEqual(str(self.player_data1), expected)

    def test_staff_permissions(self):
        """Test staff permission methods"""
        # Staff can approve applications
        self.assertTrue(self.staff_data.can_approve_applications())
        self.assertEqual(self.staff_data.get_approval_scope(), "all")

        # Regular players cannot
        self.assertFalse(self.player_data1.can_approve_applications())
        self.assertEqual(self.player_data1.get_approval_scope(), "none")


class PlayerAllowListTestCase(TestCase):
    """Test PlayerAllowList model"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account1 = AccountDB.objects.create_user(
            username="al_player1", email="al_player1@test.com", password="testpass"
        )
        cls.account2 = AccountDB.objects.create_user(
            username="al_player2", email="al_player2@test.com", password="testpass"
        )

        cls.player_data1 = PlayerData.objects.create(account=cls.account1)
        cls.player_data2 = PlayerData.objects.create(account=cls.account2)

    def test_allow_list_str_representation(self):
        """Test allow list string representation"""
        allow_entry = PlayerAllowList.objects.create(
            owner=self.player_data1, allowed_player=self.player_data2
        )

        expected = "al_player1 allows al_player2"
        self.assertEqual(str(allow_entry), expected)


class PlayerBlockListTestCase(TestCase):
    """Test PlayerBlockList model"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account1 = AccountDB.objects.create_user(
            username="bl_player1", email="bl_player1@test.com", password="testpass"
        )
        cls.account2 = AccountDB.objects.create_user(
            username="bl_player2", email="bl_player2@test.com", password="testpass"
        )

        cls.player_data1 = PlayerData.objects.create(account=cls.account1)
        cls.player_data2 = PlayerData.objects.create(account=cls.account2)

    def test_block_list_str_representation(self):
        """Test block list string representation"""
        block_entry = PlayerBlockList.objects.create(
            owner=self.player_data1, blocked_player=self.player_data2
        )

        expected = "bl_player1 blocks bl_player2"
        self.assertEqual(str(block_entry), expected)


class PlayerDataIntegrationTestCase(TestCase):
    """Test integration between PlayerData and other models"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class"""
        cls.account = AccountDB.objects.create_user(
            username="int_testplayer", email="int_test@test.com", password="testpass"
        )
        cls.player_data = PlayerData.objects.create(
            account=cls.account,
            display_name="Test Player",
            karma=100,
            hide_from_watch=True,
        )
