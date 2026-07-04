"""Online-presence (`who`) service + the presence API (#1463)."""

from time import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerAllowList
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureDisplaySettingsFactory,
)
from world.scenes.presence import (
    IDLE_ACTIVE,
    IDLE_AWAY,
    IDLE_IDLE,
    account_on_allowlist,
    character_appears_offline,
    hidden_from_viewer,
    idle_bucket,
    who_listing,
)


def _make_character(*, appear_offline: bool = False):
    """A rostered character + its controlling account, optionally in quiet mode (#1463)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    TenureDisplaySettingsFactory(tenure=tenure, appear_offline=appear_offline)
    return sheet.character, tenure.player_data.account


class IdleBucketTests(TestCase):
    def test_active_under_15m_has_no_marker(self) -> None:
        assert idle_bucket(5 * 60) == IDLE_ACTIVE

    def test_idle_between_15m_and_1h(self) -> None:
        assert idle_bucket(30 * 60) == IDLE_IDLE

    def test_away_over_1h(self) -> None:
        assert idle_bucket(2 * 60 * 60) == IDLE_AWAY


class WhoListingTests(TestCase):
    def test_lists_online_character_by_active_persona_with_coarse_idle(self) -> None:
        sheet = CharacterSheetFactory()
        session = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 30 * 60)
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [session]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].name == sheet.primary_persona.display_ic()
        assert entries[0].idle == IDLE_IDLE  # coarse bucket, never an exact duration

    def test_uses_minimum_idle_across_a_characters_sessions(self) -> None:
        sheet = CharacterSheetFactory()
        old = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 2 * 60 * 60)
        fresh = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 60)
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [old, fresh]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].idle == IDLE_ACTIVE  # most-recent activity wins → active


class PresencePrivacyHelperTests(TestCase):
    """The quiet/hidden-mode (#1463) building blocks shared by who/where/page."""

    def test_account_on_allowlist_is_one_way(self) -> None:
        owner = AccountFactory()
        viewer = AccountFactory()
        owner_pd = PlayerDataFactory(account=owner)
        viewer_pd = PlayerDataFactory(account=viewer)
        PlayerAllowList.objects.create(owner=owner_pd, allowed_player=viewer_pd)
        assert account_on_allowlist(owner_account=owner, viewer_account=viewer) is True
        # The reverse direction is not implied, and a missing viewer is never on a list.
        assert account_on_allowlist(owner_account=viewer, viewer_account=owner) is False
        assert account_on_allowlist(owner_account=owner, viewer_account=None) is False

    def test_appears_offline_reads_the_setting_and_defaults_false(self) -> None:
        visible, _ = _make_character(appear_offline=False)
        hidden, _ = _make_character(appear_offline=True)
        # A bare character with no tenure/settings defaults to visible.
        bare = CharacterSheetFactory().character
        assert character_appears_offline(visible) is False
        assert character_appears_offline(hidden) is True
        assert character_appears_offline(bare) is False

    def test_hidden_from_viewer_exempts_self_and_allowlist(self) -> None:
        hidden, owner = _make_character(appear_offline=True)
        stranger = AccountFactory()
        friend = AccountFactory()
        PlayerAllowList.objects.create(
            owner=owner.player_data, allowed_player=PlayerDataFactory(account=friend)
        )
        assert hidden_from_viewer(hidden, stranger) is True  # stranger doesn't see them
        assert hidden_from_viewer(hidden, None) is True  # nor does an anonymous viewer
        assert hidden_from_viewer(hidden, owner) is False  # the player sees themselves
        assert hidden_from_viewer(hidden, friend) is False  # allowlisted friend sees them

    def test_non_hidden_character_is_never_filtered(self) -> None:
        visible, _owner = _make_character(appear_offline=False)
        assert hidden_from_viewer(visible, None) is False
        assert hidden_from_viewer(visible, AccountFactory()) is False


class WhoListingPrivacyTests(TestCase):
    """`who` honours quiet mode and the transient afk marker (#1463)."""

    def _session(self, puppet, *, idle_seconds: float = 60.0):
        return SimpleNamespace(puppet=puppet, cmd_last_visible=time() - idle_seconds)

    def test_quiet_mode_character_hidden_except_self_and_allowlist(self) -> None:
        hidden, owner = _make_character(appear_offline=True)
        friend = AccountFactory()
        PlayerAllowList.objects.create(
            owner=owner.player_data, allowed_player=PlayerDataFactory(account=friend)
        )
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [self._session(hidden)]
            assert who_listing() == []  # stranger / anonymous
            assert len(who_listing(owner)) == 1  # the player themselves
            assert len(who_listing(friend)) == 1  # allowlisted friend

    def test_afk_marker_forces_away_bucket(self) -> None:
        sheet = CharacterSheetFactory()
        sheet.character.ndb.appear_afk = True
        with patch("evennia.SESSION_HANDLER") as handler:
            # Recent activity would normally bucket as active; afk overrides to away.
            handler.get_sessions.return_value = [self._session(sheet.character, idle_seconds=60)]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].idle == IDLE_AWAY


class WhoListingConcealmentTests(TestCase):
    """A concealed-and-undetected character is omitted from ``who`` (#1225 review gap).

    Unlike the room-occupant list (per-observer ``can_perceive``), ``who`` is an
    anonymous global directory with no coherent per-observer detection concept, so
    omission here is unconditional — mirroring the existing quiet-mode
    (``hidden_from_viewer``) omission already in ``who_listing``.
    """

    def _session(self, puppet, *, idle_seconds: float = 60.0):
        return SimpleNamespace(puppet=puppet, cmd_last_visible=time() - idle_seconds)

    def test_concealed_character_omitted_from_who(self) -> None:
        sheet = CharacterSheetFactory()
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        condition = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=sheet.character, condition=condition)

        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [self._session(sheet.character)]
            entries = who_listing()
        assert entries == []

    def test_unconcealed_character_still_appears_in_who(self) -> None:
        sheet = CharacterSheetFactory()

        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [self._session(sheet.character)]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].name == sheet.primary_persona.display_ic()


class PresenceApiTests(APITestCase):
    def test_authenticated_get_returns_who_and_where(self) -> None:
        # ty types the factory call as the factory, not AccountDB; FactoryBoy is the
        # required test-data path, so ignore the known stub mismatch here.
        self.client.force_authenticate(user=AccountFactory())  # ty: ignore[invalid-argument-type]
        response = self.client.get("/api/areas/presence/")
        assert response.status_code == status.HTTP_200_OK
        assert "who" in response.data  # noqa: STRING_LITERAL — response key, not a discriminator
        assert "where" in response.data  # noqa: STRING_LITERAL — response key

    def test_anonymous_is_denied(self) -> None:
        response = self.client.get("/api/areas/presence/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
