"""Reject em/en-dashes in identifier strings: names, keys, slugs, labels.

Ruled 2026-08-03 (Tehom):

    "we should NOT have em dashes in natural keys/names ever. Do you have any
    idea how bad it is that a search by keyboard wouldn't match them because
    people are entering a hyphen and it's an em-dash? That's incredibly bad,
    not just from a slop perspective."

This is NOT the prose/AI-voice rule. It is a correctness rule, and it is
stricter, because in this codebase **a name IS a lookup key**. The dominant
pattern is an exact match:

    ConditionTemplate.objects.get(name=CHARM_CONDITION_NAME)
    ConditionTemplate.objects.filter(name=SHIELDED_CONDITION_NAME).first()

An em-dash is not on anyone's keyboard. A row whose name contains one is a row
that cannot be found: player search misses it, staff admin autocomplete misses
it, and a hand-authored fixture cross-reference resolves to nothing instead of
raising. The failure is silent in every direction, which is what makes it worse
than a typo.

Caught in the wild by lore #42: two ConditionTemplate rows, "Abyssal Resonance
<em-dash> Minor/Deep Attunement", were unreachable by keyboard while every
prose sweep reported the corpus clean — because prose checks never look at a
`name` field.

What is flagged:

* Python keyword arguments and dict-literal entries whose key is identifier-ish
  (`name=`, `"key":`, `slug=`, `title=`, `label=`, `code=`) and whose value is a
  string literal containing an em- or en-dash.
* Identity fields and serialised natural keys in JSON fixtures.

What is NOT flagged: comments, docstrings, and prose fields (`description`,
`summary`, `player_description`, ...). Prose em-dashes are a separate, softer
rule that lives in the deslop skill; this linter only cares about strings that
have to be typed or matched.

Use `# noqa: IDENT_DASH` on the same line when a dash in an identifier is
genuinely correct — e.g. an external system's key that we do not control.
Say why, in the comment; a bare suppression is indistinguishable from an
oversight.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
import json
from pathlib import Path
import re
import sys

SUPPRESSION_TOKEN = "noqa: ident_dash"  # noqa: S105

DASHES = re.compile(r"[—–]")

#: Substring hints. Catches `display_name`, `template_key`, `natural_key`, ...
IDENTIFIER_HINTS = ("name", "key", "slug", "title", "label", "code", "ident")

#: Prose wins over the hints. `display_text` is prose; `display_name` is not.
#: Kept in step with FIXTURE_PROSE_KEYS in the deslop skill's check.py.
PROSE_KEYS = frozenset(
    {
        "description",
        "player_description",
        "observer_description",
        "summary",
        "text",
        "prose",
        "body",
        "content",
        "flavor_text",
        "narrative_snippet",
        "lore_content",
        "mechanics_content",
        "frame_narrative",
        "prompt",
        "epigraph",
        "display_text",
        "pitch",
        "success_text",
        "failure_text",
        "narrative_prose",
        "announce_template",
        "description_template",
        "epilogue",
        "tooltip",
        # `verbose_name` is an admin display string, not a lookup key.
        "verbose_name",
        "verbose_name_plural",
        "help_text",
    }
)


def is_identifier_key(key: str) -> bool:
    """True when `key` names an identity rather than prose."""
    lowered = key.lower()
    if lowered in PROSE_KEYS:
        return False
    return any(hint in lowered for hint in IDENTIFIER_HINTS)


def _suppressed(lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(lines):
        return SUPPRESSION_TOKEN in lines[lineno - 1].lower()
    return False


def _call_pairs(node: ast.Call) -> Iterator[tuple[str, ast.expr]]:
    """``Model.objects.get(name="...")``."""
    for kw in node.keywords:
        if kw.arg:
            yield kw.arg, kw.value


def _dict_pairs(node: ast.Dict) -> Iterator[tuple[str, ast.expr]]:
    """``{"name": "..."}`` — the seed specs in ``world/seeds/game_content/``."""
    for key_node, value_node in zip(node.keys, node.values, strict=True):
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            yield key_node.value, value_node


def _assign_pairs(node: ast.Assign) -> Iterator[tuple[str, ast.expr]]:
    """``SOME_NAME = "..."`` — the constants those lookups are keyed on."""
    for target in node.targets:
        if isinstance(target, ast.Name):
            yield target.id, node.value


def _identifier_pairs(tree: ast.AST) -> Iterator[tuple[str, ast.expr]]:
    """Yield every ``(key, value-node)`` pair where `key` might name an identity."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield from _call_pairs(node)
        elif isinstance(node, ast.Dict):
            yield from _dict_pairs(node)
        elif isinstance(node, ast.Assign):
            yield from _assign_pairs(node)


def _string_literals(node: ast.expr) -> Iterator[str]:
    """Yield the literal text of `node`, if any.

    Covers the plain constant and the f-string. The f-string case matters
    because name TEMPLATES are how a single bad literal becomes many bad rows:
    ``FASHION_LIVING_STYLE_NAME_TEMPLATE`` fed straight into
    ``FashionStyle.objects.get_or_create(name=...)``.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            yield node.value
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                yield part.value


def check_python(path: Path) -> list[tuple[int, str, str]]:
    """Return (line, identifier-key, offending value) for each violation."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if not DASHES.search(source):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    found: list[tuple[int, str, str]] = []
    for key, node in _identifier_pairs(tree):
        if not is_identifier_key(key) or _suppressed(lines, node.lineno):
            continue
        found.extend(
            (node.lineno, key, value) for value in _string_literals(node) if DASHES.search(value)
        )
    return found


def _row_violations(index: int, row: dict) -> Iterator[tuple[int, str, str]]:
    """Yield violations for one fixture row: serialised natural key, then fields."""
    pk = row.get("pk")
    if isinstance(pk, list):
        for part in pk:
            if isinstance(part, str) and DASHES.search(part):
                yield index, "pk", part
    fields = row.get("fields")
    if not isinstance(fields, dict):
        return
    for key, value in fields.items():
        if isinstance(value, str) and is_identifier_key(key) and DASHES.search(value):
            yield index, key, value


def check_fixture(path: Path) -> list[tuple[int, str, str]]:
    """Identity fields and natural keys inside a Django fixture."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if not DASHES.search(raw):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    found: list[tuple[int, str, str]] = []
    for index, row in enumerate(data):
        if isinstance(row, dict):
            found.extend(_row_violations(index, row))
    return found


def main(argv: list[str]) -> int:
    errors_found = False
    for name in argv:
        path = Path(name)
        if not path.is_file():
            continue
        if path.suffix == ".json":
            for index, key, value in check_fixture(path):
                errors_found = True
                print(
                    f"{path}:row {index}: IDENT_DASH "
                    f"fixture {key!r} = {value!r} contains an em/en-dash. A name is "
                    "matched exactly by name= lookups and cannot be typed with one. "
                    "Use a hyphen."
                )
        elif path.suffix == ".py":
            for lineno, key, value in check_python(path):
                errors_found = True
                print(
                    f"{path}:{lineno}: IDENT_DASH "
                    f"{key}={value!r} contains an em/en-dash. Identifier strings are "
                    "matched exactly and typed by hand; use a hyphen, or add "
                    "`# noqa: IDENT_DASH` stating why a dash is genuinely required."
                )
    return 1 if errors_found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
