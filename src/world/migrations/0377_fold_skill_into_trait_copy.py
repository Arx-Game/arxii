"""Fold Skill into Trait, step 2 of 3: copy (data only, #5008 slice 3, ADR-0237).

Forward: each ``Skill`` row's tooltip, display order and active flag go onto its
Trait, and so do its four credit fields wherever the Trait has none of its own. The
trait is marked as having had a ``Skill`` row, and every temporary ``<name>_fold`` FK
is set to the trait the old FK's skill sat on. Skill-type traits with no ``Skill`` row
keep the new fields' defaults (active, blank tooltip, order 0). Character drafts keep
skill ids in ``draft_data`` (``skills`` and ``magic_skills`` keyed by id, and
``anima_check_skill_id``); those move from the Skill's pk to its trait's. An id with
no Skill row is left as it is.

Reverse: one ``Skill`` row per marked trait (and per trait a fold FK or a draft points
at; after the contract step's reverse no trait is marked, so every skill-type trait
gets one), carrying the three fields and the trait's credits back (an existing row for
that trait is updated rather than duplicated), then every old FK and every draft id is
set from the trait to that Skill. Rows recreated after the contract step's reverse get
new primary keys; everything pointing at them is rewritten here, so nothing dangles.
"""

from django.db import migrations

# seed-data-ok: the reverse recreates the Skill rows the forward step folded into their
# traits (#5008); it restores rows the database held, it authors nothing new.

# (model, old field name) for every FK to Skill; the new one is "<old>_fold".
_SKILL_FKS = (
    ("Specialization", "parent_skill"),
    ("SkillPointBudget", "teaching_skill"),
    ("PathSkillSuggestion", "skill"),
    ("TrainingAllocation", "skill"),
    ("NPCPresetSkillLine", "skill"),
    ("LegendSpread", "skill"),
    ("TechniqueStyle", "skill"),
    ("Technique", "skill"),
    ("MagicActivitySkill", "skill"),
    ("RitualCheckConfig", "skill"),
    ("CombatStyle", "skill"),
    ("SkillCourseOfferDetails", "skill"),
    ("SceneActionRequest", "snapshot_skill"),
)

_SKILL_FIELDS = ("tooltip", "display_order", "is_active")
# CreditedContent's four columns, on both Skill and Trait.
_CREDIT_FIELDS = ("written_by_id", "written_on", "reviewed_by_id", "reviewed_on")
# draft_data keys holding skill ids: two {id: value} allocations and one bare id.
_DRAFT_ALLOCATION_KEYS = ("skills", "magic_skills")
_DRAFT_ID_KEY = "anima_check_skill_id"


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _draft_skill_ids(data: dict) -> set[int]:
    """Every skill id a draft's ``draft_data`` names."""
    ids: set[int] = set()
    for key in _DRAFT_ALLOCATION_KEYS:
        allocation = data.get(key)
        if isinstance(allocation, dict):
            ids.update(i for i in map(_as_int, allocation) if i is not None)
    single = _as_int(data.get(_DRAFT_ID_KEY))
    if single is not None:
        ids.add(single)
    return ids


def _remap_draft(data: dict, mapping: dict[int, int]) -> bool:
    """Rewrite a draft's skill ids through ``mapping``; True when anything changed."""
    changed = False
    for key in _DRAFT_ALLOCATION_KEYS:
        allocation = data.get(key)
        if not isinstance(allocation, dict):
            continue
        remapped = {}
        for skill_key, value in allocation.items():
            new_id = mapping.get(_as_int(skill_key))
            remapped[str(new_id) if new_id is not None else skill_key] = value
        if remapped != allocation:
            data[key] = remapped
            changed = True
    single = data.get(_DRAFT_ID_KEY)
    new_id = mapping.get(_as_int(single))
    if new_id is not None and new_id != _as_int(single):
        data[_DRAFT_ID_KEY] = str(new_id) if isinstance(single, str) else new_id
        changed = True
    return changed


def _remap_drafts(apps, mapping: dict[int, int]) -> None:
    CharacterDraft = apps.get_model("arxii", "CharacterDraft")
    drafts = [
        draft
        for draft in CharacterDraft.objects.order_by("pk")
        if isinstance(draft.draft_data, dict) and _remap_draft(draft.draft_data, mapping)
    ]
    CharacterDraft.objects.bulk_update(drafts, ["draft_data"])


def fold_skills_into_traits(apps, schema_editor):
    """Copy every Skill onto its Trait and point every temporary FK at that Trait."""
    Skill = apps.get_model("arxii", "Skill")
    Trait = apps.get_model("arxii", "Trait")

    trait_by_skill: dict[int, int] = {}
    traits = []
    for skill in Skill.objects.select_related("trait").order_by("pk"):
        trait = skill.trait
        for name in _SKILL_FIELDS:
            setattr(trait, name, getattr(skill, name))
        for name in _CREDIT_FIELDS:
            if getattr(trait, name) is None:
                setattr(trait, name, getattr(skill, name))
        trait.skill_fold_had_row = True
        traits.append(trait)
        trait_by_skill[skill.pk] = trait.pk
    Trait.objects.bulk_update(traits, [*_SKILL_FIELDS, *_CREDIT_FIELDS, "skill_fold_had_row"])

    for model_name, field_name in _SKILL_FKS:
        model = apps.get_model("arxii", model_name)
        old_column = f"{field_name}_id"
        new_field = f"{field_name}_fold"
        rows = list(model.objects.filter(**{f"{field_name}__isnull": False}).order_by("pk"))
        for row in rows:
            setattr(row, f"{new_field}_id", trait_by_skill[getattr(row, old_column)])
        model.objects.bulk_update(rows, [new_field])

    _remap_drafts(apps, trait_by_skill)


def unfold_skills_from_traits(apps, schema_editor):
    """Recreate a Skill row per marked Trait and point every old FK back at it."""
    Skill = apps.get_model("arxii", "Skill")
    Trait = apps.get_model("arxii", "Trait")

    rows_by_model = {}
    referenced: set[int] = set()
    for model_name, field_name in _SKILL_FKS:
        model = apps.get_model("arxii", model_name)
        rows = list(model.objects.filter(**{f"{field_name}_fold__isnull": False}).order_by("pk"))
        rows_by_model[(model, field_name)] = rows
        referenced.update(getattr(row, f"{field_name}_fold_id") for row in rows)
    CharacterDraft = apps.get_model("arxii", "CharacterDraft")
    draft_ids: set[int] = set()
    for data in CharacterDraft.objects.values_list("draft_data", flat=True):
        if isinstance(data, dict):
            draft_ids |= _draft_skill_ids(data)

    # The marker says which traits had a Skill row. Reversing the contract step recreates
    # it at its default, so after a full rollback no trait is marked: every skill-type
    # trait is a skill by then (decision 9 of #5008), so each gets a Skill row. A trait
    # pointed at after the fold (Enchanting picked on a casting style, say) needs one in
    # the old shape too, or its reference is lost.
    skill_by_trait: dict[int, int] = {}
    marked = Trait.objects.filter(skill_fold_had_row=True)
    if not marked.exists():
        marked = Trait.objects.filter(trait_type="skill")
    wanted = (
        marked
        | Trait.objects.filter(pk__in=referenced)
        | Trait.objects.filter(pk__in=draft_ids, trait_type="skill")
    )
    for trait in wanted.distinct().order_by("pk"):
        skill, _created = Skill.objects.update_or_create(
            trait=trait,
            defaults={name: getattr(trait, name) for name in (*_SKILL_FIELDS, *_CREDIT_FIELDS)},
        )
        skill_by_trait[trait.pk] = skill.pk

    for (model, field_name), rows in rows_by_model.items():
        for row in rows:
            trait_id = getattr(row, f"{field_name}_fold_id")
            setattr(row, f"{field_name}_id", skill_by_trait[trait_id])
        model.objects.bulk_update(rows, [field_name])

    _remap_drafts(apps, skill_by_trait)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0376_fold_skill_into_trait_expand"),
    ]

    operations = [
        migrations.RunPython(fold_skills_into_traits, unfold_skills_from_traits),
    ]
