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
import logging
from pathlib import Path

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
CONTENT_MODELS: frozenset[str] = frozenset(
    {
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
        "conditions.conditionresistancemodifier",
        "conditions.conditionstage",
        "conditions.conditiontemplate",
        "conditions.damagetype",
        # covenants
        "covenants.covenantrole",
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
        "magic.technique",
        "magic.techniqueappliedcondition",
        "magic.techniquecapabilitygrant",
        "magic.techniquecapabilityrequirement",
        "magic.techniquedamageprofile",
        "magic.techniquefunctiontag",
        "magic.techniqueoutcomemodifier",
        "magic.techniqueremovedcondition",
        "magic.techniquestyle",
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
    }
)


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
        if model_label == "evennia_extensions.media":
            queryset = queryset.filter(slug__isnull=False)
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

        out_dir = fixtures_dir / app_label
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{model_name}.json"
        out_path.write_text(data + "\n", encoding="utf-8")
        result.written.append(out_path)
        result.total_records += count

    return result
