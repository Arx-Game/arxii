"""Content pipeline core (#944, #2266): private authored content → fixture JSON.

The maintainers' content repository (never named in this repo — located via
the ``CONTENT_REPO_PATH`` env var) holds one file per entry: YAML
frontmatter for mechanical keys, markdown body for prose. This module
parses, validates, and emits Django fixture JSON serialized with natural
keys, so ``loaddata`` upserts by identity — idempotent across database
wipes, pk churn, and migration rebuilds.

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
mechanism needed. This is the convention every optional field in this module
follows (``default_rapport_starting_value``, ``default_description_template``,
``faction_affiliation``, ``value``, ``weight``) — keep it when adding more.

FK-by-name fields (``faction_affiliation``) are emitted in the fixture using
Django's own natural-key fixture convention — a one-element list
(``["Org Name"]``) — rather than a resolved pk or model instance, so the
generated JSON stays plain-JSON-serializable (``write_fixtures`` just calls
``json.dumps``) and also stays loadable by a real ``loaddata`` against a
fresh DB, since ``Organization`` already carries ``NaturalKeyMixin``
(``world/societies/models.py``) — no new natural-key infrastructure needed.
``load_entries`` resolves that list back into a real instance immediately
before the write.

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

import yaml

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


class ContentError(Exception):
    """A content file failed validation. Message carries file + reason."""


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
    """
    name = _require_name_and_body(entry)
    fields: dict = {"name": name, "description": entry.body}

    faction = entry.meta.get(FIELD_FACTION_AFFILIATION)
    if faction:
        if not isinstance(faction, str):
            msg = f"{entry.path}: 'faction_affiliation' must be a string (org name)."
            raise ContentError(msg)
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


def build_all(content_root: Path) -> BuildResult:
    """Walk known domains under ``content_root``; parse, validate, build.

    Unknown directories are reference canon — ignored by design. Raises
    ContentError (with every failing file listed) when validation fails.
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
    """
    for field_name, value in list(fields.items()):
        if not isinstance(value, list):
            continue
        related_model = model._meta.get_field(field_name).related_model  # noqa: SLF001
        try:
            fields[field_name] = related_model.objects.get_by_natural_key(*value)
        except related_model.DoesNotExist:
            location = source_path if source_path is not None else model._meta.label  # noqa: SLF001
            msg = f"{location}: {field_name!r} {related_model.__name__} {value!r} not found."
            raise ContentError(msg) from None


def load_entries(result: BuildResult) -> tuple[int, int]:
    """Upsert built objects into the database; returns (created, updated).

    Deliberately NOT ``loaddata``: SharedMemoryModel's identity map
    intercepts construction-by-pk and returns the cached old instance,
    silently discarding a fixture's new field values — so natural-key
    loaddata can INSERT but never UPDATE idmapper models (verified
    cross-process, #944). ``update_or_create`` mutates the live instance
    explicitly, which the identity map handles correctly. The emitted
    fixture JSON remains valid for FRESH-database seeding (pure inserts).

    Requires Django to be configured; imports are deferred so the module
    stays import-safe for pure validation.
    """
    from django.apps import apps  # noqa: PLC0415

    created_count = 0
    updated_count = 0
    for output_path, objects in result.fixtures.items():
        paths = result.source_paths.get(output_path, [])
        for obj, source_path in zip(objects, paths, strict=False):
            app_label, model_name = obj["model"].split(".")
            model = apps.get_model(app_label, model_name)
            fields = dict(obj["fields"])
            name = fields.pop("name")
            _resolve_natural_key_fields(model, fields, source_path)
            _, created = model.objects.update_or_create(name=name, defaults=fields)
            if created:
                created_count += 1
            else:
                updated_count += 1
    return created_count, updated_count


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
