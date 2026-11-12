"""Stats, skills and threads read on one scale (data only, #5091, ADR-5091, ADR-0237).

Every surface now shows a stat, a skill or a thread at its stored value, so every
authored number that was written in the old shown unit (stored // 10) is restated in
stored units here. Behaviour is unchanged: a gate at shown thread level 3 is a gate
at 30, a stat cap of 5 is a cap of 50. Character values themselves are not touched;
they were always stored at this scale.

Restated (times ten), all authored content unless marked play state:

- ``MaturationStatCap.stat_cap`` and ``skill_cap`` (band caps);
- ``SpeciesStatBonus.value`` (species stat bonuses in CG);
- ``NPCPresetTraitLine.value`` (preset stat lines; 0396 renamed it from
  ``display_value``);
- ``ThreadPullEffect.min_thread_level``;
- ``ThreadCrossingThreshold.level``;
- ``CrossingOption.crossing_level``, plus play state ``CrossingChoice`` and
  ``PendingCrossingOffer.crossing_level``;
- ``SignatureMotifBonus.min_crossing_level``;
- ``TechniqueVariant``, ``CovenantRole``, ``CovenantRoleGiftGrant`` and
  ``VowAddedEffect.unlock_thread_level``;
- ``VowFocusPick.pick_level`` (1/2/3 become 10/20/30);
- play state: each ``CharacterDraft.draft_data`` ``stats`` and
  ``stats_post_cg_bonuses`` (an in-progress character's allocation, 1-5 to 10-50).

Columns under a unique constraint are rewritten one row at a time, highest value
first, so no row ever lands on a value another row still holds. Reverse divides by ten
(every forward value is a multiple of ten).
"""

from django.db import migrations

SCALE = 10

# (model name, field name) of every authored or play-state number restated.
_FIELDS = (
    ("MaturationStatCap", "stat_cap"),
    ("MaturationStatCap", "skill_cap"),
    ("SpeciesStatBonus", "value"),
    ("NPCPresetTraitLine", "value"),
    ("ThreadPullEffect", "min_thread_level"),
    ("ThreadCrossingThreshold", "level"),
    ("CrossingOption", "crossing_level"),
    ("CrossingChoice", "crossing_level"),
    ("PendingCrossingOffer", "crossing_level"),
    ("SignatureMotifBonus", "min_crossing_level"),
    ("TechniqueVariant", "unlock_thread_level"),
    ("CovenantRole", "unlock_thread_level"),
    ("CovenantRoleGiftGrant", "unlock_thread_level"),
    ("VowAddedEffect", "unlock_thread_level"),
    ("VowFocusPick", "pick_level"),
)

_DRAFT_KEYS = ("stats", "stats_post_cg_bonuses")


def _rescale_field(model, field, *, up):
    """Multiply (up) or divide ``field`` by SCALE on every row that holds a value.

    Ordered so a unique constraint never sees two rows on one value mid-way: going up,
    the highest value moves first; going down, the lowest.
    """
    order = f"-{field}" if up else field
    rows = (
        model.objects.exclude(**{f"{field}__isnull": True})
        .exclude(**{field: 0})
        .order_by(order)
        .values_list("pk", field)
    )
    for pk, value in list(rows):
        new = value * SCALE if up else value // SCALE
        model.objects.filter(pk=pk).update(**{field: new})


def _rescale_drafts(apps, *, up):
    CharacterDraft = apps.get_model("arxii", "CharacterDraft")
    for pk, data in CharacterDraft.objects.values_list("pk", "draft_data").iterator():
        if not isinstance(data, dict):
            continue
        changed = False
        for key in _DRAFT_KEYS:
            values = data.get(key)
            if not isinstance(values, dict) or not values:
                continue
            data[key] = {
                name: (value * SCALE if up else value // SCALE)
                if isinstance(value, int) and not isinstance(value, bool)
                else value
                for name, value in values.items()
            }
            changed = True
        if changed:
            CharacterDraft.objects.filter(pk=pk).update(draft_data=data)


def _rescale(apps, *, up):
    for model_name, field in _FIELDS:
        _rescale_field(apps.get_model("arxii", model_name), field, up=up)
    _rescale_drafts(apps, up=up)


def forwards(apps, schema_editor):
    _rescale(apps, up=True)


def backwards(apps, schema_editor):
    _rescale(apps, up=False)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0396_one_scale_schema"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
