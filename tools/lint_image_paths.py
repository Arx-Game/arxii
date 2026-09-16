"""Reject image files outside approved asset and evidence directories."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import sys

ALLOWED_DIRECTORY_PARTS = (
    ("docs", "reviews"),
    (".github", "issue-evidence"),
    ("frontend", "public"),
)

IMAGE_SUFFIXES = frozenset(
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".ico",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    }
)


def is_image_path(path: str) -> bool:
    """Return whether a path has an image suffix handled by the evidence workflow."""
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def is_allowed_image_path(path: str) -> bool:
    """Return whether an image is in an approved asset or evidence directory."""
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and any(
        parts[: len(prefix)] == prefix for prefix in ALLOWED_DIRECTORY_PARTS
    )


def violations(paths: list[str]) -> list[str]:
    """Return image paths that are outside approved asset or evidence directories."""
    return [path for path in paths if is_image_path(path) and not is_allowed_image_path(path)]


def main(argv: list[str] | None = None) -> int:
    """Check image paths supplied by pre-commit."""
    offending = violations(sys.argv[1:] if argv is None else argv)
    if not offending:
        return 0
    print("Image files may only be staged under docs/reviews/ or .github/issue-evidence/:")
    for path in offending:
        print(f"  {path}")
    print("Post evidence in the PR comment, then remove temporary files before merge.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
