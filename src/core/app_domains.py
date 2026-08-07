"""Derive a model's authoring *domain* from its module path.

Before #2906 every first-party model's Django ``app_label`` doubled as its
domain: it grouped the admin index, named the lore repo's ``fixtures/<domain>/``
directory, and keyed the admin pin/exclude rows. The single-app collapse leaves
one label (``arxii``) for all 1026 models, so that signal is gone from the ORM.
This restores it from the one place that still carries it — the package path —
so those three surfaces keep behaving exactly as they did.
"""

from __future__ import annotations

from django.db import models

_WORLD_PREFIX = "world."

# Lazily-built model-name -> candidate model classes index (see
# resolve_model_by_name). A list, not a single model, because model names are
# NOT guaranteed unique across all installed apps pre-collapse (e.g., before
# #2906's Task 3 renamed it, AchievementRequirement existed in both
# world.achievements and world.progression) — collapsing to one entry would
# silently pick whichever model apps.get_models() happened to enumerate last.
# Populated on first use, not at import time, since apps.get_models()
# requires the app registry to already be populated.
_MODEL_INDEX: dict[str, list[type[models.Model]]] | None = None


def domain_of(model: type[models.Model]) -> str:
    """Return the authoring domain for ``model`` (e.g. ``"magic"``)."""
    module = model.__module__
    if module.startswith(_WORLD_PREFIX):
        # "world.magic.models" / "world.progression.models.unlocks" -> "magic" / "progression"
        return module.split(".")[1]
    # "actions.models" -> "actions"; "web.admin.models" -> "web_admin"
    head = module.split(".")[0]
    return "web_admin" if module.startswith("web.admin") else head


def _model_index() -> dict[str, list[type[models.Model]]]:
    """Return the cached lowercase-model-name -> candidate-models index, building it once.

    ``resolve_model_by_name`` is called per fixture row (thousands of them via
    ``load_entries``), so the index is built from ``apps.get_models()`` a single
    time per process and cached at module scope rather than re-scanned per call.
    A name maps to a LIST because it is not guaranteed unique (see the
    ``_MODEL_INDEX`` comment above) — collision detection happens at lookup
    time in ``resolve_model_by_name``, never here, so a colliding name doesn't
    fail the whole pipeline before anyone actually looks it up.
    """
    global _MODEL_INDEX  # noqa: PLW0603
    if _MODEL_INDEX is None:
        from django.apps import apps  # noqa: PLC0415

        index: dict[str, list[type[models.Model]]] = {}
        for model in apps.get_models():
            index.setdefault(model.__name__.lower(), []).append(model)
        _MODEL_INDEX = index
    return _MODEL_INDEX


def resolve_model_by_name(model_key: str) -> type[models.Model]:
    """Resolve ``"<label>.<model_name>"`` (or a bare ``"<model_name>"``), mostly ignoring the label.

    Used everywhere a fixture, admin toggle, or export needs to turn a
    stored/authored model reference into a live model class: fixture loading
    (``core_management.content_fixtures.load_entries``), the admin pin/exclude
    toggles, and content export.

    The label half is historical: #2906 collapsed every first-party app into
    ``arxii``, so a reference written as ``"magic.technique"`` (or any other
    stale/renamed label) names a model that may now live under a different
    Django app label entirely. Model names are unique across almost every
    installed app, so in the overwhelming common case the name alone
    identifies the model and the label is ignored outright.

    They are NOT unique in every case, though (e.g., before #2906's Task 3
    renamed it, ``AchievementRequirement`` existed in both
    ``world.achievements`` and ``world.progression``) — collapsing straight
    to a single match would silently resolve to whichever model happened to
    be enumerated last, forever. So resolution is layered:

    1. Exactly one model with this name -> return it (the common case).
    2. More than one -> if a label was supplied and exactly one candidate's
       ``app_label`` matches it, return that one (disambiguates the
       pre-collapse interim window whenever a genuine name collision like
       that recurs).
    3. Still ambiguous (no label supplied, or it matched none/several) ->
       raise ``LookupError`` naming every candidate as ``app_label.ModelName``,
       so the failure is self-diagnosing rather than a silent wrong answer.
    4. No candidates at all -> raise ``LookupError`` as before.

    A silent skip/wrong-resolution here would make a whole-repo label rename
    look like a successful load while quietly importing nothing (or importing
    into the wrong model), so every failure mode above raises loudly instead.
    """
    label, _, model_name = model_key.rpartition(".")
    candidates = _model_index().get(model_name.lower())
    if not candidates:
        msg = f"No installed model named {model_name!r} (from {model_key!r})"
        raise LookupError(msg)
    if len(candidates) == 1:
        return candidates[0]
    if label:
        label_matches = [m for m in candidates if m._meta.app_label == label]  # noqa: SLF001
        if len(label_matches) == 1:
            return label_matches[0]
    candidate_names = ", ".join(
        f"{m._meta.app_label}.{m.__name__}"  # noqa: SLF001
        for m in candidates
    )
    msg = (
        f"Ambiguous model name {model_name!r} (from {model_key!r}): "
        f"{len(candidates)} installed models share this name and the label didn't "
        f"disambiguate: {candidate_names}"
    )
    raise LookupError(msg)


def credited_content_models() -> list[type[models.Model]]:
    """Concrete models inheriting CreditedContent, sorted by (domain, name).

    The authoring workbench's iteration set (#3019): deliberately BROADER than
    content_export.CONTENT_MODELS - three builder-domain models (ItemTemplate,
    BuildingKind, DecorationKind) carry credit but sit outside the export
    registry (NPCRole was admitted to the catalog 2026-08-07: missions name it
    by natural key), and coverage of the mixin is
    what test_prose_credits enforces. The CONTENT_MODELS label loops elsewhere
    are a different, export-owned set; do not consolidate them onto this.
    """
    from django.apps import apps as dj_apps  # noqa: PLC0415

    from world.contributors.models import CreditedContent  # noqa: PLC0415

    found = [
        m
        for m in dj_apps.get_models()
        if issubclass(m, CreditedContent) and not m._meta.abstract  # noqa: SLF001
    ]
    return sorted(found, key=lambda m: (domain_of(m), m.__name__.lower()))
