# Data step of the #3621 expand/migrate/contract sequence (ADR-0237). Data only.
#
# 1. Every existing CharacterGoal gets an ordinal within its (default, short term)
#    horizon, in id order per character, so 0108's unique constraint can apply.
# 2. Any Profile.personality text on a sheet's true profile is carried into that
#    character's First Journal (a public JournalEntry of kind first_journal) as the answer
#    to the Archive's first question, so nothing authored is dropped when 0108 removes the
#    column. Cover-persona profiles are not sheets and are not carried: their personality
#    was a fabricated guise line, replaced by the guise's three answers.

from django.db import migrations

FIRST_QUESTION = "What should the world know of you first?"


def number_goals(apps, schema_editor):
    CharacterGoal = apps.get_model("arxii", "CharacterGoal")
    by_character: dict[int, int] = {}
    for goal in CharacterGoal.objects.order_by("character_id", "id").iterator():
        nxt = by_character.get(goal.character_id, 0) + 1
        by_character[goal.character_id] = nxt
        if goal.ordinal != nxt:
            goal.ordinal = nxt
            goal.save(update_fields=["ordinal"])


def carry_personality(apps, schema_editor):
    CharacterSheet = apps.get_model("arxii", "CharacterSheet")
    JournalEntry = apps.get_model("arxii", "JournalEntry")
    sheets = (
        CharacterSheet.objects.filter(true_profile__isnull=False)
        .exclude(true_profile__personality="")
        .select_related("true_profile")
    )
    for sheet in sheets.iterator():
        if JournalEntry.objects.filter(author=sheet, kind="first_journal").exists():
            continue
        JournalEntry.objects.create(
            author=sheet,
            title="First Journal",
            body=f"{FIRST_QUESTION}\n{sheet.true_profile.personality}",
            is_public=True,
            kind="first_journal",
        )


def noop(apps, schema_editor):
    """Reversing keeps the carried entries; 0108's reverse restores the empty column."""


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0106_actors_sheet"),
    ]

    operations = [
        migrations.RunPython(number_goals, noop),
        migrations.RunPython(carry_personality, noop),
    ]
