"""Tests for the CombatRoundAction.interaction FK + interaction_timestamp denorm.

The FK is declared db_constraint=False on the model — the partitioned target
table (scenes_interaction) requires a composite FK on (id, timestamp), which
is added separately in raw SQL. This test confirms the ORM-level wiring
(nullable, related_name, attach/detach) without exercising the DB-level
constraint.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase, tag

from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatRoundAction
from world.scenes.factories import InteractionFactory


class CombatRoundActionInteractionTests(TestCase):
    """Verify the Interaction FK + timestamp pair work via the ORM."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)

    def test_interaction_field_defaults_null(self) -> None:
        action = CombatRoundActionFactory(participant=self.participant)
        self.assertIsNone(action.interaction)
        self.assertIsNone(action.interaction_timestamp)

    def test_attach_interaction(self) -> None:
        action = CombatRoundActionFactory(participant=self.participant)
        interaction = InteractionFactory()
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])

        action.refresh_from_db()
        self.assertEqual(action.interaction_id, interaction.pk)
        self.assertEqual(action.interaction_timestamp, interaction.timestamp)

    def test_detach_interaction(self) -> None:
        interaction = InteractionFactory()
        action = CombatRoundActionFactory(
            participant=self.participant,
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        action.interaction = None
        action.interaction_timestamp = None
        action.save(update_fields=["interaction", "interaction_timestamp"])

        action.refresh_from_db()
        self.assertIsNone(action.interaction_id)
        self.assertIsNone(action.interaction_timestamp)

    def test_related_name_combat_round_actions(self) -> None:
        interaction = InteractionFactory()
        action = CombatRoundActionFactory(
            participant=self.participant,
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        related = list(interaction.combat_round_actions.all())
        self.assertEqual(related, [action])


@tag("postgres")
class CombatRoundActionInteractionDBConstraintTests(TestCase):
    """The single-column FK should NOT exist at the DB level (db_constraint=False)."""

    def test_no_single_column_fk_on_interaction_id(self) -> None:
        # Look for any FK constraint on combat_combatroundaction that targets
        # only interaction_id (single-column). The composite FK
        # (interaction_id, interaction_timestamp) is created by the raw-SQL
        # migration and is allowed; what we want to confirm absent is the
        # Django-default single-column FK.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tc.constraint_name, kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name = 'combat_combatroundaction'
                ORDER BY tc.constraint_name, kcu.ordinal_position
                """
            )
            rows = cursor.fetchall()
        # Group by constraint name -> set of columns.
        constraints: dict[str, set[str]] = {}
        for name, col in rows:
            constraints.setdefault(name, set()).add(col)
        single_col_interaction_fks = [
            name for name, cols in constraints.items() if cols == {"interaction_id"}
        ]
        self.assertEqual(
            single_col_interaction_fks,
            [],
            "Did not expect a single-column FK on interaction_id "
            "(db_constraint=False on the ORM side).",
        )

    def test_clashcontribution_no_single_column_fk_on_interaction_id(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tc.constraint_name, kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name = 'combat_clashcontribution'
                ORDER BY tc.constraint_name, kcu.ordinal_position
                """
            )
            rows = cursor.fetchall()
        constraints: dict[str, set[str]] = {}
        for name, col in rows:
            constraints.setdefault(name, set()).add(col)
        single_col_interaction_fks = [
            name for name, cols in constraints.items() if cols == {"interaction_id"}
        ]
        self.assertEqual(single_col_interaction_fks, [])


class ClashContributionInteractionORMTests(TestCase):
    """ClashContribution mirrors CombatRoundAction's interaction wiring."""

    def test_default_null(self) -> None:
        from world.combat.factories import ClashContributionFactory

        contribution = ClashContributionFactory()
        self.assertIsNone(contribution.interaction)
        self.assertIsNone(contribution.interaction_timestamp)

    def test_attach_and_related_name(self) -> None:
        from world.combat.factories import ClashContributionFactory

        interaction = InteractionFactory()
        contribution = ClashContributionFactory(
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.interaction_id, interaction.pk)
        self.assertEqual(contribution.interaction_timestamp, interaction.timestamp)
        self.assertEqual(list(interaction.clash_contributions.all()), [contribution])

    def test_model_fields_present(self) -> None:
        # Sanity: confirm the fields are declared and match expected spec
        # (interaction = FK to scenes.Interaction, interaction_timestamp DT).
        field = CombatRoundAction._meta.get_field("interaction")
        self.assertEqual(field.related_model.__name__, "Interaction")
        self.assertFalse(field.db_constraint)
        self.assertTrue(field.null)

        ts_field = CombatRoundAction._meta.get_field("interaction_timestamp")
        self.assertTrue(ts_field.null)
        self.assertTrue(ts_field.db_index)
