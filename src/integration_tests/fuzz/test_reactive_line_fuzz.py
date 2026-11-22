"""Fuzz: the rules for an authored reactive condition line hold (#4587).

``fill_reactive_line`` and ``ConditionTemplate.clean`` are what stand between a staff member's
typo and a failed combat round, so they are fed arbitrary text. The properties are the rules
the ``fill_reactive_line`` docstring states, with every expected result built beside the
generated text from plain string joins (never by calling the code under test):

- it never raises and returns None or a str, whatever the text and names;
- a line made of literal text (each brace doubled) and known placeholders fills to the same
  pieces joined, the names put in place of the placeholders and never read again as markup;
- a line with any bad field (a name the moment does not supply, an attribute, an index, a
  conversion, a format spec, an empty or numeric field, a stray brace), or a placeholder whose
  name is blank, cannot be used, so it is None;
- a blank or whitespace-only line is None.

The validation rule comes from the placeholders table in ``docs/systems/conditions.md``
("Narration of reactive moments"): a line is refused if and only if it is not blank and it
names a placeholder its moment does not supply, or the condition lacks the effect that makes
the moment happen. A refusal for a placeholder names the placeholders the moment allows.
"""

from __future__ import annotations

import unittest

from django.core.exceptions import ValidationError
from hypothesis import given, strategies as st

from world.conditions.constants import DurationType, ReactiveMoment
from world.conditions.models import ConditionTemplate
from world.conditions.reactive_narration import fill_reactive_line

# The placeholders table in docs/systems/conditions.md, "Narration of reactive moments".
DOCUMENTED_PLACEHOLDERS: dict[ReactiveMoment, set[str]] = {
    ReactiveMoment.RETALIATION: {"bearer", "source", "attacker"},
    ReactiveMoment.GUARD: {"bearer", "source", "attacker"},
    ReactiveMoment.PROVOKE: {"bearer", "source"},
    ReactiveMoment.GRACE: {"bearer", "source"},
    ReactiveMoment.SPENT: {"bearer", "source"},
}

# The field each effect is switched on with, from the same table's "Told when" column.
EFFECT_FIELDS: dict[ReactiveMoment, dict[str, object]] = {
    ReactiveMoment.RETALIATION: {"retaliation_damage": 5},
    ReactiveMoment.GUARD: {"source_guards_bearer": True},
    ReactiveMoment.PROVOKE: {"forces_attack_on_source": True},
    ReactiveMoment.GRACE: {"prevents_knockout": True},
    ReactiveMoment.SPENT: {"default_duration_type": DurationType.UNTIL_USED},
}

KNOWN = ("bearer", "source", "attacker")
UNSUPPLIED = ("hero", "target", "Bearer", "bearer_name", "nobody", "x")

WORD_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'-;:{}"
NAME_ALPHABET = WORD_ALPHABET + " "

# A literal with no whitespace, so a line built by joining pieces with one space has no edge
# whitespace for the fill's strip to remove. It may hold braces, which the line must double.
literals = st.text(alphabet=WORD_ALPHABET, min_size=1, max_size=12)
# A presented name: not blank, no edge whitespace, may hold a space or a brace.
name_values = st.text(alphabet=NAME_ALPHABET, min_size=1, max_size=15).filter(
    lambda value: value == value.strip()
)
names_maps = st.fixed_dictionaries(dict.fromkeys(KNOWN, name_values))
# One piece of a good line: ("lit", text) or ("name", placeholder).
good_pieces = st.lists(
    st.one_of(
        st.tuples(st.just("lit"), literals),
        st.tuples(st.just("name"), st.sampled_from(KNOWN)),
    ),
    min_size=1,
    max_size=8,
)
bad_fields = st.one_of(
    st.sampled_from(UNSUPPLIED).map(lambda name: "{" + name + "}"),
    st.sampled_from(KNOWN).flatmap(
        lambda name: st.sampled_from(
            [
                "{" + name + ".__class__}",
                "{" + name + "[0]}",
                "{" + name + "!r}",
                "{" + name + "!s}",
            ]
        )
    ),
    st.sampled_from(KNOWN).flatmap(
        lambda name: st.sampled_from(
            ["{" + name + ":>10}", "{" + name + ":s}", "{" + name + ":^3}"]
        )
    ),
    st.sampled_from(["{}", "{0}", "{1}", "{ }"]),
    st.sampled_from(["{", "}"]),
)


def _line_and_expected(pieces: list[tuple[str, str]], names: dict[str, str]) -> tuple[str, str]:
    """The authored line for ``pieces`` and what filling it with ``names`` must give."""
    line_parts: list[str] = []
    filled_parts: list[str] = []
    for kind, value in pieces:
        if kind == "lit":
            line_parts.append(value.replace("{", "{{").replace("}", "}}"))
            filled_parts.append(value)
        else:
            line_parts.append("{" + value + "}")
            filled_parts.append(names[value])
    return " ".join(line_parts), " ".join(filled_parts)


class FillingALineHoldsItsContract(unittest.TestCase):
    @given(st.text(max_size=60), st.dictionaries(st.text(max_size=8), st.text(max_size=8)))
    def test_it_never_raises_and_gives_none_or_text(self, text, names) -> None:
        result = fill_reactive_line(text, names)

        self.assertTrue(result is None or isinstance(result, str))

    @given(good_pieces, names_maps)
    def test_literals_and_known_names_fill_to_the_pieces_joined(self, pieces, names) -> None:
        line, expected = _line_and_expected(pieces, names)

        self.assertEqual(fill_reactive_line(line, names), expected)

    @given(good_pieces, names_maps, bad_fields, st.integers(min_value=0, max_value=8))
    def test_any_bad_field_makes_the_line_unusable(self, pieces, names, bad, position) -> None:
        line, _expected = _line_and_expected(pieces, names)
        parts = line.split(" ")
        parts.insert(min(position, len(parts)), bad)

        self.assertIsNone(fill_reactive_line(" ".join(parts), names))

    @given(good_pieces, names_maps, st.sampled_from(KNOWN), st.text(alphabet=" \t\n", max_size=3))
    def test_a_placeholder_with_a_blank_name_makes_the_line_unusable(
        self, pieces, names, blanked, blank
    ) -> None:
        line, _expected = _line_and_expected([*pieces, ("name", blanked)], names)
        names = {**names, blanked: blank}

        self.assertIsNone(fill_reactive_line(line, names))

    @given(st.text(alphabet=" \t\n\r  ", max_size=10), names_maps)
    def test_a_blank_line_is_none(self, text, names) -> None:
        self.assertIsNone(fill_reactive_line(text, names))


moments = st.sampled_from(list(ReactiveMoment))
placeholder_words = st.sampled_from([*KNOWN, *UNSUPPLIED])
line_pieces = st.lists(
    st.one_of(
        st.tuples(st.just("lit"), literals),
        st.tuples(st.just("name"), placeholder_words),
    ),
    max_size=6,
)


def _template(moment: ReactiveMoment, line: str, *, has_effect: bool) -> ConditionTemplate:
    """An unsaved template with ``line`` for ``moment`` and, if asked, that moment's effect."""
    fields: dict[str, object] = {"default_duration_type": DurationType.ROUNDS}
    if has_effect:
        fields.update(EFFECT_FIELDS[moment])
    return ConditionTemplate(name="Property", **{f"{moment.value}_narration": line}, **fields)


class ValidatingALineHoldsItsContract(unittest.TestCase):
    @given(moments, line_pieces, st.booleans(), st.text(alphabet=" \t", max_size=3))
    def test_a_line_is_refused_exactly_when_it_cannot_be_told(
        self, moment, pieces, has_effect, padding
    ) -> None:
        line = " ".join(
            value.replace("{", "{{").replace("}", "}}") if kind == "lit" else "{" + value + "}"
            for kind, value in pieces
        )
        template = _template(moment, line + padding, has_effect=has_effect)
        allowed = DOCUMENTED_PLACEHOLDERS[moment]
        names_unsupplied = any(kind == "name" and value not in allowed for kind, value in pieces)
        blank = not line.strip()
        expected_refused = not blank and (names_unsupplied or not has_effect)

        try:
            template.clean()
        except ValidationError as error:
            problems = error.message_dict
        else:
            problems = {}

        field = f"{moment.value}_narration"
        self.assertEqual(set(problems), {field} if expected_refused else set())
        if not blank and names_unsupplied:
            message = " ".join(problems[field])
            for name in allowed:
                self.assertIn("{" + name + "}", message)
