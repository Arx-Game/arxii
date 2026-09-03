"""Reject multi-line ``{# ... #}`` comments in Django templates.

Django's ``{# #}`` comment syntax is single-line only: the lexer never joins
lines, so an opening ``{#`` whose ``#}`` sits on a later line is not a comment
at all. Every character of it renders to the page as literal text. Three of
these were shipping visible comment prose into the production admin.

Use ``{% comment %}`` / ``{% endcomment %}`` for anything spanning lines.

Use "# noqa: TEMPLATE_COMMENT" with a justification to suppress.
"""

from __future__ import annotations

from pathlib import Path
import sys

SUPPRESSION_TOKEN = "noqa: template_comment"  # noqa: S105


def check_source(source: str) -> list[tuple[int, str]]:
    """Return (lineno, text) for each unterminated ``{#`` in the source.

    A ``{#`` is a violation when its matching ``#}`` does not appear later on
    the same line. Scanning is per-line precisely because that is the rule
    Django itself applies.

    Args:
        source: Full template text.

    Returns:
        A list of (lineno, offending line text) violation entries.
    """
    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if SUPPRESSION_TOKEN in line.lower():
            continue
        search_from = 0
        while (open_at := line.find("{#", search_from)) != -1:
            close_at = line.find("#}", open_at + 2)
            if close_at == -1:
                violations.append((lineno, line.strip()))
                break
            search_from = close_at + 2
    return violations


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return violations for a single template file.

    Args:
        path: Path to the template to inspect.

    Returns:
        A list of (lineno, offending line text) violation entries.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [(0, f"cannot read ({exc})")]
    return check_source(text)


def main(argv: list[str]) -> int:
    """Run the template-comment check across argv files.

    Args:
        argv: Command-line arguments (file paths to check).

    Returns:
        Exit status code: 1 if any violation found, 0 otherwise.
    """
    exit_code = 0
    for raw_path in argv:
        path = Path(raw_path)
        if path.suffix != ".html":
            continue
        for lineno, text in check_file(path):
            print(
                f"{path}:{lineno}: TEMPLATE_COMMENT unterminated '{{#' — Django's "
                f"'{{# #}}' is single-line only, so this renders to the page as "
                f"literal text. Use '{{% comment %}}' instead: {text}"
            )
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
