"""GET /reaction-windows/pending/ (#2987): the bystander-reaction menu list.

Scoping mirrors ``react_to_window``'s own eligibility: the caller's active
persona (never ``primary_persona`` directly, #981) must be a scene
participant AND able to see the witnessed interaction, must not be the
interaction's own author, and must not have already reacted. Settled windows
never appear.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_services import (
    open_reaction_window,
    react_to_window,
    settle_windows_for_scene,
)
from world.scenes.services import set_active_persona


def _account_with_selected_persona(scene=None):
    """Account-backed persona, selected as the account's acting character (#3412).

    Mirrors ``test_reaction_api._account_with_persona`` but additionally sets
    ``PlayerData.selected_entry`` so ``selected_character`` (the durable,
    session-free "who am I" resolver the pending endpoint uses) resolves it.
    """
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    tenure = RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    set_selected_entry(player_data, roster_entry)
    if scene is not None:
        SceneParticipationFactory(scene=scene, account=account)
    return account, roster_entry.character_sheet.primary_persona, tenure


class PendingReactionWindowTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.url = reverse("reactionwindow-pending")

    def _get_pending(self, account, **params):
        self.client.force_authenticate(user=account)
        return self.client.get(self.url, params)

    def test_own_deed_never_appears_but_other_witnesses_still_see_it(self) -> None:
        """Own-persona scoping: a persona's own authored deed is excluded from
        their own pending list, even while they are a scene participant, but
        the SAME window still appears for a different witnessing persona.

        The deed's author is the sheet's ESTABLISHED (active) persona, not its
        PRIMARY one; this is only correctly excluded if the endpoint resolves
        eligibility off the caller's active persona (``active_persona_for_sheet``)
        rather than ``primary_persona``.
        """
        author_account, _author_primary, author_tenure = _account_with_selected_persona(self.scene)
        mask = PersonaFactory(character_sheet=author_tenure.roster_entry.character_sheet)
        set_active_persona(author_tenure.roster_entry.character_sheet, mask)
        interaction = InteractionFactory(persona=mask, scene=self.scene)
        window = self._open_window(interaction)

        witness_account, _witness_persona, _tenure = _account_with_selected_persona(self.scene)

        author_response = self._get_pending(author_account)
        assert author_response.status_code == status.HTTP_200_OK
        assert window.pk not in self._ids(author_response)

        witness_response = self._get_pending(witness_account)
        assert window.pk in self._ids(witness_response)

    def test_already_reacted_window_is_excluded(self) -> None:
        actor = PersonaFactory()
        interaction = InteractionFactory(persona=actor, scene=self.scene)
        window = self._open_window(interaction)
        witness_account, witness_persona, _tenure = _account_with_selected_persona(self.scene)

        response = self._get_pending(witness_account)
        assert window.pk in self._ids(response)

        react_to_window(window=window, reactor_persona=witness_persona, choice="ignore")

        response = self._get_pending(witness_account)
        assert window.pk not in self._ids(response)

    def test_settled_window_is_excluded(self) -> None:
        actor = PersonaFactory()
        interaction = InteractionFactory(persona=actor, scene=self.scene)
        window = self._open_window(interaction)
        witness_account, _witness_persona, _tenure = _account_with_selected_persona(self.scene)

        response = self._get_pending(witness_account)
        assert window.pk in self._ids(response)

        settle_windows_for_scene(self.scene)

        response = self._get_pending(witness_account)
        assert window.pk not in self._ids(response)

    def test_non_participant_sees_nothing(self) -> None:
        actor = PersonaFactory()
        interaction = InteractionFactory(persona=actor, scene=self.scene)
        self._open_window(interaction)
        # Never joined the scene (no SceneParticipation row); the scene is
        # PUBLIC so `can_view_interaction` alone would admit them, but the
        # endpoint additionally requires scene participation (react_to_window
        # parity), so they see nothing.
        stranger_account, _stranger_persona, _tenure = _account_with_selected_persona(scene=None)

        response = self._get_pending(stranger_account)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def _open_window(self, interaction):
        return open_reaction_window(interaction=interaction, kind=ReactionWindowKind.WITNESS)

    @staticmethod
    def _ids(response) -> set[int]:
        return {row["id"] for row in response.data["results"]}
