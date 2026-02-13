"""
Import analysis and merge pipeline for fixture data.

Provides two main entry points:
- analyze_fixture(): dry-run comparison of fixture data against DB
- execute_import(): atomic merge/replace/skip pipeline

These are designed to be called from views (or tests) with raw JSON strings.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
import logging
from typing import Any

from django.apps import apps
from django.core import serializers
from django.db import models, transaction
from django.db.models.fields.related import ForeignKey

from core.natural_keys import count_natural_key_args

logger = logging.getLogger(__name__)

HARDCODED_EXCLUDED_APPS = frozenset(
    {
        "sessions",
        "contenttypes",
        "django_migrations",
        "admin",
        "server",
        "scripts",
        "comms",
        "help",
        "typeclasses",
    }
)

_MODEL_KEY_PARTS = 2  # "app_label.model_name"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ModelAnalysis:
    """Analysis results for a single model in the fixture."""

    app_label: str
    model_name: str
    verbose_name: str
    has_natural_key: bool
    # Record counts
    in_file: int = 0
    in_db: int = 0
    new_count: int = 0  # In file but not in DB
    changed_count: int = 0  # In file and DB, fields differ
    unchanged_count: int = 0  # In file and DB, fields match
    local_only_count: int = 0  # In DB but not in file
    # Warnings
    warnings: list[str] = field(default_factory=list)
    # Detailed record info for UI
    changed_records: list[dict[str, Any]] = field(default_factory=list)
    local_only_records: list[str] = field(default_factory=list)
    # Is this from an instance data app?
    is_instance_data: bool = False


@dataclass
class FixtureAnalysis:
    """Complete analysis of a fixture file."""

    models: list[ModelAnalysis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_records: int = 0
    total_models: int = 0
    # (app_label, model_name) pairs in dependency order
    dependency_order: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ModelImportResult:
    """Results for a single model's import."""

    app_label: str
    model_name: str
    action: str  # "merge", "replace", "skip"
    created: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Complete results of an import operation."""

    success: bool = True
    models: list[ModelImportResult] = field(default_factory=list)
    error_message: str = ""
    total_created: int = 0
    total_updated: int = 0
    total_deleted: int = 0


# ---------------------------------------------------------------------------
# Natural key helpers
# ---------------------------------------------------------------------------


def _extract_natural_key_from_fields(
    model_class: type[models.Model],
    fields_dict: dict[str, Any],
) -> tuple[Any, ...] | None:
    """Extract the flat natural key tuple from a fixture record's fields dict.

    For regular fields the value is taken directly. For FK fields whose related
    model also has a NaturalKeyConfig the value is already stored as a list
    (the related model's natural key) in the fixture. We flatten these into
    one continuous tuple so it can be passed to ``get_by_natural_key()``.

    Returns ``None`` if the model has no ``NaturalKeyConfig`` or a required
    field is missing from *fields_dict*.
    """
    if not hasattr(model_class, "NaturalKeyConfig"):
        return None

    config = model_class.NaturalKeyConfig
    key_parts: list[Any] = []

    for field_name in config.fields:
        if field_name not in fields_dict:
            return None
        _append_nk_part(model_class, field_name, fields_dict[field_name], key_parts)

    return tuple(key_parts)


def _append_nk_part(
    model_class: type[models.Model],
    field_name: str,
    value: Any,
    key_parts: list[Any],
) -> None:
    """Append a single natural key field's contribution to *key_parts*."""
    model_field = model_class._meta.get_field(field_name)  # noqa: SLF001

    if not isinstance(model_field, ForeignKey):
        key_parts.append(value)
        return

    related_model = model_field.related_model
    if not hasattr(related_model, "NaturalKeyConfig"):
        key_parts.append(value)
        return

    # FK with natural key support — value is a list or None
    if value is None:
        num_args = count_natural_key_args(related_model)
        key_parts.extend([None] * num_args)
    elif isinstance(value, list):
        key_parts.extend(value)
    else:
        # Scalar PK reference — shouldn't happen with
        # use_natural_foreign_keys but handle gracefully.
        key_parts.append(value)


def _has_natural_key(model_class: type[models.Model]) -> bool:
    """Return True if *model_class* supports natural keys."""
    return hasattr(model_class, "NaturalKeyConfig") and hasattr(model_class, "natural_key")


# ---------------------------------------------------------------------------
# Field comparison helpers
# ---------------------------------------------------------------------------


def _compare_fields(
    model_class: type[models.Model],
    existing: models.Model,
    fixture_fields: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare fixture fields against an existing DB record.

    Returns a list of dicts describing each changed field::

        [{"field": "description", "old": "...", "new": "..."}]

    FK fields are compared by natural key when available; otherwise by PK.
    M2M fields are skipped (they are handled separately during import).
    """
    changes: list[dict[str, Any]] = []

    for model_field in model_class._meta.get_fields():  # noqa: SLF001
        if not _is_comparable_field(model_field, fixture_fields):
            continue
        diff = _compare_single_field(model_field, existing, fixture_fields)
        if diff is not None:
            changes.append(diff)

    return changes


def _is_comparable_field(
    model_field: models.Field,
    fixture_fields: dict[str, Any],
) -> bool:
    """Return True if this field should be included in comparison."""
    if not hasattr(model_field, "attname"):
        return False
    if isinstance(model_field, models.ManyToManyField):
        return False
    if model_field.primary_key:
        return False
    return model_field.name in fixture_fields


def _compare_single_field(
    model_field: models.Field,
    existing: models.Model,
    fixture_fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Compare one field; return a change dict or None if identical."""
    field_name = model_field.name
    fixture_value = fixture_fields[field_name]

    if isinstance(model_field, ForeignKey):
        return _compare_fk_field(model_field, existing, fixture_value)

    existing_value = getattr(existing, field_name, None)
    if existing_value != fixture_value:
        return {"field": field_name, "old": existing_value, "new": fixture_value}
    return None


def _compare_fk_field(
    model_field: ForeignKey,
    existing: models.Model,
    fixture_value: Any,
) -> dict[str, Any] | None:
    """Compare a FK field; return a change dict or None if identical."""
    field_name = model_field.name
    related_model = model_field.related_model
    existing_related = getattr(existing, field_name, None)

    if hasattr(related_model, "NaturalKeyConfig") and isinstance(fixture_value, list):
        existing_nk = list(existing_related.natural_key()) if existing_related else None
        if fixture_value != existing_nk:
            return {"field": field_name, "old": existing_nk, "new": fixture_value}
    else:
        existing_fk_id = getattr(existing, model_field.attname, None)
        if fixture_value != existing_fk_id:
            return {"field": field_name, "old": existing_fk_id, "new": fixture_value}
    return None


# ---------------------------------------------------------------------------
# Dependency ordering
# ---------------------------------------------------------------------------


def _get_dependency_order(
    model_keys: set[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return topological sort of *model_keys* and any cycle nodes.

    Uses Kahn's algorithm. Models whose FK targets are also in the import set
    are placed after their dependencies. Models with no dependencies (or whose
    dependencies are outside the import set) come first.

    Returns (ordered_keys, cycle_nodes) where cycle_nodes are models involved
    in FK dependency cycles (appended at end of ordered_keys).
    """
    in_degree: dict[tuple[str, str], int] = dict.fromkeys(model_keys, 0)
    dependents: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for app_label, model_name in model_keys:
        _build_edges(app_label, model_name, model_keys, in_degree, dependents)

    order, cycle_nodes = _kahns_sort(in_degree, dependents, model_keys)
    return order, cycle_nodes


def _build_edges(
    app_label: str,
    model_name: str,
    model_keys: set[tuple[str, str]],
    in_degree: dict[tuple[str, str], int],
    dependents: dict[tuple[str, str], list[tuple[str, str]]],
) -> None:
    """Populate *in_degree* and *dependents* for one model's FK edges."""
    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        return

    for model_field in model_class._meta.get_fields():  # noqa: SLF001
        if not isinstance(model_field, ForeignKey):
            continue
        related = model_field.related_model
        rel_key = (
            related._meta.app_label,  # noqa: SLF001
            related._meta.model_name,  # noqa: SLF001
        )
        if rel_key == (app_label, model_name):
            continue  # skip self-referential FKs
        if rel_key in model_keys:
            in_degree[(app_label, model_name)] += 1
            dependents[rel_key].append((app_label, model_name))


def _kahns_sort(
    in_degree: dict[tuple[str, str], int],
    dependents: dict[tuple[str, str], list[tuple[str, str]]],
    model_keys: set[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Execute Kahn's algorithm; return (sorted, cycle_nodes)."""
    queue: deque[tuple[str, str]] = deque(sorted(k for k, deg in in_degree.items() if deg == 0))
    result: list[tuple[str, str]] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dependent in sorted(dependents[node]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Remaining nodes indicate dependency cycles
    remaining = sorted(k for k in model_keys if k not in set(result))
    result.extend(remaining)
    return result, remaining
    return result


# ---------------------------------------------------------------------------
# Analysis helpers (called from analyze_fixture)
# ---------------------------------------------------------------------------


def _parse_fixture_json(fixture_data: str) -> list | None:
    """Parse raw JSON; return the list of records or None on error."""
    try:
        data = json.loads(fixture_data)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, list):
        return data
    return None


def _group_fixture_records(
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group raw fixture records by their ``model`` key."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        model_key = record.get("model")
        if model_key:
            grouped[model_key].append(record)
    return grouped


def _analyze_model(
    model_key: str,
    model_records: list[dict[str, Any]],
    analysis: FixtureAnalysis,
) -> ModelAnalysis | None:
    """Analyse a single model's records against the DB.

    Returns a :class:`ModelAnalysis` or ``None`` if the model key is invalid.
    Appends warnings to *analysis.warnings* when the model can't be resolved.
    """
    parts = model_key.split(".")
    if len(parts) != _MODEL_KEY_PARTS:
        analysis.warnings.append(f"Invalid model key: {model_key}")
        return None

    app_label, model_name = parts

    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        analysis.warnings.append(f"Model not found: {model_key}")
        return None

    has_nk = _has_natural_key(model_class)
    verbose = str(model_class._meta.verbose_name_plural).title()  # noqa: SLF001

    ma = ModelAnalysis(
        app_label=app_label,
        model_name=model_name,
        verbose_name=verbose,
        has_natural_key=has_nk,
        in_file=len(model_records),
    )

    if app_label in HARDCODED_EXCLUDED_APPS:
        ma.is_instance_data = True
        ma.warnings.append(f"App '{app_label}' is in the hardcoded exclusion list.")

    try:
        ma.in_db = model_class.objects.count()
    except Exception:  # noqa: BLE001
        ma.warnings.append("Could not query existing records.")
        return ma

    if not has_nk:
        ma.warnings.append(
            "Model has no natural key \u2014 records cannot be "
            "individually matched. Only full replace is safe."
        )
        ma.new_count = ma.in_file
        return ma

    _analyze_records_with_nk(model_class, model_records, ma)
    return ma


def _analyze_records_with_nk(
    model_class: type[models.Model],
    model_records: list[dict[str, Any]],
    ma: ModelAnalysis,
) -> None:
    """Per-record comparison using natural keys; mutates *ma* in place."""
    seen_nk_strs: set[str] = set()

    for record in model_records:
        fixture_fields = record.get("fields", {})
        nk = _extract_natural_key_from_fields(model_class, fixture_fields)
        if nk is None:
            ma.warnings.append(
                "Could not extract natural key from a record \u2014 missing fields in fixture data."
            )
            ma.new_count += 1
            continue

        nk_str = str(nk)
        seen_nk_strs.add(nk_str)
        _classify_record(model_class, nk, nk_str, fixture_fields, ma)

    _find_local_only_records(model_class, seen_nk_strs, ma)


def _classify_record(
    model_class: type[models.Model],
    nk: tuple[Any, ...],
    nk_str: str,
    fixture_fields: dict[str, Any],
    ma: ModelAnalysis,
) -> None:
    """Classify a single fixture record as new / changed / unchanged."""
    try:
        existing = model_class.objects.get_by_natural_key(*nk)
    except model_class.DoesNotExist:
        ma.new_count += 1
        return
    except Exception as exc:  # noqa: BLE001
        ma.warnings.append(f"Error looking up {nk}: {exc}")
        ma.new_count += 1
        return

    changes = _compare_fields(model_class, existing, fixture_fields)
    if changes:
        ma.changed_count += 1
        ma.changed_records.append({"natural_key": nk_str, "changes": changes})
    else:
        ma.unchanged_count += 1


def _find_local_only_records(
    model_class: type[models.Model],
    seen_nk_strs: set[str],
    ma: ModelAnalysis,
) -> None:
    """Find DB records not present in the fixture; mutates *ma* in place."""
    try:
        for obj in model_class.objects.all().iterator():
            obj_nk_str = str(obj.natural_key())
            if obj_nk_str not in seen_nk_strs:
                ma.local_only_count += 1
                ma.local_only_records.append(obj_nk_str)
    except Exception as exc:  # noqa: BLE001
        ma.warnings.append(f"Could not enumerate local-only records: {exc}")


# ---------------------------------------------------------------------------
# Public API -- analyze
# ---------------------------------------------------------------------------


def analyze_fixture(fixture_data: str) -> FixtureAnalysis:
    """Dry-run analysis comparing fixture JSON against the current database.

    Parses the raw JSON (not Django's deserializer) to compare records
    field-by-field. Returns a :class:`FixtureAnalysis` summarising new,
    changed, unchanged, and local-only records for every model present in
    the fixture.
    """
    analysis = FixtureAnalysis()

    records = _parse_fixture_json(fixture_data)
    if records is None:
        analysis.warnings.append("Invalid JSON or not a JSON array.")
        return analysis

    grouped = _group_fixture_records(records)
    analysis.total_records = len(records)

    model_keys_set: set[tuple[str, str]] = set()

    for model_key, model_records in sorted(grouped.items()):
        ma = _analyze_model(model_key, model_records, analysis)
        if ma is not None:
            analysis.models.append(ma)
            model_keys_set.add((ma.app_label, ma.model_name))

    analysis.total_models = len(analysis.models)
    dep_order, cycle_nodes = _get_dependency_order(model_keys_set)
    analysis.dependency_order = dep_order
    if cycle_nodes:
        cycle_names = [f"{a}.{m}" for a, m in cycle_nodes]
        analysis.warnings.append(
            f"Circular FK dependencies detected: {', '.join(cycle_names)}. "
            "These models may fail to import correctly."
        )
    return analysis


# ---------------------------------------------------------------------------
# Import execution helpers
# ---------------------------------------------------------------------------


def _group_deserialized(deserialized: list) -> dict[str, list]:
    """Group deserialized objects by ``app_label.model_name``."""
    grouped: dict[str, list] = defaultdict(list)
    for obj in deserialized:
        mc = obj.object.__class__
        key = f"{mc._meta.app_label}.{mc._meta.model_name}"  # noqa: SLF001
        grouped[key].append(obj)
    return grouped


def _ordered_model_keys(
    grouped: dict[str, list],
) -> list[str]:
    """Return grouped keys in FK-dependency order."""
    model_keys_set: set[tuple[str, str]] = set()
    for key in grouped:
        parts = key.split(".")
        if len(parts) == _MODEL_KEY_PARTS:
            model_keys_set.add((parts[0], parts[1]))

    dep_order, _cycle_nodes = _get_dependency_order(model_keys_set)

    ordered: list[str] = []
    for app_label, model_name in dep_order:
        k = f"{app_label}.{model_name}"
        if k in grouped:
            ordered.append(k)

    # Append any stragglers not captured (shouldn't happen)
    for key in grouped:
        if key not in ordered:
            ordered.append(key)
    return ordered


def _process_model_action(
    model_key: str,
    objects: list,
    action: str,
) -> ModelImportResult:
    """Dispatch a single model to the correct import strategy."""
    app_label, model_name = model_key.split(".")
    model_class = objects[0].object.__class__

    mr = ModelImportResult(
        app_label=app_label,
        model_name=model_name,
        action=action,
    )

    if action == "skip":
        mr.skipped = len(objects)
    elif action == "replace":
        _execute_replace(model_class, objects, mr)
    elif action == "merge":
        _execute_merge(model_class, objects, mr)
    else:
        mr.errors.append(f"Unknown action '{action}'; skipping.")
        mr.skipped = len(objects)

    return mr


def _execute_replace(
    model_class: type[models.Model],
    objects: list,
    mr: ModelImportResult,
) -> None:
    """Replace: delete all existing, then save all deserialized objects."""
    existing_count = model_class.objects.count()
    model_class.objects.all().delete()
    mr.deleted = existing_count

    for obj in objects:
        try:
            obj.save()
            mr.created += 1
        except Exception as exc:  # noqa: BLE001
            mr.errors.append(f"Error saving record: {exc}")


def _execute_merge(
    model_class: type[models.Model],
    objects: list,
    mr: ModelImportResult,
) -> None:
    """Merge: update existing, create new, preserve local-only."""
    has_nk = _has_natural_key(model_class)

    for obj in objects:
        if not has_nk:
            _merge_without_nk(obj, mr)
        else:
            _merge_with_nk(model_class, obj, mr)


def _merge_without_nk(obj: Any, mr: ModelImportResult) -> None:
    """Merge a single record without natural key support (create only)."""
    try:
        obj.save()
        mr.created += 1
    except Exception as exc:  # noqa: BLE001
        mr.errors.append(f"Error saving record: {exc}")


def _merge_with_nk(
    model_class: type[models.Model],
    obj: Any,
    mr: ModelImportResult,
) -> None:
    """Merge a single record using natural key lookup."""
    instance = obj.object
    nk = instance.natural_key()

    try:
        existing = model_class.objects.get_by_natural_key(*nk)
    except model_class.DoesNotExist:
        _merge_create_new(obj, nk, mr)
        return
    except Exception as exc:  # noqa: BLE001
        mr.errors.append(f"Error looking up {nk}: {exc}")
        return

    _merge_update_existing(model_class, obj, existing, nk, mr)


def _merge_create_new(
    obj: Any,
    nk: tuple[Any, ...],
    mr: ModelImportResult,
) -> None:
    """Create a new record during merge (no existing match found)."""
    try:
        obj.object.pk = None
        obj.save()
        mr.created += 1
    except Exception as exc:  # noqa: BLE001
        mr.errors.append(f"Error creating {nk}: {exc}")


def _merge_update_existing(
    model_class: type[models.Model],
    obj: Any,
    existing: models.Model,
    nk: tuple[Any, ...],
    mr: ModelImportResult,
) -> None:
    """Update an existing record's fields and M2M relations during merge."""
    instance = obj.object
    try:
        update_fields = []
        for model_field in model_class._meta.fields:  # noqa: SLF001
            if model_field.primary_key:
                continue
            # Skip auto-managed timestamp fields to preserve local audit data
            if getattr(model_field, "auto_now", False) or getattr(  # noqa: GETATTR_LITERAL
                model_field,
                "auto_now_add",  # noqa: GETATTR_LITERAL
                False,
            ):
                continue
            attname = model_field.attname
            setattr(existing, attname, getattr(instance, attname))
            update_fields.append(attname)
        existing.save(update_fields=update_fields)
        mr.updated += 1
    except Exception as exc:  # noqa: BLE001
        mr.errors.append(f"Error updating {nk}: {exc}")
        return

    _merge_m2m(obj, existing, nk, mr)


def _merge_m2m(
    obj: Any,
    existing: models.Model,
    nk: tuple[Any, ...],
    mr: ModelImportResult,
) -> None:
    """Apply M2M data from a deserialized object to an existing record."""
    if not obj.m2m_data:
        return
    for m2m_field_name, m2m_pks in obj.m2m_data.items():
        try:
            m2m_manager = getattr(existing, m2m_field_name)
            m2m_manager.set(m2m_pks)
        except Exception as exc:  # noqa: BLE001
            mr.errors.append(f"Error setting M2M {m2m_field_name} on {nk}: {exc}")


# ---------------------------------------------------------------------------
# Public API -- execute import
# ---------------------------------------------------------------------------


def execute_import(
    fixture_data: str,
    model_actions: dict[str, str],
) -> ImportResult:
    """Execute an atomic import of fixture data.

    *model_actions* maps ``"app_label.model_name"`` to one of
    ``"merge"``, ``"replace"``, or ``"skip"``.

    The entire operation runs inside ``transaction.atomic()``; any error
    causes a full rollback.
    """
    result = ImportResult()

    try:
        deserialized = list(serializers.deserialize("json", fixture_data))
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.error_message = f"Failed to deserialize fixture: {exc}"
        return result

    grouped = _group_deserialized(deserialized)
    ordered_keys = _ordered_model_keys(grouped)

    try:
        with transaction.atomic():
            for model_key in ordered_keys:
                action = model_actions.get(model_key, "skip")
                mr = _process_model_action(model_key, grouped[model_key], action)
                result.models.append(mr)

            # Check for errors and raise to trigger rollback
            for mr in result.models:
                result.total_created += mr.created
                result.total_updated += mr.updated
                result.total_deleted += mr.deleted
                if mr.errors:
                    result.success = False

            if not result.success:
                error_details = []
                for mr in result.models:
                    error_details.extend(mr.errors)
                result.error_message = "Import failed (rolled back): " + "; ".join(error_details)
                msg = "Per-record errors detected; rolling back"
                raise RuntimeError(msg)
    except Exception as exc:
        result.success = False
        result.error_message = f"Import failed (rolled back): {exc}"
        logger.exception("Import transaction failed")

    return result
