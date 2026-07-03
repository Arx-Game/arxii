"""Idempotent deploy/test-DB seed for placeholder Soul Tether ritual grants.

Invoked by `tools/build_schema.py` (and callable at deploy time) in place of
a former RunPython seed migration — migrations are ephemeral pre-production
and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations


def grant_accept_soul_tether_to_all_paths() -> None:
    """Grant placeholder accept_soul_tether PathRitualGrants to every Path.

    Preserves visibility: so that `reconcile_ritual_knowledge()` (called at
    finalize_character time) will create knowledge rows for all new
    characters. Idempotent via get_or_create and silently skips when
    accept_soul_tether doesn't yet exist in this DB (e.g. before
    `wire_soul_tether_content()` has been called in tests).
    """
    from world.classes.models import Path  # noqa: PLC0415
    from world.magic.models import PathRitualGrant, Ritual  # noqa: PLC0415

    try:
        ritual = Ritual.objects.get(name="accept_soul_tether")
    except Ritual.DoesNotExist:
        return

    for path in Path.objects.all():
        PathRitualGrant.objects.get_or_create(path=path, ritual=ritual)
