"""Sanctum service strategy + (Phase 3) ritual handlers.

Phase 2b: ``handle_progression`` is the ROOM_FEATURE_PROGRESSION service
strategy that runs when a Sanctum install/upgrade Project resolves. It
creates :class:`world.magic.models.sanctum.SanctumDetails` on install,
bumps level on upgrade. Per-tier outcome modifiers (CRITICAL bonus,
PARTIAL/FAILED/CATASTROPHIC handling) land in Phase 3 alongside the
Ritual of Homecoming + LocationValueModifier helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.magic.models import SanctumDetails, SanctumInstallParams

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.projects.models import Project


class SanctumInstallError(ValueError):
    """Raised when a Sanctum install/upgrade cannot proceed.

    Carries a ``user_message`` separate from the technical message per
    ``feedback_codeql_exceptions`` — never pass ``str(exc)`` directly to
    a DRF response; surface ``exc.user_message``.
    """

    user_message: str = "This Sanctum cannot be installed."


class SanctumInstallParamsMissingError(SanctumInstallError):
    user_message = "Sanctum install is missing its required parameters."


class SanctumAlreadyInstalledError(SanctumInstallError):
    user_message = "This room already has a feature installed."


class SanctumUpgradeMissingInstanceError(SanctumInstallError):
    user_message = "Cannot upgrade — no Sanctum is installed in this room."


class SanctumUpgradeKindMismatchError(SanctumInstallError):
    user_message = "The installed feature is not a Sanctum."


@transaction.atomic
def handle_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001 — used in Phase 3
) -> None:
    """Run the per-tier outcome of a Sanctum install/upgrade Project.

    Dispatched by the framework's
    :func:`world.room_features.services.complete_room_feature_progression`
    via the service-strategy registry. The progression details row
    carries ``target_room_profile`` + ``target_feature_kind`` +
    ``target_level``. For Sanctum, the kind-specific install knobs
    (resonance_type, declared owner mode) live in a
    :class:`SanctumInstallParams` sibling row.
    """
    from world.room_features.models import (  # noqa: PLC0415 — break import cycle
        RoomFeatureProgressionDetails,
    )

    progression = RoomFeatureProgressionDetails.objects.select_related(
        "target_room_profile",
        "target_feature_kind",
    ).get(project=project)

    if target_level == 1:
        _install_sanctum(progression)
        return

    _upgrade_sanctum(progression, target_level)


def _install_sanctum(progression) -> None:
    """Create the RoomFeatureInstance + SanctumDetails for a level-1 install."""
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    params = SanctumInstallParams.objects.filter(progression_details=progression).first()
    if params is None:
        msg = (
            f"Sanctum install for project {progression.project_id} has no SanctumInstallParams row."
        )
        raise SanctumInstallParamsMissingError(msg)

    existing = RoomFeatureInstance.objects.filter(
        room_profile=progression.target_room_profile
    ).first()
    if existing is not None:
        msg = (
            f"Room {progression.target_room_profile_id} already has a "
            f"{existing.feature_kind.name} installed; cannot install Sanctum."
        )
        raise SanctumAlreadyInstalledError(msg)

    instance = RoomFeatureInstance.objects.create(
        room_profile=progression.target_room_profile,
        feature_kind=progression.target_feature_kind,
        level=1,
    )
    SanctumDetails.objects.create(
        feature_instance=instance,
        resonance_type=params.resonance_type,
        owner_mode=params.declared_owner_mode,
    )


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
