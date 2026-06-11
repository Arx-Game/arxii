"""Model-shape tests for Audere Majora threshold, offer, and crossing (#543)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.audere_majora import (
    AudereMajoraCrossing,
    AudereMajoraThreshold,
    PendingAudereMajoraOffer,
)
from world.magic.factories import ensure_audere_majora_threshold


class AudereMajoraThresholdModelTests(TestCase):
    """AudereMajoraThreshold: factory creates row; duplicate boundary_level is rejected."""

    def setUp(self) -> None:
        self.threshold = ensure_audere_majora_threshold(
            boundary_level=5,
            target_stage=PathStage.PUISSANT,
        )

    def test_factory_creates_threshold_with_puissant_target(self) -> None:
        assert self.threshold.boundary_level == 5
        assert self.threshold.target_stage == PathStage.PUISSANT
        assert self.threshold.minimum_intensity_tier_id is not None
        assert self.threshold.minimum_warp_stage_id is not None
        assert (
            self.threshold.vision_text == "[PLACEHOLDER VISION — real text is authored in the DB]"
        )
        assert (
            self.threshold.manifestation_text
            == "[PLACEHOLDER MANIFESTATION — real text is authored in the DB]"
        )

    def test_str_display(self) -> None:
        assert "Crossing at level 5" in str(self.threshold)
        assert "Puissant" in str(self.threshold)

    def test_duplicate_boundary_level_raises_integrity_error(self) -> None:
        # setUp already created boundary_level=5; force a second INSERT.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AudereMajoraThreshold.objects.create(
                    boundary_level=5,
                    target_stage=PathStage.TRUE,
                    minimum_intensity_tier=self.threshold.minimum_intensity_tier,
                    minimum_warp_stage=self.threshold.minimum_warp_stage,
                    vision_text="[PLACEHOLDER VISION — real text is authored in the DB]",
                    manifestation_text=(
                        "[PLACEHOLDER MANIFESTATION — real text is authored in the DB]"
                    ),
                )


class PendingAudereMajoraOfferModelTests(TestCase):
    """PendingAudereMajoraOffer: one offer per character sheet (unique constraint)."""

    def setUp(self) -> None:
        self.threshold = ensure_audere_majora_threshold(boundary_level=10)
        self.sheet = CharacterSheetFactory()

    def test_create_offer(self) -> None:
        offer = PendingAudereMajoraOffer.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            fired_intensity=20,
            soulfray_stage_order=3,
        )
        assert offer.pk is not None
        assert offer.character_sheet == self.sheet
        assert offer.threshold == self.threshold

    def test_duplicate_offer_for_same_sheet_raises_integrity_error(self) -> None:
        PendingAudereMajoraOffer.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            fired_intensity=20,
            soulfray_stage_order=3,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PendingAudereMajoraOffer.objects.create(
                    character_sheet=self.sheet,
                    threshold=self.threshold,
                    fired_intensity=25,
                    soulfray_stage_order=4,
                )

    def test_different_sheets_can_each_have_an_offer(self) -> None:
        sheet2 = CharacterSheetFactory()
        PendingAudereMajoraOffer.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            fired_intensity=20,
            soulfray_stage_order=3,
        )
        offer2 = PendingAudereMajoraOffer.objects.create(
            character_sheet=sheet2,
            threshold=self.threshold,
            fired_intensity=22,
            soulfray_stage_order=3,
        )
        assert offer2.pk is not None


class AudereMajoraCrossingModelTests(TestCase):
    """AudereMajoraCrossing: uniqueness + chosen_path FK acceptance."""

    def setUp(self) -> None:
        self.threshold = ensure_audere_majora_threshold(boundary_level=5)
        self.sheet = CharacterSheetFactory()
        self.path = PathFactory()

    def test_create_crossing(self) -> None:
        crossing = AudereMajoraCrossing.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            chosen_path=self.path,
            level_before=4,
            level_after=5,
        )
        assert crossing.pk is not None
        assert crossing.chosen_path == self.path
        assert crossing.level_before == 4
        assert crossing.level_after == 5

    def test_duplicate_character_threshold_pair_raises_integrity_error(self) -> None:
        AudereMajoraCrossing.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            chosen_path=self.path,
            level_before=4,
            level_after=5,
        )
        path2 = PathFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AudereMajoraCrossing.objects.create(
                    character_sheet=self.sheet,
                    threshold=self.threshold,
                    chosen_path=path2,
                    level_before=4,
                    level_after=5,
                )

    def test_scene_and_interaction_are_nullable(self) -> None:
        crossing = AudereMajoraCrossing.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            chosen_path=self.path,
            level_before=4,
            level_after=5,
            scene=None,
            declaration_interaction=None,
        )
        assert crossing.scene is None
        assert crossing.declaration_interaction is None
