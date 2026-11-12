"""Niche botch immunity (#4386): a botch_immunity modifier raises a botch to Failure.

The modifier route shares ``_apply_outcome_guarantees``' one floor with the covenant vow
``BOTCH_IMMUNITY`` perk, but needs no ``SituationContext`` and announces nothing to the
room; the roller's own breakdown carries a value-0 "Cannot botch: <source>" line.

Not ``setUpTestData``: factories create Evennia ``ObjectDB`` instances (``DbHolder``, not
deepcopyable), same rationale as ``test_outcome_guarantees.py``.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import (
    MODIFIER_SOURCE_LABEL_MAX_LENGTH,
    CombatRollKind,
    ModifierLane,
    ModifierSize,
    ModifierSourceKind,
)
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.modifier_models import ModifierValue
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.services import (
    botch_immunity_sources,
    collect_check_modifiers,
    is_botch_immune,
    perform_check,
    record_consequence_outcome,
)
from world.checks.test_helpers import force_check_outcome
from world.checks.types import ModifierContribution
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.context import SituationContext
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.constants import BOTCH_IMMUNITY_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.mechanics.services import create_distinction_modifiers
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import InteractionFactory, SceneFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


class NicheBotchImmunityTests(TestCase):
    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        ResultChart.clear_cache()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.botch = ModifierCategoryFactory(name=BOTCH_IMMUNITY_CATEGORY_NAME)
        self.wilderness = CheckCategoryFactory(name="Niche Wilderness")
        self.riding = CheckTypeFactory(name="Niche Riding", category=self.wilderness)
        self.court = CheckCategoryFactory(name="Niche Court")
        self.etiquette = CheckTypeFactory(name="Niche Etiquette", category=self.court)
        self.chart, self.outcomes = self._chart(-2, -1, 1)

    def tearDown(self) -> None:
        ModifierTarget.clear_trait_cache()

    def _chart(self, *levels: int):
        """One rank-0 chart with one outcome per success_level, roll bands stacked."""
        chart = ResultChartFactory(rank_difference=0)
        outcomes = {}
        lo = 1
        for level in levels:
            outcome = CheckOutcomeFactory(name=f"Niche L{level}", success_level=level)
            ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=lo, max_roll=lo + 9)
            outcomes[level] = outcome
            lo += 10
        return chart, outcomes

    def _target(self, **scope: object) -> ModifierTarget:
        return ModifierTargetFactory(category=self.botch, name=f"Niche {len(scope)}", **scope)

    def _distinction(
        self, target: ModifierTarget, *, name: str, value: int = 1, size: int | None = None
    ) -> None:
        distinction = DistinctionFactory(name=name)
        DistinctionEffectFactory(
            distinction=distinction, target=target, value_per_rank=value, modifier_size=size
        )
        create_distinction_modifiers(
            CharacterDistinctionFactory(character=self.sheet, distinction=distinction)
        )

    def _roll(self, check_type, forced_level: int, situation_ctx=None):
        with force_check_outcome(self.outcomes[forced_level]):
            return perform_check(self.character, check_type, situation_ctx=situation_ctx)

    def test_category_immunity_raises_a_botch_to_failure(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        self.assertEqual(self._roll(self.riding, -2).outcome, self.outcomes[-1])

    def test_type_immunity_raises_a_botch_to_failure(self) -> None:
        target = self._target(target_scope_check_type=self.riding)
        self._distinction(target, name="Horse Whisperer")

        self.assertEqual(self._roll(self.riding, -2).outcome, self.outcomes[-1])

    def test_a_check_outside_the_scope_keeps_its_botch(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        self.assertEqual(self._roll(self.etiquette, -2).outcome, self.outcomes[-2])

    def test_a_non_botch_is_unchanged(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        self.assertEqual(self._roll(self.riding, -1).outcome, self.outcomes[-1])
        self.assertEqual(self._roll(self.riding, 1).outcome, self.outcomes[1])

    def test_an_inactive_target_is_ignored(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")
        target.is_active = False
        target.save()

        self.assertEqual(self._roll(self.riding, -2).outcome, self.outcomes[-2])

    def test_a_net_zero_total_is_not_immune(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")
        shaken = ConditionTemplateFactory(name="Niche Shaken")
        ConditionModifierEffectFactory(condition=shaken, modifier_target=target, value=-1)
        ConditionInstanceFactory(target=self.character, condition=shaken)

        self.assertEqual(self._roll(self.riding, -2).outcome, self.outcomes[-2])
        breakdown = collect_check_modifiers(self.sheet, self.riding)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.BOTCH_IMMUNITY, kinds)

    def test_the_verdict_is_the_flat_sum_even_when_a_sized_source_prices_higher(self) -> None:
        """A sized +1 distinction priced at 10 by the check lane's table, against a -1
        condition: the spec sum (flat 1 - 1 = 0) says not immune, though the lane-priced
        sources (10 - 1) are positive."""
        CharacterClassLevelFactory(
            character=self.sheet, character_class=CharacterClassFactory(), level=1
        )
        self.sheet.invalidate_class_level_cache()
        ModifierValue.objects.create(
            lane=ModifierLane.CHECK, level=1, size=ModifierSize.LARGE, value=10
        )
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle", size=ModifierSize.LARGE)
        shaken = ConditionTemplateFactory(name="Niche Shaken Sized")
        ConditionModifierEffectFactory(condition=shaken, modifier_target=target, value=-1)
        ConditionInstanceFactory(target=self.character, condition=shaken)

        priced = sum(s.value for s in botch_immunity_sources(self.sheet, self.riding))
        self.assertEqual(priced, 9)  # the two pricings really disagree here
        self.assertFalse(is_botch_immune(self.sheet, self.riding))
        self.assertEqual(self._roll(self.riding, -2).outcome, self.outcomes[-2])
        kinds = [
            c.source_kind for c in collect_check_modifiers(self.sheet, self.riding).contributions
        ]
        self.assertNotIn(ModifierSourceKind.BOTCH_IMMUNITY, kinds)

    def test_a_long_source_name_is_cut_to_the_recorded_label_length(self) -> None:
        """Unit: no authorable name reaches the cut (distinction and condition names stop
        at 100 characters, under the 120 the record keeps once "Cannot botch: " is added),
        so the source list is stood in for to prove the truncation itself."""
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")
        long_source = ModifierContribution(
            source_kind=ModifierSourceKind.EQUIPMENT, source_label="x" * 200, value=1
        )
        with patch("world.checks.services.botch_immunity_sources", return_value=[long_source]):
            breakdown = collect_check_modifiers(self.sheet, self.riding)

        (line,) = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.BOTCH_IMMUNITY
        ]
        self.assertEqual(len(line.source_label), MODIFIER_SOURCE_LABEL_MAX_LENGTH)
        self.assertTrue(line.source_label.startswith("Cannot botch: xxx"))

    def test_a_recorded_outcome_keeps_the_line_and_still_sums_to_its_total(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")
        breakdown = collect_check_modifiers(
            self.sheet,
            self.riding,
            extra_contributions=[
                ModifierContribution(
                    source_kind=ModifierSourceKind.EFFORT, source_label="Effort", value=3
                )
            ],
        )

        outcome = record_consequence_outcome(
            self.sheet,
            self.riding,
            None,
            None,
            breakdown,
            combat_interaction=InteractionFactory(),
        )

        rows = list(outcome.modifiers.all())
        self.assertIn(
            ("Cannot botch: Born in the Saddle", 0),
            [(row.source_label, row.value) for row in rows],
        )
        self.assertEqual(sum(row.value for row in rows), outcome.modifier_total)
        self.assertEqual(outcome.modifier_total, 3)

    def test_vow_and_modifier_immunity_give_one_floor_and_the_vow_still_announces(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.BOTCH_IMMUNITY,
            beneficiary=PerkBeneficiary.SELF,
        )
        self.character.location = ObjectDBFactory(
            db_key="Niche Paddock", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.character.save()
        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)

        # Her terminal is the one sink the room broadcast reaches her through.
        with patch.object(self.character, "msg") as told:
            result = self._roll(self.riding, -2, situation_ctx=ctx)

        self.assertEqual(result.outcome, self.outcomes[-1])
        lines = [call.kwargs["text"][0] for call in told.call_args_list if "text" in call.kwargs]
        self.assertEqual([line for line in lines if line.startswith(f"{perk.name}:")], lines)
        self.assertEqual(len(lines), 1)

    def test_breakdown_names_the_source_at_value_zero(self) -> None:
        plain = collect_check_modifiers(self.sheet, self.riding)
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        breakdown = collect_check_modifiers(self.sheet, self.riding)

        lines = [
            (c.source_label, c.value)
            for c in breakdown.contributions
            if c.source_kind == ModifierSourceKind.BOTCH_IMMUNITY
        ]
        self.assertEqual(lines, [("Cannot botch: Born in the Saddle", 0)])
        self.assertEqual(breakdown.total, plain.total)
        self.assertEqual(breakdown.extra_modifiers_total, plain.extra_modifiers_total)


class BotchImmunityRollBreakdownTests(TestCase):
    """Unit: a Strike damage roll's ``roll_breakdown`` branch, which the niche journey's
    climb (a challenge roll, no breakdown rows) cannot reach."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = AccountFactory()
        character = CharacterFactory()
        # The list is scoped by the puppet's account; the roll detail by the roster.
        character.db_account = cls.owner
        character.save()
        sheet = CharacterSheetFactory(character=character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=character,
            player_data__account=cls.owner,
        )
        damage_interaction = InteractionFactory(scene=SceneFactory())
        cls.damage_roll = ConsequenceOutcome.objects.create(
            character=sheet,
            check_type=CheckTypeFactory(),
            modifier_total=0,
            combat_interaction=damage_interaction,
            combat_interaction_timestamp=damage_interaction.timestamp,
            combat_roll_kind=CombatRollKind.DAMAGE,
        )
        ConsequenceOutcomeModifier.objects.create(
            outcome=cls.damage_roll,
            source_kind=ModifierSourceKind.BOTCH_IMMUNITY,
            source_label="Cannot botch: Born in the Saddle",
            value=0,
        )

    def test_the_roll_breakdown_shows_the_line_with_no_number(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        (row,) = [r for r in response.json()["results"] if r["id"] == self.damage_roll.pk]
        lines = {line["label"]: line["value"] for line in row["roll_breakdown"]["lines"]}
        self.assertEqual(lines["Cannot botch: Born in the Saddle"], "")
