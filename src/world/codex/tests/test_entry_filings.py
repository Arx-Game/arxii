"""Tests for CodexEntryFiling: an entry cross-listed under a second subject.

These tests deliberately avoid CodexSubjectBreadcrumb (the materialized view
backing ``CodexSubject.breadcrumb_path``) - filings don't touch it, and the
view doesn't exist in every local test database (a known pre-existing gap;
CI is the gate for that surface).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.codex.factories import (
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexEntryFilingFactory,
    CodexSubjectFactory,
)
from world.codex.filters import CodexEntryFilter
from world.codex.models import CodexEntry, CodexEntryFiling
from world.codex.services import file_entry_under, unfile_entry


class FileEntryUnderTests(TestCase):
    """Tests for services.file_entry_under."""

    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory()
        cls.other_subject = CodexSubjectFactory(category=cls.entry.subject.category)

    def test_filing_under_a_second_subject_works(self):
        """Filing an entry under a subject other than its home creates a row."""
        filing = file_entry_under(self.entry, self.other_subject)

        assert isinstance(filing, CodexEntryFiling)
        assert filing.entry_id == self.entry.pk
        assert filing.subject_id == self.other_subject.pk
        assert self.other_subject.filed_entries.count() == 1
        assert self.entry.filings.count() == 1

    def test_filing_under_canonical_subject_raises(self):
        """Filing an entry under its own canonical home is rejected."""
        with self.assertRaises(ValidationError):
            file_entry_under(self.entry, self.entry.subject)

        assert not CodexEntryFiling.objects.exists()

    def test_filing_same_pair_twice_returns_existing_row(self):
        """A repeat filing of the same (entry, subject) pair is idempotent.

        Documented choice (see the plan brief): the service returns the
        existing row rather than raising IntegrityError - a filing is a
        link, not an event.
        """
        first = file_entry_under(self.entry, self.other_subject, sort_order=1)
        second = file_entry_under(self.entry, self.other_subject, sort_order=99)

        assert first.pk == second.pk
        assert CodexEntryFiling.objects.count() == 1
        # The second call did not overwrite the first row's sort_order.
        first.refresh_from_db()
        assert first.sort_order == 1

    def test_unfile_entry_removes_the_row(self):
        """unfile_entry removes an existing filing."""
        file_entry_under(self.entry, self.other_subject)
        assert CodexEntryFiling.objects.count() == 1

        unfile_entry(self.entry, self.other_subject)

        assert CodexEntryFiling.objects.count() == 0

    def test_unfile_entry_is_a_no_op_when_no_filing_exists(self):
        """unfile_entry does not raise when there is nothing to remove."""
        unfile_entry(self.entry, self.other_subject)
        assert CodexEntryFiling.objects.count() == 0


class CodexEntryFilingModelTests(TestCase):
    """Tests for the CodexEntryFiling model itself."""

    def test_duplicate_pair_violates_the_database_constraint(self):
        """The (entry, subject) uniqueness is enforced at the database level,
        independent of the service's get_or_create-based idempotency."""
        filing = CodexEntryFilingFactory()
        with self.assertRaises(IntegrityError):
            CodexEntryFiling.objects.create(entry=filing.entry, subject=filing.subject)

    def test_deleting_the_entry_deletes_its_filings(self):
        """CASCADE from CodexEntry removes filings when the entry is deleted."""
        filing = CodexEntryFilingFactory()
        filing_pk = filing.pk

        filing.entry.delete()

        assert not CodexEntryFiling.objects.filter(pk=filing_pk).exists()

    # Note: a CodexSubject.delete() CASCADE test is intentionally omitted here.
    # CodexSubject.delete() refreshes the codex_subjectbreadcrumb materialized
    # view, which is a known local-DB gap (missing relation); CI is the gate
    # for that path. The FK CASCADE itself is identical to the entry case
    # above, exercised by an ordinary Django ForeignKey(on_delete=CASCADE).

    def test_str_representation(self):
        """String form names both the entry and the subject it's filed under."""
        filing = CodexEntryFilingFactory()
        assert str(filing) == f"{filing.entry} filed under {filing.subject}"

    def test_clean_rejects_filing_under_the_canonical_subject(self):
        """The home-subject invariant holds at the model level (admin inlines
        bypass services.file_entry_under, so clean() is the backstop)."""
        entry = CodexEntryFactory()
        filing = CodexEntryFiling(entry=entry, subject=entry.subject)
        with self.assertRaises(ValidationError):
            filing.clean()

    def test_clean_allows_a_different_subject_and_skips_unset_fks(self):
        """clean() passes a valid cross-filing and tolerates unset FKs."""
        entry = CodexEntryFactory()
        other_subject = CodexSubjectFactory(category=entry.subject.category)
        CodexEntryFiling(entry=entry, subject=other_subject).clean()
        # Unsaved form rows may have either FK unset; clean() must not crash.
        CodexEntryFiling(entry=entry).clean()
        CodexEntryFiling(subject=other_subject).clean()


class CodexEntryFilterSubjectTests(TestCase):
    """Tests for CodexEntryFilter's subject filter (#2896).

    These stay at the queryset/filter level rather than going through the API
    client, so they exercise the OR-with-a-filing logic and its ordering
    directly without touching CodexSubjectBreadcrumb (see the module
    docstring).
    """

    @classmethod
    def setUpTestData(cls):
        cls.category = CodexCategoryFactory()
        cls.subject = CodexSubjectFactory(category=cls.category)
        cls.other_subject = CodexSubjectFactory(category=cls.category)
        cls.canonical_entry = CodexEntryFactory(subject=cls.subject, name="Canonical Entry")
        cls.filed_entry = CodexEntryFactory(subject=cls.other_subject, name="Filed Entry")
        cls.filing = file_entry_under(cls.filed_entry, cls.subject, sort_order=3)

    def _filtered(self, subject_id: int) -> list[CodexEntry]:
        filterset = CodexEntryFilter(
            data={"subject": subject_id}, queryset=CodexEntry.objects.all()
        )
        return list(filterset.qs)

    def test_subject_filter_includes_canonical_and_filed_entries(self):
        """The subject's own entry and the entry filed under it both appear."""
        results = self._filtered(self.subject.id)
        assert self.canonical_entry in results
        assert self.filed_entry in results
        assert len(results) == 2

    def test_subject_filter_returns_the_filed_entry_only_once(self):
        """A filed entry never appears twice in its filed subject's listing."""
        results = self._filtered(self.subject.id)
        assert results.count(self.filed_entry) == 1

    def test_subject_filter_orders_canonical_entries_before_filed_ones(self):
        """Canonical entries sort ahead of filed entries in the same listing."""
        results = self._filtered(self.subject.id)
        assert results.index(self.canonical_entry) < results.index(self.filed_entry)

    def test_subject_filter_does_not_leak_the_filed_entry_into_unrelated_subjects(self):
        """A filed entry does not appear in a third, unrelated subject's listing."""
        unrelated = CodexSubjectFactory(category=self.category)
        results = self._filtered(unrelated.id)
        assert self.filed_entry not in results
        assert self.canonical_entry not in results
