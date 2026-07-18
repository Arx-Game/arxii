"""Tests for CodexEntry.art (#2408)."""

from django.test import TestCase

from evennia_extensions.factories import MediaFactory
from world.codex.factories import CodexEntryFactory
from world.codex.serializers import CodexEntryDetailSerializer, CodexEntryListSerializer


class CodexEntryArtTest(TestCase):
    def _annotate_for_direct_serialization(self, entry):
        """Stand in for the ViewSet's Subquery annotations.

        ``CodexEntryDetailSerializer.get_lore_content``/``get_mechanics_content``
        read ``obj.knowledge_status`` directly (not through DRF's field
        machinery), so a bare ``CodexEntry`` instance that never went through
        the ViewSet's annotated queryset raises ``AttributeError``. These
        tests only care about ``art_url``, so a public entry with no
        knowledge record is a safe stand-in for what the ViewSet would
        annotate for an anonymous/uncovering viewer.
        """
        entry.knowledge_status = None
        entry.research_progress = None
        return entry

    def test_art_url_present_when_set(self):
        media = MediaFactory(player_data=None, slug="entry-art")
        entry = self._annotate_for_direct_serialization(CodexEntryFactory(art=media))
        data = CodexEntryDetailSerializer(entry).data
        self.assertEqual(data["art_url"], media.cloudinary_url)

    def test_art_url_null_when_unset(self):
        entry = self._annotate_for_direct_serialization(CodexEntryFactory(art=None))
        data = CodexEntryDetailSerializer(entry).data
        self.assertIsNone(data["art_url"])

    def test_list_serializer_also_exposes_art_url(self):
        media = MediaFactory(player_data=None, slug="entry-art-2")
        entry = CodexEntryFactory(art=media)
        data = CodexEntryListSerializer(entry).data
        self.assertEqual(data["art_url"], media.cloudinary_url)
