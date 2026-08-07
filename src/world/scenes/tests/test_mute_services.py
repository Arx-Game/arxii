"""Mute resolution + toggle (#1278) — the lighter, one-way sibling of Block.

A mute only changes what the muter sees: ``muted_persona_ids_for_viewer`` lists the personas they
have IC-muted, and ``set_mute`` / ``unmute`` toggle it. No mutuality, no enforcement, fully
reversible.

``account_muted``/the ``account_level`` opt-in on ``set_mute`` (#2996) are the account-first
sibling of Block's — covered separately below.
"""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.factories import PersonaFactory
from world.scenes.models import Mute
from world.scenes.mute_services import (
    account_muted,
    muted_persona_ids_for_viewer,
    set_mute,
    unmute,
)


class MuteServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.muter_account = AccountFactory()
        cls.muter = PlayerData.objects.get_or_create(account=cls.muter_account)[0]
        cls.persona = PersonaFactory(name="Annoying Bard")
        cls.other = PersonaFactory(name="Someone Else")

    def test_no_mutes_lists_nothing(self) -> None:
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()

    def test_set_mute_hides_the_persona_for_the_muter_only(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona)
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == {self.persona.pk}
        # One-way: the muted persona's owner is unaffected (different viewer → nothing muted).
        assert muted_persona_ids_for_viewer(viewer_account=AccountFactory()) == set()

    def test_ic_only_mute_is_not_listed_for_the_ic_feed_when_ic_false(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona, ic=False, ooc=True)
        # The IC feed resolver only lists IC-muted personas.
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()

    def test_set_mute_is_idempotent_and_updates_scope(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona, ic=True, ooc=True)
        set_mute(owner=self.muter, muted_persona=self.persona, ic=True, ooc=False)
        mute = Mute.objects.get(owner=self.muter, muted_persona=self.persona)
        assert mute.mute_ooc is False
        assert Mute.objects.filter(owner=self.muter, muted_persona=self.persona).count() == 1

    def test_unmute_is_fully_reversible(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona)
        unmute(owner=self.muter, muted_persona=self.persona)
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()
        assert not Mute.objects.filter(owner=self.muter).exists()


class AccountLevelMuteTests(TestCase):
    """``account_muted`` + the ``account_level``/``muted_player`` snapshot (#2996)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.muter_account = AccountFactory()
        cls.muter = PlayerData.objects.get_or_create(account=cls.muter_account)[0]

    def _played(self):
        """A persona with a resolvable current player (unlike bare ``PersonaFactory``)."""
        player_data = PlayerDataFactory()
        entry = RosterEntryFactory()
        tenure = RosterTenureFactory(player_data=player_data, roster_entry=entry)
        return entry.character_sheet.primary_persona, player_data, tenure

    def test_set_mute_defaults_to_persona_scoped_no_account_level(self) -> None:
        persona, target_player, _ = self._played()
        mute = set_mute(owner=self.muter, muted_persona=persona)
        assert mute.account_level is False
        assert account_muted(viewer_player=self.muter, target_player=target_player) is False

    def test_account_level_mute_snapshots_muted_player(self) -> None:
        persona, target_player, _ = self._played()
        mute = set_mute(owner=self.muter, muted_persona=persona, account_level=True)
        assert mute.account_level is True
        assert mute.muted_player_id == target_player.pk
        assert account_muted(viewer_player=self.muter, target_player=target_player) is True

    def test_account_muted_is_one_way(self) -> None:
        persona, target_player, _ = self._played()
        set_mute(owner=self.muter, muted_persona=persona, account_level=True)
        # The muted player never learns they were muted — no reverse signal.
        assert account_muted(viewer_player=target_player, target_player=self.muter) is False

    def test_muted_player_snapshot_survives_persona_reroster(self) -> None:
        """The FK doesn't re-derive: a later toggle keeps the original snapshot pinned."""
        persona, original_player, original_tenure = self._played()
        mute = set_mute(owner=self.muter, muted_persona=persona, account_level=True)
        assert mute.muted_player_id == original_player.pk

        # Re-roster: end the original tenure, start a new one for a different player.
        original_tenure.end_date = timezone.now()
        original_tenure.save(update_fields=["end_date"])
        new_player = PlayerDataFactory()
        RosterTenureFactory(
            player_data=new_player,
            roster_entry=original_tenure.roster_entry,
            player_number=2,
        )

        # A later scope toggle must NOT re-derive muted_player to the new current player.
        mute = set_mute(owner=self.muter, muted_persona=persona, ic=False, ooc=True)
        assert mute.muted_player_id == original_player.pk
        # account_muted still resolves against the ORIGINAL player, per the snapshot contract.
        assert account_muted(viewer_player=self.muter, target_player=original_player) is True
        assert account_muted(viewer_player=self.muter, target_player=new_player) is False
