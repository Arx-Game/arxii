"""Models for the weather system (#1522).

``Climate`` is the regional *baseline* for the environmental exposure axes — the flat,
year-round "extent" of a region's temperature and moisture. It attaches to an ``Area``
via ``Area.climate`` and resolves most-specific-wins up the area hierarchy (mirroring
``Area.realm`` / ``get_effective_realm``), so a parent region can stay temperate while a
sub-region designates desert. A global per-month temperature shift
(``constants.MONTH_TEMPERATURE_SHIFT``) rides on top of the baseline; transient weather
(a later slice) writes decaying exposure modifiers over it.

The signed ``temperature``/``moisture`` weights decompose onto the floored exposure axes
(``world.locations.constants``): ``temperature`` > 0 → HEAT, < 0 → COLD; ``moisture`` > 0
→ WET, < 0 → DRY. The decomposition + fold-into-comfort lives in
``world.weather.services`` and ``world.locations.services.felt_exposure``.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.locations.constants import StatKey

_CODEX_SUBJECT_FK = "codex.CodexSubject"


class Climate(SharedMemoryModel):
    """An authorable regional climate: a flat temperature/moisture baseline (#1522).

    Designated on a region ``Area`` (``Area.climate``) and resolved most-specific-wins down
    the hierarchy. Its player-facing lore lives in the linked ``CodexSubject``, surfaced
    inline at point-of-use rather than siloed in the Codex app.
    """

    name = models.CharField(max_length=100, unique=True)
    codex_subject = models.ForeignKey(
        _CODEX_SUBJECT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="climates",
        help_text=(
            "Player-facing lore/description for this climate, surfaced inline at "
            "point-of-use. PLACEHOLDER prose seeded from the authored region lore."
        ),
    )
    temperature = models.IntegerField(
        default=0,
        help_text=(
            "Signed baseline temperature 'weight': positive feeds the HEAT exposure axis "
            "(tropical/desert), negative feeds COLD (arctic). 0 is temperate. The global "
            "per-month shift is added to this before it decomposes onto an axis."
        ),
    )
    moisture = models.IntegerField(
        default=0,
        help_text=(
            "Signed baseline moisture 'weight': positive feeds the WET exposure axis "
            "(tropical/coastal), negative feeds DRY (desert). 0 is moderate."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this climate can be assigned to regions.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WeatherType(SharedMemoryModel):
    """A kind of transient weather that can hold over a region (#1522).

    The *current* weather of a region (``RegionWeatherState``) is one of these. Unlike the flat
    ``Climate`` baseline, weather is transient — the roll service rewrites its decaying exposure
    modifiers over the baseline. There is **no** Arx-1-style intensity scalar: the type *is* the
    intensity (Stormy carries more WET/WIND than Drizzle via its ``exposures``). Lore lives in the
    linked ``CodexSubject``.
    """

    name = models.CharField(max_length=100, unique=True)
    codex_subject = models.ForeignKey(
        _CODEX_SUBJECT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weather_types",
        help_text="Player-facing lore for this weather. PLACEHOLDER prose.",
    )
    is_automated = models.BooleanField(
        default=True,
        help_text=(
            "True: eligible for the ambient weather roll. False: special/event weather "
            "(Eclipse, Moon Madness) triggered only by the feast-day loop, never rolled randomly."
        ),
    )
    selection_weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative weight in the weighted-random ambient roll. PLACEHOLDER.",
    )
    min_temperature = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Climate eligibility floor: only rolled where the region's effective climate "
            "temperature (baseline + seasonal shift) is >= this. Null = no floor. Keeps blizzards "
            "out of the tropics. PLACEHOLDER."
        ),
    )
    max_temperature = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Climate eligibility ceiling: only rolled where the effective climate temperature is "
            "<= this. Null = no ceiling. e.g. Snow sets a low ceiling. PLACEHOLDER."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this weather type is currently in rotation.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WeatherTypeExposure(SharedMemoryModel):
    """One exposure axis a weather type imparts to a region while active (#1522).

    ``(weather_type, stat_key) -> value``: positive = more discomfort (Stormy → +WET, +WIND;
    Snowy → +COLD, +WET). Materialized as decaying source-tagged ``LocationValueModifier`` rows
    on the region's Area by the roll service, so weather stacks with the climate baseline and is
    countered by the same fixtures. Mirrors ``buildings.StyleAffinity``. Magnitudes are a
    PLACEHOLDER author pass.
    """

    weather_type = models.ForeignKey(
        WeatherType,
        on_delete=models.CASCADE,
        related_name="exposures",
    )
    stat_key = models.CharField(max_length=20, choices=StatKey.choices)
    value = models.IntegerField(
        help_text="Exposure magnitude added while this weather holds (+ = more discomfort).",
    )

    class Meta:
        ordering = ["weather_type", "stat_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["weather_type", "stat_key"], name="unique_weather_exposure_per_axis"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weather_type.name}: {self.stat_key} {self.value:+d}"


class WeatherEmit(SharedMemoryModel):
    """An atmospheric flavour line shown while a weather type holds (#1522).

    Seeded (later slice) from the Arx-1 emit corpus. Gated by IC season and time-of-day phase
    (from ``world.game_clock``): an emit is eligible when *both* its matching season flag and its
    matching phase flag are set. ``weight`` drives weighted-random selection. Arx-1's intensity
    range is intentionally dropped. ``text`` is PLACEHOLDER until the author pass.
    """

    weather_type = models.ForeignKey(
        WeatherType,
        on_delete=models.CASCADE,
        related_name="emits",
    )
    text = models.TextField(help_text="The atmospheric line shown to the room. PLACEHOLDER.")
    gm_notes = models.TextField(blank=True, default="")
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative weight in weighted-random emit selection.",
    )
    # Season gates (IC calendar season from game_clock; AUTUMN ← Arx-1 "fall").
    in_spring = models.BooleanField(default=False)
    in_summer = models.BooleanField(default=False)
    in_autumn = models.BooleanField(default=False)
    in_winter = models.BooleanField(default=False)
    # Time-of-day gates (game_clock TimePhase).
    at_dawn = models.BooleanField(default=False)
    at_day = models.BooleanField(default=False)
    at_dusk = models.BooleanField(default=False)
    at_night = models.BooleanField(default=False)

    class Meta:
        ordering = ["weather_type", "id"]

    def __str__(self) -> str:
        return f"{self.weather_type.name} emit #{self.pk}"


class RegionWeatherState(SharedMemoryModel):
    """The current weather holding over a region (#1522).

    One row per region Area that has weather; resolved most-specific-wins down the hierarchy by
    ``services.get_effective_weather`` (like climate/realm). The roll service updates this and
    rewrites the region's decaying weather exposure modifiers. Regions without a row inherit the
    nearest ancestor's weather, or have none.
    """

    area = models.OneToOneField(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="weather_state",
    )
    weather_type = models.ForeignKey(
        WeatherType,
        on_delete=models.PROTECT,
        related_name="active_in_regions",
    )
    changed_at = models.DateTimeField(
        auto_now=True,
        help_text="Real time of the last weather roll for this region.",
    )

    class Meta:
        ordering = ["area"]

    def __str__(self) -> str:
        return f"{self.area.name}: {self.weather_type.name}"
