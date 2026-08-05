"""Look content up; invent it only under ``SEED_SAMPLE_CONTENT`` (#2698).

The settled rule: **if a model is in ``CONTENT_MODELS`` the content repo owns
it and no seeder may create rows in it; if it is not, the seeder owns it.** The
Big Button press is mandatory — it is the sole source of the mechanical spine
(``CheckRank``, ``ResultChart``, ``CheckOutcome``, ``ConsequencePool``,
``ActionTemplate``, ``PointConversionRange``, ``Pronouns``, ``Heritage``, none
of which are in ``CONTENT_MODELS``) — so the fix is never "stop pressing it",
it is "stop the press from writing into content models".

Most seeders here don't *want* to author content: they want a content row to
exist so they can hang config off it (a ``CheckType`` to attach a
``ResultChart`` to, a ``ConditionTemplate`` to point a ``TriggerDefinition``
at). Against a real content repo their ``get_or_create`` calls already find the
authored row and create nothing — the invention only fires when content is
absent, and then it lands in the export as if authored. That is the whole bug.

So the shape is **look up first, create only when sample content is enabled**::

    check_type = authored_or_sample(CheckType, {"description": ...}, name=FLEE_CHECK)
    if check_type is None:
        return  # warning already logged; nothing to hang config off
    ensure_result_chart(check_type)  # config — unconditional

``SEED_SAMPLE_CONTENT`` (``ARXII_SEED_SAMPLE_CONTENT``, default off) exists for
a third party with no content repo who needs *a* starter set. Maintainers keep
it off and author in the content repo.

Skipping rather than raising follows the precedent set for the retired starter
Gift/Technique catalog (#2474): this runs inside ``seed_dev_database()``'s
cluster loop, so a raise over one cluster's missing content would abort the
whole press — including the config seeding that makes the game bootable. The
warning names the model and the lookup so a missing row is loud, not silent.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db.models import Model

logger = logging.getLogger(__name__)

_MISSING_MSG = (
    "%s matching %r is not in the content repo. Skipping the config wired to "
    "it. Author the row in the content repo and re-press the Big Button, or "
    "set ARXII_SEED_SAMPLE_CONTENT=1 to have the seeder invent a sample one "
    "(see #2698)."
)


def sample_content_enabled() -> bool:
    """True when the Big Button may invent sample content rows."""
    return bool(settings.SEED_SAMPLE_CONTENT)


def assert_sampling_allowed() -> None:
    """Refuse sample invention against a non-empty content universe (#3017).

    Called by ``seed_dev_database()`` between the content load and the cluster
    loop: within a single press, once any ``CONTENT_MODELS`` table has a row
    (authored, or just loaded by this same press), sampling is refused for the
    rest of that press, so it can never mix invented rows into a real content
    universe; the downstream guards (test_no_content_slop, the ADR-0191
    addition gate) become defense in depth instead of the only line. This
    enforcement is scoped to a ``seed_dev_database()`` call, not a standing
    database-wide invariant - a direct cluster-seeder call (test-only; see
    ``world.seeds.tests.press_helpers``) sits outside this gate by design.
    """
    if not sample_content_enabled():
        return
    from core_management.content_export import CONTENT_MODELS  # noqa: PLC0415
    from core_management.content_fixtures import (  # noqa: PLC0415
        ContentError,
        resolve_fixture_model,
    )

    nonempty = sorted(
        label for label in CONTENT_MODELS if resolve_fixture_model(label).objects.exists()
    )
    if nonempty:
        message = (
            "ARXII_SEED_SAMPLE_CONTENT is enabled but the database already has "
            f"content rows in: {', '.join(nonempty)}. Sample content may only be "
            "invented into an empty content universe - turn sampling off, or start "
            "from a fresh database with no content repo configured."
        )
        raise ContentError(message)


def authored_or_sample[M: Model](
    model: type[M], defaults: dict[str, Any] | None, **lookup: Any
) -> M | None:
    """Return the authored row, or a sample one only if sampling is enabled.

    Drop-in for ``model.objects.get_or_create(**lookup, defaults=defaults)`` at
    a seeder call site that writes into a ``CONTENT_MODELS`` model. Returns
    ``None`` — after logging which row is missing — when the content repo does
    not author it and ``SEED_SAMPLE_CONTENT`` is off. Callers must handle
    ``None`` by skipping the config that depends on the row; they must not
    fall back to creating it themselves.
    """
    existing = model.objects.filter(**lookup).first()
    if existing is not None:
        return existing
    if not sample_content_enabled():
        logger.warning(_MISSING_MSG, model.__name__, lookup)
        return None
    return model.objects.create(**lookup, **(defaults or {}))
