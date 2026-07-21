"""Content pipeline core (#944, #2266): private authored content → fixture JSON.

The maintainers' content repository (never named in this repo — located via
the ``CONTENT_REPO_PATH`` env var) holds one file per entry: YAML
frontmatter for mechanical keys, markdown body for prose. This module
parses, validates, and emits Django fixture JSON serialized with natural
keys (no "pk" key), identity-stable across database wipes, pk churn, and
migration rebuilds.

Honest ``loaddata`` semantics (#946, #2266 review fix): every domain's model
now carries ``NaturalKeyMixin``, so ``loaddata`` on the emitted JSON
correctly *resolves* an existing same-name row rather than raising
``IntegrityError`` on a blind INSERT — but on a `SharedMemoryModel`,
``loaddata`` still cannot **update** that resolved row. The identity map
returns the cached instance, `loaddata` writes the incoming field values
onto it, then Django's `save(force_insert=False)` path re-fetches from the
cache and the new values never land in the DB (verified cross-process,
#946). So the emitted fixture JSON is **fresh-DB / insert-or-resolve only**
— safe to `loaddata` against an empty table or a table whose rows it
already matches, but never a reliable way to push edited content onto rows
that already exist with different values. ``load_entries`` (below), which
drives both ``tools/build_content_fixtures.py --load`` and the admin "Load
private content repo" button, calls ``update_or_create`` directly against
the live model manager instead of going through ``loaddata`` — that is the
**only** update-safe path for re-authored content.

Import-safe without Django configured (the tools wrapper and tests use it
standalone). ``build_all()`` stays DB-free for every domain EXCEPT
``npc_roles/``'s optional ``faction_affiliation`` field: resolving an
org-by-name reference requires a live database, so that one builder does a
deferred Django import and touches the DB — only when a file actually sets
the key — to raise ``ContentError`` (naming the file + the missing org) at
validate time, mirroring how a bad ``category`` is caught today. Every other
builder (including the same domain's other fields) stays pure. Only
``load_entries`` performs the actual upsert I/O.

Optional-field update semantics (#2266 Q1): a builder OMITS an optional key
from the returned ``fields`` dict entirely when the frontmatter doesn't set
it — it never fills in `None`/0/"" as a stand-in. This is deliberate:
``load_entries`` upserts via ``update_or_create(name=..., defaults=fields)``,
and Django only touches the fields present in ``defaults`` — on CREATE, an
absent key falls through to the model field's own default; on UPDATE, an
absent key leaves the existing row's value untouched. So "key omitted from
frontmatter" already means "don't touch this field" for free, with no extra
mechanism needed. This is the convention every scalar optional field in this
module follows (``default_rapport_starting_value``,
``default_description_template``, ``value``, ``weight``) — keep it when
adding more.

Three-state convention for clearable FK-by-name fields (``faction_affiliation``,
#2266 review fix): a scalar field has only "omit" vs "set"; a nullable FK-by-name
field genuinely needs a third state — "clear the existing value" — that "omit"
can't express (omit already means "leave it alone"). So ``faction_affiliation``
is handled distinctly from the scalar fields above:

- key ABSENT from frontmatter → omitted from ``fields`` → untouched on UPDATE
  (same as every scalar field).
- key PRESENT but null/empty (``faction_affiliation:`` or ``faction_affiliation:
  null``) → emitted as ``fields["faction_affiliation"] = None`` → UPDATE sets the
  FK to null, clearing it. Requires the target field to be nullable
  (``NPCRole.faction_affiliation`` is, per spec); a future clearable FK-by-name
  field that ISN'T nullable must raise ``ContentError`` for the explicit-null
  case instead of emitting ``None``.
- key PRESENT with a non-empty string → resolved/validated as an Organization
  name and emitted using Django's own natural-key fixture convention — a
  one-element list (``["Org Name"]``) — rather than a resolved pk or model
  instance, so the generated JSON stays plain-JSON-serializable
  (``write_fixtures`` just calls ``json.dumps``) and also stays loadable by a
  real ``loaddata`` against a fresh DB, since ``Organization`` already carries
  ``NaturalKeyMixin`` (``world/societies/models.py``) — no new natural-key
  infrastructure needed. ``_resolve_natural_key_fields`` (used by
  ``load_entries``) resolves that list back into a real instance immediately
  before the write; a bare ``None`` passes through untouched (not a list, so
  the resolver skips it and ``update_or_create`` receives the null directly).

Domains: ``stats``/``skills`` → ``traits.Trait`` rows (name, type, category,
description); ``npc_roles`` → ``npc_services.NPCRole`` (name, description,
optional faction/rapport/flavor-template); ``items`` →
``items.ItemTemplate`` (name, description, optional value/weight);
``building_kinds`` → ``buildings.BuildingKind`` and ``decoration_kinds`` →
``buildings.DecorationKind`` (name, description only — mechanical flags stay
admin/seeder-authored). Every domain's model has a DB-unique ``name``, so
``load_entries``'s natural key stays a bare ``name`` for all of them; a
future domain without one (e.g. Area — see #2266) needs a configurable
natural-key field list before it can onboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
import json
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from core_management.grid_import import GridImportResult

PLACEHOLDER_MARK = "PLACEHOLDER"
FRONTMATTER_DELIMITER = "---"

# Mirrors world.traits.models.TraitType / TraitCategory values without
# importing Django models (import-safety). Validated against the real
# enums in core_management.tests.test_content_fixtures. TRAIT_TYPES is the
# subset this pipeline PRODUCES, not the full enum.
TRAIT_TYPES = {"stat", "skill"}
TRAIT_CATEGORIES = {
    "physical",
    "social",
    "mental",
    "meta",
    "magic",
    "combat",
    "general",
    "crafting",
    "war",
    "other",
}

# Optional frontmatter field names, factored out to module constants so a
# repeated ``key in entry.meta`` membership check doesn't trip the
# bare-string-literal-as-identifier lint (tools/lint_string_literal.py).
FIELD_FACTION_AFFILIATION = "faction_affiliation"
FIELD_DEFAULT_RAPPORT_STARTING_VALUE = "default_rapport_starting_value"
FIELD_DEFAULT_DESCRIPTION_TEMPLATE = "default_description_template"
FIELD_VALUE = "value"
FIELD_WEIGHT = "weight"

# _upsert_fixture_object()/load_entries()/load_world_content() outcome tokens
# (#2448) — module constants for the same reason as the FIELD_* group above:
# every use is a return value or an ``==`` comparison, which the
# bare-string-literal-as-identifier lint rejects.
OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_SKIPPED = "skipped"
OUTCOME_DEFERRED = "deferred"


class ContentError(Exception):
    """A content file failed validation. Message carries file + reason."""


class UnresolvedNaturalKeyError(ContentError):
    """A natural-key-list FK value did not resolve to an existing row (#2448).

    Narrower than the base ``ContentError`` ``_resolve_natural_key_fields``
    otherwise raises — only its two "not found" sites use this subclass, never
    the "list-valued field but not relational" shape error. That narrowness is
    what lets ``load_entries(..., defer_unresolved=True)`` DEFER only a
    genuine missing-target failure (e.g. a ``StartingArea`` fixture naming a
    room that the grid bundles haven't loaded yet) and still skip every other
    ContentError immediately, unchanged — see ``load_world_content``, which
    sequences content fixtures before grid bundles specifically to give a
    deferred object a second chance once the room it names exists.
    """


@dataclass
class ContentEntry:
    """One parsed content file."""

    path: Path
    domain: str
    meta: dict
    body: str

    @property
    def has_placeholder(self) -> bool:
        return PLACEHOLDER_MARK in self.body or any(
            isinstance(v, str) and PLACEHOLDER_MARK in v for v in self.meta.values()
        )


@dataclass
class BuildResult:
    """Outcome of a build/validate pass."""

    fixtures: dict[str, list[dict]] = field(default_factory=dict)  # output path -> objects
    entries: list[ContentEntry] = field(default_factory=list)
    placeholder_counts: dict[str, int] = field(default_factory=dict)  # domain -> count
    # output path -> source file per object, same order as fixtures[output].
    # Lets load_entries name the originating file in a resolution error.
    source_paths: dict[str, list[Path]] = field(default_factory=dict)
    # Human-readable warnings for objects that were skipped (stale models,
    # missing NaturalKeyMixin, etc.). Collected during build, surfaced to the
    # operator by the CLI / admin button.
    skipped: list[str] = field(default_factory=list)


def parse_content_file(path: Path, domain: str) -> ContentEntry:
    """Parse one frontmatter+markdown file; raise ContentError on shape errors.

    Line-based (no regex): the opening line must be ``---``; frontmatter runs
    to the next ``---`` line; everything after is the body.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        msg = f"{path}: missing YAML frontmatter block (--- ... ---)."
        raise ContentError(msg)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == FRONTMATTER_DELIMITER), None)
    if end is None:
        msg = f"{path}: unterminated YAML frontmatter block (--- ... ---)."
        raise ContentError(msg)
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        msg = f"{path}: invalid YAML frontmatter: {exc}"
        raise ContentError(msg) from exc
    if not isinstance(meta, dict):
        msg = f"{path}: frontmatter must be a mapping."
        raise ContentError(msg)
    body = "\n".join(lines[end + 1 :]).strip()
    return ContentEntry(path=path, domain=domain, meta=meta, body=body)


def _require_name_and_body(entry: ContentEntry) -> str:
    """Validate the two fields every domain requires; return ``name``.

    Shared by every per-domain builder below — one non-empty string
    ``name`` and one non-empty markdown body (PLACEHOLDER text satisfies
    the body requirement, same as today).
    """
    name = entry.meta.get("name")
    if not name or not isinstance(name, str):
        msg = f"{entry.path}: 'name' (string) is required."
        raise ContentError(msg)
    if not entry.body:
        msg = f"{entry.path}: description body is required (PLACEHOLDER is fine)."
        raise ContentError(msg)
    return name


def _build_trait_fixture(entry: ContentEntry, *, trait_type: str) -> dict:
    """Map a stats/ or skills/ entry to a traits.Trait fixture object.

    No "pk" key: with NaturalKeyManager.get_by_natural_key on the model,
    loaddata resolves existing rows by name and UPDATES them.
    """
    name = _require_name_and_body(entry)
    category = entry.meta.get("category")
    if category not in TRAIT_CATEGORIES:
        msg = f"{entry.path}: 'category' must be one of {sorted(TRAIT_CATEGORIES)}."
        raise ContentError(msg)
    return {
        "model": "traits.trait",
        "fields": {
            "name": name,
            "trait_type": trait_type,
            "category": category,
            "description": entry.body,
        },
    }


def _build_npc_role_fixture(entry: ContentEntry) -> dict:
    """Map an npc_roles/ entry to an npc_services.NPCRole fixture object.

    Required: ``name``. Optional: ``faction_affiliation`` (an Organization
    name, resolved eagerly below — raises ContentError if not found, same
    error-collection shape as a bad ``category``), ``default_rapport_starting_value``
    (int), ``default_description_template`` (string; the class-1 nameless-NPC
    flavor line, distinct from ``description`` — ratified Q1: a second
    optional key on the same file, body stays the full ``description``).

    ``faction_affiliation`` is three-state (#2266 review fix; see the module
    docstring): key ABSENT from frontmatter omits the field (UPDATE leaves the
    existing value untouched); key PRESENT but null/empty emits ``None``
    (UPDATE clears it — ``NPCRole.faction_affiliation`` is nullable); key
    PRESENT with a non-empty string resolves/validates it as an Organization
    name. Without this, a builder that only checked truthiness would make the
    field one-way-sticky — content could set it but never clear it back out.
    """
    name = _require_name_and_body(entry)
    fields: dict = {"name": name, "description": entry.body}

    if FIELD_FACTION_AFFILIATION in entry.meta:
        faction = entry.meta[FIELD_FACTION_AFFILIATION]
        if not faction:
            # Explicit null/empty: clear the FK on UPDATE. NPCRole.faction_affiliation
            # is nullable (null=True, blank=True), so a bare None is a valid
            # update_or_create default.
            fields[FIELD_FACTION_AFFILIATION] = None
        elif not isinstance(faction, str):
            msg = f"{entry.path}: 'faction_affiliation' must be a string (org name)."
            raise ContentError(msg)
        else:
            from world.societies.models import Organization  # noqa: PLC0415

            try:
                Organization.objects.get_by_natural_key(faction)
            except Organization.DoesNotExist:
                msg = f"{entry.path}: 'faction_affiliation' organization {faction!r} not found."
                raise ContentError(msg) from None
            # Django's own natural-key fixture convention (a 1-element list) —
            # keeps this JSON-serializable; load_entries resolves it back to an
            # instance right before the write.
            fields[FIELD_FACTION_AFFILIATION] = [faction]

    if FIELD_DEFAULT_RAPPORT_STARTING_VALUE in entry.meta:
        value = entry.meta[FIELD_DEFAULT_RAPPORT_STARTING_VALUE]
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"{entry.path}: 'default_rapport_starting_value' must be an int."
            raise ContentError(msg)
        fields[FIELD_DEFAULT_RAPPORT_STARTING_VALUE] = value

    if FIELD_DEFAULT_DESCRIPTION_TEMPLATE in entry.meta:
        template = entry.meta[FIELD_DEFAULT_DESCRIPTION_TEMPLATE]
        if not isinstance(template, str):
            msg = f"{entry.path}: 'default_description_template' must be a string."
            raise ContentError(msg)
        fields[FIELD_DEFAULT_DESCRIPTION_TEMPLATE] = template

    return {"model": "npc_services.npcrole", "fields": fields}


def _build_item_template_fixture(entry: ContentEntry) -> dict:
    """Map an items/ entry to an items.ItemTemplate fixture object.

    Required: ``name``. Optional: ``value`` (int), ``weight`` (decimal).
    Mechanical/balance flags (is_consumable, container sizing, etc.) stay
    admin/seeder-authored — this pipeline is for prose + identity, not
    tuning (matches the stats/skills precedent).
    """
    name = _require_name_and_body(entry)
    fields: dict = {"name": name, "description": entry.body}

    if FIELD_VALUE in entry.meta:
        value = entry.meta[FIELD_VALUE]
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"{entry.path}: 'value' must be an int."
            raise ContentError(msg)
        fields[FIELD_VALUE] = value

    if FIELD_WEIGHT in entry.meta:
        weight = entry.meta[FIELD_WEIGHT]
        if not isinstance(weight, int | float) or isinstance(weight, bool):
            msg = f"{entry.path}: 'weight' must be a number."
            raise ContentError(msg)
        fields[FIELD_WEIGHT] = str(weight)

    return {"model": "items.itemtemplate", "fields": fields}


def _build_building_kind_fixture(entry: ContentEntry) -> dict:
    """Map a building_kinds/ entry to a buildings.BuildingKind fixture object.

    Required: ``name``. Body → ``description``. Descriptive flags
    (is_residential, is_commercial, ...) stay admin/seeder-authored.
    """
    name = _require_name_and_body(entry)
    return {
        "model": "buildings.buildingkind",
        "fields": {"name": name, "description": entry.body},
    }


def _build_decoration_kind_fixture(entry: ContentEntry) -> dict:
    """Map a decoration_kinds/ entry to a buildings.DecorationKind fixture object.

    Required: ``name``. Body → ``description``. ``amenity``/affinity
    magnitudes stay admin/seeder-authored.
    """
    name = _require_name_and_body(entry)
    return {
        "model": "buildings.decorationkind",
        "fields": {"name": name, "description": entry.body},
    }


# domain dir -> {builder callable, output fixture path relative to src/}
DOMAIN_BUILDERS = {
    "stats": {
        "builder": partial(_build_trait_fixture, trait_type="stat"),
        "output": "world/traits/fixtures/content_stats.json",
    },
    "skills": {
        "builder": partial(_build_trait_fixture, trait_type="skill"),
        "output": "world/traits/fixtures/content_skills.json",
    },
    "npc_roles": {
        "builder": _build_npc_role_fixture,
        "output": "world/npc_services/fixtures/content_npc_roles.json",
    },
    "items": {
        "builder": _build_item_template_fixture,
        "output": "world/items/fixtures/content_items.json",
    },
    "building_kinds": {
        "builder": _build_building_kind_fixture,
        "output": "world/buildings/fixtures/content_building_kinds.json",
    },
    "decoration_kinds": {
        "builder": _build_decoration_kind_fixture,
        "output": "world/buildings/fixtures/content_decoration_kinds.json",
    },
}


def build_fixture_json(content_root: Path, result: BuildResult) -> None:
    """Scan ``content_root/fixtures/`` for raw Django fixture JSON files.

    Each ``.json`` file is an array of ``{"model": "app.model", "fields": {...}}``
    objects (optionally with a ``"pk"`` key that is stripped — upsert is by
    natural key, not pk). Objects are appended into ``result.fixtures`` using
    the source file path as the key, with corresponding ``source_paths`` for
    error reporting.

    Fully dynamic: no hardcoded model list. Models are resolved at load time
    in ``load_entries`` via ``apps.get_model``. Stale labels (renamed/removed
    models) are skipped there with a warning in ``result.skipped``.

    FK values that are lists (Django's natural-key fixture convention, e.g.
    ``"resonance": ["resonance", "Insidia"]``) are left as-is in the fields
    dict — ``_resolve_natural_key_fields`` resolves them at upsert time.

    ``fixtures/grid/`` is excluded (#2448): ``grid_export.export_grid_bundles``
    writes one JSON file per AUTHORED area there, but in a different shape (a
    single ``{"format": ..., "area": ..., "rooms": [...], ...}`` bundle dict,
    not an array of fixture objects) — ``load_grid_bundles`` is the only
    reader for that subtree. Without this exclusion, any content repo with
    authored grid content would fail every ``build_all`` call (including
    ``--check``) with "expected a JSON array of fixture objects."
    """
    fixtures_dir = content_root / "fixtures"
    if not fixtures_dir.is_dir():
        return
    grid_dir = fixtures_dir / "grid"
    for path in sorted(fixtures_dir.rglob("*.json")):
        if path.is_relative_to(grid_dir):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"{path}: invalid JSON: {exc}"
            raise ContentError(msg) from exc
        if not isinstance(raw, list):
            msg = f"{path}: expected a JSON array of fixture objects."
            raise ContentError(msg)
        if not raw:
            continue
        key = str(path.relative_to(content_root))
        result.fixtures[key] = raw
        result.source_paths[key] = [path] * len(raw)


def build_all(content_root: Path) -> BuildResult:
    """Walk known domains under ``content_root``; parse, validate, build.

    Also scans ``content_root/fixtures/`` for raw Django fixture JSON files
    (the lore repo's primary content format). Unknown directories are
    reference canon — ignored by design. Raises ``ContentError`` (with every
    failing file listed) when validation fails.
    """
    result = BuildResult()
    errors: list[str] = []
    for domain, config in DOMAIN_BUILDERS.items():
        domain_dir = content_root / domain
        if not domain_dir.is_dir():
            continue
        objects: list[dict] = []
        paths: list[Path] = []
        for path in sorted(domain_dir.rglob("*.md")):
            try:
                entry = parse_content_file(path, domain)
                objects.append(config["builder"](entry))
                paths.append(entry.path)
                result.entries.append(entry)
                if entry.has_placeholder:
                    result.placeholder_counts[domain] = result.placeholder_counts.get(domain, 0) + 1
            except ContentError as exc:
                errors.append(str(exc))
        if objects:
            result.fixtures[config["output"]] = objects
            result.source_paths[config["output"]] = paths
    # Raw fixture JSON from the lore repo's fixtures/ directory.
    try:
        build_fixture_json(content_root, result)
    except ContentError as exc:
        errors.append(str(exc))
    if errors:
        msg = "Content validation failed:\n" + "\n".join(errors)
        raise ContentError(msg)
    return result


def _resolve_natural_key_fields(model, fields: dict, source_path: Path | None) -> None:
    """Swap any natural-key-list field values in *fields* for real instances.

    A builder emits an FK-by-name value as a 1-element list (Django's own
    fixture natural-key convention — see the module docstring); this
    resolves it back into the related model's instance immediately before
    the upsert, using that related model's own ``get_by_natural_key``
    (``NaturalKeyMixin`` — no bespoke lookup table here). Raises
    ContentError, naming the source file, if the target no longer exists
    (build-time validation already checked this once; re-checking here is
    the only way to guarantee correctness against a DB that may have
    changed between build and load).

    Guard (#2266 review fix): ``isinstance(value, list)`` alone only tells us
    a builder emitted a list; it says nothing about whether the *field* is
    relational. A plain (non-FK) model field that happened to be list-valued
    would fall through to ``get_field(...).related_model`` and raise a bare
    ``AttributeError`` (regular ``Field`` has no ``related_model`` attribute
    — only relation fields do), crashing ``load_entries`` mid-batch instead
    of failing cleanly. So this checks ``field.is_relation`` first and raises
    a normal ``ContentError`` naming the field (and the source file, when
    known) for a non-relational list value, matching every other validation
    failure's error style in this module.
    """
    for field_name, value in list(fields.items()):
        if not isinstance(value, list):
            continue
        field = model._meta.get_field(field_name)  # noqa: SLF001
        location = source_path if source_path is not None else model._meta.label  # noqa: SLF001
        if not field.is_relation:
            msg = (
                f"{location}: {field_name!r} on {model._meta.label} is a list-valued "  # noqa: SLF001
                "field but not a relational one — natural-key resolution only "
                "supports FK-by-name values (a 1-element list)."
            )
            raise ContentError(msg)
        related_model = field.related_model
        from django.core.exceptions import (  # noqa: PLC0415
            ObjectDoesNotExist as _ObjectDoesNotExist,
        )

        try:
            fields[field_name] = related_model.objects.get_by_natural_key(*value)
        except related_model.DoesNotExist:
            msg = f"{location}: {field_name!r} {related_model.__name__} {value!r} not found."
            raise UnresolvedNaturalKeyError(msg) from None
        except _ObjectDoesNotExist as exc:
            # A nested FK resolution (inside get_by_natural_key →
            # _resolve_fk_arg) raises a DIFFERENT model's DoesNotExist —
            # not related_model.DoesNotExist. Catch the base class to
            # cover that case too.
            msg = (
                f"{location}: {field_name!r} {related_model.__name__} "
                f"{value!r} not found (nested: {exc})."
            )
            raise UnresolvedNaturalKeyError(msg) from None


def _pop_m2m_fields(model, fields: dict) -> dict[str, list]:
    """Pop many-to-many field values out of *fields*, keyed by field name.

    A many-to-many field with natural keys serializes as a LIST OF natural-key
    lists (e.g. ``"resonances": [["Insidia"], ["Ember"]]``, or ``[]`` when
    empty — Django's own serializer always emits the key, even for an
    untouched m2m). That value shape doesn't fit ``_resolve_natural_key_fields``,
    which resolves exactly one related instance per field (a to-one FK's
    natural key). Nor can it be passed through ``update_or_create``'s
    ``defaults``: assigning a many-to-many field requires an already-saved
    instance, so ``_upsert_fixture_object`` applies these via ``.set()`` after
    the row is upserted (see ``_resolve_m2m_fields``). Checking
    ``field.many_to_many`` (true only for ``ManyToManyField``, never for a
    ``ForeignKey``) keeps this purely structural — no reliance on the value's
    shape, unlike the FK-vs-non-relational check in
    ``_resolve_natural_key_fields``.

    Stale-field tolerance (#2474 review fix): a fixture field naming a
    removed/renamed model field makes ``get_field`` raise
    ``FieldDoesNotExist`` — NOT a ``FieldError`` subclass, so it would
    otherwise escape this function uncaught and crash the entire
    ``load_entries`` run for every object, not just the offending row (this
    function is called before ``_upsert_fixture_object``'s guarded
    try/except). A field that doesn't exist on the model definitely isn't an
    m2m field, so it's simply left in *fields* untouched — the existing
    schema-drift handling downstream (the ``FieldError``/``TypeError`` catch
    in ``_upsert_fixture_object``) skips that row with a diagnostic exactly
    as it already does for a stale field on a model with no m2m fields at
    all.
    """
    from django.core.exceptions import FieldDoesNotExist  # noqa: PLC0415

    m2m_fields: dict[str, list] = {}
    for field_name in list(fields):
        try:
            field = model._meta.get_field(field_name)  # noqa: SLF001
        except FieldDoesNotExist:
            continue
        if field.many_to_many:
            m2m_fields[field_name] = fields.pop(field_name)
    return m2m_fields


def _resolve_m2m_fields(
    model, m2m_fields: dict[str, list], source_path: Path | None
) -> dict[str, list]:
    """Resolve each m2m field's natural-key-list values into model instances.

    Mirrors ``_resolve_natural_key_fields``'s not-found handling (raises
    ``UnresolvedNaturalKeyError``, the one failure mode ``load_world_content``
    defers) but resolves a LIST of related instances per field instead of one.
    """
    resolved: dict[str, list] = {}
    for field_name, values in m2m_fields.items():
        field = model._meta.get_field(field_name)  # noqa: SLF001
        related_model = field.related_model
        location = source_path if source_path is not None else model._meta.label  # noqa: SLF001
        instances = []
        for value in values:
            from django.core.exceptions import (  # noqa: PLC0415
                ObjectDoesNotExist as _ObjectDoesNotExist,
            )

            try:
                instances.append(related_model.objects.get_by_natural_key(*value))
            except related_model.DoesNotExist:
                msg = f"{location}: {field_name!r} {related_model.__name__} {value!r} not found."
                raise UnresolvedNaturalKeyError(msg) from None
            except _ObjectDoesNotExist as exc:
                msg = (
                    f"{location}: {field_name!r} {related_model.__name__} "
                    f"{value!r} not found (nested: {exc})."
                )
                raise UnresolvedNaturalKeyError(msg) from None
        resolved[field_name] = instances
    return resolved


def _extract_natural_key(model, fields: dict, source_path: Path | None) -> dict:
    """Pop the natural-key fields from *fields* and return them as a lookup dict.

    For models with ``NaturalKeyMixin``, pops each field listed in
    ``NaturalKeyConfig.fields`` from *fields* (so they are NOT passed in
    ``defaults`` to ``update_or_create`` — passing them would be a no-op on
    UPDATE but would shadow the lookup on CREATE for auto-gen fields).

    For models WITHOUT ``NaturalKeyMixin``, raises ``ContentError`` naming
    the model and source file. The loader cannot upsert without a natural key
    — ``loaddata``'s pk-based INSERT is the only other option, and that path
    is unsafe for ``SharedMemoryModel`` (see ``load_entries`` docstring).
    """
    from core.natural_keys import NaturalKeyMixin  # noqa: PLC0415

    if not issubclass(model, NaturalKeyMixin):
        location = source_path if source_path is not None else model._meta.label  # noqa: SLF001
        msg = (
            f"{location}: model {model.__name__} lacks NaturalKeyMixin — "
            "cannot upsert by natural key. Add NaturalKeyMixin to the model "
            "or skip this fixture."
        )
        raise ContentError(msg)

    config = model.NaturalKeyConfig
    lookup: dict = {}
    for field_name in config.fields:
        if field_name not in fields:
            location = source_path if source_path is not None else model._meta.label  # noqa: SLF001
            msg = (
                f"{location}: natural-key field {field_name!r} not found in "
                f"fixture fields for {model.__name__}."
            )
            raise ContentError(msg)
        lookup[field_name] = fields.pop(field_name)
    return lookup


def _coerce_scalar_fields(model, fields: dict) -> None:
    """Normalize JSON-native scalar values into the types their model fields expect.

    ``json.loads`` only ever produces ``str``/``int``/``float``/``bool``/``None``/
    ``list``/``dict`` — types that happen to satisfy most Django field types
    unmodified (``CharField``, ``IntegerField``, ``BooleanField``, ``DateField``,
    ``DateTimeField`` and ``DecimalField`` all self-correct: their own
    ``get_prep_value``/``get_db_prep_value`` calls ``to_python`` internally).
    ``DurationField`` does not — its ``get_db_prep_value`` requires an actual
    ``timedelta`` and calls ``.days``/``.seconds`` on whatever it is given, so a
    still-a-string value blows up with a bare ``AttributeError`` deep in the SQL
    compiler (#2470: ``MissionTemplate.cooldown`` was the first content model
    field to hit this). Django's own fixture deserializer
    (``django.core.serializers.python.Deserializer``) avoids the whole class of
    bug by calling ``field.to_python(value)`` on every scalar field; this loader
    bypasses that deserializer entirely (it needs upsert-by-natural-key, not
    ``loaddata``'s pk-based insert — see the module docstring), so it has to redo
    the same per-field normalization here. Calling ``to_python`` on a value that
    is already the right type is a harmless no-op for every field above, so this
    runs unconditionally rather than special-casing ``DurationField``.

    Relational fields are skipped: a to-one FK's natural-key list has already
    been swapped for a real instance by ``_resolve_natural_key_fields`` by the
    time this runs, and m2m fields are popped out of *fields* before either
    function ever sees them. A fixture field naming a removed/renamed model
    field is left untouched here too (mirrors ``_pop_m2m_fields``'s stale-field
    tolerance) — the existing schema-drift handling downstream still catches it.
    """
    from django.core.exceptions import FieldDoesNotExist  # noqa: PLC0415

    for field_name, value in fields.items():
        if value is None:
            continue
        try:
            field = model._meta.get_field(field_name)  # noqa: SLF001
        except FieldDoesNotExist:
            continue
        if field.is_relation:
            continue
        fields[field_name] = field.to_python(value)


def _upsert_fixture_object(  # noqa: C901 — one branch per distinct skip reason, see docstring
    model: type,
    obj: dict,
    source_path: Path | None,
    result: BuildResult,
    *,
    defer_unresolved: bool = False,
) -> str:
    """Upsert one already-model-resolved fixture object.

    Returns ``"created"``, ``"updated"``, ``"skipped"``, or ``"deferred"``.
    Factored out of ``load_entries`` (#2448) so ``load_world_content``'s
    deferred-retry pass (after the grid bundles load) reuses this exact upsert
    body instead of a second hand-maintained copy. ``model`` is already
    resolved via ``apps.get_model`` — the stale-model-label skip stays at each
    call site, since that is a lookup failure that happens before any
    per-object upsert logic runs.

    Only ``UnresolvedNaturalKeyError`` defers, and only when
    ``defer_unresolved`` is true — every other failure mode (bad shape, stale
    field, constraint violation, or an unresolved FK when the flag is false)
    still lands in ``result.skipped`` with the exact same message text as
    before this function was factored out.
    """
    from django.core.exceptions import FieldError, ValidationError  # noqa: PLC0415
    from django.db import IntegrityError  # noqa: PLC0415

    from core.natural_keys import NaturalKeyConfigError  # noqa: PLC0415

    fields = dict(obj["fields"])
    # Strip pk if present — upsert is by natural key, not pk.
    fields.pop("pk", None)
    try:
        lookup = _extract_natural_key(model, fields, source_path)
    except ContentError as exc:
        result.skipped.append(str(exc))
        return OUTCOME_SKIPPED

    # Many-to-many values (#2474) can't be resolved/assigned the same way as a
    # to-one FK's natural key — pulled out here so _resolve_natural_key_fields
    # below never sees them, and applied via .set() after a successful upsert.
    m2m_fields = _pop_m2m_fields(model, fields)

    # Resolve natural-key-list FK values in both the lookup (the natural-key
    # fields themselves) and the remaining defaults. Each except clause below
    # only sets skip_msg (never returns directly) so this function keeps a
    # single skip-vs-success branch at the end, rather than one return per
    # exception type (ruff PLR0911) — the only early return is the
    # UnresolvedNaturalKeyError-and-deferring case, which is a genuinely
    # distinct outcome ("deferred") from every other skip.
    created = False
    skip_msg: str | None = None
    instance = None
    resolved_m2m: dict[str, list] = {}
    try:
        _resolve_natural_key_fields(model, lookup, source_path)
        _resolve_natural_key_fields(model, fields, source_path)
        resolved_m2m = _resolve_m2m_fields(model, m2m_fields, source_path)
        _coerce_scalar_fields(model, fields)
        instance, created = model.objects.update_or_create(**lookup, defaults=fields)
    except UnresolvedNaturalKeyError as exc:
        # Must be caught before the broader ContentError clause below (it's a
        # subclass) — this is the ONLY failure mode ever deferred.
        if defer_unresolved:
            return OUTCOME_DEFERRED
        skip_msg = f"{source_path}: {model.__name__} could not be loaded: {exc}"
    except NaturalKeyConfigError as exc:
        # Arity mismatch (wrong number of natural-key values). Must be caught
        # before the broader (ValueError, TypeError) clause below —
        # NaturalKeyConfigError IS a ValueError subclass, so without this
        # dedicated clause it would silently fall into the pk-based-FK-
        # reference branch and report the wrong skip reason (Sonar python:S1045
        # flagged the resulting dead tuple member once this line changed).
        skip_msg = f"{source_path}: {model.__name__} could not be loaded: {exc}"
    except (ValueError, TypeError) as exc:
        # A FK value that is a raw integer (pk-based fixture) rather than a
        # natural-key list causes a ValueError on assignment. These fixtures
        # can't be upserted by natural key — skip.
        skip_msg = (
            f"{source_path}: {model.__name__} could not be loaded "
            f"(likely pk-based FK reference): {exc}"
        )
    except (ContentError, FieldError, ValidationError) as exc:
        # FK resolution failure or schema drift. ContentError covers every
        # OTHER re-raised failure from _resolve_natural_key_fields (the
        # non-relational-list-field case) plus _extract_natural_key's own
        # errors; FieldError covers fixture fields that no longer exist on
        # the model. ValidationError covers a scalar value
        # ``_coerce_scalar_fields`` can't parse into its field's type (e.g. a
        # malformed duration string).
        skip_msg = f"{source_path}: {model.__name__} could not be loaded: {exc}"
    except model.DoesNotExist as exc:
        # The model's own DoesNotExist — the natural-key lookup didn't find
        # an existing row (shouldn't happen for update_or_create, but catch
        # just in case).
        skip_msg = f"{source_path}: {model.__name__} could not be loaded (lookup failed): {exc}"
    except IntegrityError as exc:
        # DB constraint violation (e.g. a unique constraint on a
        # non-natural-key field that the fixture data violates). The record
        # can't be loaded — skip it.
        skip_msg = (
            f"{source_path}: {model.__name__} could not be loaded (constraint violation): {exc}"
        )

    if skip_msg is not None:
        result.skipped.append(skip_msg)
        return OUTCOME_SKIPPED
    for field_name, instances in resolved_m2m.items():
        getattr(instance, field_name).set(instances)
    return OUTCOME_CREATED if created else OUTCOME_UPDATED


def load_entries(
    result: BuildResult, *, defer_unresolved: bool = False
) -> tuple[int, int, list[tuple[dict, Path | None]]]:
    """Upsert built objects into the database; returns (created, updated, deferred).

    Deliberately NOT ``loaddata``: SharedMemoryModel's identity map
    intercepts construction-by-pk and returns the cached old instance,
    silently discarding a fixture's new field values — so natural-key
    loaddata can INSERT but never UPDATE idmapper models (verified
    cross-process, #944). ``update_or_create`` mutates the live instance
    explicitly, which the identity map handles correctly. The emitted
    fixture JSON remains valid for FRESH-database seeding (pure inserts).

    Handles two sources of objects in ``result.fixtures``:

    - **YAML frontmatter entries** (built by the per-domain builders) — use
      ``name`` as the natural key (every frontmatter domain's model has a
      DB-unique ``name``).
    - **Raw fixture JSON** (loaded by ``build_fixture_json``) — resolve the
      natural key from the model's own ``NaturalKeyConfig.fields`` via
      ``_extract_natural_key``, so models with composite keys (e.g.
      ``ConditionStage`` keyed on ``condition`` + ``stage_order``) work too.

    Both paths share the same ``_resolve_natural_key_fields`` pass for FK
    natural-key-list values, via the per-object ``_upsert_fixture_object``.

    Stale model labels (referencing renamed/removed models) are skipped with
    a warning written to ``result.skipped`` — the load does not fail, but the
    skip is visible to the operator.

    ``defer_unresolved`` (#2448): when true, returns a THIRD tuple element —
    ``deferred``, a list of ``(obj, source_path)`` pairs that failed only on
    an ``UnresolvedNaturalKeyError`` (a natural-key FK target that doesn't
    exist YET, e.g. a room the grid bundles haven't imported). Every other
    failure mode still lands in ``result.skipped`` exactly as when the flag
    is false (the default) — this method's return shape and every skip
    message are otherwise byte-for-byte identical to before this flag
    existed. ``load_world_content`` is the only caller that sets it; it
    retries the deferred pairs to a FIXED POINT after the grid bundles have
    loaded — repeated passes until a pass makes no further progress (#2474
    review fix), not just a single retry — since a deferred object can itself
    depend on another deferred object (e.g. a ``Technique`` naming a ``Gift``
    that was ALSO deferred).

    When ``defer_unresolved`` is false the ``deferred`` element is an empty
    list — the tuple shape is always ``(created, updated, deferred)``.

    Requires Django to be configured; imports are deferred so the module
    stays import-safe for pure validation.
    """
    from django.apps import apps  # noqa: PLC0415

    created_count = 0
    updated_count = 0
    deferred: list[tuple[dict, Path | None]] = []
    for output_path, objects in result.fixtures.items():
        paths = result.source_paths.get(output_path, [])
        for obj, source_path in zip(objects, paths, strict=False):
            app_label, model_name = obj["model"].split(".")
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                result.skipped.append(
                    f"{source_path}: stale model {obj['model']!r} (renamed or removed) — skipped."
                )
                continue
            outcome = _upsert_fixture_object(
                model, obj, source_path, result, defer_unresolved=defer_unresolved
            )
            if outcome == OUTCOME_CREATED:
                created_count += 1
            elif outcome == OUTCOME_UPDATED:
                updated_count += 1
            elif outcome == OUTCOME_DEFERRED:
                deferred.append((obj, source_path))
    return created_count, updated_count, deferred


@dataclass
class WorldLoadResult:
    """Outcome of ``load_world_content``'s full content-fixtures + grid load (#2448).

    ``created``/``updated`` are the FINAL counts after the deferred-retry
    passes (plural — retried to a fixed point, #2474 review fix) — an object
    that resolved on any retry pass counts as created/updated here, not
    separately. ``deferred_resolved`` is how many of those came from a retry
    pass (visibility into how much the content-then-grid ordering mattered
    this run). ``skipped`` is the terminal skip list: an object still
    unresolved after retrying stopped making progress is a genuine gap, not a race.
    """

    created: int
    updated: int
    grid: GridImportResult
    skipped: list[str]
    deferred_resolved: int


def _retry_deferred(
    deferred: list[tuple[dict, Path | None]], result: BuildResult
) -> tuple[int, int, int]:
    """Retry deferred fixture objects to a fixed point (#2474/#2486).

    A single retry pass is not enough: catalog fixtures chain natural-key
    dependencies ≥ 2 levels deep against alphabetical load order (grant →
    technique → gift → resonance), so each pass runs with deferral ON until a
    pass resolves nothing new (each productive pass strictly shrinks the
    list — bounded, no retry knob). One final pass with deferral OFF then
    turns every still-blocked object into a terminal, diagnosed entry in
    ``result.skipped`` instead of looping forever.

    Module-level (not nested in ``load_world_content``) so the multi-pass
    behavior is directly unit-testable. Returns
    ``(created, updated, deferred_resolved)``.
    """
    from django.apps import apps  # noqa: PLC0415

    created = updated = deferred_resolved = 0

    def _retry_pass(
        pending: list[tuple[dict, Path | None]], *, defer_unresolved: bool
    ) -> list[tuple[dict, Path | None]]:
        """One pass over *pending*; returns the objects still deferred."""
        nonlocal created, updated, deferred_resolved
        still_pending: list[tuple[dict, Path | None]] = []
        for obj, source_path in pending:
            app_label, model_name = obj["model"].split(".")
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                result.skipped.append(
                    f"{source_path}: stale model {obj['model']!r} (renamed or removed) — skipped."
                )
                continue
            outcome = _upsert_fixture_object(
                model, obj, source_path, result, defer_unresolved=defer_unresolved
            )
            if outcome == OUTCOME_CREATED:
                created += 1
                deferred_resolved += 1
            elif outcome == OUTCOME_UPDATED:
                updated += 1
                deferred_resolved += 1
            elif outcome == OUTCOME_DEFERRED:
                still_pending.append((obj, source_path))
            # OUTCOME_SKIPPED: message already appended to result.skipped.
        return still_pending

    pending = deferred
    while pending:
        next_pending = _retry_pass(pending, defer_unresolved=True)
        if len(next_pending) == len(pending):
            # Fixed point: this pass resolved and skipped nothing — every
            # remaining object is still blocked for the same reason. One
            # last pass with deferral off turns each into a terminal,
            # diagnosed skip instead of looping forever.
            _retry_pass(next_pending, defer_unresolved=False)
            break
        pending = next_pending

    return created, updated, deferred_resolved


def load_world_content(content_root: Path) -> WorldLoadResult:
    """Sequence content fixtures -> grid bundles -> deferred natural-key retry (#2448).

    Closes the circular dependency between content fixtures and the grid:
    e.g. a ``StartingArea`` fixture's ``default_starting_room`` names a room
    by its ``RoomProfile`` natural key (``fixture_key``), but that room only
    exists once the grid bundles (Task 4's ``load_grid_bundles``) import —
    and the grid bundles are a separate file tree from the content fixtures.
    Neither can safely load first if the other's target might not exist yet,
    so this driver:

    1. Builds + loads the content fixtures with ``defer_unresolved=True`` —
       an unresolved natural-key FK target (only that failure mode) is queued
       instead of skipped.
    2. Loads the grid bundles (creating the rooms/areas/exits those FK
       targets may have named).
    3. Retries the deferred set to a FIXED POINT (#2474 review fix), not just
       once: a multi-hop chain (e.g. ``PathGiftGrant.starter_techniques`` names
       a ``Technique``, which itself names a ``Gift`` that was ALSO deferred)
       can need more than one retry pass to fully resolve, since alphabetical
       file order can attempt the grant before the technique it depends on
       even within the retry set. Each pass keeps ``defer_unresolved=True`` so
       a still-blocked object stays queued rather than skipping early; the
       pass loops while it makes progress (the deferred set shrinks — either
       something resolved or a genuinely different failure permanently
       skipped it). Once a pass resolves/skips nothing new, one final pass
       runs with ``defer_unresolved=False`` so every object still stuck lands
       in ``skipped`` with a diagnostic — exactly the same terminal shape as
       today's single-pass skip, just reached only once retrying stops paying off.

    Requires Django to be configured (delegates to ``build_all``/
    ``load_entries``/``load_grid_bundles``, all of which need it); imports of
    those are deferred so this module stays import-safe for pure validation
    callers that never load.
    """
    from core_management.grid_import import load_grid_bundles  # noqa: PLC0415

    result = build_all(content_root)
    created, updated, deferred = load_entries(result, defer_unresolved=True)
    grid = load_grid_bundles(content_root)

    retry_created, retry_updated, deferred_resolved = _retry_deferred(deferred, result)
    created += retry_created
    updated += retry_updated

    return WorldLoadResult(
        created=created,
        updated=updated,
        grid=grid,
        skipped=result.skipped,
        deferred_resolved=deferred_resolved,
    )


def write_fixtures(result: BuildResult, src_root: Path) -> list[Path]:
    """Write fixture JSON files under ``src_root``; returns written paths.

    Output dirs are inside the gitignored ``**/fixtures/`` tree — generated
    artifacts, never committed; the content repo is the durable source.
    """
    written: list[Path] = []
    for rel_path, objects in result.fixtures.items():
        out = src_root / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(objects, indent=2, ensure_ascii=False) + "\n", "utf-8")
        written.append(out)
    return written
