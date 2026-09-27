"""Tests for the persona menu (#4030): ``build_persona_menu`` and the API view.

The menu is composed server-side from each action's own ``check_availability`` so it
never offers what ``run()`` then refuses (see ``actions/persona_menu.py``).
"""

from __future__ import annotations

import django.test
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from actions.constants import PersonaMenuGroupKey
from actions.persona_menu import (
    LOOK_UNAVAILABLE,
    SCENE_EMPTY_STATE,
    SELF_NOTICE,
    build_persona_menu,
)
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.services import create_mask


class PersonaMenuServiceTests(django.test.TestCase):
    """``build_persona_menu`` composes items/groups from each action's own gate."""

    def setUp(self) -> None:
        self.room = RoomProfileFactory().objectdb

        viewer_roster = RosterEntryFactory()
        self.viewer_sheet = viewer_roster.character_sheet
        self.viewer = self.viewer_sheet.character
        self.viewer.move_to(self.room, quiet=True)
        self.viewer_account = AccountFactory()
        self.viewer.db_account = self.viewer_account

        target_roster = RosterEntryFactory()
        self.target_sheet = target_roster.character_sheet
        self.target = self.target_sheet.character
        self.target.move_to(self.room, quiet=True)

        self.persona = self.target_sheet.primary_persona

    def _item(self, key: str):
        menu = build_persona_menu(self.viewer, self.persona)
        return next(i for i in menu.items if i.key == key)

    def test_self_menu_is_look_only_with_the_self_notice(self) -> None:
        menu = build_persona_menu(self.viewer, self.viewer_sheet.primary_persona)
        assert menu.is_self
        assert [i.key for i in menu.items] == ["look"]
        assert menu.notice == SELF_NOTICE
        assert [g.key for g in menu.groups] == [PersonaMenuGroupKey.PERCEPTION]

    def test_quiet_room_lists_look_challenge_identify_mute_block_and_scene_empty_state(
        self,
    ) -> None:
        # Demo order (#4030 fix wave): Identify sits with Challenge in the conflict
        # group, right after it.
        menu = build_persona_menu(self.viewer, self.persona)
        assert [i.key for i in menu.items] == ["look", "challenge", "identify", "mute", "block"]
        scene_group = next(g for g in menu.groups if g.key == PersonaMenuGroupKey.SCENE)
        assert scene_group.empty_state == SCENE_EMPTY_STATE
        assert menu.scene is None
        assert menu.scene_actions == []

    def test_identify_unavailable_on_an_unmasked_face_with_its_own_reason(self) -> None:
        item = self._item("identify")
        assert not item.available
        assert item.reason == "Their face is their own; there is no mask to see through."

    def test_look_unavailable_elsewhere_uses_the_neutral_reason(self) -> None:
        # The Who-panel case: a target genuinely elsewhere gets the absent shape --
        # the same shape a concealed-but-co-located target gets below.
        self.target.move_to(RoomProfileFactory().objectdb, quiet=True)
        menu = build_persona_menu(self.viewer, self.persona)
        assert not menu.is_self
        assert [i.key for i in menu.items] == ["look", "mute", "block"]
        look_item = menu.items[0]
        assert not look_item.available
        assert look_item.reason == LOOK_UNAVAILABLE
        assert [g.key for g in menu.groups] == [
            PersonaMenuGroupKey.PERCEPTION,
            PersonaMenuGroupKey.SOCIAL,
        ]
        assert menu.scene is None
        assert menu.scene_actions == []

    def test_concealed_target_reads_exactly_like_an_absent_one(self) -> None:
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(target=self.target, condition=template)
        concealed_menu = build_persona_menu(self.viewer, self.persona)

        # The concealed-but-co-located target's WHOLE menu must be indistinguishable
        # from the same persona genuinely elsewhere (the condition is left in place --
        # it must not matter once co-location alone already fails).
        self.target.move_to(RoomProfileFactory().objectdb, quiet=True)
        elsewhere_menu = build_persona_menu(self.viewer, self.persona)

        assert concealed_menu == elsewhere_menu
        assert [i.key for i in concealed_menu.items] == ["look", "mute", "block"]
        assert concealed_menu.items[0].reason == LOOK_UNAVAILABLE
        assert concealed_menu.scene is None
        assert concealed_menu.scene_actions == []

    def test_concealed_target_menu_ignores_an_active_scene_in_the_room(self) -> None:
        # A concealed target's own room having an active scene must not surface it --
        # identify/challenge/scene items would leak "someone is here" through their
        # own room-equality checks even though Look itself refuses.
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(target=self.target, condition=template)
        SceneFactory(location=self.room, is_active=True)

        menu = build_persona_menu(self.viewer, self.persona)
        assert [i.key for i in menu.items] == ["look", "mute", "block"]
        assert menu.scene is None
        assert menu.scene_actions == []

    def test_shared_scene_adds_scene_items_and_clears_the_empty_state(self) -> None:
        SceneFactory(location=self.room, is_active=True)
        keys = [i.key for i in build_persona_menu(self.viewer, self.persona).items]
        assert keys[:3] == ["look", "challenge", "identify"]
        assert {"scene_succor", "scene_interpose", "treat"} <= set(keys)
        assert "give_mission" not in keys

    def test_no_reason_names_a_masked_targets_real_key(self) -> None:
        mask = create_mask(self.target_sheet, name="stag mask")
        menu = build_persona_menu(self.viewer, mask)
        assert all(self.target.key not in i.reason for i in menu.items)

    def test_gm_of_the_scene_gets_give_mission(self) -> None:
        scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=scene, account=self.viewer_account, is_gm=True)
        keys = [i.key for i in build_persona_menu(self.viewer, self.persona).items]
        assert "give_mission" in keys


class PersonaMenuViewTests(django.test.TestCase):
    """``GET /api/actions/characters/<id>/personas/<id>/menu/``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.roster_entry = RosterEntryFactory()
        cls.character = cls.roster_entry.character_sheet.character
        cls.persona = cls.roster_entry.character_sheet.primary_persona

        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        cls.other_account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def _url(self, character_id: int | None = None, persona_id: int | None = None) -> str:
        cid = character_id if character_id is not None else self.character.pk
        pid = persona_id if persona_id is not None else self.persona.pk
        return f"/api/actions/characters/{cid}/personas/{pid}/menu/"

    def test_owner_gets_200_with_expected_shape(self) -> None:
        self.client.force_authenticate(user=self.owner_account)
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        for key in (
            "persona_id",
            "is_self",
            "scene_id",
            "viewer_persona_id",
            "notice",
            "items",
            "groups",
            "scene_actions",
        ):
            assert key in response.data

    def test_non_owner_returns_403(self) -> None:
        self.client.force_authenticate(user=self.other_account)
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unknown_persona_returns_404(self) -> None:
        self.client.force_authenticate(user=self.owner_account)
        response = self.client.get(self._url(persona_id=999999))
        assert response.status_code == status.HTTP_404_NOT_FOUND
