"""Tests for ORGANIZATION-anchored Thread model constraints."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.societies.factories import OrganizationFactory
from world.traits.factories import TraitFactory


class OrganizationThreadModelTests(TestCase):
    def test_clean_rejects_organization_without_target(self):
        """target_kind=ORGANIZATION requires target_organization set."""
        sheet = CharacterSheetFactory()
        thread = Thread(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.ORGANIZATION,
            target_organization=None,
        )
        with self.assertRaises(ValidationError):
            thread.full_clean()

    def test_clean_rejects_organization_with_other_targets(self):
        """target_kind=ORGANIZATION forbids other target_* FKs."""
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        thread = Thread(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
            target_trait=TraitFactory(),
        )
        with self.assertRaises(ValidationError):
            thread.full_clean()

    def test_clean_accepts_valid_organization_thread(self):
        """A valid ORGANIZATION thread passes full_clean."""
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        thread = Thread(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
        )
        thread.full_clean()  # should not raise

    def test_target_property_returns_organization(self):
        """Thread.target returns the organization for ORGANIZATION threads."""
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        thread = Thread.objects.create(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
        )
        self.assertEqual(thread.target, org)
