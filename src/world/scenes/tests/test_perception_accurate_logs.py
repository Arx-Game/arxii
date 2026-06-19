"""Perception-accurate scene logs (#1219).

A scene log shows each viewer only what their character could perceive at the time:
- visible (room-heard) content → anyone whose character was present, or who personally played;
- private content (whispers / table-talk / very-private) → only the actual parties, *by account*,
  forever — never a bystander, never a future player who inherits the persona;
- staff + the scene's GM see non-very-private; very-private admits no exception.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneParticipationFactory,
)


def _new_character_roster():
    character = CharacterFactory()
    return RosterEntryFactory(character_sheet__character=character)


def _give_tenure(account, roster_entry, *, current=True):
    player_data = PlayerDataFactory(account=account)
    end_date = None if current else timezone.now() - timedelta(days=30)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, end_date=end_date)


def _played_persona(account=None):
    """An account playing a fresh character; returns (account, primary persona)."""
    account = account or AccountFactory()
    roster_entry = _new_character_roster()
    _give_tenure(account, roster_entry)
    return account, roster_entry.character_sheet.primary_persona


class PrivateContentByAccountTests(APITestCase):
    """Private lines reach only the actual parties, by account, forever."""

    def _ids(self, response) -> set[int]:
        return {row["id"] for row in response.data["results"]}

    def test_inheriting_a_persona_does_not_reveal_the_prior_players_whisper(self) -> None:
        """The crux: a new player of a character can never read the previous player's whispers."""
        roster_entry = _new_character_roster()
        persona = roster_entry.character_sheet.primary_persona
        former = AccountFactory()
        _give_tenure(former, roster_entry, current=False)
        current = AccountFactory()
        _give_tenure(current, roster_entry, current=True)

        # The former player wrote a whisper as this character (party = the former account).
        whisper = InteractionFactory(
            persona=persona,
            mode=InteractionMode.WHISPER,
            writer_account=former,
            scene=SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC),
        )
        _other_acct, other_persona = _played_persona()
        InteractionReceiverFactory(interaction=whisper, persona=other_persona)

        # The current (inheriting) player controls the persona now — but was never a party.
        self.client.force_authenticate(user=current)
        response = self.client.get(reverse("interaction-list"))
        assert whisper.pk not in self._ids(response)
        detail = self.client.get(reverse("interaction-detail", kwargs={"pk": whisper.pk}))
        assert detail.status_code == status.HTTP_404_NOT_FOUND

    def test_a_former_player_keeps_their_own_whisper(self) -> None:
        """Giving up the character never strips the RP you personally did."""
        roster_entry = _new_character_roster()
        persona = roster_entry.character_sheet.primary_persona
        former = AccountFactory()
        _give_tenure(former, roster_entry, current=False)
        _give_tenure(AccountFactory(), roster_entry, current=True)

        whisper = InteractionFactory(
            persona=persona,
            mode=InteractionMode.WHISPER,
            writer_account=former,
            scene=SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC),
        )
        InteractionReceiverFactory(interaction=whisper, persona=_played_persona()[1])

        self.client.force_authenticate(user=former)
        response = self.client.get(reverse("interaction-list"))
        assert whisper.pk in self._ids(response)

    def test_a_bystander_in_the_scene_cannot_read_a_whisper_between_two_others(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        _speaker_acct, speaker = _played_persona()
        _listener_acct, listener = _played_persona()
        bystander_acct, bystander = _played_persona()

        # A public pose everyone present heard, plus a whisper between speaker and listener.
        pose = InteractionFactory(persona=speaker, mode=InteractionMode.POSE, scene=scene)
        whisper = InteractionFactory(persona=speaker, mode=InteractionMode.WHISPER, scene=scene)
        InteractionReceiverFactory(interaction=whisper, persona=listener)
        # The bystander was present (posed in the scene).
        InteractionFactory(persona=bystander, mode=InteractionMode.POSE, scene=scene)

        self.client.force_authenticate(user=bystander_acct)
        ids = self._ids(self.client.get(reverse("interaction-list")))
        assert pose.pk in ids  # room-heard
        assert whisper.pk not in ids  # not a party to it

    def test_very_private_admits_no_exception_for_staff_or_gm(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        writer_acct, writer = _played_persona()
        _recv_acct, receiver = _played_persona()
        very_private = InteractionFactory(
            persona=writer,
            mode=InteractionMode.WHISPER,
            scene=scene,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        InteractionReceiverFactory(interaction=very_private, persona=receiver)

        staff = AccountFactory(is_staff=True)
        gm_acct = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm_acct)

        for viewer in (staff, gm_acct):
            self.client.force_authenticate(user=viewer)
            ids = self._ids(self.client.get(reverse("interaction-list")))
            assert very_private.pk not in ids, f"{viewer} must not see very-private"

        # The actual party still sees it.
        self.client.force_authenticate(user=writer_acct)
        assert very_private.pk in self._ids(self.client.get(reverse("interaction-list")))


class SceneGmAndPerceptionTests(APITestCase):
    def _ids(self, response) -> set[int]:
        return {row["id"] for row in response.data["results"]}

    def test_scene_gm_sees_whispers_in_their_scene_but_not_in_others(self) -> None:
        gm_acct = AccountFactory()
        their_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        SceneGMParticipationFactory(scene=their_scene, account=gm_acct)
        other_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)

        _w_acct, writer = _played_persona()
        _r_acct, receiver = _played_persona()
        mine = InteractionFactory(persona=writer, mode=InteractionMode.WHISPER, scene=their_scene)
        InteractionReceiverFactory(interaction=mine, persona=receiver)
        theirs = InteractionFactory(persona=writer, mode=InteractionMode.WHISPER, scene=other_scene)
        InteractionReceiverFactory(interaction=theirs, persona=receiver)

        self.client.force_authenticate(user=gm_acct)
        ids = self._ids(self.client.get(reverse("interaction-list")))
        assert mine.pk in ids  # GM of that scene
        assert theirs.pk not in ids  # not the GM there

    def test_current_player_inherits_a_characters_visible_history(self) -> None:
        """A new player sees the room-heard content of scenes their character was in before."""
        roster_entry = _new_character_roster()
        persona = roster_entry.character_sheet.primary_persona
        _give_tenure(AccountFactory(), roster_entry, current=False)
        current = AccountFactory()
        _give_tenure(current, roster_entry, current=True)

        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        # A public pose the character made under the previous player.
        old_pose = InteractionFactory(persona=persona, mode=InteractionMode.POSE, scene=scene)

        self.client.force_authenticate(user=current)
        assert old_pose.pk in self._ids(self.client.get(reverse("interaction-list")))

    def test_personal_participation_grants_a_former_scenes_visible_content(self) -> None:
        former = AccountFactory()
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        SceneParticipationFactory(scene=scene, account=former)
        _w_acct, writer = _played_persona()
        pose = InteractionFactory(persona=writer, mode=InteractionMode.POSE, scene=scene)

        self.client.force_authenticate(user=former)
        assert pose.pk in self._ids(self.client.get(reverse("interaction-list")))
