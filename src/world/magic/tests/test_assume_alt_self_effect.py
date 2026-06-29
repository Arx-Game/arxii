"""Tests for the ASSUME_ALTERNATE_SELF thread pull effect in technique casts (#1604)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    FormCombatProfileEffectFactory,
    FormCombatProfileFactory,
)
from world.forms.models import ActiveAlternateSelf, FormType
from world.forms.services import revert_alternate_self
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.services import use_technique
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


class AssumeAlternateSelfEffectTests(TestCase):
    """A cast pull whose ASSUME_ALTERNATE_SELF effect transforms the caster.

    The success band selects which `FormCombatProfile` is assumed and sets the
    `instance_value` scaling factor applied to the granted `CharacterModifier`
    rows.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(
            gift=cls.gift,
            intensity=1,
            control=10,
            anima_cost=1,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.anima = CharacterAnimaFactory(character=self.character, current=20, maximum=20)
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        self.true_form = CharacterFormFactory(
            character=self.character,
            name="True",
            form_type=FormType.TRUE,
        )
        CharacterFormStateFactory(character=self.character, active_form=self.true_form)
        PersonaFactory(character_sheet=self.sheet)

        self.alt_form = CharacterFormFactory(
            character=self.character,
            name="Beast",
            form_type=FormType.ALTERNATE,
        )
        self.target = ModifierTargetFactory()
        self.low_profile = FormCombatProfileFactory(form=self.alt_form, depth=1, display_name="low")
        self.mid_profile = FormCombatProfileFactory(form=self.alt_form, depth=2, display_name="mid")
        self.high_profile = FormCombatProfileFactory(
            form=self.alt_form, depth=3, display_name="high"
        )
        for profile in (self.low_profile, self.mid_profile, self.high_profile):
            FormCombatProfileEffectFactory(profile=profile, target=self.target, value=20)

        # One AlternateSelf grant per selectable profile so band selection maps 1:1
        # to an assumption target and revert can clean up by profile.  A non-unity
        # tuning_value avoids the identity branch in ``_create_assumption_grants``,
        # so instance_value scaling produces the expected monotonic values.
        self.alt_low = AlternateSelfFactory(
            character=self.sheet,
            form=self.alt_form,
            combat_profile=self.low_profile,
            tuning_value=2,
        )
        self.alt_mid = AlternateSelfFactory(
            character=self.sheet,
            form=self.alt_form,
            combat_profile=self.mid_profile,
            tuning_value=2,
        )
        self.alt_high = AlternateSelfFactory(
            character=self.sheet,
            form=self.alt_form,
            combat_profile=self.high_profile,
            tuning_value=2,
        )

        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=10,
        )
        self.pull_effect = ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.ASSUME_ALTERNATE_SELF,
            flat_bonus_amount=None,
            target_form=self.alt_form,
        )

    def _cast_with_success_level(self, success_level: int) -> None:
        """Run use_technique with a mock check result at the given success level."""
        from world.magic.types.pull import CastPullDeclaration

        outcome = CheckOutcomeFactory(name=f"outcome_{success_level}", success_level=success_level)
        check_type = CheckTypeFactory()
        check_result = CheckResult(
            check_type=check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        cast_pull = CastPullDeclaration(
            resonance=self.resonance,
            tier=1,
            threads=(self.thread,),
        )
        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
            check_result=check_result,
            cast_pull=cast_pull,
        )

    def _active_alt(self) -> ActiveAlternateSelf | None:
        return ActiveAlternateSelf.objects.filter(character=self.sheet).first()

    def _modifier_value(self) -> int | None:
        active = self._active_alt()
        if not active or not active.alternate_self:
            return None
        source = active.alternate_self.combat_profile
        if source is None:
            return None
        modifier = CharacterModifier.objects.filter(
            character=self.sheet,
            target=self.target,
            source__form_combat_profile=source,
        ).first()
        return modifier.value if modifier else None

    def test_failure_band_selects_lowest_depth_profile(self) -> None:
        """A failed cast assumes the lowest-depth profile with base scaling."""
        self._cast_with_success_level(0)

        active = self._active_alt()
        self.assertIsNotNone(active)
        self.assertEqual(active.alternate_self, self.alt_low)
        self.assertEqual(active.alternate_self.combat_profile, self.low_profile)
        self.assertEqual(self._modifier_value(), 4)  # round(20 * 2 * 1.0 / 10)

    def test_success_band_selects_mid_depth_profile(self) -> None:
        """An ordinary success selects the middle-depth profile at 1.5x scaling."""
        self._cast_with_success_level(3)

        active = self._active_alt()
        self.assertIsNotNone(active)
        self.assertEqual(active.alternate_self, self.alt_mid)
        self.assertEqual(active.alternate_self.combat_profile, self.mid_profile)
        self.assertEqual(self._modifier_value(), 6)  # round(20 * 2 * 1.5 / 10)

    def test_crit_band_selects_highest_depth_profile(self) -> None:
        """A critical success selects the highest-depth profile at 2.0x scaling."""
        self._cast_with_success_level(7)

        active = self._active_alt()
        self.assertIsNotNone(active)
        self.assertEqual(active.alternate_self, self.alt_high)
        self.assertEqual(active.alternate_self.combat_profile, self.high_profile)
        self.assertEqual(self._modifier_value(), 8)  # round(20 * 2 * 2.0 / 10)

    def test_higher_band_is_stronger_than_lower_band(self) -> None:
        """The granted modifier value strictly increases with success band."""
        self._cast_with_success_level(0)
        low_value = self._modifier_value()
        revert_alternate_self(self.sheet)  # type: ignore[arg-type]

        self._cast_with_success_level(3)
        mid_value = self._modifier_value()
        revert_alternate_self(self.sheet)  # type: ignore[arg-type]

        self._cast_with_success_level(7)
        high_value = self._modifier_value()

        assert low_value is not None
        assert mid_value is not None
        assert high_value is not None
        self.assertLess(low_value, mid_value)
        self.assertLess(mid_value, high_value)
