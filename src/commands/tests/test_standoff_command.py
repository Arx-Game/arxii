"""CmdStandoff: subverb routing, name resolution and the viewer-safe summary (#4145)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.standoff import CmdStandoff
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.mechanics.factories import PropertyFactory
from world.standoffs.constants import DriveStrength, RevealKind
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffApproachFactory,
    StandoffGroupFactory,
    StandoffRevealFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig, StandoffSparkShare
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

    def test_display_dispatches_the_casting_approach_with_the_technique(self) -> None:
        casting = StandoffApproachFactory(name="Show of Power", casts_technique=True)
        technique = TechniqueFactory(name="Thunderclap")
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        key, kwargs = self._dispatched("display thunderclap road bandits")
        self.assertEqual(key, "standoff_press")
        self.assertEqual(
            kwargs,
            {
                "group_id": self.group.pk,
                "approach_id": casting.pk,
                "technique_id": technique.pk,
            },
        )

    def test_display_with_soulfray_accepts_the_risk(self) -> None:
        StandoffApproachFactory(name="Show of Power", casts_technique=True)
        technique = TechniqueFactory(name="Thunderclap")
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        _, kwargs = self._dispatched("display thunderclap road bandits soulfray")
        self.assertEqual(kwargs["technique_id"], technique.pk)
        self.assertEqual(kwargs["group_id"], self.group.pk)
        self.assertIs(kwargs["confirm_soulfray_risk"], True)
        _, plain = self._dispatched("display thunderclap road bandits")
        self.assertNotIn("confirm_soulfray_risk", plain)

    def test_a_soulfray_refusal_says_how_to_accept(self) -> None:
        StandoffApproachFactory(name="Show of Power", casts_technique=True)
        technique = TechniqueFactory(name="Thunderclap")
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        cmd = self._cmd("display thunderclap road bandits")
        refused = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(
                success=False,
                message="Your soul is fraying.",
                data={"soulfray_warning": {"stage_name": "Fraying"}},
            ),
        )
        with patch(_DISPATCH, return_value=refused):
            cmd.func()
        sent = [call.args[0] for call in cmd.msg.call_args_list if call.args]
        self.assertEqual(sent[0], "Your soul is fraying.")
        self.assertIn("standoff display thunderclap road bandits soulfray", sent[1])

    def test_display_of_an_unknown_technique_is_a_command_error(self) -> None:
        StandoffApproachFactory(name="Show of Power", casts_technique=True)
        cmd = self._cmd("display nothing road bandits")
        cmd._subverb, cmd._rest = "display", "nothing road bandits"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

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

    def test_a_made_up_word_and_an_unrevealed_drive_both_just_read(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        made_up_key, made_up = self._dispatched("read Road Bandits zzzzqq")
        real_key, real = self._dispatched(f"read Road Bandits {drive.property.name}")
        self.assertEqual((made_up_key, real_key), ("standoff_read", "standoff_read"))
        self.assertEqual(made_up, {"group_id": self.group.pk})
        self.assertEqual(real["group_id"], self.group.pk)
        self.assertEqual(real["focus_property_id"], drive.property_id)
        self.assertNotIn("focus_drive_id", real)

    def test_a_property_this_group_lacks_resolves_the_same_way(self) -> None:
        other = PropertyFactory(name="Unheld Property")
        _, kwargs = self._dispatched("read Road Bandits unheld property")
        self.assertEqual(kwargs["focus_property_id"], other.pk)

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

    def test_summary_shows_revealed_cause_and_drives_but_not_hidden_ones(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        shown = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MAJOR)
        hidden = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        StandoffRevealFactory(group=self.group, kind=RevealKind.CAUSE)
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=shown)
        cmd = self._cmd("")
        cmd.func()
        text = cmd.msg.call_args.args[0]
        self.assertIn("Cause: Predation.", text)
        self.assertIn(f"Drive: {shown.property.name} (Major).", text)
        self.assertNotIn(hidden.property.name, text)

    def test_summary_lists_approach_and_terms_names_and_never_unshared_sparks(self) -> None:
        config = StandoffConfig.load()
        config.terms_check_type = CheckTypeFactory()
        config.save()
        RegardRuleFactory(creature_template=self.template, rule={}, spark_text="my own pang")
        RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": 999999}},
            spark_text="SOMEONE ELSES SPARK",
            revealed_text="SOMEONE ELSES DETAIL",
        )
        cmd = self._cmd("")
        cmd.func()
        text = cmd.msg.call_args.args[0]
        self.assertRegex(text, r"press Hard Stare: \w+")
        self.assertRegex(text, r"terms Let Us Pass: \w+")
        self.assertIn("my own pang", text)
        self.assertNotIn("SOMEONE ELSES", text)
        self.assertIn("unread", text)

    def test_summary_shows_the_critical_upgrade_on_terms_that_have_one(self) -> None:
        from world.standoffs.constants import TermsEffect

        config = StandoffConfig.load()
        config.terms_check_type = CheckTypeFactory()
        config.save()
        self.terms.critical_effect = TermsEffect.TURN
        self.terms.save(update_fields=["critical_effect"])
        StandoffTermsFactory(name="Plain Terms")
        cmd = self._cmd("")
        cmd.func()
        text = cmd.msg.call_args.args[0]
        self.assertRegex(text, r"terms Let Us Pass: \w+ \(on a critical: Turn\)")
        self.assertNotRegex(text, r"terms Plain Terms: \w+ \(on a critical")

    def test_summary_shows_a_spark_another_character_shared(self) -> None:
        other = CharacterSheetFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=other)
        rule = RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": 999999}},
            spark_text="a shared pang",
        )
        StandoffSparkShare.objects.create(group=self.group, character_sheet=other, regard_rule=rule)
        cmd = self._cmd("")
        cmd.func()
        self.assertIn("Shared: a shared pang", cmd.msg.call_args.args[0])

    def test_group_names_take_a_unique_word_or_prefix_case_insensitively(self) -> None:
        for typed in ("bandits", "BANDITS", "road", "Road Ban"):
            _, kwargs = self._dispatched(f"press hard stare {typed}")
            self.assertEqual(kwargs["group_id"], self.group.pk, typed)

    def test_an_ambiguous_group_name_lists_the_matches(self) -> None:
        other = CreatureTemplateFactory(name="Road Wolves", cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=other)
        StandoffGroupFactory(encounter=self.encounter, creature_template=other)
        cmd = self._cmd("press hard stare road")
        cmd._subverb, cmd._rest = "press", "hard stare road"
        with self.assertRaises(CommandError) as raised:
            cmd.resolve_action_args()
        self.assertIn("Road Bandits", str(raised.exception))
        self.assertIn("Road Wolves", str(raised.exception))
        # The exact whole name still wins.
        _, kwargs = self._dispatched("press hard stare Road Wolves")
        self.assertNotEqual(kwargs["group_id"], self.group.pk)

    def test_summary_header_names_the_place_and_grades_use_labels(self) -> None:
        cmd = self._cmd("")
        cmd.func()
        text = cmd.msg.call_args.args[0]
        self.assertTrue(text.startswith(f"Standoff at {self.encounter.room.db_key}:"))
        self.assertNotIn("impossible", text)
        self.assertIn("Hard Stare: Impossible", text)

    def test_summary_outside_a_standoff(self) -> None:
        self.character = CharacterFactory(db_key="bystander")
        CharacterSheetFactory(character=self.character)
        cmd = self._cmd("")
        cmd.func()
        cmd.msg.assert_called_with("You are not in a standoff.")
