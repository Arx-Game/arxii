"""Read-only scan that recomputes credited-row load conflicts (#3017).

``content_fixtures._upsert_fixture_object`` freezes a credited row (a row
whose ``written_by`` is set) when the incoming fixture value differs from
what's on disk, and records a one-line diagnostic in ``BuildResult.conflicts``
- but only for whatever a real load run just touched, and only as prose. This
module reruns the exact same resolution sequence *without ever writing*, so a
later admin page can list every current conflict on demand (not just the ones
surfaced by the last load) with structured per-field detail instead of a
prose blob.

Deliberately imports ``core_management.content_fixtures``'s private helpers
(``_extract_natural_key``, ``_pop_m2m_fields``, ``_resolve_or_drop_credit_fields``,
``_resolve_natural_key_fields``, ``_resolve_m2m_fields``, ``_coerce_scalar_fields``,
``_find_existing_case_insensitive``, ``_credited_conflicts``) - this is
deliberate, not a layering violation: same package, and the alternative is a
second hand-maintained copy of the resolution sequence that WILL drift from
the one the real load path uses. ``content_fixtures`` stays the single source
of resolution semantics; this module only reads what it produces.

Caveat (Task 3 review): this scan, and any single-entry reload built on it,
resolves each object in isolation - there is no deferred-retry pass and no
grid-bundle load, unlike ``load_world_content``'s full sequence. So a row
whose incoming FK target is itself new in the same corpus update may not
show up as a conflict (or reload cleanly) until after a full load brings
that target in. The divergence is one-directional: it can under-report a
conflict, never invent one, and the upsert guard in
``_upsert_fixture_object`` still protects the row regardless of which path
notices it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from core_management.content_fixtures import (
    BuildResult,
    ContentError,
    _coerce_scalar_fields,
    _credited_conflicts,
    _extract_natural_key,
    _find_existing_case_insensitive,
    _pop_m2m_fields,
    _resolve_m2m_fields,
    _resolve_natural_key_fields,
    _resolve_or_drop_credit_fields,
    build_all,
    resolve_fixture_model,
)

#: Display strings longer than this are truncated with a trailing "..." so a
#: multi-thousand-character prose field doesn't blow up the admin list view.
DISPLAY_TRUNCATE_LENGTH = 200


@dataclass
class LoadConflict:
    """One credited row whose incoming corpus value differs from the DB.

    ``model_label`` is the fixture object's own ``"model"`` key (whatever
    ``content_fixtures._fixture_model_label`` wrote at build time), not a
    freshly recomputed one - it's the value an admin view would round-trip
    back through ``resolve_fixture_model``. ``natural_key`` is a display
    string, ``", ".join(str(v) for v in lookup.values())`` - the same form
    ``_upsert_fixture_object`` puts in its own conflict message. ``fields`` is
    one ``(field name, db display, incoming display)`` triple per differing
    field, both sides truncated to ``DISPLAY_TRUNCATE_LENGTH`` characters.
    """

    model_label: str
    model_name: str
    natural_key: str
    fields: list[tuple[str, str, str]]

    @property
    def digest(self) -> str:
        """Stable hash of the reviewed diff (#3017 GET/POST staleness fix).

        The admin detail page hands this back to the resolve view as a
        hidden field alongside the typed natural key. If the corpus or the
        DB row changes between the detail GET and the resolve POST, a fresh
        ``find_load_conflict`` call produces a different digest and the
        resolve view refuses rather than silently applying corpus values the
        operator never actually reviewed - the row is still a genuine
        conflict at POST time, so a bare re-fetch-and-compare wouldn't catch
        this the way it does for a conflict that resolved out from under the
        request.

        Computed over ``model_label``, ``natural_key``, and every
        ``(field name, db display, incoming display)`` triple in order -
        exactly what the detail page rendered, nothing more. Uses ``\\x1f``
        (unit separator) as the field delimiter so no display value's own
        content can forge a collision the way a plain ``, ``/``|`` join could.
        """
        parts = [self.model_label, self.natural_key]
        parts.extend(f"{name}\x1f{db}\x1f{incoming}" for name, db, incoming in self.fields)
        payload = "\x1e".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _truncate(text: str) -> str:
    if len(text) > DISPLAY_TRUNCATE_LENGTH:
        return text[:DISPLAY_TRUNCATE_LENGTH] + "..."
    return text


def _field_display(
    model, existing, name: str, fields: dict, resolved_m2m: dict[str, list]
) -> tuple[str, str]:
    """Return ``(db display, incoming display)`` strings for one differing field.

    A many-to-many field's current value comes from the live relation
    (``getattr(existing, name).all()``) since it was popped out of ``fields``
    before this module ever saw it; the incoming side is the already-resolved
    instance list in ``resolved_m2m``. A to-one relation shows ``str()`` of
    each side's related instance - the current one fetched fresh via
    ``getattr(existing, name)`` (never written to), the incoming one already
    resolved to an instance in ``fields``. A plain scalar shows ``str()`` of
    each side's already-coerced value.
    """
    field_obj = model._meta.get_field(name)  # noqa: SLF001
    if field_obj.many_to_many:
        current = ", ".join(str(v) for v in getattr(existing, name).all())
        incoming = ", ".join(str(v) for v in resolved_m2m.get(name, []))
        return _truncate(current), _truncate(incoming)
    if field_obj.is_relation:
        current_value = getattr(existing, name)
        incoming_value = fields.get(name)
        current = str(current_value) if current_value is not None else "None"
        incoming = str(incoming_value) if incoming_value is not None else "None"
        return _truncate(current), _truncate(incoming)
    current = str(getattr(existing, name))
    incoming = str(fields.get(name))
    return _truncate(current), _truncate(incoming)


def _scan_object(obj: dict, source_path: Path | None) -> LoadConflict | None:
    """Mirror ``_upsert_fixture_object``'s resolution sequence; never writes.

    Returns ``None`` on any skip condition the real load path would also
    skip on (stale model, bad natural key, unresolved FK, schema drift, a
    constraint the DB would reject) - the load path already reports those as
    skips elsewhere; this scan only cares about actual credited-row conflicts.
    """
    from django.core.exceptions import FieldError, ValidationError  # noqa: PLC0415
    from django.db import IntegrityError  # noqa: PLC0415

    try:
        model = resolve_fixture_model(obj["model"])
    except LookupError:
        return None

    fields = dict(obj["fields"])
    fields.pop("pk", None)
    try:
        lookup = _extract_natural_key(model, fields, source_path)
    except ContentError:
        return None

    m2m_fields = _pop_m2m_fields(model, fields)

    # Same as _upsert_fixture_object: credit fields resolve separately and
    # never fail the row. The result is a throwaway - this scan doesn't
    # surface per-credit-field resolution diagnostics, only conflicts.
    _resolve_or_drop_credit_fields(model, fields, source_path, BuildResult())

    try:
        _resolve_natural_key_fields(model, lookup, source_path)
        _resolve_natural_key_fields(model, fields, source_path)
        resolved_m2m = _resolve_m2m_fields(model, m2m_fields, source_path)
        _coerce_scalar_fields(model, fields)
        # Case-insensitive lookup only - never a write, never .save(), never
        # _apply_or_create. The DB side of every display below is read from
        # `existing` before (and without) any mutation.
        existing = _find_existing_case_insensitive(model, lookup)
        conflict_fields = _credited_conflicts(model, existing, fields, resolved_m2m)
    except (
        ContentError,
        ValueError,
        TypeError,
        FieldError,
        ValidationError,
        IntegrityError,
        model.DoesNotExist,
    ):
        return None

    if not conflict_fields:
        return None

    triples = [
        (name, *_field_display(model, existing, name, fields, resolved_m2m))
        for name in conflict_fields
    ]
    natural_key = ", ".join(str(v) for v in lookup.values())
    return LoadConflict(
        model_label=obj["model"],
        model_name=model.__name__,
        natural_key=natural_key,
        fields=triples,
    )


def scan_load_conflicts(content_root: Path) -> list[LoadConflict]:
    """Recompute every current credited-row load conflict under ``content_root``.

    Runs ``build_all`` (parses/validates every domain, exactly as a real load
    would) then, per object, the same resolve-and-check sequence
    ``_upsert_fixture_object`` runs before it would write - but stops short of
    ``_apply_or_create``/``.save()``/``.set()`` every time, so this function
    never mutates the database. Safe to call on every admin page load.
    """
    conflicts: list[LoadConflict] = []
    result = build_all(content_root)
    for output_path, objects in result.fixtures.items():
        paths = result.source_paths.get(output_path, [])
        for obj, source_path in zip(objects, paths, strict=False):
            conflict = _scan_object(obj, source_path)
            if conflict is not None:
                conflicts.append(conflict)
    return conflicts


def find_load_conflict(
    content_root: Path, model_label: str, natural_key: str
) -> LoadConflict | None:
    """Return the one conflict matching ``(model_label, natural_key)``, if any.

    A thin filter over ``scan_load_conflicts`` - the admin resolve view looks
    up one specific conflict (the one a staff member is about to act on) by
    the same two fields the list view displays, so this is the round-trip
    lookup for that click.
    """
    for conflict in scan_load_conflicts(content_root):
        if conflict.model_label == model_label and conflict.natural_key == natural_key:
            return conflict
    return None
