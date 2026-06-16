"""Plain dataclasses for the captivity services (#931)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.missions.models import MissionTemplate


@dataclass(frozen=True)
class CaptureSetup:
    """The resolved captivity loops + cell flavor for one capture.

    Produced by :func:`world.captivity.services.resolve_capture_setup` from the
    CAPTURE effect's per-capture overrides layered over the one
    :class:`world.captivity.models.CaptivityConfig` default (override-then-default).
    A null template means that loop simply isn't granted; an empty string means the
    spawner falls back to its built-in placeholder cell flavor.
    """

    captive_template: MissionTemplate | None
    rescue_template: MissionTemplate | None
    cell_name: str
    cell_description: str
