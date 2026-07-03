"""Generic room-feature project actions (#1234) — the player-facing trigger the
ROOM_FEATURE_PROGRESSION project framework never had (also closes the same gap
for the already-merged Command Center kind).

``StartRoomFeatureProjectAction`` is the install/upgrade entry point.
``RepairLabStationAction`` spends coppers to restore a Lab station's durability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.room_features.constants import RoomFeatureInstallMechanism
from world.room_features.exceptions import RoomAlreadyHasFeatureError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_NOT_STANDING = "You don't have standing to build here."
_MSG_WRONG_MECHANISM = "This feature kind cannot be installed via a project."
_MSG_NOT_AN_UPGRADE = "That would not be an upgrade."

#: Placeholder tuning — content pass owns real per-kind values later.
_THRESHOLD_PER_LEVEL = 500
_TIME_LIMIT_DAYS = 14


def _resolve_active_persona(actor: ObjectDB) -> Any:
    """Return the actor's active persona, or ``None`` if unavailable.

    Shared by every room-feature Action in this module — both the project
    starter and the Lab repair verb need "does this actor have an active
    persona with standing" as their first gate.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


@dataclass
class StartRoomFeatureProjectAction(Action):
    """Create a ROOM_FEATURE_PROGRESSION project to install or upgrade a feature.

    Generic — works for any PROJECT-mechanism RoomFeatureKind (LAB, COMMAND_CENTER,
    future physical kinds). Install requires no active feature instance of ANY kind
    in the room (schema-enforced one-feature-per-room exclusivity, #1234 Decision 7);
    upgrade requires an existing active instance of the SAME target kind, at a lower
    level. Funding/resolution reuse the existing generic Project machinery
    (``project/donate`` telnet, cron `scan_active_projects`) — this Action only
    creates the row.
    """

    key: str = "start_room_feature_project"
    name: str = "Start Room Feature Project"
    icon: str = "hammer"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    @staticmethod
    def _reject_install_or_upgrade(
        existing: Any, feature_kind: Any, target_level: int
    ) -> str | None:
        """Return a failure message if the install/upgrade is not allowed, else ``None``.

        Three-way branch (#1234 Decision 7): no existing instance -> fresh install
        (mechanism-gated); existing instance of the SAME kind -> upgrade (level-gated);
        existing instance of a DIFFERENT kind -> blocked outright (one feature per room).
        """
        if existing is None:
            if feature_kind.install_mechanism != RoomFeatureInstallMechanism.PROJECT:
                return _MSG_WRONG_MECHANISM
            return None
        if existing.feature_kind_id == feature_kind.pk:
            if target_level <= existing.level:
                return _MSG_NOT_AN_UPGRADE
            return None
        return RoomAlreadyHasFeatureError.user_message

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415
        from world.room_features.models import (  # noqa: PLC0415
            RoomFeatureInstance,
            RoomFeatureProgressionDetails,
        )
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415

        room_profile = kwargs["room_profile"]
        feature_kind = kwargs["feature_kind"]
        target_level = kwargs["target_level"]

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        if not can_modify_room_features(persona, room_profile.objectdb):
            return ActionResult(success=False, message=_MSG_NOT_STANDING)

        existing = RoomFeatureInstance.objects.filter(room_profile=room_profile).active().first()
        rejection = self._reject_install_or_upgrade(existing, feature_kind, target_level)
        if rejection is not None:
            return ActionResult(success=False, message=rejection)

        now = timezone.now()
        project = Project.objects.create(
            kind=ProjectKind.ROOM_FEATURE_PROGRESSION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=_TIME_LIMIT_DAYS),
            threshold_target=_THRESHOLD_PER_LEVEL * target_level,
            description=f"Install/upgrade {feature_kind.name} to level {target_level}",
        )
        RoomFeatureProgressionDetails.objects.create(
            project=project,
            target_room_profile=room_profile,
            target_feature_kind=feature_kind,
            target_level=target_level,
        )
        return ActionResult(
            success=True,
            message=f"A project to raise the {feature_kind.name} to level {target_level} begins.",
            data={"project_id": project.pk},
        )


_MSG_NO_STATION = "There is no Lab station here."


@dataclass
class RepairLabStationAction(Action):
    """Pay coppers to restore the room's Lab station durability (#1234).

    Thin wrapper over ``world.items.crafting.station.repair_station_durability``
    — resolves the active Lab ``RoomFeatureInstance`` for ``room_profile`` (an
    actions-layer lookup rather than reusing crafting-layer internals, since
    the station's crafting-facing resolver lives one layer down), gates on the
    same owner/tenant standing as installing/upgrading, and charges the actor's
    purse.
    """

    key: str = "repair_lab_station"
    name: str = "Repair Lab Station"
    icon: str = "wrench"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.currency.services import get_or_create_purse  # noqa: PLC0415
        from world.items.crafting.models import LabStationDetails  # noqa: PLC0415
        from world.items.crafting.station import repair_station_durability  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415

        room_profile = kwargs["room_profile"]
        restore_points = kwargs["restore_points"]

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        if not can_modify_room_features(persona, room_profile.objectdb):
            return ActionResult(success=False, message=_MSG_NOT_STANDING)

        instance = (
            RoomFeatureInstance.objects.filter(
                room_profile=room_profile,
                feature_kind__service_strategy=RoomFeatureServiceStrategy.LAB,
            )
            .active()
            .first()
        )
        if instance is None:
            return ActionResult(success=False, message=_MSG_NO_STATION)
        station = LabStationDetails.objects.filter(feature_instance=instance).first()
        if station is None:
            return ActionResult(success=False, message=_MSG_NO_STATION)

        purse = get_or_create_purse(persona.character_sheet)
        try:
            repair_station_durability(
                station=station, restore_points=restore_points, payer_purse=purse
            )
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        station.refresh_from_db()
        return ActionResult(
            success=True,
            message=f"You repair the Lab station: {station.durability}/{station.max_durability}.",
            data={"durability": station.durability, "max_durability": station.max_durability},
        )
