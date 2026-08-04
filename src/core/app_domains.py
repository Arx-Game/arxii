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

# Lazily-built model-name -> model class index (see resolve_model_by_name).
# Populated on first use, not at import time, since apps.get_models() requires
# the app registry to already be populated.
_MODEL_INDEX: dict[str, type[models.Model]] | None = None


def domain_of(model: type[models.Model]) -> str:
    """Return the authoring domain for ``model`` (e.g. ``"magic"``)."""
    module = model.__module__
    if module.startswith(_WORLD_PREFIX):
        # "world.magic.models" / "world.progression.models.unlocks" -> "magic" / "progression"
        return module.split(".")[1]
    # "actions.models" -> "actions"; "web.admin.models" -> "web_admin"
    head = module.split(".")[0]
    return "web_admin" if module.startswith("web.admin") else head


def _model_index() -> dict[str, type[models.Model]]:
    """Return the cached lowercase-model-name -> model class index, building it once.

    ``resolve_model_by_name`` is called per fixture row (thousands of them via
    ``load_entries``), so the index is built from ``apps.get_models()`` a single
    time per process and cached at module scope rather than re-scanned per call.
    """
    global _MODEL_INDEX  # noqa: PLW0603
    if _MODEL_INDEX is None:
        from django.apps import apps  # noqa: PLC0415

        _MODEL_INDEX = {model.__name__.lower(): model for model in apps.get_models()}
    return _MODEL_INDEX


def resolve_model_by_name(model_key: str) -> type[models.Model]:
    """Resolve ``"<label>.<model_name>"`` (or a bare ``"<model_name>"``), ignoring the label.

    Used everywhere a fixture, admin toggle, or export needs to turn a
    stored/authored model reference into a live model class: fixture loading
    (``core_management.content_fixtures.load_entries``), the admin pin/exclude
    toggles, and content export.

    The label half is historical: #2906 collapsed every first-party app into
    ``arxii``, so a reference written as ``"magic.technique"`` (or any other
    stale/renamed label) names a model that may now live under a different
    Django app label entirely. Model *names* are unique across all installed
    apps (verified for #2906: the sole collision is renamed away in Task 3), so
    the name alone identifies the model and the label can simply be ignored.

    Raises ``LookupError`` when the model name is not installed — a silent
    skip here would make a whole-repo label rename look like a successful load
    while quietly importing nothing.
    """
    _, _, model_name = model_key.rpartition(".")
    try:
        return _model_index()[model_name.lower()]
    except KeyError:
        msg = f"No installed model named {model_name!r} (from {model_key!r})"
        raise LookupError(msg) from None
