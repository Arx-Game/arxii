"""Portal anchor lifecycle actions — install/dissolve (#2222).

Two thin REGISTRY actions wrapping ``world.magic.services.portal_travel``'s
``install_portal_anchor``/``dissolve_portal_anchor``. Kept out of
``movement.py`` (already crowded with the auto-walk pair) per the task-3
brief. Both act on the actor's CURRENT room (mirrors the Sanctum family's
"installation in room" shape, `actions/definitions/sanctum.py`) — telnet
`CmdPortalAnchor` (`commands/portals.py`) resolves the kind/anchor from text
and calls `.run()` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import (
    PortalAnchorDissolveNotAllowed,
    PortalAnchorFundsInsufficient,
    PortalAnchorKindAlreadyInstalled,
    PortalAnchorStandingRequired,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import PortalAnchor, PortalAnchorKind


_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_NO_LOCATION = "You have no location to install an anchor in."
_MSG_INSTALL_USAGE = "Install what, and of what kind?"
_MSG_NO_ANCHOR_HERE = "There is no portal anchor here to dissolve."

_INSTALL_EXC = (
    PortalAnchorStandingRequired,
    PortalAnchorKindAlreadyInstalled,
    PortalAnchorFundsInsufficient,
)


def _resolve_kind_kwarg(value: Any) -> PortalAnchorKind | None:
    """Resolve the ``kind`` kwarg to a ``PortalAnchorKind`` instance.

    Telnet (`commands/portals.py`) always resolves the kind from parsed text
    before calling ``.run()``, so ``value`` is already a model instance there.
    The generic REST dispatch path (``DispatchActionView`` ->
    ``_dispatch_registry``, `actions/player_interface.py`) does **no**
    ObjectDB/FK resolution of its own and hands ``execute()`` the raw wire
    kwarg — an int pk today, or (accepted here for symmetry, trivial to
    support) a kind name string. Mirrors ``_resolve_room()`` in
    `actions/definitions/locations.py:92-100`. Returns ``None`` on a failed
    lookup rather than raising — the caller folds that into the existing
    usage-failure message.
    """
    from world.magic.models import PortalAnchorKind  # noqa: PLC0415

    if value is None or isinstance(value, PortalAnchorKind):
        return value
    if isinstance(value, int):
        return PortalAnchorKind.objects.filter(pk=value).first()
    if isinstance(value, str):
        return PortalAnchorKind.objects.filter(name__iexact=value.strip()).first()
    return None


def _resolve_anchor_kwarg(value: Any) -> PortalAnchor | None:
    """Resolve the ``anchor`` kwarg to a ``PortalAnchor`` instance.

    Telnet (`commands/portals.py`) always resolves the anchor from parsed
    text before calling ``.run()``, so ``value`` is already a model instance
    there. The REST dispatch path passes a raw int pk — see
    ``_resolve_kind_kwarg`` above for the full rationale. Returns ``None`` on
    a failed (or dissolved) lookup rather than raising; the caller falls
    through to the existing room-based disambiguation, which fails gracefully
    on its own.
    """
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    if value is None or isinstance(value, PortalAnchor):
        return value
    if isinstance(value, int):
        return PortalAnchor.objects.active().filter(pk=value).first()
    return None


def anchors_in_room(location: Any) -> list[PortalAnchor]:
    """Active ``PortalAnchor`` rows installed in *location*'s room, or ``[]``.

    Shared by ``DissolvePortalAnchorAction`` and ``commands/portals.py`` so
    the room lookup + kind disambiguation lives in one place (mirrors
    ``sanctum_in_room`` in `actions/definitions/sanctum.py`).
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    if location is None:
        return []
    room_profile = RoomProfile.objects.filter(objectdb=location).first()
    if room_profile is None:
        return []
    return list(
        PortalAnchor.objects.active().filter(room_profile=room_profile).select_related("kind")
    )


@dataclass
class PortalAnchorActionBase(Action):
    """Shared base for the two portal-anchor lifecycle verbs."""

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

    @staticmethod
    def _fail(message: str) -> ActionResult:
        return ActionResult(success=False, message=message)


@dataclass
class InstallPortalAnchorAction(PortalAnchorActionBase):
    """Install a portal anchor of a given kind in the actor's current room.

    Expects kwargs: ``kind`` (``PortalAnchorKind``), ``name`` (str).
    """

    key: str = "portal_anchor_install"
    name: str = "Install Portal Anchor"
    icon: str = "door-open"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.portal_travel import install_portal_anchor  # noqa: PLC0415

        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)

        room = actor.location
        if room is None:
            return self._fail(_MSG_NO_LOCATION)

        kind = _resolve_kind_kwarg(kwargs.get("kind"))
        anchor_name = (kwargs.get("name") or "").strip()
        if kind is None or not anchor_name:
            return self._fail(_MSG_INSTALL_USAGE)

        try:
            anchor = install_portal_anchor(persona, room, kind, anchor_name)
        except _INSTALL_EXC as exc:
            return self._fail(exc.user_message)

        return ActionResult(
            success=True,
            message=f"You install {anchor.name} here.",
            data={"anchor_id": anchor.pk, "kind_id": anchor.kind_id},
        )


@dataclass
class DissolvePortalAnchorAction(PortalAnchorActionBase):
    """Dissolve a portal anchor in the actor's current room (owner-gated, no refund).

    Expects optional kwarg ``anchor`` (``PortalAnchor``, pre-resolved by the
    caller). When omitted, resolves the sole active anchor in the actor's
    room; a room with zero or multiple active anchors fails with a
    disambiguation message rather than guessing.
    """

    key: str = "portal_anchor_dissolve"
    name: str = "Dissolve Portal Anchor"
    icon: str = "door-closed"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.portal_travel import dissolve_portal_anchor  # noqa: PLC0415

        persona = self._persona(actor)
        if persona is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)

        anchor = _resolve_anchor_kwarg(kwargs.get("anchor"))
        if anchor is None:
            candidates = anchors_in_room(actor.location)
            if not candidates:
                return self._fail(_MSG_NO_ANCHOR_HERE)
            if len(candidates) > 1:
                names = ", ".join(a.kind.name for a in candidates)
                return self._fail(f"Multiple anchors here — specify a kind: {names}.")
            anchor = candidates[0]

        try:
            dissolve_portal_anchor(persona, anchor)
        except PortalAnchorDissolveNotAllowed as exc:
            return self._fail(exc.user_message)

        return ActionResult(
            success=True,
            message=f"{anchor.name} dissolves.",
            data={"anchor_id": anchor.pk},
        )
