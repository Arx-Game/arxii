"""Types describing technique enhancements available on a scene action.

Kept intentionally small after the deletion of the legacy
``get_available_scene_actions`` service: the only surviving export is
``AvailableEnhancement``, which is reused by ``actions/player_interface.py``
when it enriches PlayerActions with the character's technique-derived options.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from actions.models import ActionEnhancement
from world.magic.types import SoulfrayWarning

if TYPE_CHECKING:
    from world.magic.models import Technique


@dataclass
class AvailableEnhancement:
    """A technique enhancement option for a social action."""

    enhancement: ActionEnhancement
    technique: Technique
    effective_cost: int
    soulfray_warning: SoulfrayWarning | None = None
