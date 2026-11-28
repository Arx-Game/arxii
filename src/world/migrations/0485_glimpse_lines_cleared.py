"""Delete the 26 card pairings under Glimpse answers, and make the rest free (#5292).

Data only. A Glimpse answer now gives one card, free, with the answer itself
(``DistinctionOffer`` lines of the Glimpse chapter always arrive bundled). The 26 lines
below were priced choices nobody credited; the owner ruled on 2026-11-22 that the
pairings were not theirs and do not stand. Left in place each would become a free
personality card under its answer.

**Deliberate discard under ADR-0237.** The rows are authored content. Each is named by
its answer's axis and slug and its card's slug, so a line staff add later is never
touched. Counted on a copy of production of 2026-11-18: 26 lines in the chapter, all 26
listed here, none credited, no first-look pin on any. The pairs are listed in #5292 so
they can be entered again by hand. Characters already made keep their cards; a draft
holding a pick from one loses it at its next save, as with any line that goes.

Any other line of the chapter (one staff added after that count) is kept and set to
arrive bundled, which is what saving it would now do.

The reverse does nothing: the rows are gone.
"""

from django.db import migrations

#: (answer's axis, answer's slug, card's slug)
DISCARDED = (
    ("TRIGGER", "crisis", "wrathful"),
    ("TRIGGER", "deliberate", "ambitious"),
    ("TRIGGER", "deliberate", "patient"),
    ("CHOOSING", "the-bargain", "ambitious"),
    ("CHOOSING", "the-call", "highborn"),
    ("CHOOSING", "the-discovery", "old-soul"),
    ("REFLECTION", "remembered", "old-soul"),
    ("TONE", "defiance", "wrathful"),
    ("TONE", "defiance", "hubris"),
    ("TONE", "grief", "old-soul"),
    ("TONE", "hunger", "rapacious"),
    ("TONE", "hunger", "voracious"),
    ("TONE", "terror", "secretive"),
    ("CONSEQUENCE", "destruction", "nemesis"),
    ("CONSEQUENCE", "destruction", "wrathful"),
    ("CONSEQUENCE", "loss", "impoverished"),
    ("CONSEQUENCE", "loss", "old-soul"),
    ("CONSEQUENCE", "mark", "magical-scar"),
    ("CONSEQUENCE", "transformation", "giants-blood"),
    ("CONSEQUENCE", "vision", "old-soul"),
    ("CONSEQUENCE", "vision", "secretive"),
    ("WITNESS", "power-noticed", "nemesis"),
    ("WITNESS", "public", "center-of-attention"),
    ("WITNESS", "public", "highborn"),
    ("WITNESS", "secret-kept", "secretive"),
    ("WITNESS", "unwitnessed", "secretive"),
)

GLIMPSE_CHAPTER = "glimpse"


def clear_glimpse_lines(apps, schema_editor):
    DistinctionOffer = apps.get_model("arxii", "DistinctionOffer")
    lines = DistinctionOffer.objects.filter(chapter=GLIMPSE_CHAPTER)
    for axis, tag_slug, card_slug in DISCARDED:
        lines.filter(
            glimpse_tag__axis=axis,
            glimpse_tag__slug=tag_slug,
            distinction__slug=card_slug,
        ).delete()
    DistinctionOffer.objects.filter(chapter=GLIMPSE_CHAPTER).update(arrives_as="bundled")


class Migration(migrations.Migration):
    dependencies = [("arxii", "0484_affinity_skill_affinity_spend_worth_floor_percent_and_more")]

    operations = [
        migrations.RunPython(clear_glimpse_lines, migrations.RunPython.noop),
    ]
