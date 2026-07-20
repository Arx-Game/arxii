"""Tests for portal travel services (#2222 Task 2)."""

from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import CharacterPurse
from world.locations.factories import LocationOwnershipFactory, LocationTenancyFactory
from world.magic.exceptions import (
    PortalAnchorDissolveNotAllowed,
    PortalAnchorFundsInsufficient,
    PortalAnchorKindAlreadyInstalled,
    PortalAnchorStandingRequired,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    PortalAnchorFactory,
    PortalAnchorKindFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterAnima, PortalAnchor
from world.magic.services.portal_travel import (
    dissolve_portal_anchor,
    install_portal_anchor,
    install_portal_anchor_as_staff,
    perform_portal_travel as _perform_portal_travel,
    portal_destinations,
    portal_route,
    travel_anchor_kinds_for,
)
from world.magic.types.portal_travel import PortalRoute


def _make_room(key: str):
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    room_profile = RoomProfileFactory(objectdb=room)
    return room, room_profile


def _make_traveler(location, *, technique=None, anima=10):
    character = CharacterFactory(location=location)
    sheet = CharacterSheetFactory(character=character)
    CharacterAnimaFactory(character=character, current=anima, maximum=anima)
    if technique is not None:
        CharacterTechniqueFactory(character=sheet, technique=technique)
    return character, sheet


class TravelAnchorKindsForTests(TestCase):
    def test_no_known_technique_returns_empty(self) -> None:
        room, _rp = _make_room("Room")
        character, _sheet = _make_traveler(room)

        self.assertEqual(travel_anchor_kinds_for(character), [])

    def test_known_travel_technique_returns_its_kind(self) -> None:
        kind = PortalAnchorKindFactory(name="Mirror")
        technique = TechniqueFactory(travel_anchor_kind=kind)
        room, _rp = _make_room("Room")
        character, _sheet = _make_traveler(room, technique=technique)

        self.assertEqual(travel_anchor_kinds_for(character), [kind])

    def test_known_non_travel_technique_excluded(self) -> None:
        technique = TechniqueFactory()  # travel_anchor_kind=None
        room, _rp = _make_room("Room")
        character, _sheet = _make_traveler(room, technique=technique)

        self.assertEqual(travel_anchor_kinds_for(character), [])


class PortalDestinationsTests(TestCase):
    def test_empty_when_no_known_kinds(self) -> None:
        room, _rp = _make_room("Room")
        character, _sheet = _make_traveler(room)

        self.assertEqual(portal_destinations(character), [])

    def test_excludes_current_room(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        room, room_profile = _make_room("Here")
        PortalAnchorFactory(room_profile=room_profile, kind=kind)
        character, _sheet = _make_traveler(room, technique=technique)

        self.assertEqual(portal_destinations(character), [])

    def test_locked_anchor_invisible_to_stranger(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, _origin_rp = _make_room("Origin")
        _dest, dest_rp = _make_room("Locked Room")
        PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)
        character, _sheet = _make_traveler(origin, technique=technique)

        self.assertEqual(portal_destinations(character), [])

    def test_locked_anchor_visible_to_owner(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, _origin_rp = _make_room("Origin")
        _dest, dest_rp = _make_room("Owned Room")
        anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)
        character, sheet = _make_traveler(origin, technique=technique)
        LocationOwnershipFactory(
            on_room=True, room_profile=dest_rp, holder_persona=sheet.primary_persona
        )

        destinations = portal_destinations(character)

        self.assertEqual([d.anchor for d in destinations], [anchor])

    def test_open_anchor_visible_to_stranger(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, _origin_rp = _make_room("Origin")
        _dest, dest_rp = _make_room("Open Room")
        anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=True)
        character, _sheet = _make_traveler(origin, technique=technique)

        destinations = portal_destinations(character)

        self.assertEqual([d.anchor for d in destinations], [anchor])

    def test_ordered_by_room_name(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, _origin_rp = _make_room("Origin")
        _b_room, b_rp = _make_room("Bravo Hall")
        _a_room, a_rp = _make_room("Alpha Hall")
        PortalAnchorFactory(room_profile=b_rp, kind=kind, is_network_open=True)
        PortalAnchorFactory(room_profile=a_rp, kind=kind, is_network_open=True)
        character, _sheet = _make_traveler(origin, technique=technique)

        destinations = portal_destinations(character)

        self.assertEqual([d.room.key for d in destinations], ["Alpha Hall", "Bravo Hall"])


class PortalRouteTests(TestCase):
    def test_none_when_no_known_gift(self) -> None:
        kind = PortalAnchorKindFactory()
        origin, origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=kind)
        character, _sheet = _make_traveler(origin)

        self.assertIsNone(portal_route(character, dest))

    def test_none_when_no_origin_anchor(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, _origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        PortalAnchorFactory(room_profile=dest_rp, kind=kind)
        character, _sheet = _make_traveler(origin, technique=technique)

        self.assertIsNone(portal_route(character, dest))

    def test_none_when_no_destination_anchor(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, origin_rp = _make_room("Origin")
        dest, _dest_rp = _make_room("Dest")
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        character, _sheet = _make_traveler(origin, technique=technique)

        self.assertIsNone(portal_route(character, dest))

    def test_none_when_kind_mismatch(self) -> None:
        origin_kind = PortalAnchorKindFactory(name="Mirror")
        dest_kind = PortalAnchorKindFactory(name="Doorway")
        technique = TechniqueFactory(travel_anchor_kind=origin_kind)
        origin, origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        PortalAnchorFactory(room_profile=origin_rp, kind=origin_kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=dest_kind)
        character, _sheet = _make_traveler(origin, technique=technique)

        self.assertIsNone(portal_route(character, dest))

    def test_none_when_locked_and_no_standing(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)
        character, _sheet = _make_traveler(origin, technique=technique)

        self.assertIsNone(portal_route(character, dest))

    def test_route_when_locked_and_owner(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        origin_anchor = PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        dest_anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)
        character, sheet = _make_traveler(origin, technique=technique)
        LocationOwnershipFactory(
            on_room=True, room_profile=dest_rp, holder_persona=sheet.primary_persona
        )

        route = portal_route(character, dest)

        assert route is not None
        self.assertEqual(route.technique, technique)
        self.assertEqual(route.origin_anchor, origin_anchor)
        self.assertEqual(route.destination_anchor, dest_anchor)

    def test_route_when_open_and_stranger(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        origin, origin_rp = _make_room("Origin")
        dest, dest_rp = _make_room("Dest")
        origin_anchor = PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        dest_anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=True)
        character, _sheet = _make_traveler(origin, technique=technique)

        route = portal_route(character, dest)

        assert route is not None
        self.assertEqual(route.origin_anchor, origin_anchor)
        self.assertEqual(route.destination_anchor, dest_anchor)


class PerformPortalTravelTests(TestCase):
    def _make_route_and_traveler(self):
        kind = PortalAnchorKindFactory(
            name="Mirror", departure_verb="steps into", arrival_verb="steps out of"
        )
        origin, origin_rp = _make_room("Origin Room")
        dest, dest_rp = _make_room("Destination Room")
        origin_anchor = PortalAnchorFactory(
            room_profile=origin_rp, kind=kind, name="a tall silvered mirror"
        )
        dest_anchor = PortalAnchorFactory(
            room_profile=dest_rp, kind=kind, name="a dusty hand mirror"
        )
        technique = TechniqueFactory(travel_anchor_kind=kind, anima_cost=3)
        traveler, _sheet = _make_traveler(origin, technique=technique, anima=10)

        route = PortalRoute(
            technique=technique, origin_anchor=origin_anchor, destination_anchor=dest_anchor
        )
        return traveler, route, origin, dest

    def test_actor_ends_up_in_destination_room(self) -> None:
        traveler, route, _origin, dest = self._make_route_and_traveler()

        with patch.object(traveler, "msg"):
            _perform_portal_travel(traveler, route)

        traveler.refresh_from_db()
        self.assertEqual(traveler.location, dest)

    def test_broadcasts_departure_and_arrival_verbs(self) -> None:
        traveler, route, origin, dest = self._make_route_and_traveler()
        witness = CharacterFactory(location=origin)
        greeter = CharacterFactory(location=dest)

        with (
            patch.object(traveler, "msg") as traveler_msg,
            patch.object(witness, "msg") as witness_msg,
            patch.object(greeter, "msg") as greeter_msg,
        ):
            _perform_portal_travel(traveler, route)

        # Plain third-person text — no $You()/actor-stance — so the traveler's
        # own screen and observers' screens read the IDENTICAL line (#2222
        # task-2 review: $You() + a pre-conjugated phrasal verb read "You steps
        # into ..." on the actor's own screen, since actor-stance only
        # conjugates for non-actor viewers).
        departure_text = witness_msg.call_args.kwargs["text"][0]
        traveler_departure_text = traveler_msg.call_args_list[0].kwargs["text"][0]
        self.assertEqual(traveler_departure_text, departure_text)
        self.assertTrue(departure_text.endswith("steps into a tall silvered mirror."))
        self.assertNotIn("You steps", departure_text)

        arrival_text = greeter_msg.call_args.kwargs["text"][0]
        # index 2, not 1: move_object's non-quiet arrival auto-look sends an
        # intervening "text" call (index 1) between the departure (0) and
        # arrival (2) broadcasts.
        traveler_arrival_text = traveler_msg.call_args_list[2].kwargs["text"][0]
        self.assertEqual(traveler_arrival_text, arrival_text)
        self.assertTrue(arrival_text.endswith("steps out of a dusty hand mirror."))
        self.assertNotIn("You steps", arrival_text)

    def test_deducts_anima(self) -> None:
        traveler, route, *_ = self._make_route_and_traveler()

        with patch.object(traveler, "msg"):
            _perform_portal_travel(traveler, route)

        anima = CharacterAnima.objects.get(character=traveler)
        self.assertEqual(anima.current, 10 - route.technique.anima_cost)


class PerformPortalTravelWardAlarmReactionTests(TestCase):
    """#2177 whole-branch review, Important #2: portal travel must trigger the
    same ward/alarm reaction exit-traversal does -- a room's defenses must not
    be silently disabled just because the intruder arrived through an open
    portal anchor instead of an exit.
    """

    def test_alarm_notifies_owner_on_portal_arrival(self) -> None:
        from world.locations.services import transfer_ownership
        from world.narrative.models import NarrativeMessageDelivery
        from world.room_features.models import RoomAlarmDetails
        from world.scenes.factories import PersonaFactory

        kind = PortalAnchorKindFactory(name="Mirror")
        origin, origin_rp = _make_room("Origin Room")
        _dest, dest_rp = _make_room("Warded Room")
        origin_anchor = PortalAnchorFactory(room_profile=origin_rp, kind=kind)
        dest_anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=True)
        technique = TechniqueFactory(travel_anchor_kind=kind, anima_cost=0)
        traveler, _sheet = _make_traveler(origin, technique=technique, anima=10)

        owner_sheet = CharacterSheetFactory()
        owner_persona = PersonaFactory(character_sheet=owner_sheet)
        transfer_ownership(room_profile=dest_rp, to_persona=owner_persona)
        RoomAlarmDetails.objects.create(room_profile=dest_rp)

        route = PortalRoute(
            technique=technique, origin_anchor=origin_anchor, destination_anchor=dest_anchor
        )

        with patch.object(traveler, "msg"):
            _perform_portal_travel(traveler, route)

        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=owner_sheet).exists()
        )


class InstallPortalAnchorTests(TestCase):
    def test_no_standing_raises(self) -> None:
        room, _room_profile = _make_room("Locked Room")
        sheet = CharacterSheetFactory()
        kind = PortalAnchorKindFactory()

        with self.assertRaises(PortalAnchorStandingRequired):
            install_portal_anchor(sheet.primary_persona, room, kind, "a mirror")

    def test_tenant_can_install_and_debits_flat_cost(self) -> None:
        room, room_profile = _make_room("Tenant Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
        purse = CharacterPurse.objects.create(character_sheet=sheet, balance=10_000)
        kind = PortalAnchorKindFactory()

        anchor = install_portal_anchor(persona, room, kind, "a tall silvered mirror")

        self.assertEqual(anchor.room_profile, room_profile)
        self.assertEqual(anchor.kind, kind)
        self.assertEqual(anchor.name, "a tall silvered mirror")
        self.assertEqual(anchor.installed_by, persona)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 10_000 - settings.PORTAL_ANCHOR_INSTALL_COST)

    def test_owner_can_install(self) -> None:
        room, room_profile = _make_room("Owned Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationOwnershipFactory(on_room=True, room_profile=room_profile, holder_persona=persona)
        CharacterPurse.objects.create(character_sheet=sheet, balance=10_000)
        kind = PortalAnchorKindFactory()

        anchor = install_portal_anchor(persona, room, kind, "a mirror")

        self.assertTrue(PortalAnchor.objects.active().filter(pk=anchor.pk).exists())

    def test_duplicate_active_kind_rejected(self) -> None:
        room, room_profile = _make_room("Tenant Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
        purse = CharacterPurse.objects.create(character_sheet=sheet, balance=10_000)
        kind = PortalAnchorKindFactory()
        PortalAnchorFactory(room_profile=room_profile, kind=kind)

        with self.assertRaises(PortalAnchorKindAlreadyInstalled):
            install_portal_anchor(persona, room, kind, "a second mirror")

        purse.refresh_from_db()
        self.assertEqual(purse.balance, 10_000)  # no debit on rejection

    def test_insufficient_funds_rejected(self) -> None:
        room, room_profile = _make_room("Tenant Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
        CharacterPurse.objects.create(character_sheet=sheet, balance=0)
        kind = PortalAnchorKindFactory()

        with self.assertRaises(PortalAnchorFundsInsufficient):
            install_portal_anchor(persona, room, kind, "a mirror")

        self.assertFalse(PortalAnchor.objects.active().filter(room_profile=room_profile).exists())

    def test_concurrent_debit_race_contained_as_funds_insufficient(self) -> None:
        """A concurrent debit racing the balance pre-check must still surface as
        ``PortalAnchorFundsInsufficient`` — never a raw ``ValidationError`` escaping
        from ``transfer()`` (#2222 task-2 review)."""
        room, room_profile = _make_room("Tenant Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
        purse = CharacterPurse.objects.create(character_sheet=sheet, balance=10_000)
        kind = PortalAnchorKindFactory()

        with (
            patch(
                "world.currency.services.transfer",
                side_effect=ValidationError("Insufficient funds: raced by a concurrent debit."),
            ),
            self.assertRaises(PortalAnchorFundsInsufficient),
        ):
            install_portal_anchor(persona, room, kind, "a mirror")

        purse.refresh_from_db()
        self.assertEqual(purse.balance, 10_000)  # mocked transfer never actually debited
        self.assertFalse(PortalAnchor.objects.active().filter(room_profile=room_profile).exists())


class InstallPortalAnchorAsStaffTests(TestCase):
    def test_creates_anchor_without_standing_or_cost(self) -> None:
        room_profile = RoomProfileFactory()
        kind = PortalAnchorKindFactory()

        # No persona, no purse setup at all — staff install must not touch currency.
        anchor = install_portal_anchor_as_staff(
            room=room_profile.objectdb, kind=kind, name="a tall silvered mirror"
        )
        self.assertEqual(anchor.room_profile, room_profile)
        self.assertEqual(anchor.kind, kind)
        self.assertIsNone(anchor.installed_by)

    def test_rejects_duplicate_active_kind_in_same_room(self) -> None:
        room_profile = RoomProfileFactory()
        kind = PortalAnchorKindFactory()
        PortalAnchorFactory(room_profile=room_profile, kind=kind)

        with self.assertRaises(PortalAnchorKindAlreadyInstalled):
            install_portal_anchor_as_staff(room=room_profile.objectdb, kind=kind, name="another")

    def test_sets_fixture_key_when_given(self) -> None:
        room_profile = RoomProfileFactory()
        kind = PortalAnchorKindFactory()

        anchor = install_portal_anchor_as_staff(
            room=room_profile.objectdb,
            kind=kind,
            name="a doorway",
            fixture_key="arx-city/golden-hart-taproom/doorway",
        )
        self.assertEqual(anchor.fixture_key, "arx-city/golden-hart-taproom/doorway")


class DissolvePortalAnchorTests(TestCase):
    def test_owner_can_dissolve(self) -> None:
        _room, room_profile = _make_room("Owned Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationOwnershipFactory(on_room=True, room_profile=room_profile, holder_persona=persona)
        anchor = PortalAnchorFactory(room_profile=room_profile)

        dissolve_portal_anchor(persona, anchor)

        anchor.refresh_from_db()
        self.assertIsNotNone(anchor.dissolved_at)

    def test_tenant_without_ownership_cannot_dissolve(self) -> None:
        _room, room_profile = _make_room("Tenant Room")
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
        anchor = PortalAnchorFactory(room_profile=room_profile)

        with self.assertRaises(PortalAnchorDissolveNotAllowed):
            dissolve_portal_anchor(persona, anchor)

        anchor.refresh_from_db()
        self.assertIsNone(anchor.dissolved_at)

    def test_stranger_cannot_dissolve(self) -> None:
        _room, room_profile = _make_room("Room")
        sheet = CharacterSheetFactory()
        anchor = PortalAnchorFactory(room_profile=room_profile)

        with self.assertRaises(PortalAnchorDissolveNotAllowed):
            dissolve_portal_anchor(sheet.primary_persona, anchor)
