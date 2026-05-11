"""Type aliases and dataclasses for the ritual session services."""

from __future__ import annotations

from dataclasses import dataclass

from world.covenants.models import Covenant, CovenantRole


@dataclass(frozen=True)
class RitualSessionReferenceSpec:
    """Caller-provided spec for a single RitualSessionReference row.

    The discriminator-FK pattern requires exactly one ref_<x> populated;
    the constructing service translates this spec into the matching column.
    Carries model instances per project preference (not bare PKs).
    """

    kind: str  # ReferenceKind value
    ref_covenant: Covenant | None = None
    ref_covenant_role: CovenantRole | None = None
