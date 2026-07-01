"""Tests for the PvP hostile-cast consent gate (#1698).

``hostile_cast_consent_blocked`` is the consent-layer opt-out: a hostile technique cast at
another player's character is refused unless that character's consent admits the actor,
reusing the social-consent predicates scoped to the 'hostile' category. NPC/GM targets and
benign techniques are never blocked. ``is_technique_hostile`` (its own tested classifier) is
patched here so these tests isolate the consent decision.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import django.test

from actions.player_interface import hostile_cast_consent_blocked
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory

_HOSTILITY_PATH = "world.magic.services.hostility.is_technique_hostile"


class HostileCastConsentTests(django.test.TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor_sheet = CharacterSheetFactory()
        cls.actor = cls.actor_sheet.character
        actor_entry = RosterEntryFactory(character_sheet=cls.actor_sheet)
        cls.actor_tenure = RosterTenureFactory(roster_entry=actor_entry, end_date=None)

        cls.target_persona = PersonaFactory()
        cls.target_sheet = cls.target_persona.character_sheet
        target_entry = RosterEntryFactory(character_sheet=cls.target_sheet)
        cls.target_tenure = RosterTenureFactory(roster_entry=target_entry, end_date=None)

        cls.hostile_cat = SocialConsentCategoryFactory(key="hostile")

    def _blocked(self, target=None) -> bool:
        return hostile_cast_consent_blocked(
            self.actor, target if target is not None else self.target_persona, object()
        )

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_default_pc_target_not_blocked(self, mock_hostile: MagicMock) -> None:
        """Opt-out is off by default — a PC with no consent rows admits hostile casts."""
        self.assertFalse(self._blocked())

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_master_switch_off_blocks(self, mock_hostile: MagicMock) -> None:
        SocialConsentPreferenceFactory(tenure=self.target_tenure, allow_social_actions=False)
        self.assertTrue(self._blocked())

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_hostile_allowlist_blocks_non_whitelisted(self, mock_hostile: MagicMock) -> None:
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure, allow_social_actions=True)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile_cat, mode=ConsentMode.ALLOWLIST
        )
        self.assertTrue(self._blocked())

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_hostile_allowlist_allows_whitelisted_actor(self, mock_hostile: MagicMock) -> None:
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure, allow_social_actions=True)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile_cat, mode=ConsentMode.ALLOWLIST
        )
        SocialConsentWhitelistFactory(
            owner_tenure=self.target_tenure,
            allowed_tenure=self.actor_tenure,
            category=self.hostile_cat,
        )
        self.assertFalse(self._blocked())

    @patch(_HOSTILITY_PATH, return_value=False)
    def test_benign_technique_never_blocked(self, mock_hostile: MagicMock) -> None:
        """Even a fully opted-out target does not block a non-hostile cast."""
        SocialConsentPreferenceFactory(tenure=self.target_tenure, allow_social_actions=False)
        self.assertFalse(self._blocked())

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_npc_target_not_blocked(self, mock_hostile: MagicMock) -> None:
        """A target persona with no active tenure is an NPC — never PvP-gated."""
        npc_persona = PersonaFactory()  # no roster tenure wired
        self.assertFalse(self._blocked(target=npc_persona))

    @patch(_HOSTILITY_PATH, return_value=True)
    def test_no_target_not_blocked(self, mock_hostile: MagicMock) -> None:
        self.assertFalse(hostile_cast_consent_blocked(self.actor, None, object()))
