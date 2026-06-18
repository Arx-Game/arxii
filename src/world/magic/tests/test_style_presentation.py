"""Tests for STYLE_PRESENTATION gain source (Task C1, #1152)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import ResonanceGrant, StylePresentationEndorsement
from world.magic.services.resonance import grant_resonance
from world.scenes.factories import SceneFactory


class StylePresentationEndorsementFactory:
    """Minimal inline factory — mirrors SceneEntryEndorsementFactory."""

    @staticmethod
    def create(
        *,
        endorser_sheet=None,
        endorsee_sheet=None,
        scene=None,
        resonance=None,
        granted_amount=5,
    ):
        endorser_sheet = endorser_sheet or CharacterSheetFactory()
        endorsee_sheet = endorsee_sheet or CharacterSheetFactory()
        scene = scene or SceneFactory()
        resonance = resonance or ResonanceFactory()
        return StylePresentationEndorsement.objects.create(
            endorser_sheet=endorser_sheet,
            endorsee_sheet=endorsee_sheet,
            scene=scene,
            resonance=resonance,
            granted_amount=granted_amount,
        )


class StylePresentationGrantTest(TestCase):
    """grant_resonance with source=STYLE_PRESENTATION writes balance + ledger row."""

    def test_grant_resonance_raises_balance_and_creates_ledger_row(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        endorsement = StylePresentationEndorsementFactory.create(
            endorsee_sheet=sheet,
            resonance=resonance,
            granted_amount=5,
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        cr = grant_resonance(
            sheet,
            resonance,
            5,
            source=GainSource.STYLE_PRESENTATION,
            style_presentation_endorsement=endorsement,
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 5)

        grant = ResonanceGrant.objects.get(source=GainSource.STYLE_PRESENTATION)
        self.assertEqual(grant.source_style_presentation_endorsement, endorsement)
        self.assertEqual(grant.amount, 5)
        self.assertEqual(grant.character_sheet, sheet)
        self.assertEqual(grant.resonance, resonance)

    def test_grant_without_endorsement_kwarg_raises_value_error(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        with self.assertRaises(ValueError):
            grant_resonance(
                sheet,
                resonance,
                5,
                source=GainSource.STYLE_PRESENTATION,
                # no style_presentation_endorsement kwarg → should raise ValueError
            )

    def test_grant_with_wrong_source_kwarg_raises_value_error(self):
        """Passing source=STYLE_PRESENTATION with None endorsement also raises."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        with self.assertRaises(ValueError):
            grant_resonance(
                sheet,
                resonance,
                5,
                source=GainSource.STYLE_PRESENTATION,
                style_presentation_endorsement=None,
            )


class StylePresentationUniqueConstraintTest(TestCase):
    """Duplicate (endorser, endorsee, scene) rows are rejected at the DB level."""

    def test_duplicate_pair_per_scene_raises_integrity_error(self):
        endorser = CharacterSheetFactory()
        endorsee = CharacterSheetFactory()
        scene = SceneFactory()
        resonance = ResonanceFactory()

        StylePresentationEndorsementFactory.create(
            endorser_sheet=endorser,
            endorsee_sheet=endorsee,
            scene=scene,
            resonance=resonance,
        )

        with self.assertRaises(IntegrityError):
            StylePresentationEndorsementFactory.create(
                endorser_sheet=endorser,
                endorsee_sheet=endorsee,
                scene=scene,
                resonance=resonance,
            )
