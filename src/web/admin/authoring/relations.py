"""Related-entries pane and prose-mentions search for the row editor (#3019 Task 6).

Two independent lookups render below the row editor: a "related entries"
panel, an automatic structural walk of every FK/M2M this row points at and
every FK/M2M that points back at it, and a "mentions" search a writer
triggers on demand, scanning every credited model's prose fields for a name
this row carries.

``related_entries`` is the runtime sibling of ``tools/introspect_models.py``'s
model-map walk - that script classifies the same field kinds (forward FK/M2M,
reverse FK/M2M) but emits display strings for a markdown doc and its own
setup ``chdir``s into ``src/`` before Django is even configured. This module
runs inside a live request against a live instance and returns structured
``RelatedEntry`` rows instead, so the two are deliberately kept separate
rather than merged into one.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from core.app_domains import credited_content_models, domain_of
from core_management.prose_fields import prose_fields_for
from world.contributors.models import CreditedContent

#: Total RelatedEntry rows related_entries() ever returns, across every
#: forward and reverse relation combined - not a per-relation share. A single
#: flat cap ("keep simple" per the Task 6 brief) rather than dividing the
#: budget field-by-field: this panel is a writer eyeballing a handful of
#: neighbors, not a systematic audit, so an even split across relations
#: (some of which may have zero rows) isn't worth the extra bookkeeping.
_DEFAULT_RELATED_CAP = 50

_DEFAULT_MENTIONS_CAP = 200


@dataclass
class RelatedEntry:
    """One neighboring row surfaced by `related_entries` or `prose_mentions`."""

    label: str  # display name of the neighbor row (str(instance))
    model_label: str
    model_name: str
    pk: int
    relation: str  # the field/accessor name it hangs off
    direction: str  # "forward" | "reverse" | "mention"
    credited: bool | None  # None when the neighbor model is not CreditedContent
    reviewed: bool | None


def _entry(value: object, *, relation: str, direction: str) -> RelatedEntry:
    value_model = type(value)
    credited = reviewed = None
    if isinstance(value, CreditedContent):
        credited = value.written_by_id is not None
        reviewed = value.reviewed_by_id is not None
    return RelatedEntry(
        label=str(value),
        model_label=f"{domain_of(value_model)}.{value_model.__name__}",
        model_name=value_model.__name__,
        pk=value.pk,
        relation=relation,
        direction=direction,
        credited=credited,
        reviewed=reviewed,
    )


def _forward_neighbors(instance: object, model: type) -> list[tuple[object, str]]:
    """Return `(value, field_name)` pairs for every forward FK/O2O/M2M value set.

    Field selection per the Task 6 brief: `field.is_relation and
    (field.many_to_one or field.one_to_one or field.many_to_many) and
    field.concrete` - the concrete check is what excludes reverse relation
    objects (`ManyToOneRel`/`OneToOneRel`/`ManyToManyRel`, all
    `concrete=False`) from this loop, since `_meta.get_fields()` returns both
    directions in one list.
    """
    pairs: list[tuple[object, str]] = []
    for field in model._meta.get_fields():  # noqa: SLF001
        if not (
            field.is_relation
            and field.concrete
            and (field.many_to_one or field.one_to_one or field.many_to_many)
        ):
            continue
        if field.many_to_many:
            values = list(getattr(instance, field.name).all())
        else:
            value = getattr(instance, field.name, None)
            values = [value] if value is not None else []
        pairs.extend((value, field.name) for value in values)
    return pairs


def _reverse_neighbors(instance: object, model: type) -> list[tuple[object, str]]:
    """Return `(value, accessor_name)` pairs for every reverse FK/O2O/M2M row.

    Field selection: `field.auto_created and not field.concrete` picks out
    the `ManyToOneRel`/`OneToOneRel`/`ManyToManyRel` objects `_meta
    .get_fields()` synthesizes for the far side of every relation pointed at
    this model.

    Skipping `related_name="+"` needs no extra check here: `get_fields()`
    defaults to `include_hidden=False`, which already drops a "+" relation
    from the list entirely - confirmed with a shell probe against
    `world.missions.models.MissionTemplate`, the target of
    `Beginning.prelude_mission` (`related_name="+"`). That reverse relation
    only shows up once `get_fields(include_hidden=True)` is passed
    explicitly; it is absent from the default list this function walks, and
    every field in that default list reports `field.hidden == False`. So
    `field.hidden` is never actually `True` on anything this loop sees, and
    checking it here would be dead code - the filtering already happened one
    layer up, inside `get_fields()` itself.
    """
    pairs: list[tuple[object, str]] = []
    for field in model._meta.get_fields():  # noqa: SLF001
        if not (field.auto_created and not field.concrete):
            continue
        accessor = field.get_accessor_name()
        try:
            raw = getattr(instance, accessor)
        except ObjectDoesNotExist:
            raw = None
        if raw is None:
            values: list[object] = []
        elif hasattr(raw, "all"):
            values = list(raw.all())
        else:
            values = [raw]
        pairs.extend((value, accessor) for value in values)
    return pairs


def related_entries(
    instance: object, *, cap: int = _DEFAULT_RELATED_CAP
) -> tuple[list[RelatedEntry], int]:
    """Structured FK/M2M/reverse walk of `instance`'s immediate neighbors.

    Returns `(entries, truncated_count)`: `entries` is capped at `cap` rows
    total across every forward and reverse relation combined, worst-first-
    free (no sort - relation declaration order, forward before reverse);
    `truncated_count` is how many more neighbor rows exist beyond the cap.

    Scale ceiling: this materializes every neighbor row (via `list()` on
    each relation's queryset/manager) before capping, so a row with a
    reverse relation carrying thousands of rows pulls all of them into
    memory before the cap trims the result - fine for the workbench's actual
    per-row neighbor counts today. If a model ever grows a relation at that
    scale, this needs per-relation query slicing instead of a post-hoc cap.
    """
    forward = [
        _entry(value, relation=name, direction="forward")
        for value, name in _forward_neighbors(instance, type(instance))
    ]
    reverse = [
        _entry(value, relation=name, direction="reverse")
        for value, name in _reverse_neighbors(instance, type(instance))
    ]
    all_entries = forward + reverse
    return all_entries[:cap], max(0, len(all_entries) - cap)


def prose_mentions(
    name: str, *, exclude: tuple[type, object] | None = None, cap: int = _DEFAULT_MENTIONS_CAP
) -> list[RelatedEntry]:
    """Rows across every credited content model whose prose contains `name`.

    Loops `credited_content_models()`, OR-filtering `icontains` per prose
    field (`prose_fields_for`) of each model in turn; `exclude` is the
    `(model, pk)` of the row being edited, dropped from its own model's
    results so a row never lists itself as a mention of its own name.
    Returns as soon as `cap` rows are collected, without scanning the
    remaining models - `prose_mentions` never reports how many more exist
    (unlike `related_entries`), so there is nothing left to compute once the
    cap is hit.
    """
    if not name:
        return []

    entries: list[RelatedEntry] = []
    for model in credited_content_models():
        prose_names = prose_fields_for(model)
        if not prose_names:
            continue
        query = Q()
        for field_name in prose_names:
            query |= Q(**{f"{field_name}__icontains": name})
        queryset = model.objects.filter(query)
        if exclude is not None and exclude[0] is model:
            queryset = queryset.exclude(pk=exclude[1])
        for value in queryset:
            if len(entries) >= cap:
                return entries
            entries.append(_entry(value, relation="mention", direction="mention"))
    return entries
