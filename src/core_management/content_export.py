"""Export authored content models to the private lore repo's fixtures/ directory.

The allowlist below defines which models are "authored content" (lore-repo
material) vs ephemeral/runtime data. Only models in this set are exported.

The export serializes each model with natural keys (no pks) and writes one
JSON file per model to ``CONTENT_REPO_PATH/fixtures/<domain>/<model_name>.json``,
where ``<domain>`` is the model's authoring domain (see ``core.app_domains``) —
today identical to its Django ``app_label``, but sourced from the model's module
path so the directory layout survives the single-app collapse (#2906).

This is the inverse of ``core_management.content_fixtures.load_entries`` —
export writes what import reads. Round-tripping (export → import) is a no-op
when nothing has changed.

Import-safe without Django configured (the tools wrapper and tests use it
standalone). All Django imports are deferred.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

from core.app_domains import domain_of, resolve_model_by_name
from core_management.content_fixtures import (
    MARKDOWN_EXPORT_DOMAINS,
    content_slug,
    render_entry_markdown,
)
from core_management.content_repo import resolve_content_root

logger = logging.getLogger(__name__)


class ContentExportError(Exception):
    """Raised when the content export fails."""


#: Curated allowlist of model labels (``app_label.model_name``) that are
#: authored content — the lore repo's domain. Models not in this set are
#: never exported. Extend this set when a new content model is added.
#:
#: Every model here must have ``NaturalKeyMixin`` so the exported fixtures
#: are identity-stable (no pk churn) and round-trip through ``load_entries``.
#:
#: **Config never belongs here** (TehomCD, 2026-07-25; ADR-0168). This set is
#: also what #2698's seeder guard reads: whatever is registered here, the
#: content repo owns and no seeder may create. So a mechanical tuning table
#: registered by mistake doesn't just bloat the corpus — it tells the seeder to
#: stop producing something the game needs.
#:
#: The pk-keyed tuning singletons (``magic.fallredemptionconfig``,
#: ``covenants.mentorbondconfig``, ``magic.soultetherconfig``) were removed for
#: exactly that reason. Their ``NaturalKeyConfig.fields`` is ``["pk"]``, and the
#: export writes no ``pk``, so ``load_entries`` could never resolve their
#: identity — both shipped fixtures existed in the lore repo for months and
#: loaded zero rows. A natural key of "pk" carries no content identity; a table
#: whose whole payload is tuning multipliers with model-level defaults is config,
#: and config is the Big Button's job.
CONTENT_MODELS: frozenset[str] = frozenset(
    {
        # achievements
        "achievements.statdefinition",
        "achievements.achievement",
        "achievements.achievementstatrequirement",
        "achievements.achievementreward",
        "achievements.rewarddefinition",
        "achievements.conditionstatrule",
        # areas
        "areas.rampartelementprofile",
        "areas.rampartelementresistance",
        # character_creation
        "character_creation.beginnings",
        "character_creation.beginningtradition",
        "character_creation.cgexplanation",
        "character_creation.startingarea",
        "character_creation.origintemplate",
        "character_creation.origintemplateslot",
        # character_sheets
        "character_sheets.gender",
        # checks
        "checks.checkcategory",
        "checks.checktype",
        "checks.checktypecapabilitymodifier",
        "checks.checktypetrait",
        # classes
        "classes.aspect",
        "classes.path",
        "classes.pathaspect",
        # clues
        "clues.clue",
        # combat
        "combat.creaturetemplate",
        "combat.threatpool",
        "combat.threatpoolentry",
        # contributors
        "contributors.contentcontributor",
        # codex
        "codex.codexcategory",
        "codex.codexentry",
        "codex.codexsubject",
        "codex.traditioncodexgrant",
        "codex.beginningscodexgrant",
        "codex.distinctioncodexgrant",
        "codex.pathcodexgrant",
        # conditions
        "conditions.capabilitytype",
        "conditions.conditioncapabilityeffect",
        "conditions.conditioncategory",
        "conditions.conditioncheckmodifier",
        "conditions.conditionconditioninteraction",
        "conditions.conditiondamageinteraction",
        "conditions.conditiondamageovertime",
        "conditions.conditionmodifiereffect",
        "conditions.conditionresistancemodifier",
        "conditions.conditionstage",
        "conditions.conditiontemplate",
        "conditions.damagetype",
        # covenants
        "covenants.covenantrole",
        "covenants.covenantrite",
        "covenants.covenantriterolepackage",
        "covenants.covenantroleactionscaling",
        "covenants.covenantrolebonus",
        "covenants.covenantroledefenseprofile",
        "covenants.covenantrolegiftgrant",
        "covenants.covenantroletechniquespecialty",
        "covenants.geararchetypecompatibility",
        "covenants.insighttableentry",
        "covenants.weaknesspoolentry",
        "covenants.vowsituationalperk",
        "covenants.vowsituationalperkrung",
        "covenants.vowsituationalperksituation",
        "covenants.vowstatscaling",
        # distinctions
        "distinctions.distinction",
        "distinctions.distinctioncategory",
        "distinctions.distinctioneffect",
        "distinctions.distinctiontag",
        # evennia_extensions
        "evennia_extensions.media",
        "evennia_extensions.pagebackground",
        "evennia_extensions.roomsizetier",
        # forms
        "forms.build",
        "forms.formtrait",
        "forms.formtraitoption",
        "forms.heightband",
        "forms.speciesformtrait",
        # flows
        "flows.flowdefinition",
        "flows.flowstepdefinition",
        "flows.triggerdefinition",
        # gm — the scenario catalog a GM browses when adapting authored content
        # (#2127/#2865). Registered so a fresh install can ship a usable JUNIOR-GM
        # catalog from the lore repo instead of per-server database state.
        "gm.situationkind",
        "gm.checktypesituationfit",
        "gm.situationdifficultyguide",
        "gm.consequencepoolguide",
        # items — crafting (#3006)
        "items.craftingmaterialrequirement",
        "items.craftingrecipe",
        "items.craftingrecipeconsequence",
        "items.craftingskillcap",
        "items.itemtemplateproperty",
        # magic
        "magic.affinity",
        "magic.compromiseacttype",
        "magic.dramaticmomenttype",
        "magic.effecttype",
        "magic.facet",
        "magic.gift",
        "magic.giftunlock",
        "magic.glimpsetag",
        "magic.glimpsetagdistinctionsuggestion",
        "magic.intensitytier",
        "magic.pathgiftgrant",
        "magic.portalanchorkind",
        "magic.resonance",
        "magic.restriction",
        "magic.resonanceconversion",
        "magic.ritual",
        "magic.stylecapabilityrequirement",
        "magic.technique",
        "magic.techniqueappliedcondition",
        "magic.techniquecapabilitygrant",
        "magic.techniquecapabilityrequirement",
        "magic.techniquedamageprofile",
        "magic.techniquefunctiontag",
        "magic.techniqueoutcomemodifier",
        "magic.techniqueremovedcondition",
        "magic.techniquestyle",
        "magic.threadweavingunlock",
        "magic.tradition",
        "magic.traditiongiftgrant",
        # mechanics
        "mechanics.application",
        "mechanics.challengeapproach",
        "mechanics.challengecategory",
        "mechanics.challengetemplate",
        "mechanics.modifiercategory",
        "mechanics.modifiertarget",
        "mechanics.prerequisite",
        "mechanics.property",
        "mechanics.propertycategory",
        "mechanics.situationtemplate",
        "mechanics.situationchallengelink",
        "mechanics.situationtraplink",
        # npc_services - builder-domain, but missions name NPCRole by natural
        # key (MissionTemplate.report_to_role), so the role catalog must
        # travel with the content that references it (ruled 2026-08-07;
        # overturns the #3019-era builder-domain exclusion for this one
        # model). Ordered before missions so report_to_role resolves in one
        # load pass.
        "npc_services.npcrole",
        # missions
        "missions.missioncategory",
        "missions.missiontemplate",
        "missions.missionnode",
        "missions.missionoption",
        "missions.missionoptionroute",
        "missions.missionoptionroutecandidate",
        "missions.missionoptionroutereward",
        "missions.missionrenownaward",
        # realms
        "realms.realm",
        # relationships
        "relationships.relationshiptrack",
        # skills
        "skills.skill",
        # societies
        "societies.houseaspectdefinition",
        "societies.houseaspectoption",
        # species
        "species.language",
        "species.species",
        "species.speciesgiftgrant",
        # tarot
        "tarot.tarotcard",
        # traits
        "traits.trait",
        # weather
        "weather.climate",
        "weather.feastday",
        "weather.weatheremit",
        "weather.weathertype",
        "weather.weathertransition",
        "weather.weathertypeexposure",
        "weather.weathertypeshelter",
    }
)


#: Row-level export predicates, ``model_label -> filter kwargs`` applied via
#: ``queryset.filter(**kwargs)``. Applied on top of the ``CONTENT_MODELS``
#: allowlist, which is a *model*-level line.
#:
#: Some tables hold both authored content and rows that belong to one player —
#: a personal anima ``Ritual``, the per-character ``CheckType``
#: ``ensure_character_magic_check_type`` synthesizes. De-registering the model is not
#: an option (staff rituals and check types must keep exporting), so the boundary is
#: drawn per row, on a real owner column rather than a name pattern: a renamed pattern
#: would leak silently, which is the failure this guards against (#2724, ADR-0171).
#:
#: Plain kwargs rather than ``django.db.models.Q`` deliberately: this module promises
#: (see the module docstring, :13-15) to import cleanly without Django configured, and
#: every predicate below is a single lookup — expressing it as a dict literal needs no
#: Django import at module scope at all.
#:
#: This form expresses AND-of-lookups ONLY. A predicate that needs OR/NOT must switch
#: to ``django.db.models.Q``, imported INSIDE ``export_to_content_repo`` (never at
#: module scope — that would break the Django-unconfigured import contract above) —
#: NOT be bolted on as extra dict keys: ``queryset.filter(**predicate)`` silently ANDs
#: every key together, so a second key doesn't express OR/NOT, it expresses a stricter
#: AND — a wrong-but-running filter with no error, the same silent-leak failure class
#: this whole mechanism exists to close.
#:
#: NOTE: each predicate assumes staff authoring leaves the owner column NULL. If a staff
#: authoring surface ever stamps the acting account, those rows silently stop exporting —
#: ``test_content_export`` carries a count tripwire for exactly that.
EXPORT_FILTERS: dict[str, dict[str, object]] = {
    "evennia_extensions.media": {"slug__isnull": False},  # pre-existing behavior
    "magic.ritual": {"author_account__isnull": True},
    "checks.checktype": {"owner_sheet__isnull": True},
    "checks.checktypetrait": {"check_type__owner_sheet__isnull": True},
}

#: Field-level export exclusions: columns on a content model that are
#: installation config, not content. They reference rows the corpus does not
#: carry (an Organization, an account), so exporting them would make the
#: fixture load-order-dependent on a fresh database - content loads before
#: seeders, and the referenced row would not exist yet. An excluded field
#: never reaches the corpus; loads leave it untouched (an absent key is never
#: assigned) and the owning seeder wires it onto the authored row after
#: lookup (e.g. ``ensure_academy_generalist_trainer_role``'s
#: ``faction_affiliation`` stamp). The no-content-slop overwrite guard
#: ignores these fields for the same reason: they are seeder-owned.
EXPORT_FIELD_EXCLUSIONS: dict[str, frozenset[str]] = {
    "npc_services.npcrole": frozenset({"faction_affiliation"}),
}


def _strip_excluded_fields(model_label: str, data: str) -> str:
    """Drop installation-config fields from serialized rows, if any apply."""
    excluded = EXPORT_FIELD_EXCLUSIONS.get(model_label)
    if not excluded:
        return data
    records = json.loads(data)
    for record in records:
        for name in excluded:
            record["fields"].pop(name, None)
    return json.dumps(records, indent=2)


def _markdown_entry_path(root: Path, spec: dict, fields: dict) -> Path:
    """Return the file a prose-domain record renders to (#3018).

    Shared by ``_write_markdown_entries`` (whole-domain export) and
    ``export_single_row`` (row-level export) so the slug/nesting rule can
    never drift between the two callers.
    """
    domain_dir = root / spec["domain"]
    out_dir = domain_dir
    subdir_key = spec.get("subdir_from")
    if subdir_key:
        value = fields.get(subdir_key)
        if isinstance(value, list) and value:
            out_dir = domain_dir / content_slug(str(value[-1]))
    return out_dir / f"{content_slug(fields['name'])}.md"


def _write_markdown_entries(
    root: Path, spec: dict, serialized: str, *, allow_additions: bool = False
) -> tuple[list[Path], list[str]]:
    """Write one markdown file per record for a prose domain (#2688).

    Existing files are overwritten; files with no corresponding row are left
    alone rather than deleted. Deleting is how an export destroys authored
    content when the database is a subset of the repo (see the content repo's
    own README), so removing an entry stays a deliberate manual act.

    The addition gate (#2890) applies here too, and a prose domain expresses it
    without a natural-key diff: an entry's file either exists or it does not.

    **The gate keys on the domain, not the entry.** If the domain directory holds
    no entries yet, this is a first export and every entry is written — the same
    rule the JSON path applies to a model with no fixture file. Deciding per entry
    instead would withhold the entire corpus on a virgin checkout, since on a
    fresh root no entry file exists by definition.

    Returns ``(written, withheld_names)``.
    """
    domain_dir = root / spec["domain"]
    domain_has_entries = domain_dir.exists() and any(domain_dir.rglob("*.md"))
    gate_on = not allow_additions and domain_has_entries

    written: list[Path] = []
    withheld: list[str] = []
    for record in json.loads(serialized):
        fields = record["fields"]
        out_path = _markdown_entry_path(root, spec, fields)
        if gate_on and not out_path.exists():
            withheld.append(str(fields.get("name", out_path.stem)))
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_entry_markdown(fields, spec), encoding="utf-8")
        written.append(out_path)
    return written, withheld


@dataclass
class ExportResult:
    """Outcome of an export pass."""

    written: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # model labels with 0 rows
    errors: list[str] = field(default_factory=list)
    total_records: int = 0
    #: model label -> natural keys the export declined to add (#2890). Populated
    #: only when ``allow_additions`` is False, which is the default.
    withheld: dict[str, list[str]] = field(default_factory=dict)
    #: model label -> natural keys the export added to the corpus (#2890).
    #: Populated only when ``allow_additions`` is True.
    added: dict[str, list[str]] = field(default_factory=dict)

    @property
    def withheld_count(self) -> int:
        """Total rows the export declined to add across all models."""
        return sum(len(keys) for keys in self.withheld.values())

    @property
    def added_count(self) -> int:
        """Total rows the export added across all models."""
        return sum(len(keys) for keys in self.added.values())


def _natural_key_fields(model: type) -> list[str] | None:
    """Return the field names forming ``model``'s natural key, or None.

    None means the model has no ``NaturalKeyConfig`` and its rows cannot be
    identified across an export boundary — the addition gate has to let that
    model through untouched rather than guess.
    """
    from core.natural_keys import NaturalKeyMixin  # noqa: PLC0415

    if not issubclass(model, NaturalKeyMixin):
        return None
    return model.identity_fields()


def _record_key(record_fields: dict, key_fields: list[str]) -> str:
    """Return a stable string identity for one serialized record.

    Compares *serialized* field values rather than model-level
    ``natural_key()`` tuples, so both sides of the diff are produced by the same
    serializer settings and cannot disagree about how an FK is represented.
    """
    return json.dumps([record_fields.get(f) for f in key_fields], sort_keys=True)


def _record_key_folded(record_fields: dict, key_fields: list[str]) -> str:
    """Case-normalized ``_record_key``, matching the loader's iexact semantics (#2687).

    Deliberately diverges from ``_record_key``'s exact-match identity, which
    ``_apply_addition_gate`` (the corpus-wide export's addition gate) uses and
    keeps using unchanged - that gate only ever compares two exports produced
    by the same serializer settings on the same pass, so casing never drifts
    between its two sides. ``export_single_row``'s JSON path is different: it
    is a read-modify-write merge against a file that may already hold a row
    under different casing (e.g. a name edited in admin), and the loader
    resolves natural keys case-insensitively - so an exact-match comparison
    there would append a second record instead of replacing the first, and the
    next load would then treat both records as the same row (order-dependent
    double-apply).
    """

    def fold(value: object) -> object:
        if isinstance(value, str):
            return value.casefold()
        if isinstance(value, list):
            return [fold(v) for v in value]
        return value

    return json.dumps([fold(record_fields.get(f)) for f in key_fields], sort_keys=True)


def _existing_record_keys(out_path: Path, key_fields: list[str]) -> set[str] | None:
    """Return the natural keys already in the corpus file, or None if absent.

    None distinguishes "this model has no fixture file yet" (a genuinely new
    model, where every row is a first export and blocking would make the model
    impossible to seed) from "the file exists and is empty".
    """
    if not out_path.exists():
        return None
    try:
        records = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(records, list):
        return None
    return {
        _record_key(r["fields"], key_fields)
        for r in records
        if isinstance(r, dict) and isinstance(r.get("fields"), dict)
    }


def export_to_content_repo(
    content_root: Path | None = None, *, allow_additions: bool = False
) -> ExportResult:
    """Serialize content models and write fixture JSON to the lore repo.

    Writes one file per model to ``<content_root>/fixtures/<domain>/<model_name>.json``,
    where ``<domain>`` is ``core.app_domains.domain_of(model)`` (today identical to
    the model's Django ``app_label``). Models with zero rows are skipped (the file
    is not written). Existing files are overwritten.

    **The addition gate (#2890, default ON).** A row whose natural key is not
    already in the corpus file is an *addition*, and by default an addition is
    withheld: written nowhere, and reported in ``result.withheld``. Rows the
    corpus already knows are exported as before, so edits still round-trip.

    This exists because a database seeded with ``SEED_SAMPLE_CONTENT`` holds
    sample rows that ``authored_or_sample`` created on purpose, and nothing
    downstream distinguished them from authored ones — so an export laundered
    invented names into the corpus as lore. That happened: twelve resonances
    shipped, none authored, one of them (Praedari) carrying a canonically wrong
    affinity, while 22 real ones were missing entirely.

    The gate is deliberately not sample-specific. Anything a test, a stray
    script, or a half-finished import left in a content table is caught by the
    same rule, and no per-model column or provenance table is needed to do it.

    ``allow_additions=True`` is the authoring path: a staff member who wrote new
    rows in admin passes it to push them, and gets them listed in
    ``result.added``. Two cases bypass the gate because blocking them would be
    wrong rather than safe: a model whose fixture file does not exist yet (a
    genuinely new model — every row is a first export), and a model with no
    usable ``NaturalKeyConfig`` (its rows have no identity to diff on).

    Requires Django to be configured.
    """
    from django.core import serializers  # noqa: PLC0415

    root = content_root or resolve_content_root()
    if root is None:
        msg = (
            "CONTENT_REPO_PATH is not set or does not exist. "
            "Set it in src/.env pointing at your local checkout of the "
            "private content repository."
        )
        raise ContentExportError(msg)

    result = ExportResult()

    for model_label in sorted(CONTENT_MODELS):
        # model_label is "<domain>.<model_name>" (CONTENT_MODELS above), not a
        # real Django app_label post-collapse (#2906) — resolve by model name.
        try:
            model = resolve_model_by_name(model_label)
        except LookupError:
            result.skipped.append(f"{model_label} (model not found)")
            continue

        queryset = model.objects.all().order_by("pk")
        predicate = EXPORT_FILTERS.get(model_label)
        if predicate is not None:
            queryset = queryset.filter(**predicate)
        count = queryset.count()
        if count == 0:
            result.skipped.append(model_label)
            continue

        try:
            data = serializers.serialize(
                "json",
                queryset,
                indent=2,
                use_natural_foreign_keys=True,
                use_natural_primary_keys=True,
            )
        except (TypeError, ValueError, AttributeError) as exc:
            result.errors.append(f"{model_label}: serialization failed: {exc}")
            continue

        _write_one_model(model, data, root, result, allow_additions=allow_additions)

    return result


def _write_one_model(
    model: type,
    data: str,
    root: Path,
    result: ExportResult,
    *,
    allow_additions: bool,
) -> None:
    """Write one model's serialized rows, applying the addition gate (#2890).

    Extracted from ``export_to_content_repo`` to keep that function under the
    complexity ceiling; mutates ``result`` in place, as the inlined body did.
    """
    # "<domain>.<model_name>" — matches CONTENT_MODELS'/MARKDOWN_EXPORT_DOMAINS'
    # key convention (core.app_domains.domain_of), NOT model._meta.label_lower.
    # Post-#2906 every model's real Django app_label is "arxii", so a
    # label_lower-keyed lookup into MARKDOWN_EXPORT_DOMAINS would never match
    # and silently fall through to plain JSON export for every prose domain.
    model_name = model.__name__.lower()
    model_label = f"{domain_of(model)}.{model_name}"
    data = _strip_excluded_fields(model_label, data)
    count = len(json.loads(data))

    spec = MARKDOWN_EXPORT_DOMAINS.get(model_label)
    if spec is not None:
        # Prose domain (#2688): write per-entry markdown and emit NO JSON,
        # so the generated file cannot compete with the markdown source.
        written, withheld = _write_markdown_entries(
            root, spec, data, allow_additions=allow_additions
        )
        result.written.extend(written)
        if withheld:
            result.withheld[model_label] = withheld
        result.total_records += count - len(withheld)
        return

    out_dir = root / "fixtures" / domain_of(model)
    out_path = out_dir / f"{model_name}.json"

    records, withheld, added = _apply_addition_gate(
        json.loads(data), model, out_path, allow_additions=allow_additions
    )
    if withheld:
        result.withheld[model_label] = withheld
    if added:
        result.added[model_label] = added
    if not records:
        # Every row was withheld. Writing "[]" here would empty the corpus file
        # outright — the opposite of what a gate meant to protect authored
        # content should do. Creating an empty file is no better.
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    result.written.append(out_path)
    result.total_records += len(records)


@dataclass
class RowExportResult:
    """Outcome of a single-row export (#3018)."""

    paths: list[Path]
    is_addition: bool
    model_label: str
    natural_key: str
    refused: str | None = None


def export_single_row(instance, *, content_root: Path) -> RowExportResult:
    """Write ONE row's corpus form into the lore checkout working tree.

    Reuses the corpus exporter's serializer and natural-key identity so a
    row-level export can never disagree with a full export about a record's
    shape. JSON domains re-emit the model's file with the exporter's canonical
    formatting after replacing or appending the one record - a file predating
    canonical formatting shows a one-time whole-file reformat in the diff
    preview, which is the accepted trade against byte-surgery (#3018 spec).
    Addition-vs-update is decided with the ADR-0191 record keys; the CALLER
    enforces the explicit new-row acknowledgment - this function only reports.
    The JSON merge below relies on every ``CONTENT_MODELS``/``MARKDOWN_EXPORT_DOMAINS``
    row carrying ``NaturalKeyMixin`` (pinned by
    ``test_content_models_all_have_natural_key``) - a model with no natural key
    would make ``key_fields`` None and every export append a fresh record
    instead of replacing one, which is why that invariant must hold.
    """
    from django.core import serializers  # noqa: PLC0415

    model = type(instance)
    model_name = model.__name__.lower()
    model_label = f"{domain_of(model)}.{model_name}"
    # Defense-in-depth against a path-traversal taint finding (pythonsecurity:S2083):
    # re-derive the label by looking it up IN the allowlist constants themselves,
    # rather than trusting the string built above. `canonical` is then a value that
    # provably originates from CONTENT_MODELS/MARKDOWN_EXPORT_DOMAINS, not from
    # `model`/`instance`, so every path segment derived from it below breaks the
    # taint chain a static analyzer traces back to the request - not just a
    # runtime membership check, but a guarantee visible to taint analysis too.
    canonical = next((known for known in CONTENT_MODELS if known == model_label), None)
    if canonical is None:
        canonical = next((known for known in MARKDOWN_EXPORT_DOMAINS if known == model_label), None)
    if canonical is None:
        return RowExportResult(
            [],
            False,
            model_label,
            "",
            refused=(f"{model.__name__} is not a content model; the content repo does not own it."),
        )
    model_label = canonical
    canonical_domain, _, canonical_name = canonical.partition(".")
    predicate = EXPORT_FILTERS.get(model_label)
    if predicate is not None and not model.objects.filter(pk=instance.pk, **predicate).exists():
        return RowExportResult(
            [],
            False,
            model_label,
            "",
            refused=(
                f"This {model.__name__} row is excluded from export (player-owned rows "
                "stay out of the corpus)."
            ),
        )
    data = serializers.serialize(
        "json",
        model.objects.filter(pk=instance.pk),
        indent=2,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )
    record = json.loads(data)[0]
    for name in EXPORT_FIELD_EXCLUSIONS.get(model_label, frozenset()):
        record["fields"].pop(name, None)
    key_fields = _natural_key_fields(model)
    key_display = ", ".join(
        str(v)
        for v in ([record["fields"].get(f) for f in key_fields] if key_fields else [instance.pk])
    )

    # spec["domain"]/content_slug() are hardcoded allowlist constants and a
    # sanitized slug respectively, not request-derived - the markdown path is
    # already taint-safe without further changes here.
    spec = MARKDOWN_EXPORT_DOMAINS.get(model_label)
    if spec is not None:
        out_path = _markdown_entry_path(content_root, spec, record["fields"])
        is_addition = not out_path.exists()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_entry_markdown(record["fields"], spec), encoding="utf-8")
        return RowExportResult([out_path], is_addition, model_label, key_display)

    # Path segments below come from `canonical` (allowlist-derived), not from
    # `domain_of(model)`/`model_name` (model-class-derived), so the sink is
    # anchored to the allowlist rather than to `model`.
    out_dir = content_root / "fixtures" / canonical_domain
    out_path = out_dir / f"{canonical_name}.json"
    # Case-folded comparison throughout (_record_key_folded, not _record_key):
    # this is a read-modify-write merge against one file, and the loader
    # matches natural keys case-insensitively (#2687) - see that helper's
    # docstring for why this path must diverge from the corpus-wide gate.
    is_addition = _merge_record_into_fixture_file(out_path, record, key_fields)
    return RowExportResult([out_path], is_addition, model_label, key_display)


def _merge_record_into_fixture_file(
    out_path: Path, record: dict, key_fields: list[str] | None
) -> bool:
    """Read-modify-write one record into a JSON fixture file; return is_addition.

    Extracted from ``export_single_row`` to keep that function under the
    complexity ceiling; behavior is unchanged. An existing record whose
    case-folded natural key (``_record_key_folded``) matches ``record`` is
    replaced in place; otherwise ``record`` is appended. The return value is
    True when the row's natural key was not already present in the file
    (a first-export addition) - the same value ``export_single_row`` reports
    as ``RowExportResult.is_addition``.
    """
    file_existed = out_path.exists()
    row_key_folded = _record_key_folded(record["fields"], key_fields) if key_fields else None
    records: list[dict] = []
    if file_existed:
        with suppress(OSError, ValueError):
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                records = loaded
    existing_folded = (
        {
            _record_key_folded(r["fields"], key_fields)
            for r in records
            if isinstance(r, dict) and isinstance(r.get("fields"), dict)
        }
        if key_fields
        else set()
    )
    is_addition = not file_existed or row_key_folded not in existing_folded
    replaced = False
    for i, existing in enumerate(records):
        if (
            key_fields
            and isinstance(existing, dict)
            and isinstance(existing.get("fields"), dict)
            and _record_key_folded(existing["fields"], key_fields) == row_key_folded
        ):
            records[i] = record
            replaced = True
            break
    if not replaced:
        records.append(record)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return is_addition


def _apply_addition_gate(
    records: list[dict],
    model: type,
    out_path: Path,
    *,
    allow_additions: bool,
) -> tuple[list[dict], list[str], list[str]]:
    """Split serialized records into (kept, withheld_keys, added_keys) (#2890).

    Returns every record unchanged when the model has no usable natural key or
    has no fixture file yet — see ``export_to_content_repo``'s docstring for why
    those two cases bypass the gate rather than being blocked by it.
    """
    key_fields = _natural_key_fields(model)
    if key_fields is None:
        return records, [], []

    existing = _existing_record_keys(out_path, key_fields)
    if existing is None:
        return records, [], []

    kept: list[dict] = []
    new_keys: list[str] = []
    for record in records:
        key = _record_key(record.get("fields", {}), key_fields)
        if key in existing:
            kept.append(record)
        else:
            new_keys.append(key)
            if allow_additions:
                kept.append(record)
    if allow_additions:
        return kept, [], new_keys
    return kept, new_keys, []
