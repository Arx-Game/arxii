"""The bio Profile slice (#1270): bio lives on Profile, read/written transparently.

Slice 1 moves the narrative bio (concept/quote/personality/background/…) off CharacterSheet
onto a Profile. The sheet keeps forwarding properties so existing reads/writes are unchanged;
the PRIMARY persona points at the sheet's true_profile.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet, Profile
from world.character_sheets.services import create_character_with_sheet


class ProfileSliceTests(TestCase):
    def test_factory_sheet_has_a_true_profile_presented_by_the_primary_persona(self) -> None:
        sheet = CharacterSheetFactory()
        assert sheet.true_profile is not None
        # The PRIMARY persona presents the sheet's real bio.
        assert sheet.primary_persona.profile_id == sheet.true_profile_id

    def test_bio_reads_through_the_true_profile(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.true_profile.concept = "A wandering blade"
        sheet.true_profile.save()
        # The forwarding property reflects the profile value.
        assert sheet.concept == "A wandering blade"

    def test_bio_write_through_setter_persists_to_the_profile(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.concept = "Reformed thief"
        sheet.quote = "Lighter fingers, lighter conscience."
        sheet.save()

        # Re-read the profile straight from the DB — the setter + save cascade persisted it.
        profile = Profile.objects.get(pk=sheet.true_profile_id)
        assert profile.concept == "Reformed thief"
        assert profile.quote == "Lighter fingers, lighter conscience."

    def test_sheet_without_a_profile_reads_empty(self) -> None:
        # A bare sheet (no profile) reads as empty rather than raising.
        sheet = CharacterSheetFactory(primary_persona=False)
        sheet.true_profile = None
        assert sheet.concept == ""
        assert sheet.background == ""

    def test_create_character_with_sheet_routes_bio_to_the_profile(self) -> None:
        _character, sheet, primary = create_character_with_sheet(
            character_key="Test Hero",
            primary_persona_name="Test Hero",
            concept="A stoic guardian",
            quote="I stand watch.",
        )
        assert isinstance(sheet, CharacterSheet)
        # Bio landed on the profile, the sheet points at it, and the primary presents it.
        assert sheet.true_profile is not None
        assert sheet.true_profile.concept == "A stoic guardian"
        assert sheet.concept == "A stoic guardian"
        assert primary.profile_id == sheet.true_profile_id
