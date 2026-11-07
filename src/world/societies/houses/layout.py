"""A realm's layout, typed once (#4983 slice 2, #4986).

The owner draws each kingdom's outline on the region map; this module reads a few lines
of text that say how the land beneath is to be split, and plants and partitions the
ladder from them. The grammar is one entry per line, fields separated by ``|``, children
of a kingdom indented by two spaces::

    realm | counties 2-6 | baronies 1-4 | capital x1.5
    kingdom Umbros | seat Umbros | duchies 5 | capital x2 | names Umbran
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
    names: str | None = None
    duchies: Range | None = None
    capital: float | None = None
    sworn: str | None = None
    chartered: list[str] = field(default_factory=list)
    claims: list[tuple[str, str]] = field(default_factory=list)
    lore: str = ""
    claimable: bool | None = None
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
WORD_NAMES = "names"
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


def _word_names(line_no: int, target: Target, _word: str, value: str, _rest: list[str]) -> None:
    if not isinstance(target, KingdomLine) or not value:
        raise LayoutError(
            line_no,
            "names picks a kingdom's place-name culture: names <culture>, on a kingdom line",
        )
    target.names = value


def _word_claimable(line_no: int, target: Target, word: str, _value: str, _rest: list[str]) -> None:
    if isinstance(target, Defaults):
        raise LayoutError(line_no, f"{word} belongs on a kingdom or duchy line")
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
    WORD_NAMES: _word_names,
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


# ---------------------------------------------------------------------------
# The walk: plan a kingdom's children from its line, then write them (or not)
# ---------------------------------------------------------------------------

import zlib  # noqa: E402 - the grammar above stands on its own; the walk's imports follow

from django.core.exceptions import ValidationError  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402

from world.areas.models import Area  # noqa: E402
from world.areas.worldmap.constants import Terrain  # noqa: E402
from world.areas.worldmap.models import TerrainPip  # noqa: E402
from world.areas.worldmap.services import (  # noqa: E402
    WorldMapServiceError,
    footprint_of,
    set_footprint,
)
from world.character_sheets.models import CharacterSheet  # noqa: E402
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart  # noqa: E402
from world.realms.models import Realm  # noqa: E402
from world.societies.houses.almanach import (  # noqa: E402
    charter_fief,
    name_rung,
    plant_rung,
    record_claim,
    rung_area_for_title,
    set_pledged_liege,
)
from world.societies.houses.models import Domain, Title  # noqa: E402
from world.societies.houses.partition import (  # noqa: E402
    Pip,
    capital_seed,
    farthest_pips,
    partition,
)
from world.societies.houses.services import HousesServiceError  # noqa: E402

CROWN_TIERS = (TitleTier.KINGDOM, TitleTier.EMPIRE)
COUNTY_POPULATION_PER_PIP = 120
PROSPERITY_CAPITAL = 65
PROSPERITY_CHILD = 45
PLACEHOLDER = "PLACEHOLDER:"


class LayoutRefused(HousesServiceError):
    """The whole layout is refused before anything is planned (no place-name bank)."""


@dataclass
class KingdomReport:
    name: str
    line_no: int
    planted: dict[str, int] = field(default_factory=dict)
    duchies: list[dict] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    charters: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    def as_data(self) -> dict:
        return {
            "name": self.name,
            "line_no": self.line_no,
            "planted": dict(self.planted),
            "duchies": list(self.duchies),
            "names": list(self.names),
            "charters": list(self.charters),
            "claims": list(self.claims),
            "refusals": list(self.refusals),
        }


@dataclass
class LayoutReport:
    kingdoms: list[KingdomReport] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    wrote: bool = False

    def as_data(self) -> dict:
        return {
            "kingdoms": [k.as_data() for k in self.kingdoms],
            "refusals": list(self.refusals),
            "wrote": self.wrote,
        }


@dataclass
class _Rung:
    """One rung the walk will plant or reuse (the crown's own chain members)."""

    tier: str
    name: str
    pips: set[Pip]
    parent: _Rung | None
    capital: bool = False
    existing: Title | None = None  # the crown a seated line builds on
    chain: bool = False  # the parent's own chain member (plant_rung made it with the parent)
    preexisting: bool = False  # on the crown's own chain: no new title row
    lore: str = ""
    claimable: bool | None = None
    sworn: str | None = None
    chartered: list[str] = field(default_factory=list)
    claims: list[tuple[str, str]] = field(default_factory=list)
    line_no: int = 0
    title: Title | None = None
    children: list[_Rung] = field(default_factory=list)


class _Names:
    """The realm's place-name bank, drawn without replacement in a stable order."""

    def __init__(self, realm: Realm, seed: int, reserved: set[str]) -> None:
        cultures = NameCulture.objects.filter(realm=realm)
        entries = list(
            NameCultureEntry.objects.filter(culture__in=cultures, part=NamePart.PLACE).order_by(
                "-weight", "value"
            )
        )
        if not entries:
            msg = f"realm {realm.pk} has no PLACE names"
            raise LayoutRefused(
                msg,
                user_message=(
                    f"{realm.name} has no place-name bank; add Place names to its culture first."
                ),
            )
        # Title.name is unique across every realm when set, so the whole ladder is taken
        taken = set(Title.objects.exclude(name="").values_list("name", flat=True)) | reserved
        values = [(e.weight, e.value) for e in entries if e.value not in taken]
        # heaviest first; a stable per-run shuffle only among equal weights
        values.sort(key=lambda wv: (-wv[0], zlib.crc32(f"{seed}:{wv[1]}".encode())))
        self._pool = [v for _, v in values]
        self.drawn: list[str] = []

    def draw(self) -> str:
        if not self._pool:
            return ""
        value = self._pool.pop(0)
        self.drawn.append(value)
        return value


def _pick(rng_seed: int, salt: str, span: Range) -> int:
    if span.lo == span.hi:
        return span.lo
    return span.lo + zlib.crc32(f"{rng_seed}:{salt}".encode()) % (span.hi - span.lo + 1)


def _land_pips(pips: set[Pip]) -> set[Pip]:
    """The land among ``pips``, read from the terrain inside their bounding box."""
    if not pips:
        return set()
    xs = [x for x, _ in pips]
    ys = [y for _, y in pips]
    rows = TerrainPip.objects.filter(
        x__gte=min(xs), x__lte=max(xs), y__gte=min(ys), y__lte=max(ys)
    ).values_list("x", "y", "terrain")
    water = (Terrain.WATER, Terrain.LAKE)
    return {(x, y) for x, y, terrain in rows if (x, y) in pips and terrain not in water}


def _chain_member(crown: Title, tier: str) -> Title | None:
    return Title.objects.filter(seat_domain_id=crown.seat_domain_id, tier=tier).first()


def _explicit_names(layout: Layout) -> list[str]:
    """Every name the layout itself gives: dormant crowns, duchy lines, seats."""
    names: list[str] = []
    for kingdom in layout.kingdoms:
        if kingdom.station != TitleStation.SEATED and kingdom.name:
            names.append(kingdom.name)
        if kingdom.seat:
            names.append(kingdom.seat)
        names.extend(child.name for child in kingdom.children if child.name)
    return names


class _Walk:
    def __init__(self, realm: Realm, layout: Layout, *, write: bool, seed: int) -> None:
        self.realm = realm
        self.layout = layout
        self.write = write
        self.seed = seed
        self.explicit_names = _explicit_names(layout)
        self.names = _Names(realm, seed, set(self.explicit_names))
        self.report = LayoutReport(wrote=write)
        self.by_name: dict[str, _Rung] = {}
        self.claimed_names: set[str] = set()
        self._names_before: list[str] = []

    # -- planning -------------------------------------------------------------------

    def run(self) -> LayoutReport:
        for line in self.layout.kingdoms:
            report = KingdomReport(name=line.name, line_no=line.line_no)
            self.report.kingdoms.append(report)
            try:
                root = self._plan_kingdom(line)
            except LayoutError as exc:
                report.refusals.append(str(exc))
                self.report.refusals.append(str(exc))
                continue
            self._count(root, report)
            if self.write:
                self._write_kingdom(root, report)
            else:
                self._report_links(root, report)
        return self.report

    def _drawn_crown(self, line: KingdomLine) -> tuple[Title, set[Pip], set[Pip]]:
        """A seated kingdom line's rung, its chain duchy, its footprint and the land in
        it, or the line's refusal."""
        crown = Title.objects.filter(
            realm=self.realm, tier=TitleTier.KINGDOM, name=line.name
        ).first()
        if crown is None:
            raise LayoutError(line.line_no, f"no kingdom named {line.name} on the ladder")
        area = rung_area_for_title(crown)
        chain_duchy = _chain_member(crown, TitleTier.DUCHY)
        if chain_duchy is None:
            raise LayoutError(line.line_no, f"{line.name} has no seat chain to build on")
        beneath = Area.objects.filter(parent=area).exclude(pk=rung_area_for_title(chain_duchy).pk)
        if beneath.exists():
            raise LayoutError(line.line_no, f"{line.name} already has rungs beneath it")
        pips = footprint_of(area)
        if not pips:
            raise LayoutError(line.line_no, f"{line.name} has no land drawn yet")
        land = _land_pips(pips)
        if not land:
            raise LayoutError(line.line_no, f"no land inside {line.name}'s outline")
        return crown, pips, land

    def _plan_kingdom(self, line: KingdomLine) -> _Rung:
        if line.station != TitleStation.SEATED:
            return self._plan_dormant_crown(line)
        crown, pips, land = self._drawn_crown(line)
        root = _Rung(tier=TitleTier.KINGDOM, name=line.name, pips=pips, parent=None, existing=crown)
        self._apply_words(root, line)
        if line.seat:
            self._claim_name(line.seat, line.line_no)
        defaults = self.layout.defaults
        capital_w = line.capital or defaults.capital
        wanted = line.duchies or defaults.duchies or Range(2, 4)
        count = max(_pick(self.seed, f"{line.line_no}:duchies", wanted), len(line.children) + 1)
        seat_hint = self._seat_pip(crown, pips)
        regions = partition(
            pips, land, count, [capital_w, *([1.0] * (count - 1))], seat_hint, self.seed
        )
        if len(regions) < len(line.children) + 1:
            raise LayoutError(line.line_no, f"{line.name} has too little land for its duchies")
        children = list(line.children)
        for index, region in enumerate(regions):
            capital = index == 0
            child_line = children.pop(0) if (not capital and children) else None
            if child_line is not None and child_line.name:
                self._claim_name(child_line.name, child_line.line_no)
            duchy = _Rung(
                tier=TitleTier.DUCHY,
                name=(child_line.name if child_line and child_line.name else self.names.draw()),
                pips=region,
                parent=root,
                capital=capital,
                chain=capital,
                preexisting=capital,
                line_no=child_line.line_no if child_line else line.line_no,
            )
            if child_line is not None:
                self._apply_words(duchy, child_line)
            root.children.append(duchy)
            self._remember(duchy)
            self._plan_counties(duchy, child_line, land, seat_hint if capital else None, line)
        return root

    def _plan_counties(
        self,
        duchy: _Rung,
        child_line: ChildLine | None,
        land: set[Pip],
        seat_hint: Pip | None,
        line: KingdomLine,
    ) -> None:
        defaults = self.layout.defaults
        span = (child_line.counties if child_line else None) or defaults.counties
        count = _pick(self.seed, f"{duchy.line_no}:{duchy.name}:counties", span)
        capital_w = line.capital or defaults.capital
        duchy_land = duchy.pips & land
        regions = partition(
            duchy.pips, duchy_land, count, [capital_w, *([1.0] * (count - 1))], seat_hint, self.seed
        )
        baronies = _pick(
            self.seed,
            f"{duchy.line_no}:{duchy.name}:baronies",
            (child_line.baronies if child_line else None) or defaults.baronies,
        )
        for index, region in enumerate(regions):
            capital = index == 0
            county = _Rung(
                tier=TitleTier.COUNTY,
                name=(
                    line.seat if (capital and duchy.capital and line.seat) else self.names.draw()
                ),
                pips=region,
                parent=duchy,
                capital=capital and duchy.capital,
                chain=capital,
                preexisting=capital and duchy.preexisting,
                line_no=duchy.line_no,
            )
            duchy.children.append(county)
            self._remember(county)
            self._plan_baronies(county, region & land, seat_hint if capital else None, baronies)

    def _plan_baronies(
        self, county: _Rung, land: set[Pip], seat_hint: Pip | None, count: int
    ) -> None:
        seat = capital_seed(county.pips, land, seat_hint)
        if seat is None:
            return
        # the seat barony stays unnamed: Domain.name is unique, and `seat` named the county
        county.children.append(
            _Rung(
                tier=TitleTier.BARONY,
                name="",
                pips={seat},
                parent=county,
                capital=county.capital,
                chain=True,
                preexisting=county.preexisting,
            )
        )
        for pip in farthest_pips(land, seat, max(0, count - 1)):
            county.children.append(_Rung(tier=TitleTier.BARONY, name="", pips={pip}, parent=county))

    def _plan_dormant_crown(self, line: KingdomLine) -> _Rung:
        if line.name and Title.objects.filter(name=line.name).exists():
            raise LayoutError(line.line_no, f"{line.name} is already on the ladder")
        self._claim_name(line.name, line.line_no)
        root = _Rung(
            tier=TitleTier.KINGDOM, name=line.name, pips=set(), parent=None, line_no=line.line_no
        )
        root.lore = line.lore
        self._apply_words(root, line)
        for child_line in line.children:
            self._claim_name(child_line.name, child_line.line_no)
            duchy = _Rung(
                tier=TitleTier.DUCHY,
                name=child_line.name or self.names.draw(),
                pips=set(),
                parent=root,
                line_no=child_line.line_no,
            )
            self._apply_words(duchy, child_line)
            root.children.append(duchy)
            self._remember(duchy)
            # a dormant crown's own duchies are what its charter holds
            root.chartered.append(duchy.name or f"line {child_line.line_no}")
        self._remember(root)
        return root

    def _claim_name(self, name: str, line_no: int) -> None:
        """A name the layout gives must be new on every ladder and new in this layout."""
        if not name:
            return
        if name in self.claimed_names:
            raise LayoutError(line_no, f"{name} is named twice in this layout")
        if Title.objects.filter(name=name).exists():
            raise LayoutError(line_no, f"{name} is already a title")
        self.claimed_names.add(name)

    def _apply_words(self, rung: _Rung, line: KingdomLine | ChildLine) -> None:
        rung.lore = line.lore
        rung.sworn = line.sworn
        rung.chartered = list(line.chartered)
        rung.claims = list(line.claims)
        rung.line_no = line.line_no
        rung.claimable = line.claimable
        if rung.sworn and self._crown_named(rung.sworn) is None:
            raise LayoutError(line.line_no, f"no crown named {rung.sworn} to swear to")
        for fief_name in rung.chartered:
            if (
                fief_name not in self.explicit_names
                and not Title.objects.filter(name=fief_name).exists()
            ):
                raise LayoutError(line.line_no, f"no rung named {fief_name} to charter")
        for who, _basis in rung.claims:
            if self._sheet_named(who) is None:
                raise LayoutError(line.line_no, f"no character named {who} to claim it")

    def _remember(self, rung: _Rung) -> None:
        if rung.name:
            self.by_name[rung.name] = rung

    def _seat_pip(self, crown: Title, pips: set[Pip]) -> Pip | None:
        barony = _chain_member(crown, TitleTier.BARONY)
        if barony is None:
            return None
        seat_pips = footprint_of(rung_area_for_title(barony)) & pips
        return min(seat_pips) if seat_pips else None

    def _crown_named(self, name: str) -> Title | None:
        return Title.objects.filter(name=name, tier__in=CROWN_TIERS).order_by("pk").first()

    @staticmethod
    def _sheet_named(name: str) -> CharacterSheet | None:
        return CharacterSheet.objects.filter(character__db_key__iexact=name).first()

    def _count(self, root: _Rung, report: KingdomReport) -> None:
        def walk(rung: _Rung) -> None:
            if rung.existing is None and not rung.preexisting:
                report.planted[rung.tier] = report.planted.get(rung.tier, 0) + 1
            for child in rung.children:
                walk(child)

        walk(root)
        for duchy in root.children:
            report.duchies.append(
                {"name": duchy.name, "pips": len(duchy.pips), "capital": duchy.capital}
            )
        report.names = list(self.names.drawn[len(self._names_before) :])
        self._names_before = list(self.names.drawn)

    def _report_links(self, root: _Rung, report: KingdomReport) -> None:
        def walk(rung: _Rung) -> None:
            report.charters.extend(f"{rung.name or rung.tier} charters {f}" for f in rung.chartered)
            report.claims.extend(f"{who} claims {rung.name or rung.tier}" for who, _ in rung.claims)
            for child in rung.children:
                walk(child)

        walk(root)

    # -- writing --------------------------------------------------------------------

    def _write_kingdom(self, root: _Rung, report: KingdomReport) -> None:
        try:
            with transaction.atomic():
                self._write_rung(root, report)
                self._write_links(root, report)
        except LayoutError as exc:
            report.refusals.append(str(exc))
            self.report.refusals.append(str(exc))
        except (HousesServiceError, WorldMapServiceError) as exc:
            message = f"line {root.line_no}: {exc.user_message}"
            report.refusals.append(message)
            self.report.refusals.append(message)
        except (IntegrityError, ValidationError) as exc:
            message = f"line {root.line_no}: the database refused a row ({exc})"
            report.refusals.append(message)
            self.report.refusals.append(message)

    def _write_rung(self, rung: _Rung, report: KingdomReport) -> None:
        parent_title = rung.parent.title if rung.parent is not None else None
        if rung.existing is not None:
            rung.title = rung.existing
        elif rung.chain:
            if parent_title is None:
                raise LayoutError(rung.line_no, f"a {rung.tier} chain member with no parent")
            member = _chain_member(parent_title, rung.tier)
            if member is None:
                raise LayoutError(
                    rung.line_no, f"{parent_title.name or rung.tier} has no seat chain"
                )
            rung.title = member
            if rung.name and rung.title.name != rung.name:
                name_rung(rung.title, rung.name)
        else:
            rung.title = plant_rung(
                realm=self.realm,
                tier=rung.tier,
                name=rung.name,
                parent_title=parent_title,
                station=self._station_for(rung),
            )
        if rung.pips and rung.parent is not None:
            set_footprint(area=rung_area_for_title(rung.title), add=sorted(rung.pips))
        for child in rung.children:
            self._write_rung(child, report)
        self._write_figures(rung)
        self._write_claimable(rung)

    def _write_claimable(self, rung: _Rung) -> None:
        """A duchy this walk plants is a CG slot only when its line says `claimable`; a
        county or barony keeps plant_rung's default; a dormant chain is never claimable."""
        if rung.title is None or rung.title.tier in CROWN_TIERS:
            return
        if self._station_for(rung) != TitleStation.SEATED:
            return
        if rung.tier == TitleTier.DUCHY and not rung.chain:
            wanted = rung.claimable is True
        elif rung.claimable is not None:
            wanted = rung.claimable
        else:
            return
        if rung.title.is_claimable != wanted:
            rung.title.is_claimable = wanted
            rung.title.save(update_fields=["is_claimable"])

    def _station_for(self, rung: _Rung) -> str:
        top = rung
        while top.parent is not None:
            top = top.parent
        line = next((k for k in self.layout.kingdoms if k.line_no == top.line_no), None)
        return line.station if line is not None else TitleStation.SEATED

    def _write_figures(self, rung: _Rung) -> None:
        if rung.title is None:
            return
        domain = Domain.objects.filter(pk=rung_area_for_title(rung.title).pk).first()
        if domain is None:
            return
        if rung.tier == TitleTier.COUNTY:
            domain.population = COUNTY_POPULATION_PER_PIP * len(rung.pips)
        elif rung.children and rung.tier != TitleTier.BARONY:
            domain.population = sum(
                Domain.objects.get(pk=rung_area_for_title(c.title).pk).population
                for c in rung.children
                if c.title is not None and c.tier != TitleTier.BARONY
            )
        if rung.parent is not None and rung.tier != TitleTier.BARONY:
            domain.prosperity = PROSPERITY_CAPITAL if rung.capital else PROSPERITY_CHILD
        if rung.lore:
            domain.description = rung.lore
        elif rung.parent is not None or rung.existing is None:
            parent = rung.parent.name if rung.parent is not None else self.realm.name
            what = rung.name or f"An undefined {rung.tier}"
            domain.description = f"{PLACEHOLDER} {what} of {parent}."
        domain.save(update_fields=["population", "prosperity", "description"])

    def _write_links(self, root: _Rung, report: KingdomReport) -> None:
        def walk(rung: _Rung) -> None:
            if rung.title is None:  # a rung the write pass never reached
                return
            if rung.sworn:
                crown = self._crown_named(rung.sworn)
                if crown is None:
                    raise LayoutError(rung.line_no, f"no crown named {rung.sworn} to swear to")
                set_pledged_liege(rung.title, crown)
            for fief_name in rung.chartered:
                fief = self._title_named(fief_name)
                if fief is None:
                    raise LayoutError(rung.line_no, f"no rung named {fief_name} to charter")
                charter_fief(
                    title=rung.title, fief=fief, basis=f"By the layout, line {rung.line_no}"
                )
                report.charters.append(f"{rung.name or rung.tier} charters {fief.name}")
            for who, basis in rung.claims:
                sheet = self._sheet_named(who)
                if sheet is None:
                    raise LayoutError(rung.line_no, f"no character named {who} to claim it")
                record_claim(title=rung.title, claimant=sheet, basis=basis)
                report.claims.append(f"{who} claims {rung.name or rung.tier}")
            for child in rung.children:
                walk(child)

        walk(root)

    def _title_named(self, name: str) -> Title | None:
        planned = self.by_name.get(name)
        if planned is not None and planned.title is not None:
            return planned.title
        return Title.objects.filter(realm=self.realm, name=name).order_by("pk").first()


def _seed_for(realm: Realm, layout: Layout) -> int:
    text = "\n".join(f"{k.line_no}:{k.name}:{k.station}:{len(k.children)}" for k in layout.kingdoms)
    return zlib.crc32(text.encode()) ^ realm.pk


def preview_layout(realm: Realm, layout: Layout) -> LayoutReport:
    """The walk without its writes: what ``lay_out_realm`` would plant, and why not."""
    return _Walk(realm, layout, write=False, seed=_seed_for(realm, layout)).run()


def lay_out_realm(realm: Realm, layout: Layout) -> LayoutReport:
    """Plant and partition every kingdom line, one transaction per kingdom; a kingdom
    that is refused rolls back alone and says why in the report."""
    return _Walk(realm, layout, write=True, seed=_seed_for(realm, layout)).run()
