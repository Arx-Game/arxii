"""What one Save on the Soulfray Stage Builder writes, in one transaction (#4089).

Rows are classified by ``BuilderForms.table`` (re-read from the database when the
forms were built), never by anything posted; ``BaseConsequenceRowFormSet.clean``
has already refused a POST whose rows no longer line up with that table. An own
row edits its Consequence and this pool's entry; a shared row's weight or Remove
writes a child entry (``weight_override`` reweights, ``is_excluded`` drops).
Removing an own row deletes its pool entry only: the Consequence is authored
content and stays.

A row added on the page (index at or past ``len(table)``) is created with its
pool entry, its copied effects, and the effects typed into its own ``new<index>``
formset, all in the same transaction (spec story 5: one Save). A new row left
blank or ticked Remove is skipped, and so are its effects.

A shared row (one the parent pool owns) can be reweighted or dropped here, and
its text and effects edited, but it is never credited here: its own pool's
authoring owns its credit, which is also why "Mark reviewed" skips it.

Every row these forms are bound to is an identity-mapped instance the live game
reads too, and validating a ModelForm copies the posted values onto it. So the
view takes a ``CacheGuard`` over those rows before validating, and every path
that does not commit (a refusal, which also re-validates while rendering, or a
failure inside the transaction) puts them back as they were. The repo rule is
"validate before mutating" (django_notes.md); a bound ModelForm cannot validate
without mutating, so this guard is that rule's undo for the one shape that
cannot be reordered. Nothing is re-read from the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Model
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.models import ConsequencePool, ConsequencePoolEntry
from web.admin.authoring.credit import stamp_written
from web.admin.soulfray_builder.forms import BuilderForms, PoolForm, TableRow
from world.checks.models import Consequence, ConsequenceEffect
from world.conditions.models import (
    ConditionCheckModifier,
    ConditionStage,
    ConditionStageOnEntry,
)
from world.contributors.models import ContentContributor, CreditedContent
from world.magic.models import SoulfrayConfig

_CONSEQUENCE_FIELDS = ("outcome_tier", "label", "character_loss", "theater")
#: A cloned effect's own parent and credit are set fresh, never copied.
_NOT_CLONED = frozenset({"consequence", "written_by", "written_on", "reviewed_by", "reviewed_on"})

NEW_POOL_NAME_REQUIRED = (
    "Name the new pool: this save adds rows or a shared parent and the stage has no pool "
    "picked to hold them."
)


#: Every identity-mapped model this save can create a row of; a rolled-back save
#: evicts its new rows. ``ConditionCheckModifier`` is a plain ``models.Model``, so
#: it has no identity map to evict from.
_CREATED_MODELS = (
    Consequence,
    ConsequencePool,
    ConsequencePoolEntry,
    ConsequenceEffect,
    ConditionStageOnEntry,
)


@dataclass
class _RowsSaved:
    credited: list[CreditedContent] = field(default_factory=list)
    entries_changed: bool = False


class CacheGuard:
    """Puts identity-mapped rows back as they were when this POST does not commit.

    ``keep`` records a row's column values and its cached relations before
    anything changes them; ``restore`` writes those back onto the same Python
    objects, so every holder of the cached instance sees the committed state
    again. Keeping a row twice keeps the first (pre-change) state.
    """

    def __init__(self) -> None:
        self._kept: dict[int, tuple[Model, dict[str, object], dict[str, object]]] = {}
        self._cached_before: dict[type[SharedMemoryModel], set[object]] = {}

    def watch_created(self, *models: type[SharedMemoryModel]) -> None:
        """Note which pks of ``models`` the identity map holds now, so ``restore`` can
        evict the rows a rolled-back transaction created. Eviction, never a refetch."""
        for model in models:
            self._cached_before[model] = {row.pk for row in model.get_all_cached_instances()}

    def keep(self, *rows: Model | None) -> None:
        for row in rows:
            if row is None or row.pk is None or id(row) in self._kept:
                continue
            values = {
                f.attname: row.__dict__[f.attname]
                for f in row._meta.concrete_fields  # noqa: SLF001
                if f.attname in row.__dict__
            }
            self._kept[id(row)] = (row, values, dict(row._state.fields_cache))  # noqa: SLF001

    def restore(self) -> None:
        for row, values, relations in self._kept.values():
            row.__dict__.update(values)
            row._state.fields_cache = dict(relations)  # noqa: SLF001
        for model, before in self._cached_before.items():
            for row in model.get_all_cached_instances():
                if row.pk not in before:
                    model.flush_cached_instance(row, force=True)


def cache_guard_for(forms: BuilderForms) -> CacheGuard:
    """A guard over every cached row the bound forms validate onto or the save edits
    in place: the stage and its pool, the table's consequences, and the saved
    on-entry and effect rows. Take it before validating."""
    guard = CacheGuard()
    stage = forms.stage.instance
    guard.keep(stage, stage.consequence_pool, *(row.consequence for row in forms.table))
    for formset in (forms.on_entry, *forms.effects.values()):
        guard.keep(*(form.instance for form in formset.initial_forms))
    return guard


def live_new_rows(forms: BuilderForms) -> list[int]:
    """Indexes of the added rows this save creates: a label, and Remove not ticked.

    Read after ``forms.rows.is_valid()``. A blank added row is left out of
    validation by Django (an unchanged extra form), so it has no label here.
    """
    live: list[int] = []
    for index in range(len(forms.table), len(forms.rows.forms)):
        data = forms.rows.forms[index].cleaned_data
        if data.get("label") and not data.get("remove"):
            live.append(index)
    return live


def require_pool_for_new_rows(forms: BuilderForms) -> bool:
    """False (with an error on the pool form) when the save has rows or a parent to
    write and no pool to write them to: "New pool" picked with its name blanked.

    Read after ``forms.pool`` and ``forms.rows`` have validated.
    """
    data = forms.pool.cleaned_data
    if data.get("pool") is not None or (data.get("new_name") or "").strip():
        return True
    if not live_new_rows(forms) and data.get("parent") is None:
        return True
    forms.pool.add_error("new_name", NEW_POOL_NAME_REQUIRED)
    return False


def pool_switch_conflict(forms: BuilderForms) -> bool:
    """The pool or its parent changed AND an existing row was edited in the same POST."""
    pool_changed = bool({"pool", "parent"} & set(forms.pool.changed_data))
    rows_changed = any(form.has_changed() for form in forms.rows.forms[: len(forms.table)])
    return pool_changed and rows_changed


def _save_penalty(stage: ConditionStage, config: SoulfrayConfig, value: int | None) -> None:
    """``ConditionCheckModifier`` is a plain ``models.Model`` (not identity-mapped), so the
    row edited here is this query's own instance and a rollback leaves nothing cached."""
    existing = ConditionCheckModifier.objects.filter(
        stage=stage, check_type=config.resilience_check_type
    ).first()
    if value is None:
        if existing is not None:
            existing.delete()
        return
    if existing is None:
        ConditionCheckModifier.objects.create(
            stage=stage, check_type=config.resilience_check_type, modifier_value=value
        )
    elif existing.modifier_value != value:
        existing.modifier_value = value
        existing.save(update_fields=["modifier_value"])


def _save_pool(
    stage: ConditionStage, pool_form: PoolForm, guard: CacheGuard, *, needs_pool: bool
) -> tuple[ConsequencePool | None, bool]:
    data = pool_form.cleaned_data
    chosen: ConsequencePool | None = data.get("pool")
    parent: ConsequencePool | None = data.get("parent")
    if chosen is None:
        name = (data.get("new_name") or "").strip()
        if not name or not (needs_pool or parent is not None):
            return stage.consequence_pool, False
        chosen = ConsequencePool.objects.create(name=name, parent=parent)
        stage.consequence_pool = chosen
        stage.save(update_fields=["consequence_pool"])
        return chosen, True
    touched = False
    parent_id = parent.pk if parent is not None else None
    guard.keep(chosen)
    if chosen.parent_id != parent_id:
        chosen.parent = parent
        chosen.save(update_fields=["parent"])
        touched = True
    if stage.consequence_pool_id != chosen.pk:
        stage.consequence_pool = chosen
        stage.save(update_fields=["consequence_pool"])
        touched = True
    return chosen, touched


def _clone_effect(effect: ConsequenceEffect, consequence: Consequence) -> ConsequenceEffect:
    """A new effect from ``effect``'s field values. Never ``pk=None`` on an identity-mapped
    instance: that corrupts the cache."""
    values = {
        f.attname: getattr(effect, f.attname)
        for f in ConsequenceEffect._meta.concrete_fields  # noqa: SLF001
        if not f.primary_key and f.name not in _NOT_CLONED
    }
    clone = ConsequenceEffect.objects.create(consequence=consequence, **values)
    clone.crime_kinds.set(effect.crime_kinds.all())
    return clone


def _create_row(
    pool: ConsequencePool, forms: BuilderForms, index: int, data: dict[str, object]
) -> list[CreditedContent]:
    """The added row ``index``: its Consequence, pool entry, copied effects, then the
    effects typed into its own ``new<index>`` formset (the P3 contract in forms.py)."""
    consequence = Consequence.objects.create(
        outcome_tier=data["outcome_tier"],
        label=data["label"],
        weight=data["weight"],
        character_loss=data["character_loss"],
        theater=data["theater"],
    )
    ConsequencePoolEntry.objects.create(pool=pool, consequence=consequence)
    created: list[CreditedContent] = [consequence]
    source_id = data.get("copy_of")
    if source_id:
        sources = ConsequenceEffect.objects.filter(consequence_id=source_id).order_by(
            "execution_order", "pk"
        )
        created.extend(_clone_effect(effect, consequence) for effect in sources)
    typed = forms.new_effects[index]
    typed.instance = consequence
    created.extend(typed.save())
    return created


def _write_child_entry(
    pool: ConsequencePool,
    consequence: Consequence,
    entry: ConsequencePoolEntry | None,
    data: dict[str, object],
) -> None:
    """A shared row's drop or reweight, as this pool's child entry for it."""
    is_excluded = data["remove"]
    weight_override = None if is_excluded else data["weight"]
    if entry is None:
        ConsequencePoolEntry.objects.create(
            pool=pool,
            consequence=consequence,
            is_excluded=is_excluded,
            weight_override=weight_override,
        )
        return
    entry.is_excluded = is_excluded
    entry.weight_override = weight_override
    entry.save(update_fields=["is_excluded", "weight_override"])


def _update_row(
    pool: ConsequencePool,
    row: TableRow,
    data: dict[str, object],
    saved: _RowsSaved,
    guard: CacheGuard,
) -> None:
    consequence = row.consequence
    changed = [name for name in _CONSEQUENCE_FIELDS if getattr(consequence, name) != data[name]]
    entry = ConsequencePoolEntry.objects.filter(pool=pool, consequence=consequence).first()
    guard.keep(entry)
    if row.shared_from is None:
        if data["remove"]:
            entry.delete()
            saved.entries_changed = True
            return
        if entry.weight_override is None:
            if consequence.weight != data["weight"]:
                changed.append("weight")
        elif entry.weight_override != data["weight"]:
            entry.weight_override = data["weight"]
            entry.save(update_fields=["weight_override"])
            saved.entries_changed = True
    elif data["remove"] != row.dropped or data["weight"] != row.weight:
        _write_child_entry(pool, consequence, entry, data)
        saved.entries_changed = True
    if changed:
        for name in changed:
            setattr(consequence, name, data[name])
        consequence.save(update_fields=changed)
        if row.shared_from is None:
            saved.credited.append(consequence)


def _save_rows(pool: ConsequencePool | None, forms: BuilderForms, guard: CacheGuard) -> _RowsSaved:
    saved = _RowsSaved()
    if pool is None:
        return saved
    for index, row in enumerate(forms.table):
        form = forms.rows.forms[index]
        if form.has_changed():
            _update_row(pool, row, form.cleaned_data, saved, guard)
    for index in live_new_rows(forms):
        saved.credited.extend(_create_row(pool, forms, index, forms.rows.forms[index].cleaned_data))
        saved.entries_changed = True
    return saved


def save_stage(
    stage: ConditionStage,
    forms: BuilderForms,
    config: SoulfrayConfig | None,
    contributor: ContentContributor,
    *,
    guard: CacheGuard | None = None,
) -> ConditionStage:
    """Write every layer in one transaction and credit each touched CreditedContent row.

    A failure inside the transaction restores ``guard``'s rows (and the pool,
    and entry rows this save edits in place) and evicts every row the
    transaction created before it propagates, so the identity map never holds a
    value or a row the rollback took back out of the database.
    """
    guard = guard if guard is not None else cache_guard_for(forms)
    shared_ids = {row.consequence.pk for row in forms.table if row.shared_from is not None}
    guard.watch_created(*_CREATED_MODELS)
    try:
        with transaction.atomic():
            stage = forms.stage.save()
            forms.on_entry.instance = stage
            forms.on_entry.save()
            if config is not None:
                _save_penalty(stage, config, forms.penalty.cleaned_data.get("modifier_value"))
            pool, pool_touched = _save_pool(
                stage, forms.pool, guard, needs_pool=bool(live_new_rows(forms))
            )
            rows = _save_rows(pool, forms, guard)
            touched: list[CreditedContent] = [stage]
            if pool is not None and (pool_touched or rows.entries_changed or rows.credited):
                touched.append(pool)
            touched.extend(rows.credited)
            for consequence_id, effects in forms.effects.items():
                saved_effects = effects.save()
                if consequence_id not in shared_ids:
                    touched.extend(saved_effects)
            seen: set[tuple[type, int]] = set()
            for row in touched:
                key = (type(row), row.pk)
                if key not in seen:
                    seen.add(key)
                    stamp_written(row, contributor)
    except BaseException:
        guard.restore()
        raise
    return stage
