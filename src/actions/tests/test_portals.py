"""Tests for portal anchor install/dissolve Actions (#2222 Task 3).

Real DB fixtures throughout (not mocked services) — these exercise the same
``action.run()`` seam telnet ``CmdPortalAnchor`` and any future web surface
converge on, mirroring `world/magic/tests/test_portal_travel.py`'s
integration style for the underlying service.
"""

from __future__ import annotations

from django.conf import settings
from django.test import TestCase

from actions.definitions.portals import DissolvePortalAnchorAction, InstallPortalAnchorAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import CharacterPurse
from world.locations.factories import LocationOwnershipFactory, LocationTenancyFactory
from world.magic.factories import PortalAnchorFactory, PortalAnchorKindFactory
from world.magic.models import PortalAnchor


def _make_room(key):
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    room_profile = RoomProfileFactory(objectdb=room)
    return room, room_profile


def _make_resident(room, room_profile, *, tenant=False, owner=False, balance=10_000):
    """A Character resident in ``room``, with a purse and optional standing."""
    actor = CharacterFactory(location=room)
    sheet = CharacterSheetFactory(character=actor)
    persona = sheet.primary_persona
    if tenant:
        LocationTenancyFactory(room_profile=room_profile, tenant_persona=persona)
    if owner:
        LocationOwnershipFactory(on_room=True, room_profile=room_profile, holder_persona=persona)
    CharacterPurse.objects.create(character_sheet=sheet, balance=balance)
    return actor, sheet, persona


class InstallPortalAnchorActionTests(TestCase):
    def test_tenant_installs_and_debits_purse(self):
        room, room_profile = _make_room("Tenant Room")
        actor, sheet, persona = _make_resident(room, room_profile, tenant=True)
        kind = PortalAnchorKindFactory(name="Mirror")

        result = InstallPortalAnchorAction().run(actor, kind=kind, name="a tall silvered mirror")

        assert result.success is True
        anchor = PortalAnchor.objects.active().get(room_profile=room_profile, kind=kind)
        assert anchor.name == "a tall silvered mirror"
        assert anchor.installed_by == persona
        purse = CharacterPurse.objects.get(character_sheet=sheet)
        assert purse.balance == 10_000 - settings.PORTAL_ANCHOR_INSTALL_COST

    def test_owner_can_also_install(self):
        room, room_profile = _make_room("Owned Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)
        kind = PortalAnchorKindFactory()

        result = InstallPortalAnchorAction().run(actor, kind=kind, name="a mirror")

        assert result.success is True
        assert PortalAnchor.objects.active().filter(room_profile=room_profile, kind=kind).exists()

    def test_stranger_without_standing_is_denied(self):
        room, room_profile = _make_room("Stranger Room")
        actor, _sheet, _persona = _make_resident(room, room_profile)  # no standing
        kind = PortalAnchorKindFactory()

        result = InstallPortalAnchorAction().run(actor, kind=kind, name="a mirror")

        assert result.success is False
        assert result.message == "You don't have standing to install a portal anchor here."
        assert not PortalAnchor.objects.active().filter(room_profile=room_profile).exists()

    def test_insufficient_funds_is_denied(self):
        room, room_profile = _make_room("Poor Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True, balance=0)
        kind = PortalAnchorKindFactory()

        result = InstallPortalAnchorAction().run(actor, kind=kind, name="a mirror")

        assert result.success is False
        assert result.message == "You cannot afford to install a portal anchor here."
        assert not PortalAnchor.objects.active().filter(room_profile=room_profile).exists()

    def test_duplicate_kind_in_room_is_denied(self):
        room, room_profile = _make_room("Crowded Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True)
        kind = PortalAnchorKindFactory()
        PortalAnchorFactory(room_profile=room_profile, kind=kind)

        result = InstallPortalAnchorAction().run(actor, kind=kind, name="a second mirror")

        assert result.success is False
        assert result.message == "An anchor of that kind is already installed here."

    def test_missing_kwargs_fails_with_usage_message(self):
        room, room_profile = _make_room("Usage Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True)

        result = InstallPortalAnchorAction().run(actor, kind=None, name="")

        assert result.success is False
        assert result.message == "Install what, and of what kind?"

    def test_raw_int_kind_kwarg_resolves_and_installs(self):
        """REST dispatch (`_dispatch_registry`) passes raw wire kwargs straight to
        ``execute()`` with no ObjectDB/FK resolution (#2222 task-3 review) — a plain
        int pk must resolve the same as a pre-resolved ``PortalAnchorKind`` instance.
        """
        room, room_profile = _make_room("REST Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True)
        kind = PortalAnchorKindFactory(name="Mirror")

        result = InstallPortalAnchorAction().run(actor, kind=kind.pk, name="a tall silvered mirror")

        assert result.success is True
        anchor = PortalAnchor.objects.active().get(room_profile=room_profile, kind=kind)
        assert anchor.name == "a tall silvered mirror"

    def test_bogus_int_kind_kwarg_fails_gracefully(self):
        room, room_profile = _make_room("Bogus Kind Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True)

        result = InstallPortalAnchorAction().run(actor, kind=999_999, name="a mirror")

        assert result.success is False
        assert result.message == "Install what, and of what kind?"
        assert not PortalAnchor.objects.active().filter(room_profile=room_profile).exists()


class DissolvePortalAnchorActionTests(TestCase):
    def test_owner_dissolves_sole_anchor_in_room(self):
        room, room_profile = _make_room("Owned Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)
        anchor = PortalAnchorFactory(room_profile=room_profile)

        result = DissolvePortalAnchorAction().run(actor)

        assert result.success is True
        anchor.refresh_from_db()
        assert anchor.dissolved_at is not None

    def test_tenant_without_ownership_is_denied(self):
        room, room_profile = _make_room("Tenant Only Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, tenant=True)
        anchor = PortalAnchorFactory(room_profile=room_profile)

        result = DissolvePortalAnchorAction().run(actor)

        assert result.success is False
        assert result.message == "You don't have standing to dissolve this anchor."
        anchor.refresh_from_db()
        assert anchor.dissolved_at is None

    def test_no_anchor_in_room_fails_cleanly(self):
        room, room_profile = _make_room("Empty Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)

        result = DissolvePortalAnchorAction().run(actor)

        assert result.success is False
        assert result.message == "There is no portal anchor here to dissolve."

    def test_multiple_anchors_require_explicit_kind(self):
        room, room_profile = _make_room("Busy Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)
        PortalAnchorFactory(room_profile=room_profile, kind=PortalAnchorKindFactory(name="Mirror"))
        PortalAnchorFactory(room_profile=room_profile, kind=PortalAnchorKindFactory(name="Doorway"))

        result = DissolvePortalAnchorAction().run(actor)

        assert result.success is False
        assert "specify a kind" in result.message

    def test_explicit_anchor_kwarg_dissolves_that_one(self):
        room, room_profile = _make_room("Explicit Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)
        mirror = PortalAnchorFactory(
            room_profile=room_profile, kind=PortalAnchorKindFactory(name="Mirror")
        )
        doorway = PortalAnchorFactory(
            room_profile=room_profile, kind=PortalAnchorKindFactory(name="Doorway")
        )

        result = DissolvePortalAnchorAction().run(actor, anchor=mirror)

        assert result.success is True
        mirror.refresh_from_db()
        doorway.refresh_from_db()
        assert mirror.dissolved_at is not None
        assert doorway.dissolved_at is None

    def test_raw_int_anchor_kwarg_resolves_and_dissolves(self):
        """REST dispatch passes raw wire kwargs straight to ``execute()`` with no
        ObjectDB/FK resolution (#2222 task-3 review) — a plain int pk must resolve
        the same as a pre-resolved ``PortalAnchor`` instance.
        """
        room, room_profile = _make_room("REST Dissolve Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)
        mirror = PortalAnchorFactory(
            room_profile=room_profile, kind=PortalAnchorKindFactory(name="Mirror")
        )
        doorway = PortalAnchorFactory(
            room_profile=room_profile, kind=PortalAnchorKindFactory(name="Doorway")
        )

        result = DissolvePortalAnchorAction().run(actor, anchor=mirror.pk)

        assert result.success is True
        mirror.refresh_from_db()
        doorway.refresh_from_db()
        assert mirror.dissolved_at is not None
        assert doorway.dissolved_at is None

    def test_bogus_int_anchor_kwarg_fails_gracefully(self):
        room, room_profile = _make_room("Bogus Anchor Room")
        actor, _sheet, _persona = _make_resident(room, room_profile, owner=True)

        result = DissolvePortalAnchorAction().run(actor, anchor=999_999)

        assert result.success is False
        assert result.message == "There is no portal anchor here to dissolve."
