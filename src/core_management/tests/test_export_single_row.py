"""Tests for the row-level content export seam (#3018)."""

from datetime import date
import json
from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.content_export import export_single_row
from core_management.content_fixtures import content_slug


class RowExportTests(TestCase):
    """export_single_row: JSON domains, markdown domains, and refusal paths."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_json_update_replaces_exactly_one_record(self) -> None:
        """Exporting an edited row rewrites its record and leaves its sibling alone."""
        from core_management.content_export import export_to_content_repo
        from world.magic.factories import EffectTypeFactory

        effect_a = EffectTypeFactory(name="Row Export A", description="Original A")
        EffectTypeFactory(name="Row Export B", description="Original B")

        # Seed the corpus file with both rows (no gate: the file doesn't exist yet).
        seed_result = export_to_content_repo(self.root)
        assert seed_result.errors == []

        effect_a.description = "Updated A"
        effect_a.save()

        result = export_single_row(effect_a, content_root=self.root)

        assert result.refused is None
        assert result.is_addition is False
        assert result.model_label == "magic.effecttype"

        path = self.root / "fixtures" / "magic" / "effecttype.json"
        assert result.paths == [path]
        records = json.loads(path.read_text(encoding="utf-8"))
        by_name = {r["fields"]["name"]: r["fields"]["description"] for r in records}
        assert by_name["Row Export A"] == "Updated A"
        assert by_name["Row Export B"] == "Original B"
        assert len(records) == 2

    def test_json_addition_appends(self) -> None:
        """A row whose natural key isn't in the file yet is appended, not withheld."""
        from world.magic.factories import EffectTypeFactory

        effect_a = EffectTypeFactory(name="Append A")
        first = export_single_row(effect_a, content_root=self.root)
        assert first.is_addition is True

        effect_c = EffectTypeFactory(name="Append C")
        result = export_single_row(effect_c, content_root=self.root)

        assert result.refused is None
        assert result.is_addition is True

        path = self.root / "fixtures" / "magic" / "effecttype.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        names = {r["fields"]["name"] for r in records}
        assert names == {"Append A", "Append C"}

    def test_json_no_corpus_file_is_addition(self) -> None:
        """No fixture file for the model yet: written as a fresh one-record file."""
        from world.magic.factories import EffectTypeFactory

        effect = EffectTypeFactory(name="Solo Effect")
        result = export_single_row(effect, content_root=self.root)

        path = self.root / "fixtures" / "magic" / "effecttype.json"
        assert result.refused is None
        assert result.is_addition is True
        assert result.paths == [path]
        records = json.loads(path.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["fields"]["name"] == "Solo Effect"

    def test_markdown_row_writes_one_file(self) -> None:
        """A CodexEntry writes exactly one markdown file with its credit intact."""
        from world.codex.factories import (
            CodexCategoryFactory,
            CodexEntryFactory,
            CodexSubjectFactory,
        )
        from world.contributors.factories import ContentContributorFactory

        category = CodexCategoryFactory(name="Row Export Category")
        subject = CodexSubjectFactory(category=category, name="Row Export Subject")
        entry = CodexEntryFactory(
            subject=subject, name="Row Export Entry", lore_content="Some authored lore."
        )
        contributor = ContentContributorFactory(name="Row Export Writer")
        entry.written_by = contributor
        entry.written_on = date(2026, 1, 1)
        entry.save()

        result = export_single_row(entry, content_root=self.root)

        expected_path = (
            self.root
            / "content/codex_entries"
            / content_slug("Row Export Subject")
            / f"{content_slug('Row Export Entry')}.md"
        )
        assert result.refused is None
        assert result.model_label == "codex.codexentry"
        assert result.paths == [expected_path]
        assert result.is_addition is True
        assert expected_path.exists()

        text = expected_path.read_text(encoding="utf-8")
        assert "Row Export Writer" in text
        assert "Some authored lore." in text

        # Exporting again finds the file already present -> not an addition.
        second = export_single_row(entry, content_root=self.root)
        assert second.is_addition is False
        assert list(self.root.glob("content/codex_entries/**/*.md")) == [expected_path]

    def test_export_filter_refusal(self) -> None:
        """A player-owned CheckType row is excluded from export and writes nothing."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.seeds_checks import ensure_character_magic_check_type
        from world.skills.factories import SkillFactory
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        sheet = CharacterSheetFactory()
        stat = TraitFactory(name="row_export_willpower", trait_type=TraitType.STAT)
        skill = SkillFactory(trait__name="row_export_ritualism")
        synthesized = ensure_character_magic_check_type(sheet, stat=stat, skill=skill)

        result = export_single_row(synthesized, content_root=self.root)

        assert result.refused is not None
        assert result.paths == []
        path = self.root / "fixtures" / "checks" / "checktype.json"
        assert not path.exists()

    def test_non_content_model_refusal(self) -> None:
        """A model outside CONTENT_MODELS/MARKDOWN_EXPORT_DOMAINS refuses, writes nothing."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()

        result = export_single_row(sheet, content_root=self.root)

        assert result.refused is not None
        assert result.paths == []
        assert result.model_label == "character_sheets.charactersheet"
        assert not (self.root / "fixtures" / "character_sheets" / "charactersheet.json").exists()
