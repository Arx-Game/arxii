"""
Tests for codex inline link resolution service.

Tests the resolve_codex_links() function that parses [[wikilink]] syntax
from lore_content/mechanics_content and resolves to link refs with access
checking.
"""

from django.test import TestCase

from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
from world.codex.services import resolve_codex_links
from world.roster.factories import RosterEntryFactory


class ResolveCodexLinksTests(TestCase):
    """Tests for resolve_codex_links()."""

    @classmethod
    def setUpTestData(cls):
        cls.category = CodexCategoryFactory(name="Link Test Category")
        cls.subject = CodexSubjectFactory(category=cls.category, name="Link Test Subject")
        cls.other_subject = CodexSubjectFactory(category=cls.category, name="Other Subject")

        # Public entry in same subject
        cls.same_subject_public = CodexEntryFactory(
            subject=cls.subject,
            name="Same Subject Public",
            lore_content="Some lore",
            is_public=True,
        )

        # Public entry in a different subject
        cls.other_subject_public = CodexEntryFactory(
            subject=cls.other_subject,
            name="Other Subject Public",
            lore_content="Some lore",
            is_public=True,
        )

        # Restricted (private) entry in same subject
        cls.restricted_entry = CodexEntryFactory(
            subject=cls.subject,
            name="Restricted Entry",
            lore_content="Secret lore",
            is_public=False,
        )

        cls.roster_entry = RosterEntryFactory()

    def test_resolve_links_same_subject(self):
        """Link resolves to entry in same subject first."""
        content = "See [[Same Subject Public]] for details."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 1
        assert links[0]["entry_id"] == self.same_subject_public.pk
        assert links[0]["display_text"] == "Same Subject Public"
        assert links[0]["accessible"] is True

    def test_resolve_links_global_fallback(self):
        """Link resolves to entry in different subject when no same-subject match."""
        content = "See [[Other Subject Public]] for more."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 1
        assert links[0]["entry_id"] == self.other_subject_public.pk
        assert links[0]["accessible"] is True

    def test_resolve_links_inaccessible_shows_unknown(self):
        """Link to private entry the reader hasn't learned returns ??? and no entry_id."""
        content = "See [[Restricted Entry]] if you dare."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 1
        assert links[0]["entry_id"] is None
        assert links[0]["display_text"] == "???"
        assert links[0]["accessible"] is False

    def test_resolve_links_public_accessible_to_anonymous(self):
        """Public entry links are accessible even without a roster entry."""
        content = "See [[Same Subject Public]]."
        links = resolve_codex_links(content, self.subject, None)
        assert links[0]["accessible"] is True
        assert links[0]["entry_id"] == self.same_subject_public.pk

    def test_resolve_links_no_match(self):
        """Link text that doesn't match any entry returns raw text, not ???."""
        content = "See [[Nonexistent Entry]] for nothing."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 1
        assert links[0]["entry_id"] is None
        assert links[0]["display_text"] == "Nonexistent Entry"
        assert links[0]["accessible"] is False

    def test_resolve_links_inaccessible_vs_no_match(self):
        """Existing-but-locked entry returns ???, non-existent returns raw text."""
        content = "[[Restricted Entry]] and [[Totally Fake Entry]] in one string."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 2

        # First link: entry exists but is restricted
        assert links[0]["display_text"] == "???"
        assert links[0]["entry_id"] is None
        assert links[0]["accessible"] is False

        # Second link: no entry with that name
        assert links[1]["display_text"] == "Totally Fake Entry"
        assert links[1]["entry_id"] is None
        assert links[1]["accessible"] is False

    def test_resolve_links_known_entry_accessible(self):
        """Restricted entry is accessible when reader has KNOWN status."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        content = "See [[Restricted Entry]]."
        links = resolve_codex_links(content, self.subject, self.roster_entry)
        assert len(links) == 1
        assert links[0]["entry_id"] == self.restricted_entry.pk
        assert links[0]["display_text"] == "Restricted Entry"
        assert links[0]["accessible"] is True

    def test_resolve_links_uncovered_not_accessible(self):
        """Restricted entry with UNCOVERED status is NOT accessible."""
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.restricted_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        content = "See [[Restricted Entry]]."
        links = resolve_codex_links(content, self.subject, self.roster_entry)
        assert links[0]["accessible"] is False
        assert links[0]["display_text"] == "???"

    def test_resolve_links_multiple_links(self):
        """Multiple links in one content string are all resolved."""
        content = (
            "[[Same Subject Public]] and [[Other Subject Public]] "
            "and [[Restricted Entry]] and [[Fake Entry]]."
        )
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 4
        assert links[0]["display_text"] == "Same Subject Public"
        assert links[1]["display_text"] == "Other Subject Public"
        assert links[2]["display_text"] == "???"
        assert links[3]["display_text"] == "Fake Entry"

    def test_resolve_links_empty_content(self):
        """Empty or None content returns empty list."""
        assert resolve_codex_links("", self.subject, None) == []
        assert resolve_codex_links(None, self.subject, None) == []

    def test_resolve_links_no_links_in_content(self):
        """Content without wikilinks returns empty list."""
        content = "Just plain text with no links."
        links = resolve_codex_links(content, self.subject, None)
        assert links == []

    def test_resolve_links_case_sensitive(self):
        """Name matching is case-sensitive."""
        content = "See [[same subject public]]."
        links = resolve_codex_links(content, self.subject, None)
        assert len(links) == 1
        assert links[0]["entry_id"] is None
        assert links[0]["display_text"] == "same subject public"
        assert links[0]["accessible"] is False

    def test_resolve_links_inaccessible_does_not_leak_name(self):
        """The entry name of an inaccessible entry never appears in the response."""
        content = "See [[Restricted Entry]]."
        links = resolve_codex_links(content, self.subject, None)
        assert links[0]["display_text"] == "???"
        # The real name "Restricted Entry" should not appear anywhere in the link ref
        assert "Restricted Entry" not in links[0]["display_text"]
        assert links[0]["entry_id"] is None
