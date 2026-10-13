# Data only (#4329, ADR-0237 restructure). Carries description text held in Evennia's
# `desc` Attribute into ObjectDisplayData.permanent_description, the one description
# store `look` reads.
#
# Until #4329 the stock `desc` command and the two dream-room seeds wrote the Attribute,
# which nothing of ours renders. Its only reader was Evennia's stock post-move look, and
# #4329 removes that, so text still held only there would vanish from every view with
# this release. It is copied, never over a description already set, and the Attribute
# is left in place. Characters are skipped: a character's description is its sheet's,
# and a permanent_description would mask it. Evennia's install welcome on Limbo is not
# authored and is skipped too.

from django.db import migrations

STOCK_LIMBO_OPENING = "Welcome to your new |wEvennia|n-based game!"

_MARKUP = {"r": "\n", "R": "\n", "t": "\t", "T": "\t", "b": "\N{NO-BREAK SPACE}", "%": "%"}
_MARKUP["B"] = _MARKUP["b"]


def _normalize_markup(text):
    """A frozen copy of ``server.conf.mush_markup.normalize_mush_markup`` as of #4329.

    Frozen so this migration never imports live code: a rename there must not break
    every ``migrate``, and an edit there must not change what this one does on replay.
    Text staff typed into the web client's ``desc`` was never normalized at input.
    """
    out = []
    i = 0
    while i < len(text):
        if text[i] == "%" and i + 1 < len(text):
            out.append(_MARKUP.get(text[i + 1], text[i : i + 2]))
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def carry_desc_attribute_text(apps, schema_editor):
    ObjectDB = apps.get_model("objects", "ObjectDB")
    ObjectDisplayData = apps.get_model("arxii", "ObjectDisplayData")
    CharacterSheet = apps.get_model("arxii", "CharacterSheet")

    character_ids = set(CharacterSheet.objects.values_list("pk", flat=True))
    holders = ObjectDB.objects.filter(
        db_attributes__db_key="desc", db_attributes__db_category__isnull=True
    ).distinct()
    for obj in holders.iterator():
        if obj.pk in character_ids:
            continue
        attribute = obj.db_attributes.filter(db_key="desc", db_category__isnull=True).first()
        text = attribute.db_value if attribute is not None else None
        if not isinstance(text, str) or not text.strip() or text.startswith(STOCK_LIMBO_OPENING):
            continue
        display, _ = ObjectDisplayData.objects.get_or_create(object=obj)
        if display.permanent_description:
            continue
        display.permanent_description = _normalize_markup(text)
        display.save(update_fields=["permanent_description", "updated_date"])


def noop(apps, schema_editor):
    """Reversing keeps the carried text; the Attribute it came from was never removed."""


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0220_worldmap_region_pips_footprints"),
    ]

    operations = [
        migrations.RunPython(carry_desc_attribute_text, noop),
    ]
