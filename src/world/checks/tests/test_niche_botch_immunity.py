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

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.services import collect_check_modifiers, perform_check
from world.checks.test_helpers import force_check_outcome
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
from world.scenes.factories import InteractionFactory, SceneFactory, SceneParticipationFactory
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
        target = ModifierTargetFactory(category=self.botch, name=f"Niche {len(scope)}", **scope)
        ModifierTarget.clear_trait_cache()
        return target

    def _distinction(self, target: ModifierTarget, *, name: str, value: int = 1) -> None:
        distinction = DistinctionFactory(name=name)
        DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=value)
        create_distinction_modifiers(
            CharacterDistinctionFactory(character=self.sheet, distinction=distinction)
        )

    def _roll(self, check_type, forced_level: int, situation_ctx=None):
        with force_check_outcome(self.outcomes[forced_level]):
            return perform_check(self.character, check_type, situation_ctx=situation_ctx)

    def test_category_immunity_raises_a_botch_to_failure(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        with patch("world.covenants.perks.services.announce_fired_perks") as announce:
            result = self._roll(self.riding, -2)

        self.assertEqual(result.outcome, self.outcomes[-1])
        announce.assert_not_called()

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
        ModifierTarget.clear_trait_cache()

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
        VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.BOTCH_IMMUNITY,
            beneficiary=PerkBeneficiary.SELF,
        )
        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)

        with patch("world.covenants.perks.services.announce_fired_perks") as announce:
            result = self._roll(self.riding, -2, situation_ctx=ctx)

        self.assertEqual(result.outcome, self.outcomes[-1])
        announce.assert_called_once()

    def test_no_situation_context_still_applies(self) -> None:
        target = self._target(target_check_category=self.wilderness)
        self._distinction(target, name="Born in the Saddle")

        self.assertEqual(self._roll(self.riding, -2, situation_ctx=None).outcome.success_level, -1)

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


class BotchImmunityLineVisibilityTests(TestCase):
    """The "Cannot botch" row reaches the roll's own player and staff, not onlookers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = AccountFactory()
        character = CharacterFactory()
        # The list is scoped by the puppet's account; the roll detail by the roster.
        character.db_account = cls.owner
        character.save()
        cls.sheet = CharacterSheetFactory(character=character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=character,
            player_data__account=cls.owner,
        )
        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene)
        cls.outcome = ConsequenceOutcome.objects.create(
            character=cls.sheet,
            check_type=CheckTypeFactory(),
            modifier_total=1,
            combat_interaction=interaction,
            combat_interaction_timestamp=interaction.timestamp,
        )
        ConsequenceOutcomeModifier.objects.create(
            outcome=cls.outcome,
            source_kind=ModifierSourceKind.CONDITION,
            source_label="Inspired",
            value=1,
        )
        ConsequenceOutcomeModifier.objects.create(
            outcome=cls.outcome,
            source_kind=ModifierSourceKind.BOTCH_IMMUNITY,
            source_label="Cannot botch: Born in the Saddle",
            value=0,
        )
        cls.onlooker = AccountFactory()
        SceneParticipationFactory(scene=scene, account=cls.onlooker)

    def _row(self, account) -> dict:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200)
        (row,) = [r for r in response.json()["results"] if r["id"] == self.outcome.pk]
        return row

    def test_the_roller_sees_the_line(self) -> None:
        row = self._row(self.owner)
        labels = [m["source_label"] for m in row["modifiers"]]
        self.assertIn("Cannot botch: Born in the Saddle", labels)
        self.assertEqual(row["modifier_total"], 1)

    def test_an_onlooker_does_not(self) -> None:
        row = self._row(self.onlooker)
        labels = [m["source_label"] for m in row["modifiers"]]
        self.assertEqual(labels, ["Inspired"])
        self.assertEqual(row["modifier_total"], 1)
