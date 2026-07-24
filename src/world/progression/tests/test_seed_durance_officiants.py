"""Tests for the Durance ritual + officiant/training-site bootstrap (#2121).

Proves the two acceptance criteria: a fresh (seeded) DB's
``ritual draft "Ritual of the Durance"`` resolves by name, and the first-ever
Durance is conductible for a level-1 character with NO live higher-level PC
present — only the seeded NPC officiant + training site. Also proves
idempotency (re-seeding preserves a staff edit to the officiant's level).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.classes.factories import CharacterClassFactory
from world.classes.models import Path, PathStage
from world.magic.models import Ritual
from world.magic.models.sessions import RitualSession
from world.progression.models import (
    CharacterPathHistory,
    CharacterUnlock,
    ClassLevelUnlock,
    DuranceTrainingSite,
)
from world.progression.seeds import (
    _DURANCE_OFFICIANT_LEVEL,
    _DURANCE_OFFICIANT_PATH_NAMES,
    seed_durance_officiants,
)
from world.progression.services.advancement import convene_durance_at_site
from world.seeds.database import seed_dev_database
from world.seeds.tests.content_stub import stub_content_root

_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


class SeedDurancePrerequisitesTests(TestCase):
    """seed_dev_database() (magic + progression clusters) content shape."""

    @stub_content_root()
    def test_ritual_of_the_durance_is_seeded_by_name(self) -> None:
        seed_dev_database()
        self.assertTrue(Ritual.objects.filter(name="Ritual of the Durance").exists())

    @stub_content_root()
    def test_one_training_site_per_prospect_path(self) -> None:
        seed_dev_database()
        sites = DuranceTrainingSite.objects.select_related("training_path")
        self.assertEqual(sites.count(), len(_DURANCE_OFFICIANT_PATH_NAMES))
        site_path_names = {s.training_path.name for s in sites}
        self.assertEqual(site_path_names, set(_DURANCE_OFFICIANT_PATH_NAMES))
        for site in sites:
            self.assertTrue(site.is_active)
            self.assertEqual(site.officiant.current_level, _DURANCE_OFFICIANT_LEVEL)


class SeedDurationOfficiantsIdempotencyTests(TestCase):
    """Re-running seed_durance_officiants() is a no-op that preserves staff edits."""

    @stub_content_root()
    def test_rerun_is_idempotent_no_op(self) -> None:
        seed_dev_database()
        site_count = DuranceTrainingSite.objects.count()

        seed_durance_officiants()

        self.assertEqual(DuranceTrainingSite.objects.count(), site_count)

    @stub_content_root()
    def test_rerun_preserves_staff_edit_to_officiant_level(self) -> None:
        from world.classes.services import set_primary_class_level

        seed_dev_database()
        site = DuranceTrainingSite.objects.select_related("officiant").first()
        staff_class = CharacterClassFactory()
        set_primary_class_level(site.officiant.character, staff_class, 20)

        seed_durance_officiants()

        site.officiant.invalidate_class_level_cache()
        self.assertEqual(site.officiant.current_level, 20)


class FirstDuranceWithNoLiveOfficiantTests(TestCase):
    """The symptom fix: the first-ever Durance needs no live higher-level PC (#2121)."""

    @stub_content_root()
    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.seeds.character_creation import ensure_canonical_fallback_room

        seed_dev_database()
        self.room = ensure_canonical_fallback_room()
        self.path = Path.objects.get(name=_DURANCE_OFFICIANT_PATH_NAMES[0])
        self.assertEqual(self.path.stage, PathStage.PROSPECT)

        # A brand-new level-1 inductee on the same path as a seeded officiant —
        # no other character present at the room besides the (offstage) NPC.
        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(
            character=self.inductee_sheet,
            character_class=self.inductee_class,
            level=1,
            is_primary=True,
        )
        CharacterPathHistory.objects.create(character=self.inductee_sheet, path=self.path)
        self.inductee_sheet.character.location = self.room
        self.inductee_sheet.character.save()

        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.inductee_class, target_level=2
        )
        CharacterUnlock.objects.create(
            character=self.inductee_sheet,
            character_class=self.unlock.character_class,
            target_level=self.unlock.target_level,
        )

    def test_convene_succeeds_with_only_the_seeded_officiant(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )

        self.assertIsInstance(session, RitualSession)
        self.assertEqual(session.ritual.name, "Ritual of the Durance")
        # The initiator is the seeded NPC officiant for this path, not a live PC.
        site = DuranceTrainingSite.objects.get(training_path=self.path)
        self.assertEqual(session.initiator, site.officiant)
