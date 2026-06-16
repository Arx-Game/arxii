"""Tests for create_social_consequence_pools factory helper."""

from django.test import TestCase

from world.checks.factories import create_social_consequence_pools


class CreateSocialConsequencePoolsTest(TestCase):
    def test_creates_six_pools(self):
        pools = create_social_consequence_pools()

        self.assertEqual(len(pools), 6)
        expected_names = {"Intimidate", "Persuade", "Deceive", "Flirt", "Perform", "Entrance"}
        self.assertEqual(set(pools.keys()), expected_names)

    def test_each_pool_has_three_entries(self):
        pools = create_social_consequence_pools()

        for pool in pools.values():
            entry_count = pool.entries.count()
            self.assertEqual(
                entry_count,
                3,
                f"Pool '{pool.name}' expected 3 entries, got {entry_count}",
            )

    def test_idempotent(self):
        first = create_social_consequence_pools()
        second = create_social_consequence_pools()

        for action_name in first:
            self.assertEqual(
                first[action_name].pk,
                second[action_name].pk,
                f"Pool for '{action_name}' got a different pk on second call",
            )
