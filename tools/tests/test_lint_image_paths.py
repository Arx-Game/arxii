"""Tests for the pre-commit image path guard."""

from __future__ import annotations

from lint_image_paths import is_allowed_image_path, violations


def test_allows_images_in_workflow_evidence_directories() -> None:
    """Temporary evidence locations are the only approved image paths."""
    assert (
        violations(
            [
                "docs/reviews/room-state.png",
                ".github/issue-evidence/3824/screen.webp",
            ]
        )
        == []
    )


def test_rejects_images_outside_workflow_evidence_directories() -> None:
    """Images in ordinary source or documentation paths must fail pre-commit."""
    assert violations(
        [
            "docs/pr-evidence/room-state.png",
            "frontend/public/preview.svg",
            "src/world/assets/icon.jpg",
        ]
    ) == [
        "docs/pr-evidence/room-state.png",
        "frontend/public/preview.svg",
        "src/world/assets/icon.jpg",
    ]


def test_rejects_path_traversal_out_of_evidence_directory() -> None:
    """A path that escapes an evidence directory is not an approved location."""
    assert is_allowed_image_path("docs/reviews/../public/preview.png") is False


def test_ignores_non_image_files() -> None:
    """The guard only handles image extensions covered by the workflow."""
    assert violations(["frontend/public/preview.css", "docs/reviews/report.md"]) == []
