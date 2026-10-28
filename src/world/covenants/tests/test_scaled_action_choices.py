"""``CovenantRoleActionScaling.action_key`` is a ``CovenantScaledAction`` choice (#4739).

U-keep: authored-row validation and content export have no player path.
"""

from decimal import Decimal
import json
from pathlib import Path
import tempfile

from django.core.exceptions import ValidationError
from django.test import TestCase

from core_management.content_export import export_to_content_repo
from world.covenants.constants import CovenantScaledAction
from world.covenants.factories import CovenantRoleActionScalingFactory, CovenantRoleFactory


class ScaledActionChoicesTests(TestCase):
    def test_existing_action_keys_validate(self) -> None:
        role = CovenantRoleFactory()
        for key in ("combat_interpose", "combat_rally", "surges_given"):
            with self.subTest(key=key):
                row = CovenantRoleActionScalingFactory(covenant_role=role, action_key=key)
                row.full_clean()
        self.assertEqual(CovenantScaledAction.INTERPOSE, "combat_interpose")
        self.assertEqual(CovenantScaledAction.RALLY, "combat_rally")
        self.assertEqual(CovenantScaledAction.SURGES_GIVEN.label, "Surges given by Rally")

    def test_unknown_action_key_refused(self) -> None:
        row = CovenantRoleActionScalingFactory.build(
            covenant_role=CovenantRoleFactory(), action_key="combat_taunt"
        )
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("action_key", ctx.exception.message_dict)


class ScaledActionExportTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_surges_given_row_round_trips(self) -> None:
        """Export writes the stored value and import matches the same row (no new one)."""
        from core_management.content_fixtures import build_all, load_entries

        role = CovenantRoleFactory(name="Export Herald", slug="export-herald")
        scaling = CovenantRoleActionScalingFactory(
            covenant_role=role,
            action_key=CovenantScaledAction.SURGES_GIVEN,
            thread_level_multiplier=Decimal("0.250"),
        )
        result = export_to_content_repo(self.root)
        self.assertEqual(result.errors, [])
        path = self.root / "fixtures" / "covenants" / "covenantroleactionscaling.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["fields"]["action_key"], "surges_given")
        self.assertEqual(records[0]["fields"]["covenant_role"], ["export-herald"])

        created, _updated, _ = load_entries(build_all(self.root))
        self.assertEqual(created, 0)
        scaling.refresh_from_db()
        self.assertEqual(scaling.action_key, CovenantScaledAction.SURGES_GIVEN)
        self.assertEqual(scaling.thread_level_multiplier, Decimal("0.250"))
