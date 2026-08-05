"""The placeholder backlog report (#2980)."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from core_management.prose_report import render_report, scan_corpus


class ProseReportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def _write_fixture(self, relative: str, records: list[dict]) -> None:
        path = self.root / "fixtures" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records), encoding="utf-8")

    def test_counts_written_and_unwritten_rows_per_domain(self):
        self._write_fixture(
            "magic/technique.json",
            [
                {
                    "model": "magic.technique",
                    "fields": {"name": "A", "description": "one two three", "written_by": None},
                },
                {
                    "model": "magic.technique",
                    "fields": {
                        "name": "B",
                        "description": "four five",
                        "written_by": ["Tehom"],
                        "reviewed_by": ["Apostate"],
                    },
                },
            ],
        )
        report = scan_corpus(self.root)
        row = report.rows_by_domain["magic"]
        self.assertEqual(row.prose_rows, 2)
        self.assertEqual(row.written, 1)
        self.assertEqual(row.reviewed, 1)
        self.assertEqual(row.words, 5)

    def test_rows_without_prose_are_not_counted(self):
        self._write_fixture(
            "magic/effecttype.json",
            [{"model": "magic.effecttype", "fields": {"name": "Only a name"}}],
        )
        report = scan_corpus(self.root)
        self.assertNotIn("magic", report.rows_by_domain)

    def test_markdown_frontmatter_counts_too(self):
        entry = self.root / "content" / "traditions" / "thornwake.md"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            '---\nname: "Thornwake"\nwritten_by: "Tehom"\n---\n\nAuthored prose here.\n',
            encoding="utf-8",
        )
        report = scan_corpus(self.root)
        row = report.rows_by_domain["content/traditions"]
        self.assertEqual(row.prose_rows, 1)
        self.assertEqual(row.written, 1)
        self.assertEqual(row.words, 3)

    def test_grid_bundles_are_skipped(self):
        self._write_fixture("grid/area.json", [{"rooms": [], "description": "not a fixture row"}])
        report = scan_corpus(self.root)
        self.assertEqual(report.rows_by_domain, {})

    def test_render_report_leads_with_the_unwritten_total(self):
        self._write_fixture(
            "magic/technique.json",
            [{"model": "magic.technique", "fields": {"name": "A", "description": "one"}}],
        )
        lines = render_report(scan_corpus(self.root))
        self.assertIn("1 of 1 prose rows still have no writer", lines[0])
        self.assertTrue(any("magic" in line for line in lines))
