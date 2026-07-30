"""Export authored content models to the private lore repo's fixtures/ directory.

The allowlist below defines which models are "authored content" (lore-repo
material) vs ephemeral/runtime data. Only models in this set are exported.

The export serializes each model with natural keys (no pks) and writes one
JSON file per model to ``CONTENT_REPO_PATH/fixtures/<app_label>/<model_name>.json``.

This is the inverse of ``core_management.content_fixtures.load_entries`` —
export writes what import reads. Round-tripping (export → import) is a no-op
when nothing has changed.

Import-safe without Django configured (the tools wrapper and tests use it
standalone). All Django imports are deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

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
        "achievements.achievementrequirement",
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
        "combat.threatpool",
        "combat.threatpoolentry",
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
        # items
        "items.itemtemplateproperty",
        # magic
        "magic.affinity",
        "magic.compromiseacttype",
        "magic.dramaticmomenttype",
        "magic.effecttype",
        "magic.facet",
        "magic.gift",
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


def _write_markdown_entries(root: Path, spec: dict, serialized: str) -> list[Path]:
    """Write one markdown file per record for a prose domain (#2688).

    Existing files are overwritten; files with no corresponding row are left
    alone rather than deleted. Deleting is how an export destroys authored
    content when the database is a subset of the repo (see the content repo's
    own README), so removing an entry stays a deliberate manual act.
    """
    domain_dir = root / spec["domain"]
    written: list[Path] = []
    for record in json.loads(serialized):
        fields = record["fields"]
        out_dir = domain_dir
        subdir_key = spec.get("subdir_from")
        if subdir_key:
            value = fields.get(subdir_key)
            if isinstance(value, list) and value:
                out_dir = domain_dir / content_slug(str(value[-1]))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{content_slug(fields['name'])}.md"
        out_path.write_text(render_entry_markdown(fields, spec), encoding="utf-8")
        written.append(out_path)
    return written


@dataclass
class ExportResult:
    """Outcome of an export pass."""

    written: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # model labels with 0 rows
    errors: list[str] = field(default_factory=list)
    total_records: int = 0


def export_to_content_repo(content_root: Path | None = None) -> ExportResult:
    """Serialize content models and write fixture JSON to the lore repo.

    Writes one file per model to ``<content_root>/fixtures/<app_label>/<model_name>.json``.
    Models with zero rows are skipped (the file is not written). Existing files
    are overwritten.

    Requires Django to be configured.
    """
    from django.apps import apps  # noqa: PLC0415
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
    fixtures_dir = root / "fixtures"

    for model_label in sorted(CONTENT_MODELS):
        app_label, model_name = model_label.split(".")
        try:
            model = apps.get_model(app_label, model_name)
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

        spec = MARKDOWN_EXPORT_DOMAINS.get(model_label)
        if spec is not None:
            # Prose domain (#2688): write per-entry markdown and emit NO JSON,
            # so the generated file cannot compete with the markdown source.
            result.written.extend(_write_markdown_entries(root, spec, data))
            result.total_records += count
            continue

        out_dir = fixtures_dir / app_label
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{model_name}.json"
        out_path.write_text(data + "\n", encoding="utf-8")
        result.written.append(out_path)
        result.total_records += count

    return result
