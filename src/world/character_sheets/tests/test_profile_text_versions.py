"""Tests for ProfileTextVersion + update_profile_text — history is never lost (#2631)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.services import update_profile_text
from world.character_sheets.types import ProfileTextField


class UpdateProfileTextTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.profile = self.sheet.true_profile

    def test_first_change_captures_cg_original(self):
        self.profile.background = "Born in the mountains."
        self.profile.save(update_fields=["background"])

        update_profile_text(self.profile, ProfileTextField.BACKGROUND, "Reforged by the siege.")

        versions = list(
            ProfileTextVersion.objects.filter(
                profile=self.profile, field=ProfileTextField.BACKGROUND
            ).order_by("created_at")
        )
        assert len(versions) == 2
        assert versions[0].text == "Born in the mountains."
        assert versions[1].text == "Reforged by the siege."
        self.profile.refresh_from_db()
        assert self.profile.background == "Reforged by the siege."

    def test_empty_original_creates_single_version(self):
        self.profile.personality = ""
        self.profile.save(update_fields=["personality"])

        update_profile_text(self.profile, ProfileTextField.PERSONALITY, "Newly warm.")

        count = ProfileTextVersion.objects.filter(
            profile=self.profile, field=ProfileTextField.PERSONALITY
        ).count()
        assert count == 1

    def test_second_change_adds_one_version(self):
        update_profile_text(self.profile, ProfileTextField.BACKGROUND, "First rewrite.")
        update_profile_text(self.profile, ProfileTextField.BACKGROUND, "Second rewrite.")

        texts = list(
            ProfileTextVersion.objects.filter(
                profile=self.profile, field=ProfileTextField.BACKGROUND
            )
            .order_by("created_at")
            .values_list("text", flat=True)
        )
        assert texts[-2:] == ["First rewrite.", "Second rewrite."]

    def test_stamps_null_safe_without_clock_or_era(self):
        version = update_profile_text(self.profile, ProfileTextField.BACKGROUND, "Text.")
        assert version.ic_date is None
        assert version.era is None

    def test_previous_text_override_captures_supplied_original(self):
        # The admin path: instance already mutated, pre-edit text passed in.
        self.profile.background = "New text already on the instance."
        self.profile.save(update_fields=["background"])

        update_profile_text(
            self.profile,
            ProfileTextField.BACKGROUND,
            "New text already on the instance.",
            previous_text="The lost original.",
        )

        first = (
            ProfileTextVersion.objects.filter(
                profile=self.profile, field=ProfileTextField.BACKGROUND
            )
            .order_by("created_at")
            .first()
        )
        assert first.text == "The lost original."

    def test_rejects_unversioned_field(self):
        with self.assertRaises(ValueError):
            update_profile_text(self.profile, "concept", "Not versioned.")

    def test_era_stamp_when_active_era_exists(self):
        from world.stories.constants import EraStatus
        from world.stories.factories import EraFactory

        era = EraFactory(status=EraStatus.ACTIVE)
        version = update_profile_text(self.profile, ProfileTextField.BACKGROUND, "Era-stamped.")
        assert version.era == era
