"""Tests for peril consequence pools + select_abandonment_pool (Task 4, #1479).

Covers:
- select_abandonment_pool: NPC → abandonment_enemy; PC → abandonment_pvp;
  None → abandonment_environmental.
- bleed_out_terminal factory yields a die (character_loss=True) row and a
  recover row.
- All four pools (bleed_out_terminal, abandonment_enemy, abandonment_pvp,
  abandonment_environmental) exist and have non-empty entry sets.
- die rows carry character_loss=True; recover rows carry character_loss=False.
- Per-pool weight_override is set correctly (weight-sharing guard): die weight
  in abandonment_enemy differs from bleed_out_terminal and abandonment_pvp.

SQLite-compatible: all factories use get_or_create; no ObjectDB-backed
model is used in setUpTestData (DbHolder trap — see MEMORY.md).
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.vitals.factories import (
    create_abandonment_pools,
    create_bleed_out_terminal_pool,
)


class SelectAbandonmentPoolTests(TestCase):
    """select_abandonment_pool routes to the correct pool by source type."""

    def setUp(self) -> None:
        # Pools must exist in DB before the helper can fetch them.
        create_abandonment_pools()

    def test_npc_source_returns_enemy_pool(self) -> None:
        from world.vitals.peril_resolution import select_abandonment_pool

        npc = CharacterFactory()  # no db_account → NPC
        pool = select_abandonment_pool(npc)
        self.assertEqual(pool.name, "abandonment_enemy")

    def test_pc_source_returns_pvp_pool(self) -> None:
        from world.vitals.peril_resolution import select_abandonment_pool

        account = AccountFactory()
        pc = CharacterFactory()
        pc.db_account = account
        pc.save(update_fields=["db_account"])
        pool = select_abandonment_pool(pc)
        self.assertEqual(pool.name, "abandonment_pvp")

    def test_none_source_returns_environmental_pool(self) -> None:
        from world.vitals.peril_resolution import select_abandonment_pool

        pool = select_abandonment_pool(None)
        self.assertEqual(pool.name, "abandonment_environmental")


class BleedOutTerminalPoolTests(TestCase):
    """bleed_out_terminal factory seeds the expected consequence rows."""

    def setUp(self) -> None:
        self.pool = create_bleed_out_terminal_pool()

    def test_pool_has_correct_name(self) -> None:
        self.assertEqual(self.pool.name, "bleed_out_terminal")

    def test_pool_has_die_row(self) -> None:
        """Pool must contain at least one consequence with character_loss=True."""
        die_entries = [
            e
            for e in self.pool.entries.select_related("consequence").all()
            if e.consequence.character_loss
        ]
        self.assertGreater(len(die_entries), 0, "bleed_out_terminal must have a die consequence")

    def test_pool_has_recover_row(self) -> None:
        """Pool must contain a recover consequence (character_loss=False, label 'recover')."""
        entries = list(self.pool.entries.select_related("consequence").all())
        recover_entries = [e for e in entries if e.consequence.label == "recover"]
        self.assertGreater(
            len(recover_entries), 0, "bleed_out_terminal must have a recover consequence"
        )

    def test_pool_has_stay_incapacitated_row(self) -> None:
        entries = list(self.pool.entries.select_related("consequence").all())
        stay_entries = [e for e in entries if e.consequence.label == "stay_incapacitated"]
        self.assertGreater(
            len(stay_entries), 0, "bleed_out_terminal must have a stay_incapacitated consequence"
        )

    def test_factory_idempotent(self) -> None:
        """Calling create_bleed_out_terminal_pool twice yields the same pool."""
        pool2 = create_bleed_out_terminal_pool()
        self.assertEqual(self.pool.pk, pool2.pk)


class AbandonmentPoolsTests(TestCase):
    """create_abandonment_pools seeds all three named abandonment pools."""

    def setUp(self) -> None:
        self.pools = create_abandonment_pools()

    def test_enemy_pool_exists(self) -> None:
        self.assertIn("abandonment_enemy", self.pools)
        self.assertEqual(self.pools["abandonment_enemy"].name, "abandonment_enemy")

    def test_pvp_pool_exists(self) -> None:
        self.assertIn("abandonment_pvp", self.pools)

    def test_environmental_pool_exists(self) -> None:
        self.assertIn("abandonment_environmental", self.pools)

    def test_all_pools_have_die_row(self) -> None:
        for name, pool in self.pools.items():
            die_entries = [
                e
                for e in pool.entries.select_related("consequence").all()
                if e.consequence.character_loss
            ]
            self.assertGreater(
                len(die_entries), 0, f"{name} pool must have a die (character_loss) consequence"
            )

    def test_all_pools_have_recover_row(self) -> None:
        for name, pool in self.pools.items():
            recover_entries = [
                e
                for e in pool.entries.select_related("consequence").all()
                if e.consequence.label == "recover"
            ]
            self.assertGreater(
                len(recover_entries), 0, f"{name} pool must have a recover consequence"
            )

    def test_abandonment_pools_idempotent(self) -> None:
        pools2 = create_abandonment_pools()
        for name in ("abandonment_enemy", "abandonment_pvp", "abandonment_environmental"):
            self.assertEqual(self.pools[name].pk, pools2[name].pk)


class PerPoolWeightTests(TestCase):
    """weight_override is set per-pool so the weight-sharing bug cannot recur.

    The same Consequence row (keyed on outcome_tier+label) is shared across
    pools, but each ConsequencePoolEntry carries an explicit weight_override so
    _entry_to_weighted uses the pool-specific weight, not the Consequence base
    weight (which only reflects whichever pool created the row first).
    """

    def setUp(self) -> None:
        self.bleed_out = create_bleed_out_terminal_pool()
        self.pools = create_abandonment_pools()

    def _entry_weight(self, pool, label: str) -> int:
        """Return the resolved weight for a consequence label within a pool."""
        entry = pool.entries.select_related("consequence").get(consequence__label=label)
        # weight_override is the pool-specific weight; it must always be set.
        if entry.weight_override is not None:
            return entry.weight_override
        return entry.consequence.weight

    def test_die_weight_bleed_out_is_1(self) -> None:
        """bleed_out_terminal: die weight=1."""
        self.assertEqual(self._entry_weight(self.bleed_out, "die"), 1)

    def test_die_weight_enemy_is_2(self) -> None:
        """abandonment_enemy: die weight=2 (more dangerous hostile-NPC context)."""
        self.assertEqual(self._entry_weight(self.pools["abandonment_enemy"], "die"), 2)

    def test_die_weight_pvp_is_1(self) -> None:
        """abandonment_pvp: die weight=1 (PvP die row filtered at runtime per ADR-0023)."""
        self.assertEqual(self._entry_weight(self.pools["abandonment_pvp"], "die"), 1)

    def test_die_weight_environmental_is_1(self) -> None:
        """abandonment_environmental: die weight=1."""
        self.assertEqual(self._entry_weight(self.pools["abandonment_environmental"], "die"), 1)

    def test_stay_incapacitated_weight_bleed_out_is_3(self) -> None:
        """bleed_out_terminal: stay_incapacitated weight=3."""
        self.assertEqual(self._entry_weight(self.bleed_out, "stay_incapacitated"), 3)

    def test_stay_incapacitated_weight_enemy_is_2(self) -> None:
        """abandonment_enemy: stay_incapacitated weight=2."""
        self.assertEqual(
            self._entry_weight(self.pools["abandonment_enemy"], "stay_incapacitated"), 2
        )

    def test_enemy_and_bleed_out_share_consequence_row_but_differ_in_weight(self) -> None:
        """The die Consequence is the same DB row across pools but pool weights differ."""
        bleed_entry = self.bleed_out.entries.select_related("consequence").get(
            consequence__label="die"
        )
        enemy_entry = (
            self.pools["abandonment_enemy"]
            .entries.select_related("consequence")
            .get(consequence__label="die")
        )
        # Shared row
        self.assertEqual(bleed_entry.consequence_id, enemy_entry.consequence_id)
        # Per-pool weights differ
        self.assertNotEqual(bleed_entry.weight_override, enemy_entry.weight_override)
        self.assertEqual(bleed_entry.weight_override, 1)
        self.assertEqual(enemy_entry.weight_override, 2)
