"""CmdStandoff: subverb routing, name resolution and the viewer-safe summary (#4145)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.standoff import CmdStandoff
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.standoffs.constants import DriveStrength, RevealKind
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffApproachFactory,
    StandoffTermsFactory,
)
from world.standoffs.services.state import open_standoff

_DISPATCH = "commands.command.dispatch_player_action"


class CmdStandoffTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="standoffer")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.template = CreatureTemplateFactory(name="Road Bandits", cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=self.template)
        self.group = open_standoff(self.encounter)[0]
        self.approach = StandoffApproachFactory(name="Hard Stare")
        self.terms = StandoffTermsFactory(name="Let Us Pass")

    def _cmd(self, args: str) -> CmdStandoff:
        cmd = CmdStandoff()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"standoff {args}"
        cmd.cmdname = "standoff"
        cmd.msg = MagicMock()
        return cmd

    def _dispatched(self, args: str) -> tuple[str, dict]:
        cmd = self._cmd(args)
        ok = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="ok"),
        )
        with patch(_DISPATCH, return_value=ok) as dispatch:
            cmd.func()
        ref, kwargs = dispatch.call_args.args[1], dispatch.call_args.args[2]
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        return ref.registry_key, kwargs

    def test_fight_dispatches_standoff_fight(self) -> None:
        self.assertEqual(self._dispatched("fight"), ("standoff_fight", {}))

    def test_press_resolves_multiword_names(self) -> None:
        key, kwargs = self._dispatched("press hard stare road bandits")
        self.assertEqual(key, "standoff_press")
        self.assertEqual(kwargs, {"group_id": self.group.pk, "approach_id": self.approach.pk})

    def test_terms_resolves_names(self) -> None:
        key, kwargs = self._dispatched("terms Let Us Pass Road Bandits")
        self.assertEqual(key, "standoff_terms")
        self.assertEqual(kwargs, {"group_id": self.group.pk, "terms_id": self.terms.pk})

    def test_read_bare_group_and_cause_focus(self) -> None:
        self.assertEqual(
            self._dispatched("read Road Bandits"), ("standoff_read", {"group_id": self.group.pk})
        )
        _, kwargs = self._dispatched("read Road Bandits cause")
        self.assertEqual(kwargs["focus_kind"], RevealKind.CAUSE)

    def test_read_drive_focus(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        _, kwargs = self._dispatched(f"read Road Bandits {drive.property.name}")
        self.assertEqual(kwargs["focus_drive_id"], drive.pk)

    def test_share_resolves_own_spark(self) -> None:
        rule = RegardRuleFactory(creature_template=self.template, rule={}, spark_text="a pang")
        key, kwargs = self._dispatched("share Road Bandits a pang")
        self.assertEqual(key, "standoff_share_spark")
        self.assertEqual(kwargs["regard_rule_id"], rule.pk)

    def test_unknown_group_is_a_command_error(self) -> None:
        cmd = self._cmd("press Hard Stare Nobody")
        cmd._subverb, cmd._rest = "press", "Hard Stare Nobody"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_summary_lists_groups_and_own_sparks_only(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={}, spark_text="a pang")
        RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": 999999}},
            spark_text="SOMEONE ELSES SPARK",
        )
        CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        cmd = self._cmd("")
        cmd.func()
        text = cmd.msg.call_args.args[0]
        self.assertIn("Road Bandits (1)", text)
        self.assertIn("a pang", text)
        self.assertNotIn("SOMEONE ELSES SPARK", text)
        self.assertNotIn("PLACEHOLDER revealed", text)

    def test_summary_outside_a_standoff(self) -> None:
        self.character = CharacterFactory(db_key="bystander")
        CharacterSheetFactory(character=self.character)
        cmd = self._cmd("")
        cmd.func()
        cmd.msg.assert_called_with("You are not in a standoff.")
