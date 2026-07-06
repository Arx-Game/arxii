"""Tests for the kudos source/claim category seed functions (#2026).

Before this seed step existed, `KudosSourceCategory` rows for `pose_kudos` /
`spread_assist` self-healed lazily via `get_or_create` inside their reaction-kind
helpers, but `social_engagement` (weekly good-sport grant) and
`relationship_writeup` (writeup commend) both do a plain `.get()` with no
self-heal — on a fresh DB neither category exists, so both award paths silently
log a warning and skip the kudos award. These tests cover the seed step itself
(every row exists with the shape the consuming services expect) and confirm the
two previously silent no-ops now actually produce a `KudosTransaction`.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.progression.models import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.seeds import (
    seed_kudos_content,
    seed_pose_kudos_category,
    seed_relationship_writeup_kudos_category,
    seed_social_engagement_kudos_category,
    seed_spread_assist_kudos_category,
    seed_xp_kudos_claim_category,
)
from world.progression.services.engagement import accrue, grant_social_engagement_kudos
from world.relationships.constants import (
    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    WRITEUP_KUDOS_AMOUNT,
    UpdateVisibility,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipUpdateFactory,
)
from world.relationships.services import give_writeup_kudos
from world.roster.factories import RosterTenureFactory


def _flush_kudos_caches() -> None:
    KudosSourceCategory.flush_instance_cache()
    KudosClaimCategory.flush_instance_cache()
    KudosPointsData.flush_instance_cache()


def _make_linked_account(character_sheet):
    """Create a RosterTenure that links character_sheet.character to a fresh account."""
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


class SeedKudosContentTest(TestCase):
    """seed_kudos_content() seeds every category the kudos economy needs."""

    def setUp(self):
        _flush_kudos_caches()

    def test_seeds_all_four_source_categories_and_the_claim_category(self):
        seed_kudos_content()

        names = set(KudosSourceCategory.objects.values_list("name", flat=True))
        self.assertEqual(
            names,
            {
                "pose_kudos",
                "spread_assist",
                "social_engagement",
                RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
            },
        )
        self.assertTrue(KudosClaimCategory.objects.filter(name="xp", is_active=True).exists())

    def test_relationship_writeup_category_matches_service_constants(self):
        seed_relationship_writeup_kudos_category()

        category = KudosSourceCategory.objects.get(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)
        self.assertEqual(category.default_amount, WRITEUP_KUDOS_AMOUNT)
        self.assertTrue(category.is_active)

    def test_pose_kudos_category_matches_reaction_kind_defaults(self):
        seed_pose_kudos_category()

        category = KudosSourceCategory.objects.get(name="pose_kudos")
        self.assertEqual(category.default_amount, 1)
        self.assertEqual(category.display_name, "Pose Kudos")

    def test_spread_assist_category_matches_reaction_kind_defaults(self):
        seed_spread_assist_kudos_category()

        category = KudosSourceCategory.objects.get(name="spread_assist")
        self.assertEqual(category.default_amount, 1)
        self.assertEqual(category.display_name, "Telling Acclaim")

    def test_xp_claim_category_reward_shape(self):
        seed_xp_kudos_claim_category()

        category = KudosClaimCategory.objects.get(name="xp")
        self.assertEqual(category.calculate_reward(10), 5)
        self.assertEqual(category.calculate_reward(9), 0)

    def test_idempotent_no_new_rows_on_second_run(self):
        seed_kudos_content()
        first_count = KudosSourceCategory.objects.count()

        seed_kudos_content()

        self.assertEqual(KudosSourceCategory.objects.count(), first_count)


class SeededGoodSportGrantTest(TestCase):
    """grant_social_engagement_kudos() no longer no-ops once the DB is seeded."""

    def setUp(self):
        _flush_kudos_caches()
        seed_social_engagement_kudos_category()
        self.account = AccountDB.objects.create(username="seeded_grantee", email="g@test.com")
        self.initiator = AccountDB.objects.create(username="seeded_initiator", email="i@test.com")

    def test_grant_awards_kudos_transaction_on_seeded_db(self):
        from world.progression.services import engagement as engagement_mod

        accrue(self.account, self.initiator, Decimal("1.00"))

        # Guaranteed first point regardless of the roll.
        with patch.object(engagement_mod.random, "random", return_value=0.99):
            count = grant_social_engagement_kudos()

        self.assertEqual(count, 1)
        kudos_transaction = KudosTransaction.objects.get(account=self.account)
        self.assertEqual(kudos_transaction.amount, 1)
        self.assertEqual(kudos_transaction.source_category.name, "social_engagement")


class SeededWriteupKudosTest(TestCase):
    """give_writeup_kudos() no longer no-ops once the DB is seeded."""

    def setUp(self):
        _flush_kudos_caches()
        seed_relationship_writeup_kudos_category()

        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target
        self.author_account = _make_linked_account(self.author_sheet)
        self.subject_account = _make_linked_account(self.subject_sheet)
        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )

    def test_commend_awards_kudos_transaction_on_seeded_db(self):
        give_writeup_kudos(giver_account=self.subject_account, writeup=self.update)

        kudos_transaction = KudosTransaction.objects.get(account=self.author_account)
        self.assertEqual(kudos_transaction.amount, WRITEUP_KUDOS_AMOUNT)
        self.assertEqual(
            kudos_transaction.source_category.name, RELATIONSHIP_WRITEUP_KUDOS_CATEGORY
        )
