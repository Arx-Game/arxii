"""Tests for category-aware social consent enforcement (#1141).

Covers:
- no preference row → not blocked (default allow).
- master off (allow_social_actions=False) → blocked for any category.
- rule EVERYONE → not blocked.
- rule ALLOWLIST + actor not whitelisted for that category → blocked.
- rule ALLOWLIST + actor whitelisted for that category → not blocked.
- rule ALLOWLIST for category A only → category B (no rule) still allowed.
- category=None → not blocked unless master off.
Integration:
- _social_consent_exclusions threads category through to _tenure_blocks_actor.
"""

from __future__ import annotations

import django.test
from evennia.objects.models import ObjectDB

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentBlacklistFactory,
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.roster.factories import RosterTenureFactory


def _blocks(tenure: object, actor_tenure: object | None, category: object | None) -> bool:
    """Thin wrapper so tests call the function under test by name."""
    from actions.player_interface import _tenure_blocks_actor

    return _tenure_blocks_actor(tenure, actor_tenure, category)


class TenureBlocksActorNoPrefTest(django.test.TestCase):
    """No SocialConsentPreference row → default-allow (not blocked)."""

    def test_no_pref_not_blocked_with_category(self) -> None:
        tenure = RosterTenureFactory()
        actor_tenure = RosterTenureFactory()
        cat = SocialConsentCategoryFactory()
        self.assertFalse(_blocks(tenure, actor_tenure, cat))

    def test_no_pref_not_blocked_category_none(self) -> None:
        tenure = RosterTenureFactory()
        actor_tenure = RosterTenureFactory()
        self.assertFalse(_blocks(tenure, actor_tenure, None))


class TenureBlocksActorMasterOffTest(django.test.TestCase):
    """allow_social_actions=False → always blocked, regardless of category."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=False)
        self.actor_tenure = RosterTenureFactory()

    def test_master_off_blocks_with_category(self) -> None:
        cat = SocialConsentCategoryFactory()
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, cat))

    def test_master_off_blocks_category_none(self) -> None:
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, None))

    def test_master_off_blocks_unknown_actor(self) -> None:
        cat = SocialConsentCategoryFactory()
        self.assertTrue(_blocks(self.tenure, None, cat))


class TenureBlocksActorCategoryNoneTest(django.test.TestCase):
    """category=None with master on → not blocked (uncategorized uses master switch only)."""

    def test_category_none_not_blocked_when_master_on(self) -> None:
        tenure = RosterTenureFactory()
        SocialConsentPreferenceFactory(tenure=tenure, allow_social_actions=True)
        actor_tenure = RosterTenureFactory()
        self.assertFalse(_blocks(tenure, actor_tenure, None))


class TenureBlocksActorRuleEveryoneTest(django.test.TestCase):
    """rule.mode == EVERYONE → not blocked (anyone may target)."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.EVERYONE
        )
        self.actor_tenure = RosterTenureFactory()

    def test_everyone_rule_not_blocked(self) -> None:
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_everyone_rule_not_blocked_unknown_actor(self) -> None:
        self.assertFalse(_blocks(self.tenure, None, self.cat))


class TenureBlocksActorAllowlistNotWhitelistedTest(django.test.TestCase):
    """rule ALLOWLIST + actor not in whitelist for that category → blocked."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.ALLOWLIST
        )
        self.actor_tenure = RosterTenureFactory()

    def test_allowlist_not_whitelisted_is_blocked(self) -> None:
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_allowlist_unknown_actor_is_blocked(self) -> None:
        self.assertTrue(_blocks(self.tenure, None, self.cat))


class TenureBlocksActorAllowlistWhitelistedTest(django.test.TestCase):
    """rule ALLOWLIST + actor whitelisted for that category → not blocked."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.ALLOWLIST
        )
        self.actor_tenure = RosterTenureFactory()
        SocialConsentWhitelistFactory(
            owner_tenure=self.tenure, allowed_tenure=self.actor_tenure, category=self.cat
        )

    def test_allowlist_whitelisted_not_blocked(self) -> None:
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))


class TenureBlocksActorCategoryAOnlyTest(django.test.TestCase):
    """rule ALLOWLIST exists for category A only; category B has no rule → B still allowed."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat_a = SocialConsentCategoryFactory()
        self.cat_b = SocialConsentCategoryFactory()
        # Only category A is restricted
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat_a, mode=ConsentMode.ALLOWLIST
        )
        self.actor_tenure = RosterTenureFactory()

    def test_cat_a_not_whitelisted_is_blocked(self) -> None:
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, self.cat_a))

    def test_cat_b_no_rule_is_not_blocked(self) -> None:
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat_b))


class TenureBlocksActorAllButBlacklistTest(django.test.TestCase):
    """rule ALL_BUT_BLACKLIST → blocked only when the actor is on this category's blacklist."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.ALL_BUT_BLACKLIST
        )
        self.actor_tenure = RosterTenureFactory()

    def test_non_blacklisted_actor_not_blocked(self) -> None:
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_blacklisted_actor_is_blocked(self) -> None:
        SocialConsentBlacklistFactory(
            owner_tenure=self.tenure, blocked_tenure=self.actor_tenure, category=self.cat
        )
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_blacklist_is_category_scoped(self) -> None:
        """A blacklist entry in another category does not bar this category."""
        other_cat = SocialConsentCategoryFactory()
        SocialConsentBlacklistFactory(
            owner_tenure=self.tenure, blocked_tenure=self.actor_tenure, category=other_cat
        )
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_unknown_actor_not_blocked(self) -> None:
        """A general-visibility probe (no actor) is allowed under all-but-blacklist."""
        self.assertFalse(_blocks(self.tenure, None, self.cat))


class TenureBlocksActorFriendsWhitelistTest(django.test.TestCase):
    """rule FRIENDS_WHITELIST → allowed only for an OOC friend or a whitelisted actor."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.tenure, allow_social_actions=True)
        self.cat = SocialConsentCategoryFactory()
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.FRIENDS_WHITELIST
        )
        self.actor_tenure = RosterTenureFactory()

    def test_stranger_is_blocked(self) -> None:
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_unknown_actor_is_blocked(self) -> None:
        self.assertTrue(_blocks(self.tenure, None, self.cat))

    def test_ooc_friend_is_not_blocked(self) -> None:
        """The owner having friended the actor (friender=owner) admits them to every category."""
        from world.scenes.friend_services import add_friend

        add_friend(friender_tenure=self.tenure, friend_tenure=self.actor_tenure)
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_whitelisted_non_friend_is_not_blocked(self) -> None:
        SocialConsentWhitelistFactory(
            owner_tenure=self.tenure, allowed_tenure=self.actor_tenure, category=self.cat
        )
        self.assertFalse(_blocks(self.tenure, self.actor_tenure, self.cat))

    def test_reverse_friendship_does_not_admit(self) -> None:
        """Actor friending the owner (not vice-versa) does NOT grant the actor access."""
        from world.scenes.friend_services import add_friend

        add_friend(friender_tenure=self.actor_tenure, friend_tenure=self.tenure)
        self.assertTrue(_blocks(self.tenure, self.actor_tenure, self.cat))


class SocialConsentExclusionsIntegrationTest(django.test.TestCase):
    """Integration: _social_consent_exclusions threads category to _tenure_blocks_actor.

    Uses CharacterSheetFactory → character ObjectDB (TestCase pattern, not EvenniaTest).
    Sets up a real Scene + SceneParticipation so the exclusion path is exercised.
    """

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory
        from world.scenes.factories import (
            SceneFactory,
            SceneParticipationFactory,
        )

        self.room = ObjectDB.objects.create(db_key="ConsentTestRoom")

        # Actor character (has a RosterTenure so actor_tenure is resolved)
        self.actor_sheet = CharacterSheetFactory()
        self.actor_char = self.actor_sheet.character
        ObjectDB.objects.filter(pk=self.actor_char.pk).update(db_location=self.room)
        self.actor_char.db_location = self.room  # patch in-memory instance

        actor_entry = RosterEntryFactory(character_sheet=self.actor_sheet)
        self.actor_tenure = RosterTenureFactory(roster_entry=actor_entry, end_date=None)

        # Target character
        self.target_sheet = CharacterSheetFactory()
        self.target_char = self.target_sheet.character

        target_entry = RosterEntryFactory(character_sheet=self.target_sheet)
        self.target_tenure = RosterTenureFactory(roster_entry=target_entry, end_date=None)

        # Scene in the same room (is_active=True is the default; no end_time field)
        self.scene = SceneFactory(location=self.room, is_active=True)

        # Participate both actors in the scene via their accounts
        SceneParticipationFactory(scene=self.scene, account=self.actor_tenure.player_data.account)
        SceneParticipationFactory(scene=self.scene, account=self.target_tenure.player_data.account)

        # Consent setup: target has ALLOWLIST rule for this category (master on)
        self.cat = SocialConsentCategoryFactory()
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure, allow_social_actions=True)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.cat, mode=ConsentMode.ALLOWLIST
        )

    def test_category_aware_exclusion_blocks_non_whitelisted_actor(self) -> None:
        """_social_consent_exclusions returns target's persona IDs when not whitelisted."""
        from actions.player_interface import _social_consent_exclusions

        excluded = _social_consent_exclusions(self.actor_char, self.cat)
        # The target's persona IDs should be in the excluded set
        target_persona_ids = set(self.target_sheet.personas.values_list("pk", flat=True))
        self.assertTrue(
            excluded & target_persona_ids,
            "Target's persona IDs should be excluded when actor is not whitelisted",
        )

    def test_category_none_does_not_exclude_when_master_on(self) -> None:
        """_social_consent_exclusions with category=None: no exclusion when master is on."""
        from actions.player_interface import _social_consent_exclusions

        excluded = _social_consent_exclusions(self.actor_char, None)
        target_persona_ids = set(self.target_sheet.personas.values_list("pk", flat=True))
        self.assertFalse(
            excluded & target_persona_ids,
            "category=None should not exclude anyone when master switch is on",
        )


class SocialConsentExclusionsQueryBudgetTest(django.test.TestCase):
    """Pin the batched query budget for the exclusion sweep (#1248).

    The sweep must batch its preference / category-rule / whitelist lookups so the
    query count is **constant in the number of scene participants** — not the
    per-tenure fan-out it replaced. The scaling assertion is the real guard: adding
    non-blocking participants must not add queries.
    """

    def _build_scene(self, num_targets: int, category: object):
        """Build a fresh scene: one actor + *num_targets* non-blocking targets.

        Every target opts into an EVERYONE rule for *category* (master on), so the
        sweep resolves them as allowed and never walks the persona-id path — keeping
        the measured budget purely the batched loads, independent of target count.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.consent.constants import ConsentMode
        from world.consent.factories import (
            SocialConsentCategoryRuleFactory,
            SocialConsentPreferenceFactory,
        )
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        room = ObjectDB.objects.create(db_key=f"BudgetRoom{num_targets}")

        actor_sheet = CharacterSheetFactory()
        actor_char = actor_sheet.character
        ObjectDB.objects.filter(pk=actor_char.pk).update(db_location=room)
        actor_char.db_location = room
        actor_entry = RosterEntryFactory(character_sheet=actor_sheet)
        actor_tenure = RosterTenureFactory(roster_entry=actor_entry, end_date=None)

        scene = SceneFactory(location=room, is_active=True)
        SceneParticipationFactory(scene=scene, account=actor_tenure.player_data.account)

        for _ in range(num_targets):
            target_sheet = CharacterSheetFactory()
            target_entry = RosterEntryFactory(character_sheet=target_sheet)
            target_tenure = RosterTenureFactory(roster_entry=target_entry, end_date=None)
            SceneParticipationFactory(scene=scene, account=target_tenure.player_data.account)
            pref = SocialConsentPreferenceFactory(tenure=target_tenure, allow_social_actions=True)
            SocialConsentCategoryRuleFactory(
                preference=pref, category=category, mode=ConsentMode.EVERYONE
            )

        return actor_char

    def _sweep_query_count(self, actor_char, category) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from actions.player_interface import _social_consent_exclusions

        with CaptureQueriesContext(connection) as ctx:
            _social_consent_exclusions(actor_char, category)
        return len(ctx.captured_queries)

    def test_query_count_is_constant_in_participant_count(self) -> None:
        """Adding non-blocking participants must not add queries (no per-tenure fan-out)."""
        from world.consent.factories import SocialConsentCategoryFactory

        category = SocialConsentCategoryFactory()

        # Warm process-global caches (content types, etc.) so neither measured run pays
        # a one-off cost the other doesn't.
        self._sweep_query_count(self._build_scene(1, category), category)

        small = self._sweep_query_count(self._build_scene(2, category), category)
        large = self._sweep_query_count(self._build_scene(8, category), category)

        self.assertEqual(
            small,
            large,
            f"Sweep query count must not scale with participants "
            f"(2 targets: {small}, 8 targets: {large}) — per-tenure fan-out regressed.",
        )
