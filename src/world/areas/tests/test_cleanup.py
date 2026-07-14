"""Tests for the CLEANUP area quality system (#1889)."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.areas.cleanup_services import (
    area_quality_description_suffix,
    cleanup_quality_decay_tick,
    erode_area_quality,
    resolve_cleanup,
    start_cleanup_project,
)
from world.areas.combat_erosion import erode_on_encounter_completed
from world.areas.constants import (
    AREA_QUALITY_NORMAL,
    CLEANUP_DWELL_DAYS,
    CLEANUP_REGAIN_WEEKS,
    AreaLevel,
)
from world.areas.factories import AreaFactory
from world.areas.models import AreaQuality, CleanupProjectDetails, CleanupTierThreshold
from world.character_sheets.factories import CharacterSheetFactory
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.models import Project
from world.projects.services import donate_to_project, scan_active_projects
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


def _ensure_check_outcomes():
    """Create the canonical CheckOutcome rows that start_cleanup_project looks up by name."""
    names_and_levels = [
        ("Failure", -1),
        ("Partial Success", 0),
        ("Success", 1),
        ("Critical Success", 2),
    ]
    for name, level in names_and_levels:
        CheckOutcomeFactory(name=name, success_level=level)


class AreaQualityModelTests(TestCase):
    """Tests for AreaQuality, CleanupProjectDetails, CleanupTierThreshold models."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(name="Test Neighborhood", level=AreaLevel.NEIGHBORHOOD)
        cls.sheet = CharacterSheetFactory()
        cls.persona = PersonaFactory(character_sheet=cls.sheet)

    def test_area_quality_defaults_to_normal(self):
        quality = AreaQuality.objects.create(area=self.area)
        self.assertEqual(quality.quality, AREA_QUALITY_NORMAL)
        self.assertIsNotNone(quality.condition_since)

    def test_area_quality_one_per_area(self):
        AreaQuality.objects.create(area=self.area)
        with self.assertRaises(IntegrityError):
            AreaQuality.objects.create(area=self.area)

    def test_cleanup_tier_threshold_fields(self):
        project = Project.objects.create(
            kind=ProjectKind.CLEANUP,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            owner_persona=self.persona,
            started_at=timezone.now(),
            time_limit=timezone.now() + timedelta(days=30),
        )
        details = CleanupProjectDetails.objects.create(project=project, target_area=self.area)
        outcome = CheckOutcomeFactory(success_level=1)
        threshold = CleanupTierThreshold.objects.create(
            details=details, outcome_tier=outcome, min_progress=50, quality_delta=1
        )
        self.assertEqual(threshold.quality_delta, 1)
        self.assertEqual(threshold.min_progress, 50)


class CleanupServiceTests(TestCase):
    """Tests for cleanup project lifecycle, erosion, and decay."""

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_check_outcomes()
        cls.area = AreaFactory(name="Cleanup Neighborhood", level=AreaLevel.NEIGHBORHOOD)
        cls.sheet = CharacterSheetFactory()
        cls.persona = PersonaFactory(character_sheet=cls.sheet)

    def test_start_cleanup_project_creates_project_and_details(self):
        project = start_cleanup_project(area=self.area, owner_persona=self.persona)
        self.assertEqual(project.kind, ProjectKind.CLEANUP)
        self.assertEqual(project.completion_mode, CompletionMode.TIERED_PERIOD)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        details = project.cleanup_details
        self.assertEqual(details.target_area, self.area)
        self.assertIsNone(details.applied_at)
        thresholds = list(details.tier_thresholds.all())
        self.assertGreater(len(thresholds), 0)

    def test_start_cleanup_rejects_non_neighborhood(self):
        ward = AreaFactory(name="Ward", level=AreaLevel.WARD)
        with self.assertRaises(ValueError):
            start_cleanup_project(area=ward, owner_persona=self.persona)

    def test_complete_cleanup_bumps_quality(self):
        AreaQuality.objects.create(area=self.area, quality=AREA_QUALITY_NORMAL)
        project = start_cleanup_project(area=self.area, owner_persona=self.persona)
        project.current_progress = 100
        project.save(update_fields=["current_progress"])
        # Transition to RESOLVING (as scan_active_projects would).
        project.status = ProjectStatus.RESOLVING
        project.save(update_fields=["status"])
        resolve_cleanup(project)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        quality = AreaQuality.objects.get(area=self.area)
        self.assertGreater(quality.quality, AREA_QUALITY_NORMAL)

    def test_complete_cleanup_failure_does_not_bump(self):
        AreaQuality.objects.create(area=self.area, quality=AREA_QUALITY_NORMAL)
        project = start_cleanup_project(area=self.area, owner_persona=self.persona)
        # Transition to RESOLVING (as scan_active_projects would).
        project.status = ProjectStatus.RESOLVING
        project.save(update_fields=["status"])
        resolve_cleanup(project)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.FAILED)
        quality = AreaQuality.objects.get(area=self.area)
        self.assertEqual(quality.quality, AREA_QUALITY_NORMAL)

    def test_erode_area_quality_decrements(self):
        AreaQuality.objects.create(area=self.area, quality=4)
        erode_area_quality(self.area)
        quality = AreaQuality.objects.get(area=self.area)
        self.assertEqual(quality.quality, 3)

    def test_erode_area_quality_clamps_at_zero(self):
        AreaQuality.objects.create(area=self.area, quality=0)
        erode_area_quality(self.area)
        quality = AreaQuality.objects.get(area=self.area)
        self.assertEqual(quality.quality, 0)

    def test_erode_area_quality_no_quality_row_is_noop(self):
        erode_area_quality(self.area)
        self.assertFalse(AreaQuality.objects.filter(area=self.area).exists())

    def test_decay_tick_lowers_above_normal(self):
        aq = AreaQuality.objects.create(area=self.area, quality=5)
        aq.condition_since = timezone.now() - timedelta(days=CLEANUP_DWELL_DAYS + 1)
        aq.save(update_fields=["condition_since"])
        cleanup_quality_decay_tick()
        aq.refresh_from_db()
        self.assertEqual(aq.quality, 4)

    def test_decay_tick_raises_below_normal(self):
        aq = AreaQuality.objects.create(area=self.area, quality=1)
        aq.condition_since = timezone.now() - timedelta(days=CLEANUP_REGAIN_WEEKS * 7 + 1)
        aq.save(update_fields=["condition_since"])
        cleanup_quality_decay_tick()
        aq.refresh_from_db()
        self.assertEqual(aq.quality, 2)

    def test_decay_tick_normal_is_unchanged(self):
        aq = AreaQuality.objects.create(area=self.area, quality=AREA_QUALITY_NORMAL)
        aq.condition_since = timezone.now() - timedelta(days=365)
        aq.save(update_fields=["condition_since"])
        cleanup_quality_decay_tick()
        aq.refresh_from_db()
        self.assertEqual(aq.quality, AREA_QUALITY_NORMAL)


class CombatErosionTests(TestCase):
    """Tests for area quality erosion from combat encounters (#1889)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(name="Combat Neighborhood", level=AreaLevel.NEIGHBORHOOD)
        cls.aq = AreaQuality.objects.create(area=cls.area, quality=4)

    def test_open_encounter_erodes_quality(self):
        from world.combat.constants import EncounterType

        erode_on_encounter_completed(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            area=self.area,
        )
        self.aq.refresh_from_db()
        self.assertEqual(self.aq.quality, 3)

    def test_duel_does_not_erode_quality(self):
        from world.combat.constants import EncounterType

        erode_on_encounter_completed(
            encounter_type=EncounterType.DUEL,
            area=self.area,
        )
        self.aq.refresh_from_db()
        self.assertEqual(self.aq.quality, 4)

    def test_party_combat_does_not_erode_quality(self):
        from world.combat.constants import EncounterType

        erode_on_encounter_completed(
            encounter_type=EncounterType.PARTY_COMBAT,
            area=self.area,
        )
        self.aq.refresh_from_db()
        self.assertEqual(self.aq.quality, 4)

    def test_none_area_is_noop(self):
        from world.combat.constants import EncounterType

        erode_on_encounter_completed(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            area=None,
        )
        self.aq.refresh_from_db()
        self.assertEqual(self.aq.quality, 4)


class RoomDescriptionModifierTests(TestCase):
    """Tests for area quality room description modifiers (#1889)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(name="Desc Neighborhood", level=AreaLevel.NEIGHBORHOOD)

    def test_quality_label_for_high_quality(self):
        from world.areas.constants import AREA_QUALITY_LABELS

        self.assertEqual(AREA_QUALITY_LABELS[5], "Pristine")
        self.assertEqual(AREA_QUALITY_LABELS[3], "Ordinary")
        self.assertEqual(AREA_QUALITY_LABELS[0], "Blighted")

    def test_description_suffix_pristine(self):
        AreaQuality.objects.create(area=self.area, quality=5)
        suffix = area_quality_description_suffix(self.area)
        self.assertIsNotNone(suffix)
        self.assertIn("pristine", suffix.lower())

    def test_description_suffix_tidy(self):
        AreaQuality.objects.create(area=self.area, quality=4)
        suffix = area_quality_description_suffix(self.area)
        self.assertIsNotNone(suffix)
        self.assertIn("tidy", suffix.lower())

    def test_description_suffix_normal_returns_none(self):
        AreaQuality.objects.create(area=self.area, quality=AREA_QUALITY_NORMAL)
        suffix = area_quality_description_suffix(self.area)
        self.assertIsNone(suffix)

    def test_description_suffix_low(self):
        AreaQuality.objects.create(area=self.area, quality=1)
        suffix = area_quality_description_suffix(self.area)
        self.assertIsNotNone(suffix)
        self.assertIn("neglect", suffix.lower())

    def test_description_suffix_no_quality_row_returns_none(self):
        suffix = area_quality_description_suffix(self.area)
        self.assertIsNone(suffix)


class CleanupE2ETests(TestCase):
    """End-to-end lifecycle: start -> contribute -> resolve -> quality bump + rewards."""

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_check_outcomes()
        cls.area = AreaFactory(name="E2E Neighborhood", level=AreaLevel.NEIGHBORHOOD)
        cls.sheet = CharacterSheetFactory()
        cls.persona = PersonaFactory(character_sheet=cls.sheet)

    def test_full_lifecycle_donate_and_resolve(self):
        AreaQuality.objects.create(area=self.area, quality=AREA_QUALITY_NORMAL)
        project = start_cleanup_project(area=self.area, owner_persona=self.persona)

        from world.currency.services import get_or_create_purse

        purse = get_or_create_purse(self.sheet)
        purse.balance = 10000
        purse.save(update_fields=["balance"])
        donate_to_project(project, donor_persona=self.persona, amount=5000)

        project.refresh_from_db()
        self.assertGreaterEqual(project.current_progress, 50)

        project.time_limit = timezone.now() - timedelta(days=1)
        project.save(update_fields=["time_limit"])

        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)

        aq = AreaQuality.objects.get(area=self.area)
        self.assertGreater(aq.quality, AREA_QUALITY_NORMAL)

    def test_contributor_gets_resonance(self):
        from world.areas.seeds import ensure_cleanup_content
        from world.magic.models.aura import CharacterResonance

        hope = ensure_cleanup_content()
        project = start_cleanup_project(area=self.area, owner_persona=self.persona)
        # Set the resonance FK so the contribution resonance award fires.
        project.resonance = hope
        project.save(update_fields=["resonance"])

        from world.currency.services import get_or_create_purse

        purse = get_or_create_purse(self.sheet)
        purse.balance = 10000
        purse.save(update_fields=["balance"])
        donate_to_project(project, donor_persona=self.persona, amount=500)

        cr = CharacterResonance.objects.filter(character_sheet=self.sheet, resonance=hope).first()
        self.assertIsNotNone(cr)
        self.assertGreater(cr.balance, 0)


class CleanupSeedTests(TestCase):
    """Tests for cleanup seed content (#1889)."""

    def test_ensure_cleanup_content_is_idempotent(self):
        from world.areas.seeds import ensure_cleanup_content
        from world.projects.constants import ProjectKind
        from world.projects.models import ProjectKindResonanceAward

        ensure_cleanup_content()
        ensure_cleanup_content()
        award = ProjectKindResonanceAward.objects.filter(kind=ProjectKind.CLEANUP).first()
        self.assertIsNotNone(award)
        self.assertGreater(award.resonance_award_amount, 0)
