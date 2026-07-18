"""Content-load health helpers (#2501): skip grouping, KNOWN_DRIFT allowlist, verdict."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from core_management.content_health import (
    group_skips,
    load_known_drift,
    partition_skips,
    render_health_report,
)


class GroupSkipsTests(SimpleTestCase):
    def test_groups_by_source_prefix(self) -> None:
        skipped = [
            "gifts/foo.md: Gift could not be loaded: bad category",
            "gifts/foo.md: Technique could not be loaded: bad rank",
            "gifts/bar.md: Gift could not be loaded: missing name",
        ]

        grouped = group_skips(skipped)

        self.assertEqual(
            grouped,
            {
                "gifts/foo.md": [
                    "gifts/foo.md: Gift could not be loaded: bad category",
                    "gifts/foo.md: Technique could not be loaded: bad rank",
                ],
                "gifts/bar.md": ["gifts/bar.md: Gift could not be loaded: missing name"],
            },
        )

    def test_missing_separator_groups_under_unknown(self) -> None:
        skipped = ["no separator here at all"]

        grouped = group_skips(skipped)

        self.assertEqual(grouped, {"<unknown>": ["no separator here at all"]})

    def test_empty_list_yields_empty_dict(self) -> None:
        self.assertEqual(group_skips([]), {})


class LoadKnownDriftTests(SimpleTestCase):
    def test_absent_file_returns_empty_list(self) -> None:
        with TemporaryDirectory() as temp_dir:
            patterns = load_known_drift(Path(temp_dir))

        self.assertEqual(patterns, [])

    def test_strips_blank_lines_and_comments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixtures_dir = root / "fixtures"
            fixtures_dir.mkdir(parents=True)
            content = (
                "# stale drift entries\n\nbad category\n  # another comment\nmissing name  \n\n"
            )
            (fixtures_dir / "KNOWN_DRIFT.txt").write_text(content, encoding="utf-8")

            patterns = load_known_drift(root)

        self.assertEqual(patterns, ["bad category", "missing name"])


class PartitionSkipsTests(SimpleTestCase):
    def test_partitions_known_vs_unexpected_by_substring(self) -> None:
        skipped = [
            "gifts/foo.md: Gift could not be loaded: bad category",
            "gifts/bar.md: Gift could not be loaded: missing name",
            "gifts/baz.md: Gift could not be loaded: totally new failure",
        ]
        patterns = ["bad category", "missing name"]

        known, unexpected = partition_skips(skipped, patterns)

        self.assertEqual(
            known,
            [
                "gifts/foo.md: Gift could not be loaded: bad category",
                "gifts/bar.md: Gift could not be loaded: missing name",
            ],
        )
        self.assertEqual(
            unexpected, ["gifts/baz.md: Gift could not be loaded: totally new failure"]
        )

    def test_no_patterns_means_everything_unexpected(self) -> None:
        skipped = ["gifts/foo.md: Gift could not be loaded: bad category"]

        known, unexpected = partition_skips(skipped, [])

        self.assertEqual(known, [])
        self.assertEqual(unexpected, skipped)


class RenderHealthReportTests(SimpleTestCase):
    def test_healthy_when_all_skips_known(self) -> None:
        skipped = [
            "gifts/foo.md: Gift could not be loaded: bad category",
            "gifts/foo.md: Technique could not be loaded: bad category",
        ]
        patterns = ["bad category"]

        lines, healthy = render_health_report(skipped, patterns)

        self.assertTrue(healthy)
        self.assertTrue(any("gifts/foo.md" in line for line in lines))
        self.assertTrue(any("known" in line.lower() for line in lines))

    def test_unhealthy_when_unexpected_skip_present(self) -> None:
        skipped = [
            "gifts/foo.md: Gift could not be loaded: bad category",
            "gifts/baz.md: Gift could not be loaded: totally new failure",
        ]
        patterns = ["bad category"]

        lines, healthy = render_health_report(skipped, patterns)

        self.assertFalse(healthy)
        self.assertTrue(
            any(
                "gifts/baz.md: Gift could not be loaded: totally new failure" in line
                for line in lines
            )
        )

    def test_empty_skipped_is_healthy_with_no_unexpected(self) -> None:
        _lines, healthy = render_health_report([], [])

        self.assertTrue(healthy)
