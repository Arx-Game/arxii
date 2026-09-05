"""Tests for evennia_extensions model defaults (#3164)."""

from django.test import TestCase, override_settings

from evennia_extensions.factories import MediaFactory
from world.roster.factories import PlayerDataFactory


class PlayerDataMediaQuotaTests(TestCase):
    @override_settings(DEFAULT_PLAYER_MEDIA_QUOTA_BYTES=12345)
    def test_new_player_data_gets_settings_default(self) -> None:
        player_data = PlayerDataFactory()
        self.assertEqual(player_data.media_quota_bytes, 12345)


class MediaFileSizeBytesTests(TestCase):
    def test_defaults_to_null(self) -> None:
        media = MediaFactory()
        self.assertIsNone(media.file_size_bytes)
