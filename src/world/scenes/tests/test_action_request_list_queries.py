"""The action-request list costs the same however many requests it holds (#4418)."""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.models import ActionTemplate
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentCategory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import Roster, RosterEntry
from world.roster.models.choices import RosterType
from world.scenes.action_models import SceneActionRequest, SceneActionTarget
from world.scenes.factories import SceneActionRequestFactory, SceneActionTargetFactory, SceneFactory
from world.scenes.models import Persona

# The models a list row reads while the serializer decides resist-only.
_READ_MODELS = (
    SceneActionRequest,
    SceneActionTarget,
    Persona,
    CharacterSheet,
    RosterEntry,
    Roster,
    ActionTemplate,
    SocialConsentCategory,
)


class ActionRequestListQueryCountTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=cls.account),
            roster_entry=entry,
            end_date=None,
        )
        cls.persona = sheet.primary_persona
        cls.scene = SceneFactory()
        cls.template = ActionTemplateFactory(
            name="Deceive",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
            resist_check_type=CheckTypeFactory(name="Composure"),
            consent_category=SocialConsentCategoryFactory(key="hostile"),
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def _add_npc_requests(self, count: int) -> None:
        for _ in range(count):
            npc_entry = RosterEntryFactory(roster__roster_type=RosterType.NPC)
            request = SceneActionRequestFactory(
                scene=self.scene,
                initiator_persona=npc_entry.character_sheet.primary_persona,
                target_persona=self.persona,
                action_key="deceive",
                action_template=self.template,
            )
            SceneActionTargetFactory(action_request=request, target_persona=self.persona)

    def _list_query_count(self, route: str = "sceneactionrequest-list") -> int:
        # Rows the factories just made sit in the identity map; read them as a request would.
        for model in _READ_MODELS:
            model.flush_instance_cache()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(route))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx.captured_queries)

    def test_listing_costs_the_same_for_more_requests(self) -> None:
        self._add_npc_requests(2)
        self._list_query_count()  # warm the account's cached persona ids
        few = self._list_query_count()
        self._add_npc_requests(4)
        many = self._list_query_count()
        self.assertEqual(many, few)

    def test_listing_extra_targets_costs_the_same_for_more_rows(self) -> None:
        route = "sceneactiontarget-list"
        self._add_npc_requests(2)
        self._list_query_count(route)
        few = self._list_query_count(route)
        self._add_npc_requests(4)
        many = self._list_query_count(route)
        self.assertEqual(many, few)
