"""Tests for the REST accept() auto-fire parity fix (#3045).

Telnet's ``ritual join`` auto-fires a site-convened Durance session (no live
initiator exists to issue a separate ``ritual fire``) — see
``commands.ritual.CmdRitual._maybe_auto_fire``. Before this fix,
``RitualSessionViewSet.accept`` had no equivalent, so a web player who opened a
Durance via ``DuranceConveneView`` and then accepted over REST would strand the
session PENDING forever (their character is never the session's initiator, so
they cannot call ``.../fire/`` themselves either). This proves the web path now
completes the rite in one step, matching telnet.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import ObjectDBFactory
from world.areas.services import get_room_profile
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import CharacterClassLevel, PathStage
from world.magic.factories import RitualOfTheDuranceFactory
from world.magic.models.sessions import RitualSession
from world.progression.factories import DuranceTrainingSiteFactory
from world.progression.models import CharacterPathHistory, CharacterUnlock, ClassLevelUnlock
from world.progression.services.advancement import convene_durance_at_site

_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


def _make_tenure_with_account():
    """Return (tenure, account, sheet) with an active RosterTenure (mirrors magic tests)."""
    from world.magic.services.gain import account_for_sheet
    from world.roster.factories import RosterTenureFactory

    tenure = RosterTenureFactory()
    sheet = tenure.roster_entry.character_sheet
    account = account_for_sheet(sheet)
    return tenure, account, sheet


def _wire_path(sheet, path) -> None:
    """Record *path* as the character's current path via CharacterPathHistory."""
    CharacterPathHistory.objects.create(character=sheet, path=path)


def _set_primary_level(sheet, *, character_class, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at *level*."""
    CharacterClassLevelFactory(
        character=sheet,
        character_class=character_class,
        level=level,
        is_primary=True,
    )


def _place_in_room(sheet, room) -> None:
    """Move a character into *room* (ObjectDB) and persist the change."""
    sheet.character.location = room
    sheet.character.save()


def _purchase_unlock(sheet, unlock) -> None:
    """Record the XP-unlock purchase gate as satisfied for ``sheet`` (#2116)."""
    CharacterUnlock.objects.create(
        character=sheet,
        character_class=unlock.character_class,
        target_level=unlock.target_level,
    )


class DuranceSiteConvenedAutoFireOnRestAcceptTests(TestCase):
    """POST .../accept/ auto-fires a site-convened Durance session, matching telnet (#3045)."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.path = PathFactory(stage=PathStage.PROSPECT)

        _, self.trainer_account, self.trainer_sheet = _make_tenure_with_account()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

        _, self.inductee_account, self.inductee_sheet = _make_tenure_with_account()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)

        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        _purchase_unlock(self.inductee_sheet, self.unlock)
        RitualOfTheDuranceFactory()

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.trainer_sheet, self.room)
        _place_in_room(self.inductee_sheet, self.room)
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(self.room),
            officiant=self.trainer_sheet,
            is_active=True,
        )

    def test_accept_auto_fires_and_advances_the_level(self) -> None:
        """A site-convened session fires on accept, with no separate fire call needed."""
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(inductee_sheet=self.inductee_sheet, room=self.room)

            self.client.force_authenticate(user=self.inductee_account)
            response = self.client.post(
                f"/api/magic/rituals/sessions/{session.pk}/accept/",
                data={"participant_kwargs": {"testament": "I stand ready."}},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data.get("fired"))
        self.assertFalse(RitualSession.objects.filter(pk=session.pk).exists())

        cl = CharacterClassLevel.objects.get(
            character_id=self.inductee_sheet.character.pk,
            character_class=self.inductee_class,
        )
        self.assertEqual(cl.level, 3)

    def test_non_site_convened_session_does_not_auto_fire(self) -> None:
        """An ordinary session (drafted via ``ritual draft``) still needs an explicit fire."""
        from world.magic.constants import ParticipantState
        from world.magic.factories import RitualSessionFactory, RitualSessionParticipantFactory

        ritual = RitualOfTheDuranceFactory()
        session = RitualSessionFactory(ritual=ritual, initiator=self.trainer_sheet)
        session.participants.all().delete()
        RitualSessionParticipantFactory(
            session=session,
            character_sheet=self.inductee_sheet,
            state=ParticipantState.INVITED,
        )

        self.client.force_authenticate(user=self.inductee_account)
        response = self.client.post(
            f"/api/magic/rituals/sessions/{session.pk}/accept/",
            data={"participant_kwargs": {"testament": "I stand ready."}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("fired", response.data)
        self.assertTrue(RitualSession.objects.filter(pk=session.pk).exists())
