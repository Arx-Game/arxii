"""Content pipeline (#944): parsing, validation, fixture shape, idempotent load."""

from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase

from core_management.content_fixtures import (
    TRAIT_CATEGORIES,
    TRAIT_TYPES,
    ContentError,
    build_all,
    load_entries,
    parse_content_file,
    write_fixtures,
)
from world.traits.models import Trait, TraitCategory, TraitType


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


GOOD_SKILL = """---
name: Performance
category: social
---
PLACEHOLDER Captivating an audience through music, oration, or storytelling.
"""


class ParseAndValidateTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_enums_mirror_real_trait_choices(self) -> None:
        # TRAIT_TYPES is the producible subset; categories mirror exactly.
        assert {t.value for t in TraitType} >= TRAIT_TYPES
        assert {c.value for c in TraitCategory} == TRAIT_CATEGORIES

    def test_parse_good_file(self) -> None:
        path = _write(self.root, "skills/performance.md", GOOD_SKILL)
        entry = parse_content_file(path, "skills")
        assert entry.meta["name"] == "Performance"
        assert entry.has_placeholder is True

    def test_missing_frontmatter_fails(self) -> None:
        path = _write(self.root, "skills/bad.md", "just prose, no frontmatter")
        with self.assertRaises(ContentError):
            parse_content_file(path, "skills")

    def test_build_all_validates_and_counts_placeholders(self) -> None:
        _write(self.root, "skills/performance.md", GOOD_SKILL)
        _write(
            self.root,
            "stats/presence.md",
            "---\nname: presence\ncategory: social\n---\nForce of personality.\n",
        )
        _write(self.root, "worldbook/secret.md", "reference canon — ignored by the builder")
        result = build_all(self.root)
        assert len(result.entries) == 2
        assert result.placeholder_counts == {"skills": 1}
        outputs = set(result.fixtures)
        assert "world/traits/fixtures/content_skills.json" in outputs
        assert "world/traits/fixtures/content_stats.json" in outputs

    def test_bad_category_collects_error(self) -> None:
        _write(
            self.root,
            "skills/oops.md",
            "---\nname: Oops\ncategory: nonsense\n---\nbody\n",
        )
        with self.assertRaises(ContentError):
            build_all(self.root)


class ContentLoadTests(TestCase):
    """End-to-end: build → load_entries twice → idempotent upsert.

    Uses load_entries, NOT loaddata: SharedMemoryModel's identity map makes
    natural-key loaddata silently drop updates (verified cross-process —
    see load_entries' docstring). Fresh-DB inserts via the emitted fixture
    JSON remain valid; the authoring loop must upsert.
    """

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)
        _write(self.root, "skills/performance.md", GOOD_SKILL)

    def test_load_creates_then_updates_by_natural_key(self) -> None:
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        trait = Trait.objects.get(name="Performance")
        assert trait.trait_type == TraitType.SKILL
        assert "PLACEHOLDER" in trait.description

        # Author rewrites the prose; reload must UPDATE the same row.
        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nThe rewritten voice.\n",
        )
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)
        assert Trait.objects.filter(name="Performance").count() == 1
        trait.refresh_from_db()
        assert trait.description == "The rewritten voice."

    def test_fresh_db_fixture_json_still_loads(self) -> None:
        """The emitted fixture files stay valid for fresh-DB seeding."""
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        written = write_fixtures(build_all(self.root), Path(out.name))
        call_command("loaddata", str(written[0]), verbosity=0)
        assert Trait.objects.filter(name="Performance").exists()
