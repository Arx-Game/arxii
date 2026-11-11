"""Journeys for a smoke form paid and rolled on every blow it softens (#5066 decision 18).

The cellar is the dodging journeys' (``_TheCellar``). Ysolde cast Drifting Smoke on herself
(a technique costing 3 anima): its condition, "Smoke Form", resists slashing by 4. Blades
strike her for 10 slashing each. She has no dodge.

- Each blow is a cast of Drifting Smoke as it lands: three blows, three casts, 9 anima.
- The technique roll scales the form's 4 for that blow: a bare success softens 4, one level
  better 6 (the MovementConfig default of 50 percent per level), a failure nothing (the
  blow lands whole, and the cast is still paid).
- A resistance she did not cast on herself (the same condition put on her by someone else),
  a passive's condition, and the condition her technique's price inflicts on her all stay
  flat and cost nothing (maintainer ruling 2026-11-11). Ticks and hazards read the form's
  resistance flat too; only blows are cast.
- Her baseline defenses are free (maintainer, 2026-11-11: "I don't want those bonuses to
  charge anima: they're always there"): a ward her covenant vow's added effect put on her
  while riding a cast of hers, and a thread's standing tier-0 resistance she is not
  pulling, each soften the blow by their full amount with no roll and no anima.

Expected values come from the spec (decision 18) and the rows built here: a full hit is the
strike's 10 at the defence roll's multiplier, so each case compares her health lost against
the same blow with no form.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actions.factories import ActionTemplateFactory
from integration_tests.test_dodging_journeys import RecordingRoll, _clean_hit, _TheCellar
from world.checks.factories import CheckTypeFactory
from world.combat.models import CombatEncounter
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.damage.passive_techniques import PASSIVE_SOURCE_PREFIX
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.covenants.added_effects import apply_vow_effect_payloads
from world.covenants.factories import (
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectFactory,
)
from world.covenants.types import FiredVowEffect
from world.magic.constants import EffectKind, RestrictionKind, TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    RestrictionFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.constants import RoundStatus

FORM_COST = 3
FORM_RESISTANCE = 4


class _SmokeInTheCellar(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.slashing = DamageTypeFactory(name="Slashing")
        self.smoke = TechniqueFactory(
            name="Drifting Smoke",
            anima_cost=FORM_COST,
            intensity=1,
            control=1,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Smoke Cast")),
        )
        self.form = ConditionTemplateFactory(name="Smoke Form")
        ConditionResistanceModifierFactory(
            condition=self.form, damage_type=self.slashing, modifier_value=FORM_RESISTANCE
        )
        # Drifting Smoke's own authored condition: the form she casts on herself.
        TechniqueAppliedConditionFactory(
            technique=self.smoke, condition=self.form, target_kind=ConditionTargetKind.SELF
        )
        self.ysolde = self.fighter("Ysolde", at=self.stage)
        CharacterTechniqueFactory(character=self.ysolde.sheet_data, technique=self.smoke)
        self.form_level = 1

    def wear_the_form(self, *, cast_by=None) -> None:
        caster = cast_by or self.ysolde
        ConditionInstanceFactory(
            target=self.ysolde,
            condition=self.form,
            source_character=caster,
            source_technique=self.smoke if caster == self.ysolde else None,
        )
        self.ysolde.conditions.invalidate()

    def slashers(self, count: int) -> None:
        for index in range(count):
            self.blade(f"Slasher {index}", at=self.gallery, damage_type=self.slashing)

    def hit(self, *defence_levels: int) -> int:
        """Resolve the round with the form's roll forced; the health she lost."""
        self.encounter = CombatEncounter.objects.get(pk=self.encounter.pk)
        if self.encounter.status != RoundStatus.DECLARING:
            begin_declaration_phase(self.encounter)
        before = self.health(self.ysolde)
        with patch(
            "world.combat.services.movement_use.roll_technique",
            side_effect=lambda *_a, **_k: MagicMock(success_level=self.form_level),
        ):
            resolve_round(
                self.encounter,
                defense_check_fn=RecordingRoll(*defence_levels),
                offense_check_fn=_clean_hit,
            )
        return before - self.health(self.ysolde)

    def lost_without_form(self) -> int:
        self.slashers(1)
        return self.hit(0)

    def ysolde_health_reset(self) -> None:
        from world.vitals.models import CharacterVitals

        vitals = CharacterVitals.objects.get(character_sheet=self.ysolde.sheet_data)
        vitals.health = 100
        vitals.save(update_fields=["health"])


class EachBlowIsACast(_SmokeInTheCellar):
    def test_three_blows_three_casts(self) -> None:
        self.wear_the_form()
        self.slashers(3)

        self.hit(0, 0, 0)

        self.assertEqual(self.anima(self.ysolde), 20 - 3 * FORM_COST)


class TheRollSetsHowMuch(_SmokeInTheCellar):
    def test_a_bare_success_softens_the_authored_amount(self) -> None:
        unformed = self.lost_without_form()
        self.wear_the_form()
        self.ysolde_health_reset()

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)

    def test_a_better_roll_softens_more_and_a_failure_none(self) -> None:
        unformed = self.lost_without_form()
        self.wear_the_form()
        self.ysolde_health_reset()
        self.form_level = 2
        self.assertEqual(self.hit(0), unformed - 6)  # 4 x 150 / 100
        self.ysolde_health_reset()
        self.form_level = 0
        anima_before = self.anima(self.ysolde)
        self.assertEqual(self.hit(0), unformed)
        self.assertEqual(self.anima(self.ysolde), anima_before - FORM_COST)

    def test_someone_elses_ward_stays_flat_and_free(self) -> None:
        unformed = self.lost_without_form()
        warder = self.fighter("Warder", at=self.floor)
        self.wear_the_form(cast_by=warder)
        self.ysolde_health_reset()
        self.form_level = 0  # a roll would soften nothing; there is no roll

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)
        self.assertEqual(self.anima(self.ysolde), 20)

    def test_a_passives_condition_stays_flat_and_free(self) -> None:
        """A passive applies with no roll; its resistance is never a per-blow cast
        (maintainer ruling 2026-11-11)."""
        unformed = self.lost_without_form()
        ConditionInstanceFactory(
            target=self.ysolde,
            condition=self.form,
            source_character=self.ysolde,
            source_technique=self.smoke,
            source_description=f"{PASSIVE_SOURCE_PREFIX}{self.smoke.name}",
        )
        self.ysolde.conditions.invalidate()
        self.ysolde_health_reset()
        self.form_level = 0

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)
        self.assertEqual(self.anima(self.ysolde), 20)

    def test_a_prices_inflicted_condition_stays_flat_and_free(self) -> None:
        """A price is a drawback she chose for her hold, not a buff she casts per blow."""
        unformed = self.lost_without_form()
        price = RestrictionFactory(kind=RestrictionKind.PRICE, inflicted_condition=self.form)
        hold = CharacterTechnique.objects.get(
            character=self.ysolde.sheet_data, technique=self.smoke
        )
        hold.price = price
        hold.save(update_fields=["price"])
        self.wear_the_form()
        self.ysolde_health_reset()
        self.form_level = 0

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)
        self.assertEqual(self.anima(self.ysolde), 20)


class BaselineDefensesAreFree(_SmokeInTheCellar):
    """Vow defenses and standing thread bonuses are her baseline: never a cast per blow."""

    def test_a_vow_ward_riding_her_cast_softens_a_blow_for_free(self) -> None:
        unformed = self.lost_without_form()
        oath = TechniqueFactory(name="Oathbound Guard", anima_cost=2)
        ward = ConditionTemplateFactory(name="Oath Ward")
        ConditionResistanceModifierFactory(
            condition=ward, damage_type=self.slashing, modifier_value=FORM_RESISTANCE
        )
        effect = VowAddedEffectFactory()
        VowAddedEffectAppliedConditionFactory(
            effect=effect, condition=ward, target_kind=ConditionTargetKind.SELF
        )
        # The vow's added effect fires on her cast of Oathbound Guard: the ward carries the
        # cast as provenance, the way every cast path applies a vow row's conditions.
        apply_vow_effect_payloads(
            [
                FiredVowEffect(
                    effect=effect,
                    holder=self.ysolde.sheet_data,
                    is_secondary=False,
                    severity_bonus=0,
                    duration_bonus=0,
                    damage_bonus=0,
                )
            ],
            technique=oath,
            success_level=1,
            eff_intensity=1,
            targets_by_kind={},
            source_character=self.ysolde,
            scene=None,
        )
        self.ysolde.conditions.invalidate()
        self.ysolde_health_reset()
        self.form_level = 0  # a roll would soften nothing; there is no roll

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)
        self.assertEqual(self.anima(self.ysolde), 20)

    def test_a_threads_standing_resistance_softens_a_blow_for_free(self) -> None:
        unformed = self.lost_without_form()
        thread = ThreadFactory(owner=self.ysolde.sheet_data, level=10, name="Ashen Skin")
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=thread.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=FORM_RESISTANCE,
            resistance_damage_type=self.slashing,
        )
        self.ysolde.threads.invalidate()
        self.ysolde_health_reset()
        self.form_level = 0

        lost = self.hit(0)

        self.assertEqual(lost, unformed - FORM_RESISTANCE)
        self.assertEqual(self.anima(self.ysolde), 20)
