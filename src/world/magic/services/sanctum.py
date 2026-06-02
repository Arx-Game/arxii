"""Sanctum service strategy — Phase 4.1 onwards: upgrades only.

``handle_progression`` is the ROOM_FEATURE_PROGRESSION service strategy
that runs when a Sanctum upgrade Project resolves. Plan 4 revised
2026-06-03: installs no longer flow through this handler — Sanctification
ritual creates the Sanctum directly (see
``world.magic.services.sanctum_install``). Upgrades (L1 → L2+) stay
Project-driven and dispatch through here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.projects.models import Project


class SanctumProgressionError(ValueError):
    """Raised when a Sanctum upgrade Project cannot be resolved.

    Carries a ``user_message`` separate from the technical message per
    ``feedback_codeql_exceptions``.
    """

    user_message: str = "This Sanctum upgrade cannot be applied."


class SanctumUpgradeMissingInstanceError(SanctumProgressionError):
    user_message = "Cannot upgrade — no Sanctum is installed in this room."


class SanctumUpgradeKindMismatchError(SanctumProgressionError):
    user_message = "The installed feature is not a Sanctum."


class SanctumInstallViaProjectError(SanctumProgressionError):
    """A target_level=1 Sanctum project shouldn't reach this handler.

    Sanctum installs via Ritual of Sanctification (Plan 4 §F revised
    2026-06-03). If a ROOM_FEATURE_PROGRESSION Project with target_level=1
    targeting Sanctum somehow lands here, that's an authoring error —
    surface it loudly.
    """

    user_message = (
        "Sanctums install via Ritual of Sanctification, not via Project. "
        "This Project should not have been opened with target_level=1."
    )


@transaction.atomic
def handle_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001 — used in Phase 3 for tier modifiers
) -> None:
    """Run the per-tier outcome of a Sanctum upgrade Project.

    Dispatched by the framework's
    :func:`world.room_features.services.complete_room_feature_progression`
    via the service-strategy registry. Sanctum-specific upgrade behavior:
    bump ``RoomFeatureInstance.level`` + ``last_upgraded_at``.

    ``target_level=1`` is rejected — installs go through Sanctification
    ritual, not through this handler. See Plan 4 §F revised 2026-06-03.
    """
    from world.room_features.models import RoomFeatureProgressionDetails  # noqa: PLC0415

    progression = RoomFeatureProgressionDetails.objects.select_related(
        "target_room_profile",
        "target_feature_kind",
    ).get(project=project)

    if target_level == 1:
        msg = (
            f"Sanctum install for project {project.pk} reached handle_progression "
            "with target_level=1; installs must use Ritual of Sanctification."
        )
        raise SanctumInstallViaProjectError(msg)

    _upgrade_sanctum(progression, target_level)


def _upgrade_sanctum(progression, target_level: int) -> None:
    """Bump RoomFeatureInstance.level + last_upgraded_at for an upgrade.

    SanctumDetails fields don't change on upgrade — the level lives on
    the framework's RoomFeatureInstance row, and income payouts read
    ``feature_instance.level`` directly to pick the level multiplier.
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    instance = RoomFeatureInstance.objects.filter(
        room_profile=progression.target_room_profile
    ).first()
    if instance is None:
        msg = (
            f"Sanctum upgrade for project {progression.project_id} found no "
            f"installed feature in room {progression.target_room_profile_id}."
        )
        raise SanctumUpgradeMissingInstanceError(msg)
    if instance.feature_kind_id != progression.target_feature_kind_id:
        msg = (
            f"Sanctum upgrade for project {progression.project_id} targets "
            f"kind {progression.target_feature_kind_id} but room has "
            f"{instance.feature_kind_id} installed."
        )
        raise SanctumUpgradeKindMismatchError(msg)

    instance.level = target_level
    instance.last_upgraded_at = timezone.now()
    instance.save(update_fields=["level", "last_upgraded_at"])
