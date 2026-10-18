"""What the consent journey cannot stage of category-aware consent enforcement (#1141).

Every mode a player can set (everyone, whitelist, all-but-blacklist, friends, rivals,
the category's default) and the master switch are typed and then tried, through
``consent ...`` and ``carry_body``, in ``integration_tests/test_membership_and_consent_journeys.py``
(``KeepingHandsOffHerBody``). What stays here: the branches for an actor with no tenure
(a general-visibility probe, which no player types), and the query budget of the batched
exclusion sweep, which no reply reads back.
"""

from __future__ import annotations

import django.test
from evennia.objects.models import ObjectDB

from actions.player_interface import _social_consent_exclusions, _tenure_blocks_actor
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class TenureBlocksUnknownActorTests(django.test.TestCase):
    """``_tenure_blocks_actor`` with ``actor_tenure=None``: a visibility probe with nobody
    behind it. Blocked under the master switch, the whitelist and the friends modes;
    allowed under everyone and all-but-blacklist."""

    def _rule(self, mode: str | None, *, master: bool = True):
        tenure = RosterTenureFactory()
        pref = SocialConsentPreferenceFactory(tenure=tenure, allow_social_actions=master)
        cat = SocialConsentCategoryFactory()
        if mode is not None:
            SocialConsentCategoryRuleFactory(preference=pref, category=cat, mode=mode)
        return tenure, cat

    def test_master_off_blocks_unknown_actor(self) -> None:
        tenure, cat = self._rule(None, master=False)
        self.assertTrue(_tenure_blocks_actor(tenure, None, cat))

    def test_everyone_rule_admits_unknown_actor(self) -> None:
        tenure, cat = self._rule(ConsentMode.EVERYONE)
        self.assertFalse(_tenure_blocks_actor(tenure, None, cat))

    def test_allowlist_blocks_unknown_actor(self) -> None:
        tenure, cat = self._rule(ConsentMode.ALLOWLIST)
        self.assertTrue(_tenure_blocks_actor(tenure, None, cat))

    def test_all_but_blacklist_admits_unknown_actor(self) -> None:
        tenure, cat = self._rule(ConsentMode.ALL_BUT_BLACKLIST)
        self.assertFalse(_tenure_blocks_actor(tenure, None, cat))

    def test_friends_blocks_unknown_actor(self) -> None:
        tenure, cat = self._rule(ConsentMode.FRIENDS_WHITELIST)
        self.assertTrue(_tenure_blocks_actor(tenure, None, cat))


class SocialConsentExclusionsQueryBudgetTest(django.test.TestCase):
    """Pin the batched query budget for the exclusion sweep (#1248).

    The sweep must batch its preference / category-rule / whitelist lookups so the
    query count is **constant in the number of scene participants** -- not the
    per-tenure fan-out it replaced. The scaling assertion is the real guard: adding
    non-blocking participants must not add queries.
    """

    def _build_scene(self, num_targets: int, category: object):
        """Build a fresh scene: one actor + *num_targets* non-blocking targets.

        Every target opts into an EVERYONE rule for *category* (master on), so the
        sweep resolves them as allowed and never walks the persona-id path -- keeping
        the measured budget purely the batched loads, independent of target count.
        """
        room = ObjectDBFactory(db_key=f"BudgetRoom{num_targets}")

        actor_sheet = CharacterSheetFactory()
        actor_char = actor_sheet.character
        ObjectDB.objects.filter(pk=actor_char.pk).update(db_location=room)
        actor_char.db_location = room
        actor_entry = RosterEntryFactory(character_sheet=actor_sheet)
        actor_tenure = RosterTenureFactory(roster_entry=actor_entry, end_date=None)

        scene = SceneFactory(room=room, is_active=True)
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

        with CaptureQueriesContext(connection) as ctx:
            _social_consent_exclusions(actor_char, category)
        return len(ctx.captured_queries)

    def test_query_count_is_constant_in_participant_count(self) -> None:
        """Adding non-blocking participants must not add queries (no per-tenure fan-out)."""
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
            f"(2 targets: {small}, 8 targets: {large}) -- per-tenure fan-out regressed.",
        )
