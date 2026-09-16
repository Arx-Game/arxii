"""Reject image files outside the temporary evidence staging directories."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import sys

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
    """Return whether an image is in a temporary evidence staging directory."""
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and parts[:2] in (("docs", "reviews"), (".github", "issue-evidence"))


def violations(paths: list[str]) -> list[str]:
    """Return image paths that are outside the approved evidence directories."""
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
