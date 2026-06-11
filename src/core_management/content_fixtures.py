"""Content pipeline core (#944): private authored content → fixture JSON.

The maintainers' content repository (never named in this repo — located via
the ``CONTENT_REPO_PATH`` env var) holds one file per entry: YAML
frontmatter for mechanical keys, markdown body for prose. This module
parses, validates, and emits Django fixture JSON serialized with natural
keys, so ``loaddata`` upserts by identity — idempotent across database
wipes, pk churn, and migration rebuilds.

Import-safe without Django configured (the tools wrapper and tests use it
standalone); only fixture WRITING touches the filesystem and nothing here
touches the database.

Phase 1 domains: ``stats/`` and ``skills/`` → ``traits.Trait`` rows
(name, type, category, description). Wrapper models without natural keys
(e.g. ``skills.Skill``) onboard in later phases once they grow them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

import yaml

PLACEHOLDER_MARK = "PLACEHOLDER"

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

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


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


def parse_content_file(path: Path, domain: str) -> ContentEntry:
    """Parse one frontmatter+markdown file; raise ContentError on shape errors."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        msg = f"{path}: missing YAML frontmatter block (--- ... ---)."
        raise ContentError(msg)
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        msg = f"{path}: invalid YAML frontmatter: {exc}"
        raise ContentError(msg) from exc
    if not isinstance(meta, dict):
        msg = f"{path}: frontmatter must be a mapping."
        raise ContentError(msg)
    return ContentEntry(path=path, domain=domain, meta=meta, body=match.group(2).strip())


def _build_trait_fixture(entry: ContentEntry, *, trait_type: str) -> dict:
    """Map a stats/ or skills/ entry to a traits.Trait fixture object.

    No "pk" key: with NaturalKeyManager.get_by_natural_key on the model,
    loaddata resolves existing rows by name and UPDATES them.
    """
    name = entry.meta.get("name")
    if not name or not isinstance(name, str):
        msg = f"{entry.path}: 'name' (string) is required."
        raise ContentError(msg)
    category = entry.meta.get("category")
    if category not in TRAIT_CATEGORIES:
        msg = f"{entry.path}: 'category' must be one of {sorted(TRAIT_CATEGORIES)}."
        raise ContentError(msg)
    if not entry.body:
        msg = f"{entry.path}: description body is required (PLACEHOLDER is fine)."
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


# domain dir -> (builder callable kwargs, output fixture path relative to src/)
DOMAIN_BUILDERS = {
    "stats": {"trait_type": "stat", "output": "world/traits/fixtures/content_stats.json"},
    "skills": {"trait_type": "skill", "output": "world/traits/fixtures/content_skills.json"},
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
        for path in sorted(domain_dir.rglob("*.md")):
            try:
                entry = parse_content_file(path, domain)
                objects.append(_build_trait_fixture(entry, trait_type=config["trait_type"]))
                result.entries.append(entry)
                if entry.has_placeholder:
                    result.placeholder_counts[domain] = result.placeholder_counts.get(domain, 0) + 1
            except ContentError as exc:
                errors.append(str(exc))
        if objects:
            result.fixtures[config["output"]] = objects
    if errors:
        msg = "Content validation failed:\n" + "\n".join(errors)
        raise ContentError(msg)
    return result


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
    for objects in result.fixtures.values():
        for obj in objects:
            app_label, model_name = obj["model"].split(".")
            model = apps.get_model(app_label, model_name)
            fields = dict(obj["fields"])
            name = fields.pop("name")
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
