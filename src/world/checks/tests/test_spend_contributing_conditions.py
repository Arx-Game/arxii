"""A once-only (UNTIL_USED) condition that helped a real roll ends after it (#4584).

Collecting modifiers and previewing a check never spend; only a real roll does.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import ObjectDBFactory
from flows.constants import EventName
import world
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType, ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.services import (
    collect_check_modifiers,
    perform_check_with_modifiers,
    preview_check_difficulty,
)
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction
from world.combat.services import resolve_npc_attack
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
    DurationType,
)
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionConditionInteractionFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import bulk_apply_conditions
from world.conditions.types import BulkConditionApplication
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import (
    _ensure_endurance_check_type,
    get_vitals_consequence_config,
    process_damage_consequences,
)

# The resist rolls below must fail so both conditions land; pin the d100.
_ROLL = "world.checks.services.random.randint"
_EMIT = "world.conditions.services.emit_event"


class SpendContributingConditionsTests(TestCase):
    def setUp(self) -> None:
        CheckSystemSetupFactory.create()
        self.sheet = CharacterSheetFactory()
        self.char = self.sheet.character
        self.ct = CheckTypeFactory(name="Steadying Check 4584")
        self.blessing = ConditionTemplateFactory(
            name="Steadying Word 4584",
            default_duration_type=DurationType.UNTIL_USED,
        )
        ConditionCheckModifierFactory(condition=self.blessing, check_type=self.ct, modifier_value=3)
        self.blessing_inst_pk = ConditionInstanceFactory(
            target=self.char, condition=self.blessing
        ).pk

    def _blessing_exists(self) -> bool:
        return ConditionInstance.objects.filter(pk=self.blessing_inst_pk).exists()

    def test_a_real_roll_spends_a_once_only_blessing(self) -> None:
        perform_check_with_modifiers(self.char, self.ct, target_difficulty=0)

        self.assertFalse(self._blessing_exists())

    def test_collecting_modifiers_spends_nothing(self) -> None:
        breakdown = collect_check_modifiers(self.sheet, self.ct)

        self.assertEqual(
            [
                c.condition_instance_id
                for c in breakdown.contributions
                if c.source_kind == ModifierSourceKind.CONDITION
            ],
            [self.blessing_inst_pk],
        )
        self.assertTrue(self._blessing_exists())

    def test_a_preview_spends_nothing(self) -> None:
        preview_check_difficulty(self.char, self.ct, 0)

        self.assertTrue(self._blessing_exists())

    def test_a_zero_term_is_not_a_use(self) -> None:
        idle = ConditionTemplateFactory(
            name="Idle Word 4584", default_duration_type=DurationType.UNTIL_USED
        )
        ConditionCheckModifierFactory(condition=idle, check_type=self.ct, modifier_value=0)
        idle_pk = ConditionInstanceFactory(target=self.char, condition=idle).pk

        perform_check_with_modifiers(self.char, self.ct, target_difficulty=0)

        self.assertTrue(ConditionInstance.objects.filter(pk=idle_pk).exists())

    def test_a_lasting_blessing_survives_a_roll(self) -> None:
        lasting = ConditionTemplateFactory(
            name="Lasting Word 4584", default_duration_type=DurationType.ROUNDS
        )
        ConditionCheckModifierFactory(condition=lasting, check_type=self.ct, modifier_value=3)
        lasting_pk = ConditionInstanceFactory(target=self.char, condition=lasting).pk

        perform_check_with_modifiers(self.char, self.ct, target_difficulty=0)

        self.assertTrue(ConditionInstance.objects.filter(pk=lasting_pk).exists())
        self.assertFalse(self._blessing_exists())

    def test_an_npc_attack_defense_spends_a_defense_blessing_once(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CharacterVitalsFactory(character_sheet=self.sheet, health=200, max_health=200)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=ThreatPoolFactory())
        entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool, base_damage=10, defense_check_type=self.ct
        )
        swing = CombatOpponentAction.objects.create(
            opponent=opponent, round_number=1, threat_entry=entry
        )
        roll = MagicMock(return_value=MagicMock(success_level=2))

        resolve_npc_attack(swing, participant, self.ct, perform_check_fn=roll)
        resolve_npc_attack(swing, participant, self.ct, perform_check_fn=roll)

        self.assertFalse(self._blessing_exists())
        first, second = (call.kwargs["extra_modifiers"] for call in roll.call_args_list)
        self.assertEqual((first, second), (3, 0))

    def test_a_spent_resist_ward_does_not_break_the_rest_of_a_batch(self) -> None:
        # Review Focus 5: the first item's resist roll spends the once-only ward;
        # the second item still resolves against a batch context that held it.
        first = ConditionTemplateFactory(
            name="Clinging Ash 4584", resist_check_type=self.ct, resist_difficulty=100
        )
        second = ConditionTemplateFactory(
            name="Choking Smoke 4584", resist_check_type=self.ct, resist_difficulty=100
        )

        with patch(_ROLL, return_value=1):  # the lowest roll fails on every chart
            results = bulk_apply_conditions(
                [
                    BulkConditionApplication(target=self.char, template=first),
                    BulkConditionApplication(target=self.char, template=second),
                ]
            )

        self.assertTrue(all(r.success for r in results))
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.char, condition=first).exists()
        )
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.char, condition=second).exists()
        )
        self.assertFalse(self._blessing_exists())

    def test_a_ward_spent_by_the_resist_roll_no_longer_blocks_in_a_batch(self) -> None:
        # The batch context is fetched before any resist roll; a ward the roll spent
        # must not go on preventing the condition, exactly as a single apply would.
        incoming = ConditionTemplateFactory(
            name="Creeping Frost 4584", resist_check_type=self.ct, resist_difficulty=100
        )
        ConditionConditionInteractionFactory(
            condition=self.blessing,
            other_condition=incoming,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.PREVENT_OTHER,
        )

        with patch(_ROLL, return_value=1):  # the lowest roll fails on every chart
            (result,) = bulk_apply_conditions(
                [BulkConditionApplication(target=self.char, template=incoming)]
            )

        self.assertTrue(result.success)
        self.assertFalse(self._blessing_exists())


@override_settings(SEED_SAMPLE_CONTENT=True)  # Endurance CheckType gates on #2698
class KnockoutRollSpendsTests(TestCase):
    def test_a_knockout_roll_spends_a_blessing_on_endurance(self) -> None:
        vitals = CharacterVitalsFactory(health=10, max_health=100)
        character = vitals.character_sheet.character
        endurance = _ensure_endurance_check_type()
        blessing = ConditionTemplateFactory(
            name="Iron Breath 4584", default_duration_type=DurationType.UNTIL_USED
        )
        ConditionCheckModifierFactory(condition=blessing, check_type=endurance, modifier_value=3)
        blessing_pk = ConditionInstanceFactory(target=character, condition=blessing).pk

        failure_outcome = CheckOutcomeFactory(name="KO-Spend-Failure 4584", success_level=-1)
        consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=UnconsciousConditionFactory(),
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])

        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=character.sheet_data,
                damage_dealt=5,
                damage_type=None,
            )

        self.assertTrue(result.knocked_out)
        self.assertFalse(ConditionInstance.objects.filter(pk=blessing_pk).exists())


class BatchForgetsAMarkerItsFlowSpentTests(TestCase):
    """A marker its own CONDITION_APPLIED flow spends is gone for the rest of the batch."""

    def setUp(self) -> None:
        self.char = CharacterSheetFactory().character
        self.char.location = ObjectDBFactory(
            db_key="Marker Batch Room 4584", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.marker = ConditionTemplateFactory(
            name="Lingering Spark 4584",
            default_duration_type=DurationType.UNTIL_USED,
            is_stackable=True,
            max_stacks=3,
        )

    def test_a_later_item_lands_fresh_instead_of_stacking_onto_the_spent_marker(self) -> None:
        spent: list[int] = []

        def _flow_spends_the_first_marker(event_name, payload, **_kwargs):
            if event_name == EventName.CONDITION_APPLIED and not spent:
                spent.append(payload.instance.pk)
                payload.instance.delete()
            return MagicMock(was_cancelled=MagicMock(return_value=False))

        with patch(_EMIT, side_effect=_flow_spends_the_first_marker):
            _first, second = bulk_apply_conditions(
                [
                    BulkConditionApplication(target=self.char, template=self.marker),
                    BulkConditionApplication(target=self.char, template=self.marker),
                ]
            )

        self.assertTrue(second.success)
        (standing,) = ConditionInstance.objects.filter(target=self.char, condition=self.marker)
        self.assertNotEqual(standing.pk, spent[0])
        self.assertEqual(standing.stacks, 1)


# Functions that call ``collect_check_modifiers`` without a roll of their own to spend on,
# as "file::function" (a method is "file::Class.method").
_NOT_A_ROLL = {
    # preview grading: previews never spend
    "world/standoffs/services/view.py::_Grader.grade",
    # gathers for its two callers, which spend: resolve_challenge
    # (spend_contributing_conditions) and _resolve_via_template (spend_or_defer_condition_uses)
    "world/mechanics/challenge_resolution.py::_gather_challenge_modifiers",
}
# Calls that settle a breakdown's once-only terms (the second defers to the resume).
_SPENDERS = {"spend_contributing_conditions", "spend_or_defer_condition_uses"}


def _call_counts(node: ast.AST) -> tuple[int, int]:
    """(collect_check_modifiers calls, spend calls) in ``node``, nested closures included."""
    collects = spends = 0
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name == "collect_check_modifiers":
            collects += 1
        elif name in _SPENDERS:
            spends += 1
    return collects, spends


def _outer_functions(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """Module-level functions and the methods of module-level classes, by qualified name."""
    found: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            found.extend(
                (f"{node.name}.{item.name}", item)
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            )
    return found


class EverySiteSpendsTests(TestCase):
    def test_every_function_that_folds_conditions_into_a_roll_spends_them(self) -> None:
        """Per function, so a new unspent site in a file that spends elsewhere is caught."""
        src = Path(world.__file__).resolve().parent.parent
        offenders = []
        for path in sorted(src.rglob("*.py")):
            relative = path.relative_to(src)
            rel = relative.as_posix()
            # Test code calls collect_check_modifiers on purpose (a journey checks a
            # breakdown), so skip test modules, test packages and integration_tests.
            if (
                path.name.startswith("test_")
                or relative.parts[0] == "integration_tests"
                or "tests" in relative.parts[:-1]
            ):
                continue
            for name, node in _outer_functions(ast.parse(path.read_text())):
                collects, spends = _call_counts(node)
                if collects > spends and f"{rel}::{name}" not in _NOT_A_ROLL:
                    offenders.append(f"{rel}::{name} ({collects} collects, {spends} spends)")
        self.assertEqual(offenders, [])
