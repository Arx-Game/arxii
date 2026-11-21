"""Give the colour options production already holds a first-pass colour value (#5241).

The migration before this one added ``FormTraitOption.swatch_hex``, blank on every
row. The Appearance stage draws that value beside a colour's name. The owner, asked
on 2026-11-21 who supplies the values for the 62 single-colour options, chose a first
pass written here that staff then correct on the option's admin page.

This migration creates no row. It writes one column on rows the database already
holds, matched by the trait's and the option's own keys, and only where the value is
still blank, so a value staff have set is never replaced. An option the table does
not name (Prismatic, Multihued, Mismatched, Mottled, and anything authored later)
stays blank and is drawn as a striped swatch. A database with no such options is
left as it is.

The table is a frozen copy of ``world.forms.swatches.DEFAULT_SWATCHES`` as it stood
when this was written; migrations do not import application code.
"""

from django.db import migrations

SWATCHES = {
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


def fill_blank_swatches(apps, schema_editor):
    FormTraitOption = apps.get_model("arxii", "FormTraitOption")
    blank = list(
        FormTraitOption.objects.filter(trait__name__in=SWATCHES, swatch_hex="").select_related(
            "trait"
        )
    )
    changed = []
    for option in blank:
        colour = SWATCHES[option.trait.name].get(option.name)
        if colour:
            option.swatch_hex = colour
            changed.append(option)
    FormTraitOption.objects.bulk_update(changed, ["swatch_hex"])


class Migration(migrations.Migration):
    dependencies = [("arxii", "0466_feature_qualities_and_swatch_colour")]

    operations = [
        # Going back, the reverse of the migration before this one drops the column, so
        # there is nothing to undo here.
        migrations.RunPython(fill_blank_swatches, migrations.RunPython.noop),
    ]
