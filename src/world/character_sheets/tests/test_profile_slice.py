"""The bio Profile slice (#1270): bio lives on Profile, read/written transparently.

Slice 1 moves the narrative bio (concept/quote/personality/background/…) off CharacterSheet
onto a Profile. The sheet keeps forwarding properties so existing reads/writes are unchanged;
the PRIMARY persona points at the sheet's true_profile.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet, Heritage, Profile
from world.character_sheets.services import create_character_with_sheet
from world.roster.factories import FamilyFactory


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


class LineageProfileSliceTests(TestCase):
    """The lineage slice (#1270 slice 3): family/heritage/tarot/origin live on Profile,
    surfaced through the same forwarding properties so mechanical reads are unchanged."""

    def test_lineage_reads_through_the_true_profile(self) -> None:
        sheet = CharacterSheetFactory()
        family = FamilyFactory(name="Stormwind")
        sheet.true_profile.family = family
        sheet.true_profile.tarot_reversed = True
        sheet.true_profile.save()
        # The forwarding properties reflect the profile values.
        assert sheet.family == family
        assert sheet.tarot_reversed is True

    def test_lineage_write_through_setter_persists_to_the_profile(self) -> None:
        sheet = CharacterSheetFactory()
        family = FamilyFactory(name="Ashford")
        heritage = Heritage.objects.create(name="Sleeper", description="Awoke without a past.")
        sheet.family = family
        sheet.heritage = heritage
        sheet.save()

        # Re-read the profile straight from the DB — the setter + save cascade persisted it.
        profile = Profile.objects.get(pk=sheet.true_profile_id)
        assert profile.family_id == family.pk
        assert profile.heritage_id == heritage.pk

    def test_sheet_without_a_profile_reads_empty_lineage(self) -> None:
        sheet = CharacterSheetFactory(primary_persona=False)
        sheet.true_profile = None
        # A bare sheet reads lineage as the field's empty default rather than raising.
        assert sheet.family is None
        assert sheet.heritage is None
        assert sheet.tarot_card is None
        assert sheet.tarot_reversed is False

    def test_create_character_with_sheet_routes_lineage_to_the_profile(self) -> None:
        family = FamilyFactory(name="Valdris")
        _character, sheet, _primary = create_character_with_sheet(
            character_key="Test Heir",
            primary_persona_name="Test Heir",
            family=family,
        )
        # Lineage landed on the profile; the sheet reads it through forwarding.
        assert sheet.true_profile is not None
        assert sheet.true_profile.family_id == family.pk
        assert sheet.family == family

    def test_factory_routes_lineage_kwargs_to_the_profile(self) -> None:
        family = FamilyFactory(name="Corwin")
        sheet = CharacterSheetFactory(family=family)
        assert sheet.true_profile.family_id == family.pk
        assert sheet.family == family
