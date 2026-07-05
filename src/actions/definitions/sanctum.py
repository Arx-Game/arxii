"""Sanctum player actions — the action.run() seam for the 7 sanctum ops (#1497).

Each Action wraps an existing service in world/magic/services/sanctum_*.py and is
shared by telnet (commands/sanctum.py via dispatch_player_action) and the web
(world/magic/views_sanctum.py via Action().run()). The Action receives the already
-resolved sanctum / resonance / thread / room_profile as kwargs — each surface
resolves them independently (web: URL id; telnet: caller's room) — and never
self-resolves, so the web detail-ops keep their no-presence-check contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import ResonanceInsufficient, RitualComponentError
from world.magic.models import Ritual, SanctumOwnerMode
from world.magic.services.sanctum_install import (
    AbsorbError,
    DissolutionError,
    SanctificationError,
    absorb_sanctum_pool,
    perform_dissolution,
    perform_sanctification,
    sanctification_fizzle_detail,
)
from world.magic.services.sanctum_rituals import (
    HomecomingValidationError,
    PurgingValidationError,
    perform_homecoming_ritual,
    perform_purging_ritual,
)
from world.magic.services.sanctum_weaving import (
    SanctumWeavingError,
    sever_sanctum_thread,
    weave_sanctum_thread,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_OPERATION_FAILED = "Operation failed."


# ---------------------------------------------------------------------------
# Module-level resolution helpers — shared with commands/sanctum.py so the
# room→RoomProfile→SanctumDetails walk lives in exactly one place.
# ---------------------------------------------------------------------------


def room_profile_for_location(location: Any) -> Any:
    """Return the ``RoomProfile`` for *location*, or ``None``.

    Imported by ``commands/sanctum.py`` so the room-profile resolution is
    single-sourced.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if location is None:
        return None
    return RoomProfile.objects.filter(objectdb=location).first()


def sanctum_in_room(location: Any) -> Any:
    """Return the ``SanctumDetails`` for the room at *location*, or ``None``.

    Imported by ``commands/sanctum.py`` and tested independently so both
    surfaces share one resolution path.
    """
    from world.magic.models import SanctumDetails  # noqa: PLC0415

    rp = room_profile_for_location(location)
    if rp is None:
        return None
    return (
        SanctumDetails.objects.select_related("feature_instance__room_profile", "resonance_type")
        .filter(feature_instance__room_profile=rp, feature_instance__dissolved_at__isnull=True)
        .first()
    )


SANCTUM_EXC = (
    SanctificationError,
    DissolutionError,
    AbsorbError,
    HomecomingValidationError,
    PurgingValidationError,
    SanctumWeavingError,
    ResonanceInsufficient,
)


@dataclass
class SanctumActionBase(Action):
    """Shared base for the seven sanctum verbs."""

    key: str = ""
    name: str = ""
    icon: str = ""
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def _persona(self, actor: ObjectDB) -> Any:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        return active_persona_for_sheet(sheet)

    def _room_profile(self, actor: ObjectDB) -> Any:
        return room_profile_for_location(actor.location)

    def _sanctum_in_room(self, actor: ObjectDB) -> Any:
        return sanctum_in_room(actor.location)

    @staticmethod
    def _fail(message: str) -> ActionResult:
        return ActionResult(success=False, message=message)


# ---------------------------------------------------------------------------
# Concrete sanctum Actions
# ---------------------------------------------------------------------------


@dataclass
class SanctumInstallAction(SanctumActionBase):
    """Sanctify a room — create a new Sanctum (Personal or Covenant)."""

    key: str = "sanctum_install"
    name: str = "Sanctify Room"
    icon: str = "home"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from django.db import transaction  # noqa: PLC0415

        from world.magic.seeds_sanctum import (  # noqa: PLC0415
            SANCTIFICATION_COVENANT_RITUAL_NAME,
            SANCTIFICATION_PERSONAL_RITUAL_NAME,
        )
        from world.magic.services.ritual_components import (  # noqa: PLC0415
            resolve_and_consume_ritual_components,
        )

        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)

        owner_mode = kwargs["owner_mode"]
        ritual_name = (
            SANCTIFICATION_PERSONAL_RITUAL_NAME
            if owner_mode == SanctumOwnerMode.PERSONAL
            else SANCTIFICATION_COVENANT_RITUAL_NAME
        )
        ritual = Ritual.objects.get(name=ritual_name)
        components = kwargs.get("components_provided", [])

        # Both the component consumption AND perform_sanctification's own
        # validation must live in ONE transaction: perform_sanctification does
        # its own @transaction.atomic, but that only wraps ITS body — by the
        # time it's called, the consumption above would already be committed
        # if not for this outer atomic block. A downstream SANCTUM_EXC (e.g.
        # "room already has a feature installed") must roll back the
        # already-consumed touchstone/reagents, not just fail cleanly while
        # leaving them deleted.
        try:
            with transaction.atomic():
                resolve_and_consume_ritual_components(
                    ritual=ritual,
                    components=components,
                    performer_sheet=persona.character_sheet,
                    resonance_context=kwargs["resonance"],
                )
                result = perform_sanctification(
                    kwargs["room_profile"],
                    persona,
                    kwargs["resonance"],
                    owner_mode=owner_mode,
                )
        except RitualComponentError as exc:
            return self._fail(exc.user_message)
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        if result.fizzled:
            return ActionResult(
                success=True,
                message="The sanctification fizzles.",
                data={
                    "fizzled": True,
                    "success_level": result.success_level,
                    "tier": result.tier,
                    "detail": sanctification_fizzle_detail(result.tier),
                },
            )
        return ActionResult(
            success=True,
            message="You sanctify the room.",
            data={
                "sanctum_id": result.sanctum_id,
                "fizzled": False,
                "success_level": result.success_level,
                "tier": result.tier,
            },
        )


@dataclass
class SanctumHomecomingAction(SanctumActionBase):
    """Sacrifice resonance to grow the Sanctum's Homecoming pool."""

    key: str = "sanctum_homecoming"
    name: str = "Perform Homecoming Ritual"
    icon: str = "heart"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            result = perform_homecoming_ritual(
                kwargs["sanctum"],
                persona,
                kwargs["resonance_sacrificed"],
                narrative_text=kwargs.get("narrative_text", ""),
            )
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="The Homecoming ritual is complete.",
            data={
                "base_resonance_added": result.base_resonance_added,
                "overflow_escrowed": result.overflow_escrowed,
                "new_homecoming_sum": result.new_homecoming_sum,
                "new_cap": result.new_cap,
                "success_level": result.success_level,
                "tier": result.tier,
            },
        )


@dataclass
class SanctumPurgingAction(SanctumActionBase):
    """Change the Sanctum's consecrated resonance type."""

    key: str = "sanctum_purging"
    name: str = "Perform Purging Ritual"
    icon: str = "refresh"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            result = perform_purging_ritual(
                kwargs["sanctum"],
                persona,
                kwargs["new_resonance"],
                kwargs["resonance_sacrificed"],
            )
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="The Purging ritual is complete.",
            data={
                "new_resonance_id": result.new_resonance_id,
                "sum_after_drain": result.sum_after_drain,
                "sacrifice_paid": result.sacrifice_paid,
                "success_level": result.success_level,
                "tier": result.tier,
            },
        )


@dataclass
class SanctumWeaveAction(SanctumActionBase):
    """Weave a thread into a Sanctum."""

    key: str = "sanctum_weave"
    name: str = "Weave Sanctum Thread"
    icon: str = "link"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            thread = weave_sanctum_thread(
                kwargs["sanctum"], persona.character_sheet, kwargs["slot_kind"]
            )
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="You weave a thread into the Sanctum.",
            data={"thread_id": thread.pk},
        )


@dataclass
class SanctumDissolveAction(SanctumActionBase):
    """Dissolve a Sanctum, recovering a fraction of its resonance."""

    key: str = "sanctum_dissolve"
    name: str = "Dissolve Sanctum"
    icon: str = "x-circle"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            result = perform_dissolution(kwargs["sanctum"], persona)
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="The Sanctum is dissolved.",
            data={
                "sanctum_id": result.sanctum_id,
                "success_level": result.success_level,
                "recovered_amount": result.recovered_amount,
                "is_botch": result.is_botch,
                "tier": result.tier,
            },
        )


@dataclass
class SanctumAbsorbAction(SanctumActionBase):
    """Drain the Sanctum's weaving pool into resonance currency."""

    key: str = "sanctum_absorb"
    name: str = "Absorb Sanctum Pool"
    icon: str = "download"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            result = absorb_sanctum_pool(kwargs["sanctum"], persona)
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="You absorb the Sanctum's resonance pool.",
            data={
                "sanctum_id": result.sanctum_id,
                "weaving_drained": result.weaving_drained,
                "owner_bonus_drained": result.owner_bonus_drained,
                "total_drained": result.total_drained,
            },
        )


@dataclass
class SanctumSeverAction(SanctumActionBase):
    """Soft-retire a SANCTUM-target Thread."""

    key: str = "sanctum_sever"
    name: str = "Sever Sanctum Thread"
    icon: str = "scissors"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        try:
            sever_sanctum_thread(kwargs["thread"])
        except SANCTUM_EXC as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message="You sever the thread.",
            data={},
        )
