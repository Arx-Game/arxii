"""The Scaling settings panel's reader (#5093, "Rank means level").

Every number that sets how strong a level is lives in a row: the level baselines, the level
tiers, the check scale share, the size fractions, the development cost curve, the fatigue
terms and the pool and cap lanes. ``build_scaling_settings_panel`` reads them live and lays
them out as frozen dataclasses for the dashboard panel. It writes nothing: a missing row or
config reads as a plain "not set" or "no rows yet", never an error and never a created row.

Each table is loaded once, whatever the number of levels, sizes or lanes shown: the baselines,
the size fractions and the value overrides of every lane come in one query each, and the level
strength, level term and rank ladder helpers in ``world.checks`` are handed those loaded
tables.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Model
from django.urls import reverse

from world.checks.constants import ModifierLane, ModifierSize
from world.checks.exceptions import ModifierConfigError
from world.checks.modifier_models import (
    LevelTier,
    ModifierLevelBaseline,
    ModifierSizeFraction,
    ModifierValue,
)
from world.checks.modifier_values import BaselineTable, TierTable, ValueTable, load_tier_table
from world.checks.scale_config import CheckScaleConfig
from world.checks.services import (
    DifficultyTables,
    difficulty_points,
    level_points,
)
from world.checks.slide import band_position, load_ranks
from world.fatigue.models import FatigueConfig
from world.magic.constants import TargetKind
from world.magic.models.resonance_environment import ResonanceEnvironmentConfig
from world.magic.services.threads import get_imbue_cost_multiplier
from world.progression.constants import DP_STEPS_PER_BAND
from world.progression.models import DevelopmentCostConfig
from world.progression.services.dev_cost import dp_cost_for_step
from world.traits.models import ResultChart

#: The levels a character changes path at, the columns every level table on the panel shows.
PATH_CHANGE_LEVELS: tuple[int, ...] = (1, 3, 6, 11, 16, 21, 26)

#: How many value bands the development cost table shows (0 to 9 up to 50 to 59).
DEV_COST_BAND_COUNT = 6

#: The character and NPC levels the worked example compares: (character, NPC).
EXAMPLE_PAIRS: tuple[tuple[int, int], ...] = ((5, 4), (6, 5), (11, 5))

NOT_SET = "not set"
NO_ROWS_YET = "no rows yet"


@dataclass(frozen=True)
class AdminLink:
    """A link to the admin page that edits a row."""

    label: str
    url: str


@dataclass(frozen=True)
class LevelCell:
    """One cell of a level table: the number at a level, or None when no row gives one."""

    level: int
    value: int | None
    signed: bool = False
    highlighted: bool = False

    @property
    def text(self) -> str:
        if self.value is None:
            return NOT_SET
        return f"+{self.value}" if self.signed else str(self.value)


@dataclass(frozen=True)
class StrengthRow:
    """One row of the strength table. ``edit`` is None for a row worked out from the others."""

    label: str
    cells: tuple[LevelCell, ...]
    edit: AdminLink | None


@dataclass(frozen=True)
class ExampleLine:
    """One worked comparison: a character of one level against an NPC of another.

    ``ranks_above`` is the rank difference the roll reads (``None`` when the ladder cannot be
    read). ``tier_jump_points`` is the extra tier bonus the character carries over the NPC,
    and ``at_chart_edge`` is true when the difference reaches the highest authored chart.
    """

    character_level: int
    npc_level: int
    ranks_above: Decimal | None
    tier_jump_points: int
    at_chart_edge: bool

    @property
    def text(self) -> str:
        who = f"a level {self.character_level} character"
        npc = f"a level {self.npc_level} NPC"
        if self.ranks_above is None:
            return f"{who} against {npc} cannot be worked out yet: {NOT_SET}"
        if self.at_chart_edge:
            return f"{who} is at the edge of the chart against {npc}"
        text = f"{who} stands {_ranks(self.ranks_above)} above {npc}"
        level_ranks = self.character_level - self.npc_level
        tier_ranks = self.ranks_above - level_ranks
        if self.tier_jump_points > 0 and level_ranks >= 0 and tier_ranks > 0:
            text += (
                f": {_ranks(Decimal(level_ranks))} for the level and {_ranks(tier_ranks)} "
                f"for the tier bonus of {self.tier_jump_points} points"
            )
        return text


@dataclass(frozen=True)
class WorkedExample:
    """The worked example line under the strength table."""

    lines: tuple[ExampleLine, ...]

    @property
    def text(self) -> str:
        return ". ".join(line.text[0].upper() + line.text[1:] for line in self.lines) + "."


@dataclass(frozen=True)
class SettingRow:
    """One row of the settings table."""

    name: str
    value: str
    effect: str
    edit: AdminLink


@dataclass(frozen=True)
class DevCostRow:
    """The development point cost of one step in each value band shown."""

    label: str
    costs: tuple[int, ...]


@dataclass(frozen=True)
class DevCostTable:
    """Development cost per step by value band. ``rows`` is empty when no config row exists."""

    band_labels: tuple[str, ...]
    rows: tuple[DevCostRow, ...]
    edit: AdminLink


@dataclass(frozen=True)
class PoolRow:
    """One pool or cap and its value at each path-change level."""

    label: str
    grows_with: str
    cells: tuple[LevelCell, ...]
    has_rows: bool
    empty_note: str
    edit: AdminLink


@dataclass(frozen=True)
class BuffRow:
    """A buff's points at one level (or at any level), one value per size."""

    label: str
    points: tuple[int | None, ...]


@dataclass(frozen=True)
class BuffTable:
    """What a buff adds to one kind of number, in points, for each size."""

    title: str
    unit: str
    size_names: tuple[str, ...]
    rows: tuple[BuffRow, ...]
    has_sizes: bool
    edit: AdminLink


@dataclass(frozen=True)
class ScalingSettingsPanel:
    """Everything the Scaling settings panel shows, in the order it shows it."""

    levels: tuple[int, ...]
    strength: tuple[StrengthRow, ...]
    example: WorkedExample
    settings: tuple[SettingRow, ...]
    dev_cost: DevCostTable
    pools: tuple[PoolRow, ...]
    rolls: BuffTable
    buff_tables: tuple[BuffTable, ...]


@dataclass(frozen=True)
class _PoolSpec:
    lane: str
    label: str
    grows_with: str
    empty_note: str = NO_ROWS_YET


#: Every pool, cap and rung lane (#5093): what it is and what its row's level means.
_POOL_SPECS: tuple[_PoolSpec, ...] = (
    _PoolSpec(ModifierLane.ANIMA_POOL, "Anima pool", "character level"),
    _PoolSpec(
        ModifierLane.FATIGUE_LEVEL_BONUS,
        "Fatigue level bonus",
        "combat level",
        "no rows yet, so it adds nothing",
    ),
    _PoolSpec(ModifierLane.SOUL_TETHER_SCENE_CAP, "Soul tether scene cap", "thread rung"),
    _PoolSpec(ModifierLane.HOLLOW_MAX, "Hollow maximum", "thread rung"),
    _PoolSpec(ModifierLane.OUTFIT_TRICKLE, "Outfit trickle", "thread rung"),
    _PoolSpec(ModifierLane.TECHNIQUES_PER_GIFT, "Techniques per gift", "gift depth"),
    _PoolSpec(
        ModifierLane.RESCUE_BUDGET_THREAD,
        "Rescue budget from a thread (hundredths)",
        "Sineater thread rung",
    ),
    _PoolSpec(ModifierLane.MOON_TUNING, "Moon tuning from a thread", "gift thread rung"),
    _PoolSpec(ModifierLane.FACET_EFFECT_BONUS, "Facet effect bonus", "facet thread rung"),
    _PoolSpec(ModifierLane.VOW_EFFECT_SEVERITY, "Vow effect severity", "vow thread rung"),
    _PoolSpec(ModifierLane.VOW_EFFECT_DURATION, "Vow effect duration", "vow thread rung"),
    _PoolSpec(ModifierLane.VOW_EFFECT_DAMAGE, "Vow effect damage", "vow thread rung"),
)

#: The kinds of number a buff can add to, after rolls: (lane, table title, unit).
_BUFF_SPECS: tuple[tuple[str, str, str], ...] = (
    (ModifierLane.STAT, "Stats", "stat points"),
    (ModifierLane.TO_HIT, "To-hit", "check points"),
    (ModifierLane.DAMAGE, "Damage", "damage points"),
    (ModifierLane.PARTIAL_PROTECTION, "Protection", "percentage points of protection"),
)


def _plain(number: Decimal) -> str:
    """A decimal without trailing zeros: 0.500 reads 0.5 and 100 reads 100."""
    return format(number.normalize(), "f")


def _ranks(number: Decimal) -> str:
    """A rank count in words: "1 rank", "4 ranks", "1.5 ranks"."""
    shown = _plain(number.quantize(Decimal("0.1")))
    return f"{shown} rank" if shown == "1" else f"{shown} ranks"


def _changelist(model: type[Model], label: str, query: str = "") -> AdminLink:
    meta = model._meta  # noqa: SLF001 - the admin url names are built from the model's meta
    url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
    return AdminLink(label=label, url=f"{url}?{query}" if query else url)


def _singleton_link(model: type[Model], label: str, *, exists: bool) -> AdminLink:
    """The change page of a pk 1 singleton, or its add page while no row exists."""
    meta = model._meta  # noqa: SLF001
    prefix = f"admin:{meta.app_label}_{meta.model_name}"
    if exists:
        return AdminLink(label=label, url=reverse(f"{prefix}_change", args=[1]))
    return AdminLink(label=label, url=reverse(f"{prefix}_add"))


def _baseline_link(lane: str) -> AdminLink:
    return _changelist(ModifierLevelBaseline, "Level baselines", f"lane__exact={lane}")


def _lane_tables(
    baseline_rows: list[tuple[str, int, int]],
) -> dict[str, BaselineTable]:
    """Every lane's baseline table from one query's rows (lane, level, baseline), by lane."""
    by_lane: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for lane, level, baseline in baseline_rows:
        by_lane[lane].append((level, baseline))
    return {
        lane: BaselineTable(
            lane=lane,
            levels=tuple(level for level, _ in sorted(rows)),
            baselines=tuple(baseline for _, baseline in sorted(rows)),
        )
        for lane, rows in by_lane.items()
    }


def _baseline_or_none(table: BaselineTable, level: int) -> int | None:
    try:
        return table.baseline(level)
    except ModifierConfigError:
        return None


def _width_or_none(table: BaselineTable, level: int) -> int | None:
    try:
        return table.width(level)
    except ModifierConfigError:
        return None


def _tier_jumps(tiers: TierTable, levels: tuple[int, ...]) -> tuple[LevelCell, ...]:
    """The jump on reaching each level: the bonus its level has over the one before it shown."""
    cells: list[LevelCell] = []
    previous = 0
    for position, level in enumerate(levels):
        total = tiers.bonus(level)
        jump = total - previous
        cells.append(LevelCell(level=level, value=jump, signed=position > 0, highlighted=jump > 0))
        previous = total
    return tuple(cells)


def _strength_rows(
    levels: tuple[int, ...],
    tables: DifficultyTables,
    level_share: Decimal,
    *,
    share_link: AdminLink,
) -> tuple[StrengthRow, ...]:
    baselines = tables.baselines
    jumps = _tier_jumps(tables.tiers, levels)
    has_baselines = bool(baselines.levels)

    def cells(values: list[int | None], *, mark_jumps: bool = False) -> tuple[LevelCell, ...]:
        return tuple(
            LevelCell(level=level, value=value, highlighted=mark_jumps and jump.highlighted)
            for level, value, jump in zip(levels, values, jumps, strict=True)
        )

    base = [_baseline_or_none(baselines, level) for level in levels]
    term = [level_points(level, tables, level_share) if has_baselines else None for level in levels]
    opposition = [difficulty_points(level, tables) if has_baselines else None for level in levels]
    widths = [_width_or_none(baselines, level) for level in levels]
    return (
        StrengthRow(
            "Baseline (typical total)",
            cells(base),
            _changelist(ModifierLevelBaseline, "Level baselines", "lane__exact=check"),
        ),
        StrengthRow(
            "Tier bonus (the jump on reaching this level)",
            jumps,
            _changelist(LevelTier, "Level tiers"),
        ),
        StrengthRow(
            "A character's level term (half the baseline, plus the tier bonus)",
            cells(term, mark_jumps=True),
            share_link,
        ),
        StrengthRow(
            "An NPC's opposition (baseline plus tier bonus)",
            cells(opposition, mark_jumps=True),
            None,
        ),
        StrengthRow("One level's width (the size buffs are measured against)", cells(widths), None),
    )


def _example(tables: DifficultyTables) -> WorkedExample:
    """The worked comparisons, each through the rank ladder the roll itself reads.

    A character of level L with ordinary skills and stats totals her level's strength (the
    level term and what skills supply add up to the baseline, and the tier bonus comes on top),
    so each side is ``difficulty_points``. The difference is the band positions' difference,
    the same subtraction ``resolve_standing`` makes.
    """
    try:
        ranks = load_ranks(tables.baselines, tables.tiers) if tables.baselines.levels else []
    except ModifierConfigError:
        ranks = []
    authored = ResultChart.authored_range()
    lines = []
    for character_level, npc_level in EXAMPLE_PAIRS:
        difference: Decimal | None = None
        edge = False
        if ranks:
            roller = band_position(difficulty_points(character_level, tables), ranks)
            target = band_position(difficulty_points(npc_level, tables), ranks)
            raw = roller.value - target.value
            difference = Decimal(str(raw))
            edge = authored is not None and raw >= authored[1]
        lines.append(
            ExampleLine(
                character_level=character_level,
                npc_level=npc_level,
                ranks_above=difference,
                tier_jump_points=tables.tiers.bonus(character_level)
                - tables.tiers.bonus(npc_level),
                at_chart_edge=edge,
            )
        )
    return WorkedExample(lines=tuple(lines))


def _value_tables(
    lane_baselines: dict[str, BaselineTable],
    fraction_rows: list[tuple[str, int, Decimal]],
    override_rows: list[tuple[str, int, int, int]],
) -> dict[str, ValueTable]:
    """A ``ValueTable`` for every lane from the three queries' rows."""
    fractions: dict[str, dict[int, Decimal]] = defaultdict(dict)
    for lane, size, fraction in fraction_rows:
        fractions[lane][size] = fraction
    overrides: dict[str, dict[tuple[int, int], int]] = defaultdict(dict)
    for lane, size, level, value in override_rows:
        overrides[lane][(level, size)] = value
    lanes = set(lane_baselines) | set(fractions) | set(overrides)
    return {
        lane: ValueTable(
            overrides=overrides[lane],
            fractions=fractions[lane],
            baselines=lane_baselines.get(lane, BaselineTable(lane=lane)),
        )
        for lane in lanes
    }


def _value_or_none(table: ValueTable, level: int, size: int) -> int | None:
    try:
        return table.value(level, size)
    except ModifierConfigError:
        return None


def _buff_table(  # noqa: PLR0913 - one keyword per part of the table
    values: ValueTable,
    *,
    title: str,
    unit: str,
    levels: tuple[int, ...],
    edit: AdminLink,
    collapse_equal: bool = False,
) -> BuffTable:
    sizes = list(ModifierSize)
    rows = [
        BuffRow(
            label=f"Level {level}",
            points=tuple(_value_or_none(values, level, size) for size in sizes),
        )
        for level in levels
    ]
    if collapse_equal and len({row.points for row in rows}) == 1:
        rows = [BuffRow(label="At any level", points=rows[0].points)]
    has_sizes = bool(values.fractions or values.overrides)
    return BuffTable(
        title=title,
        unit=unit,
        size_names=tuple(size.label for size in sizes),
        rows=tuple(rows),
        has_sizes=has_sizes,
        edit=edit,
    )


def _pool_rows(
    levels: tuple[int, ...], lane_baselines: dict[str, BaselineTable]
) -> tuple[PoolRow, ...]:
    rows = []
    for spec in _POOL_SPECS:
        table = lane_baselines.get(spec.lane, BaselineTable(lane=spec.lane))
        rows.append(
            PoolRow(
                label=spec.label,
                grows_with=spec.grows_with,
                cells=tuple(
                    LevelCell(level=level, value=_baseline_or_none(table, level))
                    for level in levels
                ),
                has_rows=bool(table.levels),
                empty_note=spec.empty_note,
                edit=_baseline_link(spec.lane),
            )
        )
    return tuple(rows)


def _dev_cost_table(config: DevelopmentCostConfig | None) -> DevCostTable:
    edit = _singleton_link(DevelopmentCostConfig, "Development cost", exists=config is not None)
    bands = range(DEV_COST_BAND_COUNT)
    labels = tuple(
        f"{band * DP_STEPS_PER_BAND} to {(band + 1) * DP_STEPS_PER_BAND - 1}" for band in bands
    )
    if config is None:
        return DevCostTable(band_labels=labels, rows=(), edit=edit)
    one_step = tuple(dp_cost_for_step(band * DP_STEPS_PER_BAND) for band in bands)
    multiplier = get_imbue_cost_multiplier(TargetKind.GIFT)
    rows = [DevCostRow("Cost of one step", one_step)]
    rows.append(
        DevCostRow(
            f"Gift thread step (×{multiplier})", tuple(cost * multiplier for cost in one_step)
        )
    )
    return DevCostTable(band_labels=labels, rows=tuple(rows), edit=edit)


def _settings_rows(  # noqa: PLR0913 - one argument per config row the table reports
    *,
    scale: CheckScaleConfig | None,
    tiers: tuple[tuple[int, int], ...],
    check_values: ValueTable,
    override_count: int,
    dev_config: DevelopmentCostConfig | None,
    fatigue: FatigueConfig | None,
    environment: ResonanceEnvironmentConfig | None,
) -> tuple[SettingRow, ...]:
    tier_text = (
        " · ".join(f"level {start}: +{bonus}" for start, bonus in tiers) if tiers else NO_ROWS_YET
    )
    fractions = check_values.fractions
    fraction_text = (
        " · ".join(
            f"{size.label} {_plain(fractions[size])}" for size in ModifierSize if size in fractions
        )
        or NO_ROWS_YET
    )
    if dev_config is None:
        dev_text, growth_text = NOT_SET, "each band costs more than the one before"
    else:
        dev_text = (
            f"start {dev_config.start_level} · base {dev_config.base_cost} "
            f"· growth {dev_config.growth_percent}%"
        )
        growth_text = (
            f"each band costs {_plain(Decimal(dev_config.growth_percent) / 100)} times the "
            "one before"
        )
    fatigue_text = (
        NOT_SET
        if fatigue is None
        else (
            f"stat ×{fatigue.stat_multiplier} · willpower "
            f"×{fatigue.willpower_multiplier} · well rested "
            f"{fatigue.well_rested_percent}%"
        )
    )
    backfire_text = (
        NOT_SET
        if environment is None
        else (
            f"level {environment.backfire_base_difficulty_level} · "
            f"{_plain(environment.backfire_difficulty_per_magnitude_tenths)} tenths per magnitude"
        )
    )
    return (
        SettingRow(
            "Level share",
            NOT_SET if scale is None else _plain(scale.level_share),
            "How much of a level's baseline a character's level adds to every roll. Skills "
            "and stats make up the rest.",
            _singleton_link(CheckScaleConfig, "Check scale", exists=scale is not None),
        ),
        SettingRow(
            "Tier rows",
            tier_text,
            "The path changes where power jumps, and how many points each jump adds to both "
            "sides of a check. A row at 0 changes nothing, so a jump at that level is one "
            "edit away.",
            _changelist(LevelTier, "Level tiers"),
        ),
        SettingRow(
            "Buff sizes on rolls",
            fraction_text,
            "How big each buff size is, as a share of one level's width. A Large buff at "
            "0.5 is half a rank.",
            _changelist(ModifierSizeFraction, "Size fractions", "lane__exact=check"),
        ),
        SettingRow(
            "Value overrides",
            f"{override_count} rows",
            "A hand-set number for one kind of bonus at one level and size, used in place "
            "of the share above.",
            _changelist(ModifierValue, "Modifier values"),
        ),
        SettingRow(
            "Development cost",
            dev_text,
            "What one step of a skill, stat or thread costs. Every step inside a band of "
            f"ten costs the same, and {growth_text}.",
            _singleton_link(
                DevelopmentCostConfig, "Development cost", exists=dev_config is not None
            ),
        ),
        SettingRow(
            "Fatigue",
            fatigue_text,
            "How much fatigue a character can take before tiring, from stamina and "
            "willpower, plus the per-level bonus below.",
            _singleton_link(FatigueConfig, "Fatigue", exists=fatigue is not None),
        ),
        SettingRow(
            "Backfire difficulty",
            backfire_text,
            "How hard a resonance backfire is to resist in a charged room.",
            _singleton_link(
                ResonanceEnvironmentConfig, "Resonance environment", exists=environment is not None
            ),
        ),
    )


def _tier_rows(table: TierTable) -> tuple[tuple[int, int], ...]:
    """Each tier's (start level, own bonus), from the table's running totals."""
    rows = []
    previous = 0
    for start, total in zip(table.starts, table.totals, strict=True):
        rows.append((start, total - previous))
        previous = total
    return tuple(rows)


def build_scaling_settings_panel() -> ScalingSettingsPanel:
    """Read every scaling row live and lay the panel out. Writes nothing and never raises on
    a missing row."""
    levels = PATH_CHANGE_LEVELS
    baseline_rows = list(ModifierLevelBaseline.objects.values_list("lane", "level", "baseline"))
    fraction_rows = list(ModifierSizeFraction.objects.values_list("lane", "size", "fraction"))
    override_rows = list(ModifierValue.objects.values_list("lane", "size", "level", "value"))
    lane_baselines = _lane_tables(baseline_rows)
    tiers = load_tier_table()
    tables = DifficultyTables(
        baselines=lane_baselines.get(ModifierLane.CHECK, BaselineTable(lane=ModifierLane.CHECK)),
        tiers=tiers,
    )
    value_tables = _value_tables(lane_baselines, fraction_rows, override_rows)
    empty_values = ValueTable()

    # A singleton read here never creates the row the way the game's own reader does.
    scale = CheckScaleConfig.objects.filter(pk=1).first()
    dev_config = DevelopmentCostConfig.objects.filter(pk=1).first()
    fatigue = FatigueConfig.objects.filter(pk=1).first()
    environment = ResonanceEnvironmentConfig.objects.filter(pk=1).first()
    level_share = scale.level_share if scale is not None else CheckScaleConfig().level_share
    share_link = _singleton_link(CheckScaleConfig, "Check scale", exists=scale is not None)

    check_values = value_tables.get(ModifierLane.CHECK, empty_values)
    rolls = _buff_table(
        check_values,
        title="Rolls",
        unit="check points",
        levels=levels,
        edit=_changelist(ModifierSizeFraction, "Size fractions", "lane__exact=check"),
        collapse_equal=True,
    )
    buff_tables = tuple(
        _buff_table(
            value_tables.get(lane, empty_values),
            title=title,
            unit=unit,
            levels=levels,
            edit=_changelist(ModifierSizeFraction, "Size fractions", f"lane__exact={lane}"),
        )
        for lane, title, unit in _BUFF_SPECS
    )
    return ScalingSettingsPanel(
        levels=levels,
        strength=_strength_rows(levels, tables, level_share, share_link=share_link),
        example=_example(tables),
        settings=_settings_rows(
            scale=scale,
            tiers=_tier_rows(tiers),
            check_values=check_values,
            override_count=len(override_rows),
            dev_config=dev_config,
            fatigue=fatigue,
            environment=environment,
        ),
        dev_cost=_dev_cost_table(dev_config),
        pools=_pool_rows(levels, lane_baselines),
        rolls=rolls,
        buff_tables=buff_tables,
    )
