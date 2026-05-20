"""Service-level validation for the mission graph (Phase 2).

``MissionOption.clean()`` cannot validate the ``accepted_affordances`` M2M
because M2M rows do not exist until the option row has a pk. The
"AFFORDANCE-sourced option requires ≥1 accepted affordance" invariant is
therefore enforced here, post-save, by callers that build options (and is
covered by a dedicated test). This is a real check, not a faked model
clean — it queries the persisted M2M.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from world.missions.constants import OptionSource
from world.missions.models import MissionOption


def validate_mission_option(option: MissionOption) -> None:
    """Validate post-save invariants for ``option``.

    Re-runs the model-level field invariants via ``full_clean`` excluding the
    M2M, then enforces the M2M rule: an AFFORDANCE-sourced option must accept
    at least one affordance. Raises ``ValidationError`` on violation.
    """
    option.full_clean()
    if option.source_kind == OptionSource.AFFORDANCE and not option.accepted_affordances.exists():
        raise ValidationError(
            {
                "accepted_affordances": (
                    "AFFORDANCE-sourced options must accept at least one affordance."
                )
            }
        )
