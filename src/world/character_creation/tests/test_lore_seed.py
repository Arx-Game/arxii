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
        for key in ("arrival_title", "arrival_intro", "arrival_door", "arrival_quiet"):
            assert key in CG_EXPLANATION_COPY, f"{key} missing from CG_EXPLANATION_COPY"
        for key, text in CG_EXPLANATION_COPY.items():
            assert "—" not in text, f"{key} carries an em-dash"
            assert "–" not in text, f"{key} carries an en-dash"

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_folio_stage_internal_keys_seed_cg_explanations(self):
        """Folio stage-internal copy keys (#3630 Plan B) each seed a non-empty
        CGExplanation row. None of these have a content-repo counterpart yet,
        so sample seeding is forced on for this check (mirrors the
        `*_lore_intro` keys above)."""
        _seed_cg_explanations()
        stage_internal_keys = (
            "gift_tradition_heading",
            "appearance_age_heading",
            "appearance_birthday_heading",
            "appearance_height_heading",
            "appearance_build_heading",
            "appearance_features_heading",
            "appearance_description_heading",
            "appearance_markings_heading",
            "identity_name_heading",
            "identity_concept_heading",
            "identity_quote_heading",
            "identity_worship_heading",
            "finaltouches_how_note",
            "finaltouches_never_do_prompt",
            "finaltouches_never_do_example",
            "finaltouches_protect_prompt",
            "finaltouches_fear_prompt",
            "finaltouches_enemy_heading",
            "introductions_heading",
            "introductions_intro",
            "first_journal_q1",
            "application_q3",
            "whispers_frame",
        )
        for key in stage_internal_keys:
            explanation = CGExplanation.objects.get(key=key)
            assert explanation.text, f"{key} seeded an empty CGExplanation"

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_offers_chapter_keys_seed_cg_explanations(self):
        """The CG chapters' own offered-distinctions copy (#3675 Tasks 13-15):
        the Glimpse, Lineage, Appearance and Actor's Sheet headings/chips/closed
        leads, plus gift_schooling_label (TraditionPicker.tsx, predates #3675 but
        was undeclared until the same grep that found these keys caught it),
        none of which have a content-repo counterpart yet."""
        _seed_cg_explanations()
        offers_chapter_keys = (
            "glimpse_choose_any",
            "glimpse_choose_one",
            "glimpse_offers_heading",
            "offers_optional_chip",
            "glimpse_story_label",
            "glimpse_story_hint",
            "lineage_bundles_word",
            "lineage_offers_word",
            "lineage_offers_heading",
            "lineage_offers_chip",
            "lineage_closed_lead",
            "appearance_offers_heading",
            "appearance_offers_chip",
            "appearance_closed_lead",
            "finaltouches_offers_heading",
            "finaltouches_offers_chip",
            "finaltouches_closed_lead",
            "gift_schooling_label",
        )
        for key in offers_chapter_keys:
            assert key in CG_EXPLANATION_COPY, f"{key} missing from CG_EXPLANATION_COPY"
            explanation = CGExplanation.objects.get(key=key)
            assert explanation.text, f"{key} seeded an empty CGExplanation"
