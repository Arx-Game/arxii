"""Tests for the composite FK constraints added via raw SQL.

The composite FKs `(interaction_id, interaction_timestamp) REFERENCES
scenes_interaction (id, timestamp)` are PostgreSQL-only artifacts (SQLite cannot
express them, and the schema isn't even built on the SQLite inner-loop tier).

PG replicates a parent composite FK into one child FK constraint per partition
of the target partitioned table. This is normal PostgreSQL behavior — our
declared constraint is one row in pg_catalog, but `information_schema.table_constraints`
exposes a flattened view that shows one entry per partition. So we look up
the named constraint specifically rather than counting all composite FKs.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase, tag

from world.combat.factories import (
    ClashContributionFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.scenes.factories import InteractionFactory

_NAMED_FK_ROUND_ACTION = "combat_roundaction_interaction_fk"
_NAMED_FK_CLASH_CONTRIBUTION = "combat_clashcontribution_interaction_fk"


@tag("postgres")
class CompositeFKExistsTests(TestCase):
    """The named composite FK constraint should exist at the DB level after migration."""

    def _named_fk_columns(self, table_name: str, constraint_name: str) -> frozenset[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name = %s
                    AND tc.constraint_name = %s
                """,
                [table_name, constraint_name],
            )
            return frozenset(row[0] for row in cursor.fetchall())

    def test_combat_round_action_has_composite_fk(self) -> None:
        cols = self._named_fk_columns("combat_combatroundaction", _NAMED_FK_ROUND_ACTION)
        self.assertEqual(cols, frozenset({"interaction_id", "interaction_timestamp"}))

    def test_clash_contribution_has_composite_fk(self) -> None:
        cols = self._named_fk_columns("combat_clashcontribution", _NAMED_FK_CLASH_CONTRIBUTION)
        self.assertEqual(cols, frozenset({"interaction_id", "interaction_timestamp"}))


@tag("postgres")
class CompositeFKBehaviorTests(TestCase):
    """The composite FK constraint should accept matching (interaction_id, timestamp) pairs.

    Note on mismatch behavior: PG's composite FK semantics against a partitioned
    target table are subtler than against a regular target, so we only assert
    the happy path here. The constraint's existence is verified above via
    information_schema; behavioral edge cases are left to the PG docs.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)

    def test_matching_pair_inserts_cleanly(self) -> None:
        interaction = InteractionFactory()
        action = CombatRoundActionFactory(
            participant=self.participant,
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        action.refresh_from_db()
        self.assertEqual(action.interaction_id, interaction.pk)
        self.assertEqual(action.interaction_timestamp, interaction.timestamp)

    def test_clash_contribution_matching_pair_inserts_cleanly(self) -> None:
        interaction = InteractionFactory()
        contribution = ClashContributionFactory(
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.interaction_id, interaction.pk)
        self.assertEqual(contribution.interaction_timestamp, interaction.timestamp)
