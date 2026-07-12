"""Forms-app-owned check-type name constants.

Mirrors the sibling-app convention (``secrets.constants.GOSSIP_CHECK_TYPE_NAME``,
``items.constants.FASHION_PRESENTATION_CHECK_TYPE_NAME``): the app that owns a check's
domain owns the ``CheckType`` name constant, imported by its seed + its service module.
"""

# The "recognize the person under the mask" check (#1107 slice 5) — intellect + Investigation.
# Seeded in ``world.seeds.investigation_checks.ensure_identification_check``. Deliberately NOT
# the "Search" CheckType (perception + Investigation, #1705) — wrong stat pairing per Apostate's
# 2026-07-03 ruling.
IDENTIFICATION_CHECK_TYPE_NAME = "Identification"
