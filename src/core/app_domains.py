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


def domain_of(model: type[models.Model]) -> str:
    """Return the authoring domain for ``model`` (e.g. ``"magic"``)."""
    module = model.__module__
    if module.startswith(_WORLD_PREFIX):
        # "world.magic.models" / "world.progression.models.unlocks" -> "magic" / "progression"
        return module.split(".")[1]
    # "actions.models" -> "actions"; "web.admin.models" -> "web_admin"
    head = module.split(".")[0]
    return "web_admin" if module.startswith("web.admin") else head
