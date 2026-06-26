"""Tests for consent preference Actions (#1487)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.definitions.consent_preferences import (
    AddSocialConsentWhitelistAction,
    RemoveSocialConsentWhitelistAction,
    SetSocialConsentCategoryRuleAction,
    SetSocialConsentPreferenceAction,
)
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentCategoryRule, SocialConsentWhitelist
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class ConsentPreferenceActionsTests(TestCase):
    def setUp(self):
        self.player = PlayerDataFactory()
        self.char = CharacterFactory(db_key="Alice")
        self.char_sheet = CharacterSheetFactory(character=self.char)
        self.roster_entry = RosterEntryFactory(character_sheet=self.char_sheet)
        self.tenure = RosterTenureFactory(
            player_data=self.player,
            roster_entry=self.roster_entry,
        )
        self.char.account = self.player.account

    def test_set_social_consent_preference_action(self):
        action = SetSocialConsentPreferenceAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            allow_social_actions=False,
        )
        assert result.success is True
        assert "blocked" in result.message
        preference = self.tenure.social_consent_preference
        assert preference.allow_social_actions is False

    def test_set_social_consent_preference_requires_bool(self):
        action = SetSocialConsentPreferenceAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            allow_social_actions="maybe",
        )
        assert result.success is False

    def test_set_social_consent_category_rule_action(self):
        SocialConsentCategoryFactory(key="romantic")
        action = SetSocialConsentCategoryRuleAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            mode=ConsentMode.ALLOWLIST,
        )
        assert result.success is True
        assert SocialConsentCategoryRule.objects.filter(
            preference__tenure=self.tenure,
            mode=ConsentMode.ALLOWLIST,
        ).exists()

    def test_set_social_consent_category_rule_default_removes(self):
        SocialConsentCategoryFactory(key="romantic")
        action = SetSocialConsentCategoryRuleAction()
        action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            mode=ConsentMode.ALLOWLIST,
        )
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            mode="default",
        )
        assert result.success is True
        assert not SocialConsentCategoryRule.objects.filter(
            preference__tenure=self.tenure,
        ).exists()

    def test_add_social_consent_whitelist_action(self):
        category = SocialConsentCategoryFactory(key="romantic")
        allowed = RosterTenureFactory()
        action = AddSocialConsentWhitelistAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            allowed_tenure_id=allowed.pk,
        )
        assert result.success is True
        assert SocialConsentWhitelist.objects.filter(
            owner_tenure=self.tenure,
            allowed_tenure=allowed,
            category=category,
        ).exists()

    def test_add_social_consent_whitelist_action_inactive_fails(self):
        SocialConsentCategoryFactory(key="romantic")
        allowed = RosterTenureFactory(
            end_date=timezone.now() - timedelta(days=1),
        )
        action = AddSocialConsentWhitelistAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            allowed_tenure_id=allowed.pk,
        )
        assert result.success is False
        assert "not currently active" in result.message
        assert not SocialConsentWhitelist.objects.filter(
            owner_tenure=self.tenure,
            allowed_tenure=allowed,
        ).exists()

    def test_remove_social_consent_whitelist_action(self):
        category = SocialConsentCategoryFactory(key="romantic")
        allowed = RosterTenureFactory()
        action_add = AddSocialConsentWhitelistAction()
        action_add.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            allowed_tenure_id=allowed.pk,
        )
        action = RemoveSocialConsentWhitelistAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            allowed_tenure_id=allowed.pk,
        )
        assert result.success is True
        assert not SocialConsentWhitelist.objects.filter(
            owner_tenure=self.tenure,
            allowed_tenure=allowed,
            category=category,
        ).exists()

    def test_remove_social_consent_whitelist_action_missing_fails(self):
        SocialConsentCategoryFactory(key="romantic")
        allowed = RosterTenureFactory()
        action = RemoveSocialConsentWhitelistAction()
        result = action.run(
            self.char,
            tenure_id=self.tenure.pk,
            category_key="romantic",
            allowed_tenure_id=allowed.pk,
        )
        assert result.success is False

    def test_cannot_manage_other_players_tenure(self):
        other_player = PlayerDataFactory()
        other_tenure = RosterTenureFactory(player_data=other_player)
        action = SetSocialConsentPreferenceAction()
        result = action.run(
            self.char,
            tenure_id=other_tenure.pk,
            allow_social_actions=False,
        )
        assert result.success is False
        assert "own characters" in result.message
