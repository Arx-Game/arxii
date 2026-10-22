"""A once-only (UNTIL_USED) condition that helped a real roll ends after it (#4584).

Collecting modifiers and previewing a check never spend; only a real roll does.
"""

from django.test import TestCase, override_settings

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType, ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.services import (
    collect_check_modifiers,
    perform_check_with_modifiers,
    preview_check_difficulty,
)
from world.checks.test_helpers import force_check_outcome
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
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import (
    _ensure_endurance_check_type,
    get_vitals_consequence_config,
    process_damage_consequences,
)


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

    def test_a_spent_resist_ward_does_not_break_the_rest_of_a_batch(self) -> None:
        # Review Focus 5: the first item's resist roll spends the once-only ward;
        # the second item still resolves against a batch context that held it.
        first = ConditionTemplateFactory(
            name="Clinging Ash 4584", resist_check_type=self.ct, resist_difficulty=100
        )
        second = ConditionTemplateFactory(
            name="Choking Smoke 4584", resist_check_type=self.ct, resist_difficulty=100
        )

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
