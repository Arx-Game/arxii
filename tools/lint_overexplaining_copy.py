"""Flag user-visible copy that tells the reader who may see a thing.

The lintable subset of the over-explaining rule (#4193, 2026-10-08). A screen says who may
read a thing with a tone, a region heading or a word in a label, never with a sentence:
"Only you can see this", "Staff view: every entry is shown", "visible to everyone",
"They are never told", "No messages yet. Narrative messages from your GM will appear
here." Players read these screens hundreds of times and every extra word is friction
(ApostateCD; the no-unnecessary-labeling rule, the #4124 "privacy is a tone shift, not a
caption" ruling). The reflex that writes them is structural: an agent's default is to say
the critical thing rather than risk leaving it unsaid, so the copy comes back in every new
screen. The `overexplaining-copy-reviewer` agent reads a diff for the whole shape; this
linter catches the instances a regex can name.

What is flagged: a line of a `.tsx` file under `frontend/src` (tests excluded by the hook's
`files:` pattern) whose non-comment text contains one of the phrases in `PHRASES`.

What is NOT flagged: comments (`//`, `/* */`, `{/* */}`), import lines, and a line that
carries `noqa: OVEREXPLAIN` itself or on the line above. The suppression must say why; a
bare one is indistinguishable from an oversight. Legitimate reasons: a destructive-action
consequence, an account-security disclosure, a voice line ApostateCD wrote.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import re
import sys

SUPPRESSION_TOKEN = "noqa: overexplain"  # noqa: S105

#: Each one is a caption shape, never a fact the screen cannot carry otherwise.
PHRASES = (
    r"\bonly you\b",
    r"\bonly staff\b",
    r"\bstaff only\b",
    r"\bvisible to\b",
    r"\bvisible only\b",
    r"\bshown to\b",
    r"\bnever shown\b",
    r"\bnot shown\b",
    # "Nobody else here." is a presence fact; the caption is "nobody else can/may/sees".
    r"\bnobody else (?:can|may|sees|reads|learns|knows|is told|is ever)\b",
    r"\bno one else (?:can|may|sees|reads|learns|knows|is told|is ever)\b",
    r"\bnever told\b",
    r"\bnever learn who\b",
    r"\bwill appear here\b",
)
PATTERN = re.compile("|".join(PHRASES), re.IGNORECASE)

LINE_COMMENT = re.compile(r"(^|\s)//.*$")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Blank out comments while keeping every newline, so line numbers hold."""
    without_blocks = BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)
    return "\n".join(LINE_COMMENT.sub(r"\1", line) for line in without_blocks.split("\n"))


def check_source(source: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line_number, phrase)`` for every flagged line."""
    raw_lines = source.split("\n")
    for index, line in enumerate(_strip_comments(source).split("\n")):
        match = PATTERN.search(line)
        if match is None:
            continue
        if line.lstrip().startswith("import "):
            continue
        here = raw_lines[index].lower()
        above = raw_lines[index - 1].lower() if index > 0 else ""
        if SUPPRESSION_TOKEN in here or SUPPRESSION_TOKEN in above:
            continue
        yield index + 1, match.group(0)


def main(argv: list[str]) -> int:
    failed = False
    for filename in argv:
        source = Path(filename).read_text(encoding="utf-8")
        for line_number, phrase in check_source(source):
            failed = True
            print(
                f"{filename}:{line_number}: OVEREXPLAIN copy says who may see this "
                f'("{phrase}"). A tone, a region heading or a word in the label says it; '
                "add `// noqa: OVEREXPLAIN - <why>` only for a consequence, a security "
                "disclosure or an authored voice line."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
