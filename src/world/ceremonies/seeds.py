"""Production seed content for the ceremonies framework (#2289, #2393, #2361).

No committed migration ever creates ``CeremonyType`` rows (ADR-0013 — no data
migrations); this cluster is what makes ANY ceremony type openable on a real
deploy. Idempotent (``get_or_create``) so staff edits to name/description
survive re-seeding.
"""

from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.models import CeremonyType

_TYPE_NAMES: dict[str, str] = {
    CeremonyTypeKey.FUNERAL: "Funeral",
    CeremonyTypeKey.BLESSING: "Blessing",
    CeremonyTypeKey.SERMON: "Sermon",
    CeremonyTypeKey.SEANCE: "Seance",
    # WEDDING (#2999), CONVERSION (#2361) and CORONATION (#2358) — WEDDING was
    # originally added to CeremonyTypeKey without a seed entry; closed on sight.
    CeremonyTypeKey.WEDDING: "Wedding",
    CeremonyTypeKey.CONVERSION: "Conversion",
    CeremonyTypeKey.CORONATION: "Coronation",
}


def seed_ceremony_types() -> None:
    """Get-or-create the six authored CeremonyType rows."""
    for key, name in _TYPE_NAMES.items():
        CeremonyType.objects.get_or_create(key=key, defaults={"name": name})
