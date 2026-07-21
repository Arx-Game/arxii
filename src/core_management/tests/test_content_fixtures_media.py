"""Content-pipeline natural-key resolution for Media across every referencing model (#2408).

The approved spec requires proof that ``Media`` resolves by natural key from
every model that FKs into it via the content pipeline: ``PageBackground``
(this task), ``CodexEntry.art`` (#2408 Task 3), and the retrofitted
``StartingArea.crest_art``/``Beginnings.art`` (#2408 Task 4). Per the task-2
brief's Step 8a, this file lands now with only the ``PageBackground`` case —
Tasks 3 and 4 append their own test methods to this class in the same commit
that adds the field each method exercises, since ``CodexEntry.art``,
``StartingArea.crest_art``, and ``Beginnings.art`` don't exist yet.
"""

from pathlib import Path

from django.test import TestCase, tag

from core_management.content_fixtures import BuildResult, load_entries
from evennia_extensions.models import Media, PageBackground, PageBackgroundSlot
from world.character_creation.models import Beginnings, StartingArea
from world.codex.models import CodexCategory, CodexEntry, CodexSubject


class MediaContentPipelineTest(TestCase):
    def _load_raw_fixture(self, key: str, objects: list[dict]) -> None:
        """Build a BuildResult around raw fixture-JSON objects and load it.

        Mirrors the pattern used by ``LoadEntriesM2MTest``/``test_load_sequencing.py``
        for exercising ``load_entries`` against hand-built fixture rows without
        going through the file-parsing ``build_all`` pipeline. ``load_entries``'s
        real signature is ``load_entries(result: BuildResult, *,
        defer_unresolved: bool = False)`` — it does not take
        ``(app_label, model_name, rows)`` positionally.
        """
        result = BuildResult()
        result.fixtures[key] = objects
        result.source_paths[key] = [Path(key)] * len(objects)
        created, _updated, _ = load_entries(result)
        assert result.skipped == [], f"Unexpected skips loading {key}: {result.skipped}"
        return created

    def setUp(self):
        self.media_rows = [
            {
                "model": "evennia_extensions.media",
                "fields": {
                    "slug": "homepage-hero",
                    "cloudinary_public_id": "game_art/homepage_hero",
                    "cloudinary_url": "https://res.cloudinary.com/test/homepage_hero.jpg",
                    "media_type": "background",
                },
            },
            {
                "model": "evennia_extensions.media",
                "fields": {
                    "slug": "entry-art",
                    "cloudinary_public_id": "game_art/entry_art",
                    "cloudinary_url": "https://res.cloudinary.com/test/entry_art.jpg",
                    "media_type": "illustration",
                },
            },
            {
                "model": "evennia_extensions.media",
                "fields": {
                    "slug": "crest-arx",
                    "cloudinary_public_id": "game_art/crest_arx",
                    "cloudinary_url": "https://res.cloudinary.com/test/crest_arx.jpg",
                    "media_type": "illustration",
                },
            },
            {
                "model": "evennia_extensions.media",
                "fields": {
                    "slug": "sleeper-art",
                    "cloudinary_public_id": "game_art/sleeper_art",
                    "cloudinary_url": "https://res.cloudinary.com/test/sleeper_art.jpg",
                    "media_type": "illustration",
                },
            },
        ]
        self._load_raw_fixture("fixtures/evennia_extensions/media.json", self.media_rows)

    def test_pagebackground_resolves_media_by_natural_key(self):
        rows = [
            {
                "model": "evennia_extensions.pagebackground",
                "fields": {"slot": PageBackgroundSlot.HOMEPAGE, "art": ["homepage-hero"]},
            },
        ]
        self._load_raw_fixture("fixtures/evennia_extensions/pagebackground.json", rows)
        media = Media.objects.get(slug="homepage-hero")
        bg = PageBackground.objects.get(slot=PageBackgroundSlot.HOMEPAGE)
        self.assertEqual(bg.art_id, media.pk)

    @tag("postgres")
    def test_codexentry_resolves_media_by_natural_key(self):
        """PG-only: ``CodexSubject.save()`` refreshes the ``codex_subjectbreadcrumb``
        materialized view, which doesn't exist on the SQLite inner-loop tier.
        """
        category = CodexCategory.objects.create(name="Test Category")
        subject = CodexSubject.objects.create(category=category, name="Test Subject")
        rows = [
            {
                "model": "codex.codexentry",
                "fields": {
                    "subject": [category.name, None, subject.name],
                    "name": "Test Entry",
                    "art": ["entry-art"],
                },
            },
        ]
        self._load_raw_fixture("fixtures/codex/codexentry.json", rows)
        media = Media.objects.get(slug="entry-art")
        entry = CodexEntry.objects.get(subject=subject, name="Test Entry")
        self.assertEqual(entry.art_id, media.pk)

    def test_startingarea_resolves_media_by_natural_key(self):
        rows = [
            {
                "model": "character_creation.startingarea",
                "fields": {
                    "name": "Test Crest Area",
                    "description": "A place with a crest.",
                    "crest_art": ["crest-arx"],
                },
            },
        ]
        self._load_raw_fixture("fixtures/character_creation/startingarea.json", rows)
        media = Media.objects.get(slug="crest-arx")
        area = StartingArea.objects.get(name="Test Crest Area")
        self.assertEqual(area.crest_art_id, media.pk)

    def test_beginnings_resolves_media_by_natural_key(self):
        area = StartingArea.objects.create(name="Test Beginnings Area", description="...")
        rows = [
            {
                "model": "character_creation.beginnings",
                "fields": {
                    "starting_area": [area.name],
                    "name": "Test Sleeper",
                    "description": "Woke up with no memories.",
                    "art": ["sleeper-art"],
                },
            },
        ]
        self._load_raw_fixture("fixtures/character_creation/beginnings.json", rows)
        media = Media.objects.get(slug="sleeper-art")
        beginnings = Beginnings.objects.get(starting_area=area, name="Test Sleeper")
        self.assertEqual(beginnings.art_id, media.pk)
