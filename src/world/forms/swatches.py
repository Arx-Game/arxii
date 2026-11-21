"""A first pass of colour values for the colour trait options (#5241).

``FormTraitOption.swatch_hex`` is what the Appearance stage draws beside a colour's
name, so a player can see which red "Rust" is beside "Copper". Staff own the values
and correct them on the option's admin page; this table is only the starting point
the owner asked for (2026-11-21: "I write a first pass"), used by the sample seed
when it creates an option on a fresh clone. Migration ``swatch_colour_fill`` wrote
the same values onto the options production already held.

Keyed by trait name, then option name. An option with no single colour (Prismatic,
Multihued, Mismatched, Mottled) is absent on purpose and keeps a blank value, which
the page draws as a striped swatch.
"""

from __future__ import annotations

DEFAULT_SWATCHES: dict[str, dict[str, str]] = {
    "hair_color": {
        "black": "#1c1a1a",
        "dark_brown": "#3b2a20",
        "brown": "#5a3d2b",
        "light_brown": "#8a6a4a",
        "auburn": "#7a3220",
        "chestnut": "#6b3a26",
        "blonde": "#d9b96a",
        "blue": "#3a6ea8",
        "platinum_blonde": "#e9e2c8",
        "strawberry_blonde": "#d99a6c",
        "yellow": "#e6cf4a",
        "red": "#a8321e",
        "violet": "#7a4ea0",
        "copper": "#b5651d",
        "orange": "#d9772b",
        "mahogany": "#4a1f1a",
        "burgundy": "#5c1a2b",
        "rust": "#8b3a1a",
        "white": "#f2f0ea",
        "silver": "#c0c4c8",
        "gray": "#8c8c8c",
        "tawny": "#a67b4b",
        "golden": "#c9a13a",
        "green": "#3f7d4a",
        "olive": "#6b6b3a",
    },
    "eye_color": {
        "brown": "#6b4423",
        "dark_brown": "#3a2414",
        "amber": "#c98a1e",
        "hazel": "#8a6f3a",
        "green": "#4a8a4f",
        "gray": "#8a949c",
        "blue": "#3f6fb0",
        "light_blue": "#8fc1e3",
        "black": "#15130f",
        "violet": "#7d57b0",
        "gold": "#d4a92a",
        "red": "#a82020",
    },
    "skin_tone": {
        "porcelain": "#f6e7dc",
        "fair": "#f1d5bf",
        "light": "#e6bf9f",
        "medium": "#c8946b",
        "olive": "#b59a63",
        "tan": "#b9834f",
        "bronze": "#a46a3c",
        "brown": "#7c4f2e",
        "dark_brown": "#56351f",
        "dark": "#452b1b",
        "deep": "#2f1d14",
        "red": "#a33a2e",
        "crimson": "#7d1622",
        "purple": "#6f4a8a",
        "dark_purple": "#3f2757",
        "ash_gray": "#9a9a96",
        "charcoal": "#46464a",
        "obsidian": "#1a181c",
    },
    "scale_color": {
        "green": "#4c8a45",
        "dark_green": "#24502b",
        "brown": "#6a4a2e",
        "gray": "#7e8480",
        "black": "#1a1c1a",
        "rust": "#8f4a26",
        "olive": "#6c6f3c",
    },
}


def default_swatch(trait_name: str, option_name: str) -> str:
    """The first-pass colour for one option, or blank when the table has none."""
    return DEFAULT_SWATCHES.get(trait_name, {}).get(option_name, "")
