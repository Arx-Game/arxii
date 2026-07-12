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
from evennia_extensions.models import ExitProfile, RoomProfile
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

_MSG_LEVEL_EXCEEDS_MAX = "Level {level} exceeds the maximum of {max_level}."
_MSG_NO_EXIT = "Install bars on which exit?"
_MSG_WARD_NEEDS_RESONANCE = "A ward installation needs a resonance."
_MSG_NO_WARD = "There is no ward here to fund."
_MSG_INSUFFICIENT_RESONANCE = "You don't have enough resonance."
_MSG_INVALID_AMOUNT = "Amount must be positive."

_DEFENSE_THRESHOLD_PER_LEVEL = 500
_DEFENSE_TIME_LIMIT_DAYS = 14


def _resolve_exit_obj_for_defense(actor: ObjectDB, kwargs: dict) -> ObjectDB | None:
    """Resolve the `exit` kwarg -- ObjectDB (telnet) or exit_id int (web).

    Mirrors `actions.definitions.doors._resolve_exit_obj` (#2176) -- a 6-line
    dual-path resolver duplicated here rather than imported, since it's not
    worth cross-module coupling two definitions files for.
    """
    exit_obj = kwargs.get("exit")
    if exit_obj is not None and hasattr(exit_obj, "pk"):
        return exit_obj
    exit_id = kwargs.get("exit_id")
    if exit_id is not None:
        from evennia.objects.models import ObjectDB as _ObjectDB  # noqa: PLC0415

        return _ObjectDB.objects.filter(pk=exit_id, db_location=actor.location).first()
    return None


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


def _debit_resonance_and_credit_ward(cr: Any, ward: Any, amount: int) -> int | None:
    """Atomically debit ``cr.balance`` and credit ``ward.resonance_reserve``.

    Row-locked (``select_for_update``) + wrapped in ``transaction.atomic`` --
    mirrors ``world.currency.services.transfer``'s established pattern
    (#2177 whole-branch review, Important #3; a prior version did two
    separate, unguarded ``.save()`` calls). The locked re-fetch + re-check
    here is the guaranteed backstop against a concurrent debit racing this
    one, and it also ensures the debit and the credit either both land or
    neither does.

    Returns the ward's new ``resonance_reserve``, or ``None`` if the
    locked balance no longer covers ``amount``.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415
    from world.room_features.models import RoomWardDetails  # noqa: PLC0415

    with transaction.atomic():
        cr = CharacterResonance.objects.select_for_update().get(pk=cr.pk)
        if cr.balance < amount:
            return None
        cr.balance -= amount
        cr.save(update_fields=["balance"])

        ward = RoomWardDetails.objects.select_for_update().get(pk=ward.pk)
        ward.resonance_reserve += amount
        update_fields = ["resonance_reserve"]
        if ward.lapsed_at is not None:
            ward.lapsed_at = None
            update_fields.append("lapsed_at")
        ward.save(update_fields=update_fields)
        return ward.resonance_reserve


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
        ``target_level`` is bounded by ``feature_kind.max_level`` on BOTH the install
        and upgrade paths — this is the only player-reachable write path for
        ``target_level``/``RoomFeatureInstance.level``, so the bound their docstrings
        claim is enforced "at write/project-creation time" has to live here.
        """
        if target_level > feature_kind.max_level:
            return (
                f"Level {target_level} exceeds this feature kind's maximum of "
                f"{feature_kind.max_level}."
            )
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
            return ActionResult(success=False, message=exc.messages[0])

        station.refresh_from_db()
        return ActionResult(
            success=True,
            message=f"You repair the Lab station: {station.durability}/{station.max_durability}.",
            data={"durability": station.durability, "max_durability": station.max_durability},
        )


@dataclass
class StartDefenseInstallationAction(Action):
    """Create a ROOM_DEFENSE_INSTALLATION project to install/upgrade a defense (#2177).

    Bars target a specific exit (ExitProfile); ward/alarm target the actor's
    current room (RoomProfile). Independent of RoomFeatureKind/
    RoomFeatureInstance (Decision 1) -- a room may hold a RoomFeatureInstance
    AND a ward AND an alarm simultaneously; bars on one exit don't affect
    another exit from the same room.
    """

    key: str = "start_defense_installation"
    name: str = "Start Defense Installation"
    icon: str = "shield"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    @staticmethod
    def _max_level_for(defense_kind: str) -> int:
        from world.room_features.constants import (  # noqa: PLC0415
            EXIT_BARS_MAX_LEVEL,
            ROOM_ALARM_MAX_LEVEL,
            ROOM_WARD_MAX_LEVEL,
            DefenseKind,
        )

        return {
            DefenseKind.EXIT_BARS: EXIT_BARS_MAX_LEVEL,
            DefenseKind.ROOM_WARD: ROOM_WARD_MAX_LEVEL,
            DefenseKind.ROOM_ALARM: ROOM_ALARM_MAX_LEVEL,
        }[defense_kind]

    @staticmethod
    def _resolve_bars_target(
        actor: ObjectDB, persona: Any, target_level: int, kwargs: dict
    ) -> tuple[Any, str | None]:
        """Resolve the exit bars target; returns ``(target_exit_profile, rejection)``."""
        from world.room_features.models import ExitBarsDetails  # noqa: PLC0415
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415

        exit_obj = _resolve_exit_obj_for_defense(actor, kwargs)
        if exit_obj is None:
            return None, _MSG_NO_EXIT
        if not can_modify_room_features(persona, exit_obj.location):
            return None, _MSG_NOT_STANDING

        target_exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        existing = ExitBarsDetails.objects.filter(exit_profile=target_exit_profile).active().first()
        if existing is not None and target_level <= existing.level:
            return None, _MSG_NOT_AN_UPGRADE
        return target_exit_profile, None

    @staticmethod
    def _resolve_room_target(
        actor: ObjectDB, persona: Any, defense_kind: str, target_level: int, kwargs: dict
    ) -> tuple[Any, Any, str | None]:
        """Resolve the ward/alarm target room.

        Returns ``(target_room_profile, resonance, rejection)``.
        """
        from world.room_features.constants import DefenseKind  # noqa: PLC0415
        from world.room_features.models import RoomAlarmDetails, RoomWardDetails  # noqa: PLC0415
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415

        room = actor.location
        if not can_modify_room_features(persona, room):
            return None, None, _MSG_NOT_STANDING

        target_room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)

        resonance = None
        if defense_kind == DefenseKind.ROOM_WARD:
            resonance = kwargs.get("resonance")
            if resonance is None:
                return target_room_profile, None, _MSG_WARD_NEEDS_RESONANCE
            existing = (
                RoomWardDetails.objects.filter(room_profile=target_room_profile).active().first()
            )
        else:
            existing = (
                RoomAlarmDetails.objects.filter(room_profile=target_room_profile).active().first()
            )
        if existing is not None and target_level <= existing.level:
            return target_room_profile, resonance, _MSG_NOT_AN_UPGRADE
        return target_room_profile, resonance, None

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415
        from world.room_features.constants import DefenseKind  # noqa: PLC0415
        from world.room_features.models import DefenseProgressionDetails  # noqa: PLC0415

        defense_kind = kwargs["defense_kind"]
        target_level = kwargs["target_level"]

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        max_level = self._max_level_for(defense_kind)
        if target_level > max_level:
            return ActionResult(
                success=False,
                message=_MSG_LEVEL_EXCEEDS_MAX.format(level=target_level, max_level=max_level),
            )

        target_exit_profile = None
        target_room_profile = None
        resonance = None
        if defense_kind == DefenseKind.EXIT_BARS:
            target_exit_profile, rejection = self._resolve_bars_target(
                actor, persona, target_level, kwargs
            )
        else:
            target_room_profile, resonance, rejection = self._resolve_room_target(
                actor, persona, defense_kind, target_level, kwargs
            )
        if rejection is not None:
            return ActionResult(success=False, message=rejection)

        now = timezone.now()
        project = Project.objects.create(
            kind=ProjectKind.ROOM_DEFENSE_INSTALLATION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=_DEFENSE_TIME_LIMIT_DAYS),
            threshold_target=_DEFENSE_THRESHOLD_PER_LEVEL * target_level,
            description=f"Install/upgrade {defense_kind} to level {target_level}",
        )
        DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=defense_kind,
            target_exit_profile=target_exit_profile,
            target_room_profile=target_room_profile,
            target_level=target_level,
            resonance=resonance,
        )
        return ActionResult(
            success=True,
            message=f"A project to raise this defense to level {target_level} begins.",
            data={"project_id": project.pk},
        )


@dataclass
class FundRoomWardAction(Action):
    """Spend personal resonance into a room ward's upkeep reserve (#2177).

    Decoupled from the Project-funded install (copper/effort) -- Project
    funding is copper-only (world.projects has no arbitrary-resource funding
    path), so the ward's ongoing resonance upkeep is a separate mechanic.
    """

    key: str = "fund_room_ward"
    name: str = "Fund Room Ward"
    icon: str = "sparkles"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.models.aura import CharacterResonance  # noqa: PLC0415
        from world.room_features.models import RoomWardDetails  # noqa: PLC0415
        from world.room_features.services import can_modify_room_features  # noqa: PLC0415

        amount = kwargs["amount"]
        if amount <= 0:
            return ActionResult(success=False, message=_MSG_INVALID_AMOUNT)

        persona = _resolve_active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        room = actor.location
        if not can_modify_room_features(persona, room):
            return ActionResult(success=False, message=_MSG_NOT_STANDING)

        room_profile = RoomProfile.objects.filter(objectdb=room).first()
        ward = (
            RoomWardDetails.objects.filter(room_profile=room_profile).active().first()
            if room_profile is not None
            else None
        )
        if ward is None:
            return ActionResult(success=False, message=_MSG_NO_WARD)

        cr = CharacterResonance.objects.filter(
            character_sheet=persona.character_sheet, resonance=ward.resonance
        ).first()
        reserve = _debit_resonance_and_credit_ward(cr, ward, amount) if cr is not None else None
        if reserve is None:
            return ActionResult(success=False, message=_MSG_INSUFFICIENT_RESONANCE)

        return ActionResult(
            success=True,
            message=f"You channel {amount} resonance into the ward.",
            data={"resonance_reserve": reserve},
        )
