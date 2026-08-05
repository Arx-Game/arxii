"""Content loads never overwrite credited rows (#3017).

A row a human has credited (``written_by`` set) whose incoming values differ
from what's already on disk must be left untouched by the load, not silently
overwritten - the credit is a signal that a person has already made an
editorial pass, and a regenerated corpus value should never clobber it. This
covers the guard end-to-end: ``build_all`` -> ``load_entries`` -> a real
``CreditedContent`` row, same seam ``CreditEndToEndLoadTests`` in
``test_content_fixtures.py`` exercises for the credit-write path itself.
"""

from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.content_fixtures import build_all, load_entries
from world.contributors.factories import ContentContributorFactory
from world.items.models import ItemTemplate
from world.traits.models import Trait


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class LoadConflictGuardTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_credited_row_with_differing_prose_field_is_left_untouched(self) -> None:
        ContentContributorFactory(name="Tehom")
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Tehom"\n---\nHuman words.\n',
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        trait = Trait.objects.get(name="Performance")
        assert trait.written_by is not None
        assert trait.description == "Human words."

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
        result = build_all(self.root)
        created, updated, _ = load_entries(result)

        # The conflict is terminal on first detection - no counter bumps.
        assert (created, updated) == (0, 0)
        assert len(result.conflicts) == 1
        assert "description" in result.conflicts[0]

        trait.refresh_from_db()
        assert trait.description == "Human words."

    def test_credited_row_with_differing_mechanical_field_is_left_untouched(self) -> None:
        ContentContributorFactory(name="Tehom")
        _write(
            self.root,
            "items/iron_longsword.md",
            "---\n"
            "name: Iron Longsword\n"
            "value: 40\n"
            'written_by: "Tehom"\n'
            "---\n"
            "A well-balanced blade, plain but serviceable.\n",
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        item = ItemTemplate.objects.get(name="Iron Longsword")
        assert item.written_by is not None
        assert item.value == 40

        _write(
            self.root,
            "items/iron_longsword.md",
            "---\n"
            "name: Iron Longsword\n"
            "value: 999\n"
            'written_by: "Tehom"\n'
            "---\n"
            "A well-balanced blade, plain but serviceable.\n",
        )
        result = build_all(self.root)
        created, updated, _ = load_entries(result)

        assert (created, updated) == (0, 0)
        assert len(result.conflicts) == 1
        assert "value" in result.conflicts[0]

        item.refresh_from_db()
        assert item.value == 40

    def test_credited_row_with_identical_values_is_a_quiet_noop(self) -> None:
        ContentContributorFactory(name="Tehom")
        entry = '---\nname: Performance\ncategory: social\nwritten_by: "Tehom"\n---\nHuman words.\n'
        _write(self.root, "skills/performance.md", entry)
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)

        # Same file, reloaded - incoming values are byte-for-byte identical.
        result = build_all(self.root)
        created, updated, _ = load_entries(result)

        assert (created, updated) == (0, 1)
        assert result.conflicts == []
        trait = Trait.objects.get(name="Performance")
        assert trait.description == "Human words."

    def test_uncredited_row_still_upserts(self) -> None:
        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nHuman words.\n",
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        trait = Trait.objects.get(name="Performance")
        assert trait.written_by is None

        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nRegenerated words.\n",
        )
        result = build_all(self.root)
        created, updated, _ = load_entries(result)

        assert (created, updated) == (0, 1)
        assert result.conflicts == []
        trait.refresh_from_db()
        assert trait.description == "Regenerated words."

    def test_differing_credit_fields_alone_freeze_the_row(self) -> None:
        ContentContributorFactory(name="Alice")
        ContentContributorFactory(name="Bob")
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Alice"\n---\nHuman words.\n',
        )
        created, updated, _ = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        trait = Trait.objects.get(name="Performance")
        assert trait.written_by.name == "Alice"

        # Same description - only the credited author differs.
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Bob"\n---\nHuman words.\n',
        )
        result = build_all(self.root)
        created, updated, _ = load_entries(result)

        assert (created, updated) == (0, 0)
        assert len(result.conflicts) == 1
        assert "written_by" in result.conflicts[0]

        trait.refresh_from_db()
        assert trait.written_by.name == "Alice"

    def test_conflict_message_names_model_key_and_fields(self) -> None:
        ContentContributorFactory(name="Tehom")
        _write(
            self.root,
            "skills/performance.md",
            '---\nname: Performance\ncategory: social\nwritten_by: "Tehom"\n---\nHuman words.\n',
        )
        load_entries(build_all(self.root))

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
        result = build_all(self.root)
        load_entries(result)

        assert len(result.conflicts) == 1
        message = result.conflicts[0]
        assert "Trait" in message
        assert "Performance" in message
        assert "description" in message
