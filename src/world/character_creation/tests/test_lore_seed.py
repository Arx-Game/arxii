"""Tests for the lore onboarding seed (#2430)."""

from django.test import TestCase, override_settings

from world.character_creation.models import CGExplanation
from world.codex.models import CodexEntry
from world.seeds.character_creation import (
    CG_EXPLANATION_COPY,
    _seed_cg_explanations,
    seed_onboarding_codex,
)


class TestLoreOnboardingSeed(TestCase):
    """Lore keys and placeholder codex entries are seeded."""

    def test_lore_keys_in_copy_dict(self):
        """The 5 new lore keys are in CG_EXPLANATION_COPY."""
        expected_keys = [
            "origin_lore_intro",
            "heritage_lore_intro",
            "path_lore_durance",
            "gift_lore_intro",
            "roster_lore_intro",
        ]
        for key in expected_keys:
            assert key in CG_EXPLANATION_COPY, f"{key} missing from CG_EXPLANATION_COPY"

    def test_seed_onboarding_codex_creates_featured_entries(self):
        """seed_onboarding_codex creates featured public entries."""
        seed_onboarding_codex()
        featured = CodexEntry.objects.filter(is_featured=True, is_public=True)
        assert featured.count() >= 3
        # All featured entries should have a featured_order
        for entry in featured:
            assert entry.featured_order is not None

    def test_seed_onboarding_codex_is_idempotent(self):
        """Re-running seed_onboarding_codex doesn't duplicate entries."""
        seed_onboarding_codex()
        count_first = CodexEntry.objects.filter(is_featured=True).count()
        seed_onboarding_codex()
        count_second = CodexEntry.objects.filter(is_featured=True).count()
        assert count_first == count_second

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_lore_keys_seeded_by_seed_cg_explanations(self):
        """character_creation.cgexplanation is content-repo-owned (#2698); the
        "_lore_intro" keys have no authored counterpart today, so
        _seed_cg_explanations only creates them under SEED_SAMPLE_CONTENT."""
        _seed_cg_explanations()
        assert CGExplanation.objects.filter(key="origin_lore_intro").exists()
        assert CGExplanation.objects.filter(key="roster_lore_intro").exists()

    def test_folio_keys_in_copy_dict(self):
        """The Folio chapter keys (#3540) ship with the sample copy, em-dash free."""
        for key in ("arrival_eyebrow", "arrival_title", "arrival_door", "arrival_quiet"):
            assert key in CG_EXPLANATION_COPY, f"{key} missing from CG_EXPLANATION_COPY"
        for key, text in CG_EXPLANATION_COPY.items():
            assert "—" not in text, f"{key} carries an em-dash"
            assert "–" not in text, f"{key} carries an en-dash"
