"""Portal travel services (#2222) — route resolution, discovery, install/dissolve.

A character who KNOWS a portal-travel ``Technique`` (one with
``travel_anchor_kind`` set) and stands in a room carrying an active
``PortalAnchor`` of that kind can travel instantly to any other room whose
matching anchor is open to the network (``is_network_open=True``) or where
they hold owner/tenant standing. ``RoomProfile.is_public`` is never
consulted (issue #2222 Decision 5b) — network reachability is governed
entirely by the anchor's own openness/standing gate.

Public functions:
- ``travel_anchor_kinds_for(character)`` — the anchor kinds the character can
  travel through (kinds of their known travel-mode techniques).
- ``portal_destinations(character)`` — every reachable destination anchor,
  for discovery UIs.
- ``portal_route(character, destination_room)`` — the eligible
  (technique, origin anchor, destination anchor) triple for one specific
  destination, or ``None``.
- ``perform_portal_travel(character, route)`` — commits the travel: anima
  debit, departure/arrival broadcasts, the move itself, room-state push.
- ``install_portal_anchor(persona, room, kind, name)`` /
  ``dissolve_portal_anchor(persona, anchor)`` — standing-gated anchor
  lifecycle management.
- ``install_portal_anchor_as_staff(room, kind, name, *, fixture_key=None)`` —
  staff world-building variant (#2451): no owner/tenant standing check, no
  currency cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from world.magic.exceptions import (
    PortalAnchorDissolveNotAllowed,
    PortalAnchorFundsInsufficient,
    PortalAnchorKindAlreadyInstalled,
    PortalAnchorStandingRequired,
)
from world.magic.models import PortalAnchor, PortalAnchorKind, Technique
from world.magic.types.portal_travel import PortalDestination, PortalRoute

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.scenes.models import Persona


def _room_profile_for(location: ObjectDB | None) -> RoomProfile | None:
    """Return the ``RoomProfile`` for ``location``, or ``None``.

    Local, in-app lookup rather than importing
    ``actions.definitions.sanctum.room_profile_for_location`` — services
    don't depend on the actions layer. Mirrors the identical inline query in
    ``world.magic.services.technique_acquisition._training_room_discounted_ap_cost``.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if location is None:
        return None
    return RoomProfile.objects.filter(objectdb=location).first()


def _active_persona_for(character: ObjectDB) -> Persona | None:
    """The character's active persona, or ``None`` if unresolvable.

    Standing checks (``is_owner``/``is_tenant``) are persona-scoped; a
    character with no provisioned sheet/persona simply has no standing
    anywhere.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        return None


def _known_travel_technique_map(character: ObjectDB) -> dict[int, Technique]:
    """``{travel_anchor_kind_id: a known Technique of that kind}`` for ``character``.

    One technique per kind (first by name) — enough to build a route; a
    character who knows several techniques bound to the same anchor kind
    still only needs one to travel through it.
    """
    sheet = character.character_sheet
    if sheet is None:
        return {}

    techniques = Technique.objects.filter(
        character_grants__character=sheet,
        travel_anchor_kind__isnull=False,
    ).order_by("travel_anchor_kind_id", "name")

    result: dict[int, Technique] = {}
    for technique in techniques:
        result.setdefault(technique.travel_anchor_kind_id, technique)
    return result


def _anchor_reachable(anchor: PortalAnchor, persona: Persona | None) -> bool:
    """True when ``anchor`` is open-or-standing for ``persona`` (#2222 Decision).

    Never consults ``RoomProfile.is_public`` — only the anchor's own
    ``is_network_open`` flag, or owner/tenant standing at the anchor's room.
    """
    if anchor.is_network_open:
        return True
    if persona is None:
        return False

    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415

    room = anchor.room_profile.objectdb
    return is_owner(persona, room) or is_tenant(persona, room)


def travel_anchor_kinds_for(character: ObjectDB) -> list[PortalAnchorKind]:
    """The anchor kinds ``character`` can travel through.

    = the ``travel_anchor_kind`` of every ``Technique`` the character knows
    (via ``CharacterTechnique``) that has one set.
    """
    kind_ids = _known_travel_technique_map(character).keys()
    if not kind_ids:
        return []
    return list(PortalAnchorKind.objects.filter(pk__in=kind_ids))


def portal_destinations(character: ObjectDB) -> list[PortalDestination]:
    """Every active destination anchor ``character`` could travel to right now.

    Anchor kinds are narrowed to the character's known travel techniques;
    the current room's own anchors are excluded (that's not a destination);
    a locked (``is_network_open=False``) anchor is visible only when the
    character holds owner/tenant standing there. Ordered by destination
    room name.
    """
    kind_map = _known_travel_technique_map(character)
    if not kind_map:
        return []

    origin_rp = _room_profile_for(character.location)
    persona = _active_persona_for(character)

    anchors = (
        PortalAnchor.objects.active()
        .filter(kind_id__in=kind_map.keys())
        .select_related("kind", "room_profile__objectdb")
    )
    if origin_rp is not None:
        anchors = anchors.exclude(room_profile=origin_rp)

    destinations = [
        PortalDestination(anchor=anchor, room=anchor.room_profile.objectdb, kind=anchor.kind)
        for anchor in anchors
        if _anchor_reachable(anchor, persona)
    ]
    destinations.sort(key=lambda dest: dest.room.key)
    return destinations


def portal_route(character: ObjectDB, destination_room: ObjectDB) -> PortalRoute | None:
    """The eligible portal route from ``character``'s current room to ``destination_room``.

    ``None`` unless: an active origin anchor of a known travel kind is in the
    character's CURRENT room AND the destination room has an active anchor
    of the SAME kind that is open-or-standing. Never consults
    ``RoomProfile.is_public``.
    """
    kind_map = _known_travel_technique_map(character)
    if not kind_map:
        return None

    origin_rp = _room_profile_for(character.location)
    dest_rp = _room_profile_for(destination_room)
    if origin_rp is None or dest_rp is None or origin_rp == dest_rp:
        return None

    origin_anchors = {
        anchor.kind_id: anchor
        for anchor in PortalAnchor.objects.active().filter(
            room_profile=origin_rp, kind_id__in=kind_map.keys()
        )
    }
    if not origin_anchors:
        return None

    persona = _active_persona_for(character)

    destination_anchors = (
        PortalAnchor.objects.active()
        .filter(room_profile=dest_rp, kind_id__in=origin_anchors.keys())
        .select_related("kind", "room_profile__objectdb")
    )
    for destination_anchor in destination_anchors:
        if not _anchor_reachable(destination_anchor, persona):
            continue
        technique = kind_map.get(destination_anchor.kind_id)
        if technique is None:
            continue
        return PortalRoute(
            technique=technique,
            origin_anchor=origin_anchors[destination_anchor.kind_id],
            destination_anchor=destination_anchor,
        )

    return None


@transaction.atomic
def perform_portal_travel(character: ObjectDB, route: PortalRoute) -> None:
    """Commit an eligible portal travel: debit, broadcast, move, broadcast, push.

    Anima debit goes through ``world.magic.services.anima.deduct_anima`` —
    the same standalone debit primitive ``use_technique`` calls in the scene
    cast pipeline (verified callable outside a scene cast; no-ops for
    ``anima_cost <= 0``, which is every seeded travel technique today).
    Movement reuses ``move_object`` + the state-handle/``send_room_state``
    idiom ``HomeAction`` uses (``actions/definitions/movement.py``).
    """
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import (  # noqa: PLC0415
        message_location,
        send_room_state,
    )
    from flows.service_functions.movement import move_object  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    deduct_anima(character, route.technique.anima_cost)

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(character)
    actor_name = actor_state.get_display_name()

    # Plain third-person text, not $You()/actor-stance — actor-stance conjugates
    # the verb only for non-actor viewers, so a pre-conjugated phrasal verb like
    # "steps into" reads "You steps into ..." on the traveler's own screen. Every
    # viewer, including the traveler, sees the identical third-person line (#2222
    # task-2 review).
    message_location(
        actor_state,
        f"{actor_name} {route.origin_anchor.kind.departure_verb} {route.origin_anchor.name}.",
    )

    destination_room = route.destination_anchor.room_profile.objectdb
    dest_state = sdm.initialize_state_for_object(destination_room)
    move_object(actor_state, dest_state, quiet=True)

    actor_state = sdm.initialize_state_for_object(character)
    dest_anchor = route.destination_anchor
    message_location(
        actor_state,
        f"{actor_name} {dest_anchor.kind.arrival_verb} {dest_anchor.name}.",
    )
    send_room_state(actor_state)

    # #2177 whole-branch review, Important #2: portal travel bypassed the
    # ward/alarm reaction entirely -- react_to_unauthorized_entry was only
    # wired into flows.service_functions.movement.traverse_exit, so a room
    # with both a network-open portal anchor and an installed ward/alarm had
    # those defenses silently disabled for portal arrivals (exactly the
    # non-owner/non-tenant population this module's own docstring says can
    # travel to an open anchor). Guard on genuine arrival, mirroring
    # traverse_exit's own discipline.
    if character.location == destination_room:
        from world.room_features.services import react_to_unauthorized_entry  # noqa: PLC0415

        react_to_unauthorized_entry(character, destination_room)


@transaction.atomic
def install_portal_anchor(
    persona: Persona,
    room: ObjectDB,
    kind: PortalAnchorKind,
    name: str,
) -> PortalAnchor:
    """Install a new active ``PortalAnchor`` of ``kind`` in ``room``.

    Gates, in order: owner/tenant standing at ``room``, no existing active
    anchor of ``kind`` already there, and a flat
    ``settings.PORTAL_ANCHOR_INSTALL_COST`` copper debit from the persona's
    purse (checked before debiting — never take the installer's money for an
    install that would be rejected anyway). The balance pre-check covers the
    common case; ``transfer()``'s own row-locked check is the guaranteed
    backstop against a concurrent debit racing the pre-check (#2222 task-2
    review) — its ``ValidationError`` is caught and re-raised as
    ``PortalAnchorFundsInsufficient`` so callers never see a raw currency
    exception.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415
    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415

    if not (is_owner(persona, room) or is_tenant(persona, room)):
        msg = f"persona={persona.pk} has no owner/tenant standing at room={room.pk}."
        raise PortalAnchorStandingRequired(msg)

    room_profile = _room_profile_for(room)
    if room_profile is None:
        msg = f"room={room.pk} has no RoomProfile."
        raise PortalAnchorStandingRequired(msg)

    if PortalAnchor.objects.active().filter(room_profile=room_profile, kind=kind).exists():
        msg = f"room_profile={room_profile.pk} already has an active anchor of kind={kind.pk}."
        raise PortalAnchorKindAlreadyInstalled(msg)

    cost = settings.PORTAL_ANCHOR_INSTALL_COST
    purse = get_or_create_purse(persona.character_sheet)
    if purse.balance < cost:
        msg = f"purse={purse.pk} balance={purse.balance} < install cost={cost}."
        raise PortalAnchorFundsInsufficient(msg)

    try:
        transfer(amount=cost, reason="portal_anchor_install", from_purse=purse)
    except ValidationError as exc:
        msg = f"purse={purse.pk} transfer of cost={cost} failed: {exc}."
        raise PortalAnchorFundsInsufficient(msg) from exc

    return PortalAnchor.objects.create(
        room_profile=room_profile,
        kind=kind,
        name=name,
        installed_by=persona,
    )


def install_portal_anchor_as_staff(
    room: ObjectDB,
    kind: PortalAnchorKind,
    name: str,
    *,
    fixture_key: str | None = None,
) -> PortalAnchor:
    """Install a ``PortalAnchor`` from the staff world-builder canvas (#2451).

    A genuine staff variant of ``install_portal_anchor`` — same model write, but
    skips the owner/tenant standing check and the ``PORTAL_ANCHOR_INSTALL_COST``
    debit entirely (staff authoring, not a player action; mirrors slice 2's
    budget-free staff sibling for ``dig_room``). Still enforces the one
    real data invariant: no two active anchors of the same ``kind`` in one room
    (``PortalAnchorKindAlreadyInstalled``, same as the player path).
    """
    room_profile = _room_profile_for(room)
    if room_profile is None:
        msg = f"room={room.pk} has no RoomProfile."
        raise PortalAnchorStandingRequired(msg)

    if PortalAnchor.objects.active().filter(room_profile=room_profile, kind=kind).exists():
        msg = f"room_profile={room_profile.pk} already has an active anchor of kind={kind.pk}."
        raise PortalAnchorKindAlreadyInstalled(msg)

    return PortalAnchor.objects.create(
        room_profile=room_profile,
        kind=kind,
        name=name,
        fixture_key=fixture_key,
    )


def dissolve_portal_anchor(persona: Persona, anchor: PortalAnchor) -> None:
    """Soft-delete ``anchor`` (owner-gated, no refund — #2222 design)."""
    from world.locations.services import is_owner  # noqa: PLC0415

    room = anchor.room_profile.objectdb
    if not is_owner(persona, room):
        msg = f"persona={persona.pk} lacks owner standing to dissolve anchor={anchor.pk}."
        raise PortalAnchorDissolveNotAllowed(msg)

    anchor.dissolved_at = timezone.now()
    anchor.save(update_fields=["dissolved_at"])
