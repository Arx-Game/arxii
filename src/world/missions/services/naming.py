"""Auto-suffix helper for collision-free naming on create/copy.

Used by MissionTemplateSerializer.create, MissionGiverSerializer.create,
and the copy_template / copy_giver services. PATCH renames intentionally
do not auto-suffix — deliberate rename collisions surface as DRF 400 so
the user sees feedback on a choice they made explicitly.
"""

from django.db.models import QuerySet


def next_available_name(base_name: str, queryset: QuerySet, max_length: int = 200) -> str:
    """Return ``base_name``, or ``base_name + " N"`` for the smallest N>=2 free.

    Looks up the queryset's model on the ``name`` field. Truncates ``base_name``
    when adding the suffix would exceed ``max_length``.

    Args:
        base_name: Candidate name. If unused, returned unchanged.
        queryset: QuerySet of the model that owns the ``name`` field.
        max_length: Hard cap on the returned string length.
    """
    if not queryset.filter(name=base_name).exists():
        return base_name
    n = 2
    while True:
        suffix = f" {n}"
        truncated_base = base_name[: max_length - len(suffix)]
        candidate = f"{truncated_base}{suffix}"
        if not queryset.filter(name=candidate).exists():
            return candidate
        n += 1
