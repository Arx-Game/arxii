"""A realm's layout, typed once (#4983 slice 2, #4986).

The owner draws each kingdom's outline on the region map; this module reads a few lines
of text that say how the land beneath is to be split, and plants and partitions the
ladder from them. The grammar is one entry per line, fields separated by ``|``, children
of a kingdom indented by two spaces::

    realm | counties 2-6 | baronies 1-4 | capital x1.5
    kingdom Umbros | seat Umbros | duchies 5 | capital x2
    kingdom East Cinderus | titular | lore The Daeva remnant ...
      duchy Ashfall | counties 3
      duchy Embermarch | sworn Cinderus
    kingdom | potential

``parse_layout`` turns the text into a ``Layout`` tree or raises a ``LayoutError`` that
names the line. The walk that plants it (``preview_layout``/``lay_out_realm``) lives
beside it in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from world.societies.houses.constants import TitleStation, TitleTier


class LayoutError(ValueError):
    """A line of the layout the parser or the walk cannot use; ``str()`` names the line."""

    def __init__(self, line_no: int, message: str) -> None:
        self.line_no = line_no
        self.message = message
        super().__init__(f"line {line_no}: {message}")


@dataclass(frozen=True)
class Range:
    """An inclusive count range; ``"3"`` is ``Range(3, 3)``."""

    lo: int
    hi: int


@dataclass
class Defaults:
    """The ``realm`` line: what every kingdom uses unless its own line says otherwise."""

    duchies: Range | None = None
    counties: Range = Range(2, 4)
    baronies: Range = Range(1, 2)
    capital: float = 1.5


@dataclass
class ChildLine:
    """A ``duchy`` line beneath a kingdom."""

    tier: str
    name: str
    line_no: int
    counties: Range | None = None
    baronies: Range | None = None
    sworn: str | None = None
    chartered: list[str] = field(default_factory=list)
    claims: list[tuple[str, str]] = field(default_factory=list)
    claimable: bool | None = None
    lore: str = ""


@dataclass
class KingdomLine:
    """A ``kingdom`` line: a drawn crown to split, or a titular or potential one to plant."""

    name: str
    line_no: int
    station: str = TitleStation.SEATED
    seat: str | None = None
    duchies: Range | None = None
    capital: float | None = None
    sworn: str | None = None
    chartered: list[str] = field(default_factory=list)
    claims: list[tuple[str, str]] = field(default_factory=list)
    lore: str = ""
    children: list[ChildLine] = field(default_factory=list)


@dataclass
class Layout:
    defaults: Defaults
    kingdoms: list[KingdomLine]


_RANGE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")
KIND_REALM = "realm"
KIND_KINGDOM = "kingdom"
KIND_DUCHY = "duchy"
WORD_DUCHIES = "duchies"
WORD_COUNTIES = "counties"
WORD_BARONIES = "baronies"
WORD_CAPITAL = "capital"
WORD_CLAIMABLE = "claimable"
WORD_BY = "by"
_COUNT_WORDS = (WORD_DUCHIES, WORD_COUNTIES, WORD_BARONIES)
_STATION_WORDS = {"titular": TitleStation.TITULAR, "potential": TitleStation.POTENTIAL}


def _parse_range(line_no: int, word: str, text: str) -> Range:
    match = _RANGE.match(text.strip())
    if not match:
        raise LayoutError(line_no, f"{word} wants a count like 3 or 2-5, not {text!r}")
    lo = int(match.group(1))
    hi = int(match.group(2)) if match.group(2) else lo
    if lo < 1 or hi < lo:
        raise LayoutError(line_no, f"{word} {text.strip()} is not a range from 1 up")
    return Range(lo, hi)


def _parse_capital(line_no: int, text: str) -> float:
    raw = text.strip()
    if not raw.startswith("x"):
        raise LayoutError(line_no, f"capital wants a weight like x1.5, not {raw!r}")
    try:
        weight = float(raw[1:])
    except ValueError as exc:
        raise LayoutError(line_no, f"capital wants a weight like x1.5, not {raw!r}") from exc
    if weight <= 0:
        raise LayoutError(line_no, "capital's weight must be above zero")
    return weight


def _split_fields(raw: str) -> tuple[str, list[str]]:
    fields = [f.strip() for f in raw.strip().split("|")]
    return fields[0], fields[1:]


def _head(line_no: int, head: str) -> tuple[str, str]:
    """The first field: ``realm``, ``kingdom [name]`` or ``duchy [name]``."""
    kind, _, name = head.partition(" ")
    kind = kind.lower()
    if kind not in (KIND_REALM, KIND_KINGDOM, KIND_DUCHY):
        raise LayoutError(line_no, f"a line starts with realm, kingdom or duchy, not {kind!r}")
    return kind, name.strip()


Target = KingdomLine | ChildLine | Defaults


def _word_count(line_no: int, target: Target, word: str, value: str, _rest: list[str]) -> None:
    if word == WORD_DUCHIES and isinstance(target, ChildLine):
        raise LayoutError(line_no, "a duchy line has counties and baronies, not duchies")
    setattr(target, word, _parse_range(line_no, word, value))


def _word_capital(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    target.capital = _parse_capital(line_no, value)


def _word_station(line_no: int, target: Target, word: str, _value: str, _rest: list[str]) -> None:
    if not isinstance(target, KingdomLine):
        raise LayoutError(line_no, f"only a kingdom line may be {word}")
    target.station = _STATION_WORDS[word]


def _word_seat(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    if not isinstance(target, KingdomLine) or not value:
        raise LayoutError(line_no, "seat names a kingdom's capital seat: seat <name>")
    target.seat = value


def _word_claimable(line_no: int, target: Target, word: str, _value: str, _rest: list[str]) -> None:
    if not isinstance(target, ChildLine):
        raise LayoutError(line_no, f"{word} belongs on a duchy line")
    target.claimable = word == WORD_CLAIMABLE


def _word_sworn(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    if isinstance(target, Defaults) or not value:
        raise LayoutError(line_no, "sworn names a crown: sworn <kingdom name>")
    target.sworn = value


def _word_chartered(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    names = [n.strip() for n in value.split(",") if n.strip()]
    if isinstance(target, Defaults) or not names:
        raise LayoutError(line_no, "chartered lists rungs: chartered <name>, <name>")
    target.chartered.extend(names)


def _word_claimed(line_no: int, target: Target, _word: str, value: str, rest: list[str]) -> None:
    """``claimed by <character>``; a following ``basis <text>`` field belongs to it."""
    by, _, who = value.partition(" ")
    if isinstance(target, Defaults) or by.lower() != WORD_BY or not who.strip():
        raise LayoutError(line_no, "a claim reads: claimed by <character> | basis <text>")
    basis = ""
    if rest and rest[0].lower().startswith("basis"):
        basis = rest.pop(0)[len("basis") :].strip()
    target.claims.append((who.strip(), basis))


def _word_lore(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    if isinstance(target, Defaults):
        raise LayoutError(line_no, "lore belongs on a kingdom or duchy line")
    target.lore = value


_WORDS = {
    "duchies": _word_count,
    "counties": _word_count,
    "baronies": _word_count,
    "capital": _word_capital,
    "titular": _word_station,
    "potential": _word_station,
    "seat": _word_seat,
    "held": _word_claimable,
    "claimable": _word_claimable,
    "sworn": _word_sworn,
    "chartered": _word_chartered,
    "claimed": _word_claimed,
    "lore": _word_lore,
}
_REALM_WORDS = (*_COUNT_WORDS, WORD_CAPITAL)


def _apply_fields(line_no: int, target: Target, fields: list[str]) -> None:
    """Apply each ``|`` field to its line; ``claimed by`` may consume the next field."""
    rest = list(fields)
    while rest:
        word_text = rest.pop(0)
        if not word_text:
            continue
        word, _, value = word_text.partition(" ")
        word = word.lower()
        handler = _WORDS.get(word)
        if handler is None:
            raise LayoutError(line_no, f"unknown word {word!r}")
        if isinstance(target, Defaults) and word not in _REALM_WORDS:
            raise LayoutError(
                line_no, f"the realm line takes only counts and capital, not {word!r}"
            )
        handler(line_no, target, word, value.strip(), rest)


def parse_layout(text: str) -> Layout:
    """Read a layout; see the module docstring for the grammar."""
    defaults = Defaults()
    seen_realm = False
    kingdoms: list[KingdomLine] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw.startswith("  ")
        head, fields = _split_fields(raw)
        kind, name = _head(index, head)
        if kind == KIND_REALM:
            if indented or seen_realm:
                raise LayoutError(index, "one realm line, at the top")
            seen_realm = True
            _apply_fields(index, defaults, fields)
            continue
        if kind == KIND_DUCHY:
            if not indented or not kingdoms:
                raise LayoutError(index, "a duchy line sits two spaces under its kingdom")
            child = ChildLine(tier=TitleTier.DUCHY, name=name, line_no=index)
            _apply_fields(index, child, fields)
            kingdoms[-1].children.append(child)
            continue
        if indented:
            raise LayoutError(index, "a kingdom line starts at the margin")
        kingdom = KingdomLine(name=name, line_no=index)
        _apply_fields(index, kingdom, fields)
        if not kingdom.name and kingdom.station != TitleStation.POTENTIAL:
            raise LayoutError(index, "an unnamed kingdom line must be potential")
        if kingdom.station == TitleStation.TITULAR and not kingdom.name:
            raise LayoutError(index, "a titular kingdom needs a name")
        kingdoms.append(kingdom)
    return Layout(defaults=defaults, kingdoms=kingdoms)
