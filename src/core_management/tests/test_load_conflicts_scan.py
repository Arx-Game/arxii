"""Tests for the read-only credited-row conflict scan (#3017).

``scan_load_conflicts``/``find_load_conflict`` recompute the same
credited-row conflicts ``_upsert_fixture_object`` would detect on a real
load, but by reading only - the admin conflict-list page (a later task)
calls this on every page load, so it must never write to the database.
"""

from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.content_fixtures import build_all, load_entries, resolve_fixture_model
from core_management.load_conflicts import find_load_conflict, scan_load_conflicts
from world.contributors.factories import ContentContributorFactory
from world.traits.models import Trait


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class LoadConflictsScanTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _seed_credited_row(self) -> None:
        ContentContributorFactory(name="Tehom")
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Tehom"\n---\nHuman words.\n',
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)

    def test_scan_finds_a_differing_credited_row(self) -> None:
        self._seed_credited_row()
        _write(
            self.root,
            "skills/performance.md",
            "---\n"
            "name: Performance\n"
            "category: social\n"
            'written_by: "Tehom"\n'
            "---\n"
            "Regenerated words.\n",
        )

        conflicts = scan_load_conflicts(self.root)

        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.model_name == "Trait"
        assert conflict.natural_key == "Performance"
        assert resolve_fixture_model(conflict.model_label) is Trait
        assert ("description", "Human words.", "Regenerated words.") in conflict.fields

    def test_scan_mutates_nothing(self) -> None:
        self._seed_credited_row()
        _write(
            self.root,
            "skills/performance.md",
            "---\n"
            "name: Performance\n"
            "category: social\n"
            'written_by: "Tehom"\n'
            "---\n"
            "Regenerated words.\n",
        )

        scan_load_conflicts(self.root)

        trait = Trait.objects.get(name="Performance")
        assert trait.description == "Human words."

    def test_find_load_conflict_round_trips(self) -> None:
        self._seed_credited_row()
        _write(
            self.root,
            "skills/performance.md",
            "---\n"
            "name: Performance\n"
            "category: social\n"
            'written_by: "Tehom"\n'
            "---\n"
            "Regenerated words.\n",
        )
        [conflict] = scan_load_conflicts(self.root)

        found = find_load_conflict(self.root, conflict.model_label, conflict.natural_key)

        assert found is not None
        assert found.model_label == conflict.model_label
        assert found.natural_key == conflict.natural_key
        assert found.fields == conflict.fields

    def test_find_load_conflict_returns_none_for_unknown_key(self) -> None:
        self._seed_credited_row()

        assert find_load_conflict(self.root, "arxii.trait", "Nonexistent") is None

    def test_scan_skips_uncredited_rows(self) -> None:
        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nHuman words.\n",
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)

        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nRegenerated words.\n",
        )

        assert scan_load_conflicts(self.root) == []

    def test_scan_skips_identical_credited_rows(self) -> None:
        self._seed_credited_row()
        # File on disk is unchanged - incoming values are byte-for-byte identical.

        assert scan_load_conflicts(self.root) == []
