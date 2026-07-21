"""Tests for power-scoped modifiers and power-term providers feeding _derive_power (#634, #637)."""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.covenants.factories import CovenantRoleTechniqueSpecialtyFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.magic.constants import TechniqueFunction
from world.magic.factories import ResonanceFactory, TechniqueDamageProfileFactory, TechniqueFactory
from world.magic.services.techniques import _derive_power
from world.mechanics.constants import POWER_CATEGORY_NAME
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    GlobalPowerTargetFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.services import (
    create_distinction_modifiers,
    get_modifier_breakdown,
    get_modifier_total,
)


class PowerDerivationTests(TestCase):
    """A power-scoped CharacterModifier raises derived power, additively, floored at 0."""

    def setUp(self):
        self.category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        self.global_target = ModifierTargetFactory(
            category=self.category, name="power", target_resonance=None
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _add_power(self, target, value):
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(character=self.sheet, target=target, value=value, source=source)

    def test_global_power_modifier_raises_derived_power(self):
        self._add_power(self.global_target, 5)
        result = _derive_power(
            channeled_intensity=7, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 12)

    def test_resonance_scoped_power_applies_on_matching_technique(self):
        fire = ResonanceFactory(name="Fire")
        self.technique.gift.resonances.add(fire)
        fire_target = ModifierTargetFactory(
            category=self.category, name="power_fire", target_resonance=fire
        )
        self._add_power(fire_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 7)

    def test_resonance_scoped_power_skipped_on_non_matching_technique(self):
        fire = ResonanceFactory(name="Fire")  # NOT added to the technique's gift
        fire_target = ModifierTargetFactory(
            category=self.category, name="power_fire", target_resonance=fire
        )
        self._add_power(fire_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 3)

    def test_global_power_applies_regardless_of_resonance(self):
        fire = ResonanceFactory(name="Fire")
        self.technique.gift.resonances.add(fire)
        self._add_power(self.global_target, 2)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 5)

    def test_none_character_returns_channeled_intensity(self):
        self._add_power(self.global_target, 5)
        self.assertEqual(
            _derive_power(channeled_intensity=4, technique=self.technique, character=None).total,
            4,
        )

    def test_character_without_sheet_returns_channeled_intensity(self):
        bare = CharacterFactory()  # no CharacterSheet created for this character
        self._add_power(self.global_target, 5)
        self.assertEqual(
            _derive_power(channeled_intensity=4, technique=self.technique, character=bare).total,
            4,
        )

    def test_none_technique_still_applies_global_power(self):
        self._add_power(self.global_target, 6)
        self.assertEqual(
            _derive_power(channeled_intensity=1, technique=None, character=self.character).total,
            7,
        )

    def test_negative_power_modifier_floors_at_zero(self):
        self._add_power(self.global_target, -100)
        self.assertEqual(
            _derive_power(
                channeled_intensity=5, technique=self.technique, character=self.character
            ).total,
            0,
        )

    def test_power_modifier_does_not_change_channeled_intensity(self):
        self._add_power(self.global_target, 5)
        channeled = 7
        power = _derive_power(
            channeled_intensity=channeled, technique=self.technique, character=self.character
        )
        # Power rose; the channeled-intensity input (which drives anima/mishap/Soulfray) did not.
        self.assertEqual(power.total, 12)
        self.assertEqual(channeled, 7)


class PowerFactoryDefaultsTests(TestCase):
    """The power default factories are idempotent and feed _derive_power."""

    def test_factories_are_idempotent(self):
        from world.mechanics.factories import GlobalPowerTargetFactory

        first = GlobalPowerTargetFactory()
        second = GlobalPowerTargetFactory()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.category.name, "power")
        self.assertIsNone(first.target_resonance_id)


class LevelPowerTermTests(TestCase):
    """LevelPowerConfig drives how character and technique level feed into _derive_power (#637)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _set_character_level(self, level: int) -> None:
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=self.character, level=level)
        self.sheet.invalidate_class_level_cache()

    def _make_config(self, *, char_bonus: int = 0, tech_bonus: int = 0):
        from world.magic.models import LevelPowerConfig

        return LevelPowerConfig.objects.create(
            pk=1, character_level_bonus=char_bonus, technique_level_bonus=tech_bonus
        )

    def test_character_level_raises_derived_power(self):
        self._make_config(char_bonus=2)
        self._set_character_level(3)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 11)  # 5 intensity + 3 levels * 2

    def test_technique_level_raises_derived_power(self):
        self._make_config(tech_bonus=1)
        self.technique.level = 7
        self.technique.save()
        result = _derive_power(
            channeled_intensity=4, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 11)  # 4 intensity + 7 technique levels * 1

    def test_both_bonuses_accumulate(self):
        self._make_config(char_bonus=1, tech_bonus=2)
        self._set_character_level(4)
        self.technique.level = 3
        self.technique.save()
        result = _derive_power(
            channeled_intensity=10, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 20)  # 10 + 4*1 + 3*2

    def test_zero_bonuses_contribute_nothing(self):
        self._make_config(char_bonus=0, tech_bonus=0)
        self._set_character_level(10)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 5)

    def test_no_config_row_contributes_nothing(self):
        self._set_character_level(5)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 5)

    def test_character_with_no_class_level_contributes_nothing(self):
        self._make_config(char_bonus=5)
        # no CharacterClassLevel created → current_level == 0
        result = _derive_power(
            channeled_intensity=8, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 8)

    def test_none_technique_still_applies_character_level(self):
        self._make_config(char_bonus=3)
        self._set_character_level(2)
        result = _derive_power(channeled_intensity=5, technique=None, character=self.character)
        self.assertEqual(result.total, 11)  # 5 + 2*3

    def test_level_term_does_not_affect_channeled_intensity(self):
        self._make_config(char_bonus=3)
        self._set_character_level(2)
        channeled = 7
        _derive_power(
            channeled_intensity=channeled, technique=self.technique, character=self.character
        )
        self.assertEqual(channeled, 7)


class ApplicableThreadsParameterTests(TestCase):
    """_derive_power accepts applicable_threads; thread provider is a stub returning 0 (#637)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def test_empty_applicable_threads_does_not_change_power(self):
        result = _derive_power(
            channeled_intensity=5,
            technique=self.technique,
            character=self.character,
            applicable_threads=[],
        )
        self.assertEqual(result.total, 5)

    def test_applicable_threads_kwarg_accepted(self):
        from world.magic.factories import ThreadFactory
        from world.magic.services.power_terms import ApplicableThread

        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance)
        threads = [ApplicableThread(thread=thread, pull_tier=1)]
        result = _derive_power(
            channeled_intensity=6,
            technique=self.technique,
            character=self.character,
            applicable_threads=threads,
        )
        # Stub returns 0 — power unchanged
        self.assertEqual(result.total, 6)


class DamageTypePowerDerivationTests(TestCase):
    """Damage-type-scoped power targets apply only when technique has a matching damage profile."""

    def setUp(self):
        self.category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        # Global target (no scopes) — present in DB but no modifier added by default.
        self.global_target = ModifierTargetFactory(
            category=self.category,
            name="power_dt_global",
            target_resonance=None,
            target_damage_type=None,
        )
        self.slashing = DamageTypeFactory(name="Slashing")
        self.fire = DamageTypeFactory(name="Fire")
        self.slashing_target = ModifierTargetFactory(
            category=self.category,
            name="power_slashing",
            target_damage_type=self.slashing,
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory(damage_profile=False)

    def _add_power(self, target, value):
        source = DistinctionModifierSourceFactory()
        CharacterModifierFactory(character=self.sheet, target=target, value=value, source=source)

    def test_damage_type_scoped_power_applies_on_matching_profile(self):
        """A slashing-scoped modifier raises power when technique has a slashing profile."""
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.slashing)
        self._add_power(self.slashing_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 7)

    def test_damage_type_scoped_power_skipped_on_non_matching_profile(self):
        """A slashing-scoped modifier does NOT apply when technique has only a fire profile."""
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.fire)
        self._add_power(self.slashing_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 3)

    def test_damage_type_scoped_power_skipped_when_no_profiles(self):
        """A slashing-scoped modifier does NOT apply when technique has no damage profiles."""
        self._add_power(self.slashing_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 3)

    def test_damage_type_scoped_power_skipped_on_untyped_profile(self):
        """A slashing-scoped modifier does NOT apply when technique has only untyped damage.

        Creates a separate technique with untyped damage to avoid unique constraint.
        """
        untyped_technique = TechniqueFactory(damage_profile=False)
        TechniqueDamageProfileFactory(technique=untyped_technique, damage_type=None)
        self._add_power(self.slashing_target, 4)
        result = _derive_power(
            channeled_intensity=3, technique=untyped_technique, character=self.character
        )
        self.assertEqual(result.total, 3)

    def test_damage_type_applies_when_any_profile_matches(self):
        """Modifier applies when technique has multiple profiles including a matching one."""
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.fire)
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.slashing)
        self._add_power(self.slashing_target, 3)
        result = _derive_power(
            channeled_intensity=2, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 5)

    def test_global_target_applies_regardless_of_damage_type(self):
        """A global (null damage-type) modifier applies even when technique has a typed profile."""
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.fire)
        self._add_power(self.global_target, 2)
        result = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        self.assertEqual(result.total, 7)

    def test_channeled_intensity_unaffected_by_damage_type_modifier(self):
        """Damage-type-scoped power raises landed effect only, not channeled intensity."""
        TechniqueDamageProfileFactory(technique=self.technique, damage_type=self.slashing)
        self._add_power(self.slashing_target, 5)
        channeled = 7
        power = _derive_power(
            channeled_intensity=channeled, technique=self.technique, character=self.character
        )
        self.assertEqual(power.total, 12)
        self.assertEqual(channeled, 7)


class PowerLedgerStructureTests(TestCase):
    """_derive_power returns an ordered PowerLedger; entries attribute every stage (#639)."""

    def setUp(self):
        self.category = ModifierCategoryFactory(name=POWER_CATEGORY_NAME)
        self.global_target = ModifierTargetFactory(
            category=self.category, name="power", target_resonance=None
        )
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _add_power(self, target, value, *, source_name=None):
        kwargs = {}
        if source_name is not None:
            kwargs["distinction_effect__distinction__name"] = source_name
        source = DistinctionModifierSourceFactory(**kwargs)
        CharacterModifierFactory(character=self.sheet, target=target, value=value, source=source)

    def test_ledger_has_base_entry_equal_to_channeled_intensity(self):
        from world.magic.constants import LedgerOp, PowerStage

        ledger = _derive_power(
            channeled_intensity=9, technique=self.technique, character=self.character
        )
        base_entries = [e for e in ledger.entries if e.stage == PowerStage.BASE]
        self.assertEqual(len(base_entries), 1)
        self.assertEqual(base_entries[0].amount, 9)
        self.assertEqual(base_entries[0].op, LedgerOp.SET)
        # Invariant: total == last running_total.
        self.assertEqual(ledger.total, ledger.entries[-1].running_total)

    def test_flat_modifier_entry_per_source_in_multi_source_case(self):
        from world.magic.constants import PowerStage

        self._add_power(self.global_target, 3, source_name="Source A")
        self._add_power(self.global_target, 4, source_name="Source B")
        ledger = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        flat_entries = [e for e in ledger.entries if e.stage == PowerStage.FLAT_MODIFIER]
        self.assertEqual(len(flat_entries), 2)
        names = {e.source_label for e in flat_entries}
        self.assertEqual(names, {"Source A", "Source B"})
        self.assertEqual(ledger.total, 12)  # 5 + 3 + 4

    def test_multiplier_entry_when_power_multiplier_source_exists(self):
        from world.magic.constants import LedgerOp, PowerStage
        from world.mechanics.factories import PowerMultiplierTargetFactory

        mult_target = PowerMultiplierTargetFactory()
        self._add_power(mult_target, 50)
        ledger = _derive_power(
            channeled_intensity=10, technique=self.technique, character=self.character
        )
        mult_entries = [e for e in ledger.entries if e.stage == PowerStage.MULTIPLIER]
        self.assertEqual(len(mult_entries), 1)
        self.assertEqual(mult_entries[0].op, LedgerOp.MULTIPLY)
        self.assertEqual(mult_entries[0].amount, 50)  # whole percent delta
        self.assertEqual(ledger.total, 15)  # round(10 * 150 / 100)

    def test_term_entry_when_provider_returns_nonzero(self):
        from world.classes.factories import CharacterClassLevelFactory
        from world.magic.constants import PowerStage
        from world.magic.models import LevelPowerConfig

        LevelPowerConfig.objects.create(pk=1, character_level_bonus=2, technique_level_bonus=0)
        CharacterClassLevelFactory(character=self.character, level=3)
        self.sheet.invalidate_class_level_cache()
        ledger = _derive_power(
            channeled_intensity=5, technique=self.technique, character=self.character
        )
        term_entries = [e for e in ledger.entries if e.stage == PowerStage.TERM]
        self.assertEqual(len(term_entries), 1)
        self.assertEqual(term_entries[0].amount, 6)  # 3 levels * 2
        self.assertEqual(term_entries[0].source_label, "level power")
        self.assertEqual(ledger.total, 11)

    def test_ledger_total_matches_old_formula_for_mixed_case(self):
        """Numeric-fidelity proof: flat + multiplier + level term together equal the
        pre-ledger formula round(base*(100+delta)/100) + flat + Σterms."""
        from world.classes.factories import CharacterClassLevelFactory
        from world.magic.constants import PowerStage
        from world.magic.models import LevelPowerConfig
        from world.mechanics.factories import PowerMultiplierTargetFactory

        # Flat: two sources summing to 7.
        self._add_power(self.global_target, 3, source_name="Flat A")
        self._add_power(self.global_target, 4, source_name="Flat B")
        # Multiplier: +35% delta.
        mult_target = PowerMultiplierTargetFactory()
        self._add_power(mult_target, 35)
        # Term: 4 character levels * 2 = 8.
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=2, technique_level_bonus=0)
        CharacterClassLevelFactory(character=self.character, level=4)
        self.sheet.invalidate_class_level_cache()

        base = 13
        delta = 35
        flat = 7
        terms = 8
        expected = round(base * (100 + delta) / 100) + flat + terms

        ledger = _derive_power(
            channeled_intensity=base, technique=self.technique, character=self.character
        )
        self.assertEqual(ledger.total, expected)
        # And the ledger actually exercised all three stages.
        stages = {e.stage for e in ledger.entries}
        self.assertIn(PowerStage.MULTIPLIER, stages)
        self.assertIn(PowerStage.FLAT_MODIFIER, stages)
        self.assertIn(PowerStage.TERM, stages)


class EnvironmentPowerStageTests(TestCase):
    """The ENVIRONMENT power-shift stage (#639 Task 4): AMPLIFY-only, no double-count."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.technique = TechniqueFactory()

    def _effect(self, *, valence, kind, magnitude):
        from world.magic.constants import ResonanceDirection
        from world.magic.services.resonance_environment import ResonanceEnvironmentEffect

        return ResonanceEnvironmentEffect(
            valence=valence,
            kind=kind,
            direction=ResonanceDirection.ENVIRONMENT_DOMINANT,
            magnitude=magnitude,
            source_affinity=None,
            environment_affinity=None,
            interaction=None,
            backfire_difficulty=0,
        )

    def test_amplify_adds_magnitude_as_single_environment_entry(self):
        from world.magic.constants import (
            AffinityInteractionKind,
            LedgerOp,
            PowerStage,
            ResonanceValence,
        )

        magnitude = 4
        baseline = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=None,
        )
        effect = self._effect(
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            magnitude=magnitude,
        )
        ledger = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=effect,
        )
        env_entries = [e for e in ledger.entries if e.stage == PowerStage.ENVIRONMENT]
        self.assertEqual(len(env_entries), 1)
        self.assertEqual(env_entries[0].amount, magnitude)
        self.assertEqual(env_entries[0].op, LedgerOp.ADD)
        self.assertEqual(env_entries[0].source_label, "resonance environment")
        self.assertEqual(ledger.total, baseline.total + magnitude)

    def test_opposed_reject_adds_no_power(self):
        """OPPOSED penalty lives in the Step-10 backfire; no power change here (no double-count)."""
        from world.magic.constants import (
            AffinityInteractionKind,
            PowerStage,
            ResonanceValence,
        )

        baseline = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=None,
        )
        effect = self._effect(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            magnitude=4,
        )
        ledger = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=effect,
        )
        env_entries = [e for e in ledger.entries if e.stage == PowerStage.ENVIRONMENT]
        self.assertEqual(env_entries, [])
        self.assertEqual(ledger.total, baseline.total)

    def test_aligned_non_amplify_kind_does_not_double_count(self):
        """ALIGNED presence boon flows through the FLAT/condition stage; no ENVIRONMENT entry."""
        from world.magic.constants import PowerStage, ResonanceValence

        baseline = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=None,
        )
        # ALIGNED valence but kind is "" (inert/non-AMPLIFY) — must not add power here.
        effect = self._effect(valence=ResonanceValence.ALIGNED, kind="", magnitude=4)
        ledger = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=effect,
        )
        env_entries = [e for e in ledger.entries if e.stage == PowerStage.ENVIRONMENT]
        self.assertEqual(env_entries, [])
        self.assertEqual(ledger.total, baseline.total)

    def test_none_environment_adds_no_entry(self):
        from world.magic.constants import PowerStage

        ledger = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=None,
        )
        env_entries = [e for e in ledger.entries if e.stage == PowerStage.ENVIRONMENT]
        self.assertEqual(env_entries, [])

    def test_amplify_zero_magnitude_adds_no_entry(self):
        from world.magic.constants import (
            AffinityInteractionKind,
            PowerStage,
            ResonanceValence,
        )

        effect = self._effect(
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            magnitude=0,
        )
        ledger = _derive_power(
            channeled_intensity=10,
            technique=self.technique,
            character=self.character,
            environment=effect,
        )
        env_entries = [e for e in ledger.entries if e.stage == PowerStage.ENVIRONMENT]
        self.assertEqual(env_entries, [])


class AuraPowerConfigAccessorTests(TestCase):
    def test_accessor_returns_none_when_absent(self):
        from world.magic.services.power_terms import get_aura_power_config

        self.assertIsNone(get_aura_power_config())

    def test_accessor_returns_singleton(self):
        from world.magic.models import AuraPowerConfig
        from world.magic.services.power_terms import get_aura_power_config

        cfg = AuraPowerConfig.objects.create(
            pk=1, affinity_alignment_bonus=10, resonance_standing_bonus=2
        )
        self.assertEqual(get_aura_power_config(), cfg)


class ImmunityBlockedFlatSourceTests(TestCase):
    """Immunity-blocked negative sources must be excluded from FLAT stage (#639 fidelity).

    Regression: the refactored _derive_power iterated all breakdown.sources including
    immunity-blocked ones, re-adding the blocked negative and diverging from the old
    get_modifier_total result. The fix skips sources with blocked_by_immunity=True.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        # Global power target (no scope gates — matches technique=None).
        self.power_target = GlobalPowerTargetFactory()

        # Immunity-granting source: +5 power, grants_immunity_to_negative=True.
        self.immunity_distinction = DistinctionFactory(name="Warded Strike")
        DistinctionEffectFactory(
            distinction=self.immunity_distinction,
            target=self.power_target,
            value_per_rank=5,
            grants_immunity_to_negative=True,
        )
        cd_immunity = CharacterDistinctionFactory(
            character=self.character,
            distinction=self.immunity_distinction,
            rank=1,
        )
        create_distinction_modifiers(cd_immunity)

        # Negative source: -3 power (should be blocked by immunity).
        self.negative_distinction = DistinctionFactory(name="Cursed Aim")
        DistinctionEffectFactory(
            distinction=self.negative_distinction,
            target=self.power_target,
            value_per_rank=-3,
        )
        cd_negative = CharacterDistinctionFactory(
            character=self.character,
            distinction=self.negative_distinction,
            rank=1,
        )
        create_distinction_modifiers(cd_negative)

    def test_mechanics_breakdown_excludes_blocked_negative(self):
        """Sanity: get_modifier_breakdown already blocks the negative source."""
        breakdown = get_modifier_breakdown(self.sheet, self.power_target)
        self.assertEqual(breakdown.total, 5)  # only the +5; -3 is blocked
        self.assertTrue(breakdown.has_immunity)
        self.assertEqual(breakdown.negatives_blocked, 1)
        cursed = next(s for s in breakdown.sources if s.source_name == "Cursed Aim")
        self.assertTrue(cursed.blocked_by_immunity)

    def test_derive_power_total_excludes_blocked_negative(self):
        """_derive_power.total must equal get_modifier_total (i.e. NOT subtract the blocked -3)."""
        expected_flat = get_modifier_total(self.sheet, self.power_target)  # == 5
        channeled = 10
        ledger = _derive_power(
            channeled_intensity=channeled,
            technique=None,  # global target matches with no technique
            character=self.character,
        )
        # 10 (base) + 5 (unblocked flat) = 15; NOT 10 + 5 - 3 = 12.
        self.assertEqual(ledger.total, channeled + expected_flat)

    def test_blocked_source_absent_from_flat_ledger_entries(self):
        """No FLAT_MODIFIER ledger entry should exist for the blocked negative source."""
        from world.magic.constants import PowerStage

        ledger = _derive_power(
            channeled_intensity=10,
            technique=None,
            character=self.character,
        )
        flat_labels = {
            e.source_label for e in ledger.entries if e.stage == PowerStage.FLAT_MODIFIER
        }
        self.assertNotIn("Cursed Aim", flat_labels)
        self.assertIn("Warded Strike", flat_labels)


class AuraPowerTermTests(TestCase):
    def setUp(self):
        from world.magic.factories import (
            AffinityFactory,
            CharacterAuraFactory,
            GiftFactory,
            ResonanceFactory,
            TechniqueFactory,
        )

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.affinity = AffinityFactory(name="Celestial")
        self.resonance = ResonanceFactory(affinity=self.affinity)
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(gift=gift)
        CharacterAuraFactory(
            character=self.character,
            celestial=Decimal("50.00"),
            primal=Decimal("30.00"),
            abyssal=Decimal("20.00"),
        )

    def _ctx(self):
        from world.magic.services.power_terms import PowerTermContext

        return PowerTermContext(sheet=self.sheet, technique=self.technique, applicable_threads=[])

    def test_returns_zero_without_config(self):
        from world.magic.services.power_terms import aura_power_term

        self.assertEqual(aura_power_term(self._ctx()), 0)

    def test_affinity_alignment_axis(self):
        from world.magic.factories import AuraPowerConfigFactory
        from world.magic.services.power_terms import aura_power_term

        AuraPowerConfigFactory(affinity_alignment_bonus=20)  # 50% celestial * 20 = 10
        self.assertEqual(aura_power_term(self._ctx()), 10)

    def _set_level(self, level: int) -> None:
        from world.classes.factories import CharacterClassLevelFactory

        CharacterClassLevelFactory(character=self.character, level=level)
        self.sheet.invalidate_class_level_cache()

    def _standing_setup(self, lifetime_earned: int, bonus: int) -> None:
        from world.magic.factories import AuraPowerConfigFactory, CharacterResonanceFactory

        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.resonance, lifetime_earned=lifetime_earned
        )
        AuraPowerConfigFactory(resonance_standing_bonus=bonus)

    def test_standing_uncapped_when_no_bands(self):
        from world.magic.services.power_terms import aura_power_term

        self._standing_setup(lifetime_earned=30, bonus=2)  # 60, no bands
        self._set_level(5)
        self.assertEqual(aura_power_term(self._ctx()), 60)

    def test_standing_uncapped_when_level_below_lowest_band(self):
        from world.magic.factories import StandingCapBandFactory
        from world.magic.services.power_terms import aura_power_term

        self._standing_setup(lifetime_earned=30, bonus=2)  # 60
        StandingCapBandFactory(min_level=5, cap=40, mode="HARD")
        self._set_level(3)  # below the only band
        self.assertEqual(aura_power_term(self._ctx()), 60)

    def test_hard_band_clamps(self):
        from world.magic.factories import StandingCapBandFactory
        from world.magic.services.power_terms import aura_power_term

        self._standing_setup(lifetime_earned=30, bonus=2)  # 60
        StandingCapBandFactory(min_level=1, cap=40, mode="HARD")
        self._set_level(5)
        self.assertEqual(aura_power_term(self._ctx()), 40)  # reproduces the old flat-cap behavior

    def test_soft_band_diminishes_excess(self):
        from world.magic.factories import StandingCapBandFactory
        from world.magic.services.power_terms import aura_power_term

        self._standing_setup(lifetime_earned=30, bonus=2)  # 60
        StandingCapBandFactory(min_level=1, cap=40, mode="SOFT", diminish_pct=50)
        self._set_level(5)
        # 40 + (60 - 40) * 50 // 100 = 40 + 10 = 50
        self.assertEqual(aura_power_term(self._ctx()), 50)

    def test_highest_applicable_band_wins(self):
        from world.magic.factories import StandingCapBandFactory
        from world.magic.services.power_terms import aura_power_term

        self._standing_setup(lifetime_earned=100, bonus=2)  # 200
        StandingCapBandFactory(min_level=1, cap=40, mode="HARD")
        StandingCapBandFactory(min_level=6, cap=150, mode="HARD")
        self._set_level(8)  # picks the L6 band, not L1
        self.assertEqual(aura_power_term(self._ctx()), 150)

    def test_no_technique_returns_zero(self):
        from world.magic.factories import AuraPowerConfigFactory
        from world.magic.services.power_terms import PowerTermContext, aura_power_term

        AuraPowerConfigFactory(affinity_alignment_bonus=20)
        ctx = PowerTermContext(sheet=self.sheet, technique=None, applicable_threads=[])
        self.assertEqual(aura_power_term(ctx), 0)


class ThreadPowerTermTests(TestCase):
    def setUp(self):
        from world.magic.factories import ResonanceFactory

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.resonance = ResonanceFactory()

    def _thread(self, level=0):
        from world.magic.factories import ThreadFactory

        return ThreadFactory(owner=self.sheet, resonance=self.resonance, level=level)

    def test_empty_returns_zero(self):
        from world.magic.services.power_terms import PowerTermContext, thread_power_term

        ctx = PowerTermContext(sheet=self.sheet, technique=None, applicable_threads=[])
        self.assertEqual(thread_power_term(ctx), 0)

    def test_sums_intensity_bump_for_passive_tier0(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadPullEffectFactory
        from world.magic.services.power_terms import (
            ApplicableThread,
            PowerTermContext,
            thread_power_term,
        )

        thread = self._thread(level=0)  # multiplier max(1, 0//10) = 1
        ThreadPullEffectFactory(
            as_intensity_bump=True,
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=0,
            intensity_bump_amount=3,
        )
        ctx = PowerTermContext(
            sheet=self.sheet,
            technique=None,
            applicable_threads=[ApplicableThread(thread=thread, pull_tier=0)],
        )
        self.assertEqual(thread_power_term(ctx), 3)

    def test_flat_bonus_ignored(self):
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadPullEffectFactory
        from world.magic.services.power_terms import (
            ApplicableThread,
            PowerTermContext,
            thread_power_term,
        )

        thread = self._thread(level=0)
        ThreadPullEffectFactory(  # FLAT_BONUS (default) must NOT contribute to power
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=0,
            flat_bonus_amount=9,
        )
        ctx = PowerTermContext(
            sheet=self.sheet,
            technique=None,
            applicable_threads=[ApplicableThread(thread=thread, pull_tier=0)],
        )
        self.assertEqual(thread_power_term(ctx), 0)


class CastPullDeclarationTests(TestCase):
    def test_is_frozen_dataclass(self):
        import dataclasses

        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.magic.types.pull import CastPullDeclaration

        res = ResonanceFactory()
        thread = ThreadFactory(resonance=res)
        decl = CastPullDeclaration(resonance=res, tier=2, threads=(thread,))
        self.assertEqual(decl.tier, 2)
        self.assertEqual(decl.resonance, res)
        self.assertEqual(decl.threads, (thread,))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decl.tier = 3  # frozen


class StandingCapBandModelTests(TestCase):
    def test_factory_creates_band(self):
        from world.magic.factories import StandingCapBandFactory

        band = StandingCapBandFactory(min_level=1, cap=50)
        self.assertEqual(band.min_level, 1)
        self.assertEqual(band.cap, 50)

    def test_hard_band_rejects_nonzero_diminish(self):
        from django.core.exceptions import ValidationError

        from world.magic.constants import StandingCapMode
        from world.magic.models import StandingCapBand

        band = StandingCapBand(min_level=1, cap=50, mode=StandingCapMode.HARD, diminish_pct=25)
        with self.assertRaises(ValidationError):
            band.full_clean()

    def test_soft_band_allows_diminish(self):
        from world.magic.constants import StandingCapMode
        from world.magic.models import StandingCapBand

        band = StandingCapBand(min_level=6, cap=100, mode=StandingCapMode.SOFT, diminish_pct=50)
        band.full_clean()  # no raise


class CovenantRoleBlendPowerTermTests(TestCase):
    """covenant_role_blend_power_term: always-on blend floor for engaged roles (#2529)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique=None):
        from world.magic.services.power_terms import PowerTermContext

        return PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])

    def _technique(self, alignment):
        return TechniqueFactory(archetype_alignment=alignment)

    def _thread(self, level):
        from world.magic.factories import ThreadFactory

        return ThreadFactory(owner=self.sheet, level=level)

    def _engage_role(self, *, sword=0, shield=0, crown=0, covenant=None):
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        role = CovenantRoleFactory(
            sword_weight=Decimal(str(sword)),
            shield_weight=Decimal(str(shield)),
            crown_weight=Decimal(str(crown)),
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=covenant or CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        return role

    def test_no_engaged_role_returns_zero(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        technique = self._technique("sword")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 0)

    def test_no_threads_returns_zero(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        technique = self._technique("sword")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 0)

    def test_no_technique_returns_zero(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        self.assertEqual(covenant_role_blend_power_term(self._ctx(None)), 0)

    def test_sword_aligned_technique_scales_by_sword_weight(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        technique = self._technique("sword")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 6)

    def test_crown_aligned_technique_scales_by_crown_weight(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        technique = self._technique("crown")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 4)

    def test_shield_aligned_technique_with_zero_weight_returns_zero(self):
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        technique = self._technique("shield")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 0)

    def test_two_engaged_roles_sum(self):
        from world.covenants.factories import CovenantFactory
        from world.magic.services.power_terms import covenant_role_blend_power_term

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"), covenant=CovenantFactory())
        self._engage_role(sword=Decimal("0.3"), crown=Decimal("0.7"), covenant=CovenantFactory())
        technique = self._technique("sword")
        # (10*0.6*1.0) + (10*0.3*1.0) = 6.0 + 3.0 = 9.0 -> int(9.0) = 9
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 9)

    def test_multiplier_tenths_scales_result(self):
        from world.magic.services.power_terms import (
            covenant_role_blend_power_term,
            get_covenant_role_blend_config,
        )

        self._thread(level=10)
        self._engage_role(sword=Decimal("0.6"), crown=Decimal("0.4"))
        technique = self._technique("sword")
        config = get_covenant_role_blend_config()
        config.multiplier_tenths = 20
        config.save()
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 12)


class CovenantRoleSpecialtyPowerTermTests(TestCase):
    """covenant_role_specialty_power_term: per-vow technique-specialty boost (#2443)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique=None):
        from world.magic.services.power_terms import PowerTermContext

        return PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])

    def _thread(self, level):
        from world.magic.factories import ThreadFactory

        return ThreadFactory(owner=self.sheet, level=level)

    def _engage_role(self, role=None, *, engaged=True, covenant=None):
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        role = role or CovenantRoleFactory(sword_weight=0, shield_weight=0, crown_weight=1)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=covenant or CovenantFactory(),
            covenant_role=role,
            engaged=engaged,
        )
        return role

    def test_matching_tag_boosted(self):
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        role = self._engage_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=15
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 15)

    def test_untagged_technique_returns_zero(self):
        from world.magic.factories import TechniqueFactory
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        role = self._engage_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=15
        )
        technique = TechniqueFactory()  # no function_tags at all
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 0)

    def test_two_matching_tags_compound(self):
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        role = self._engage_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.DAMAGE_BUFF_SELF, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        TechniqueFunctionTagFactory(
            technique=technique, function=TechniqueFunction.DAMAGE_BUFF_SELF
        )
        # 10*10/10 (WEAKEN) + 10*10/10 (DAMAGE_BUFF_SELF) = 10 + 10 = 20
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 20)

    def test_two_engaged_roles_sum(self):
        """Two SEPARATELY engaged CovenantRole memberships (different covenants) each
        contribute their own matching specialty row — the ``Σ over engaged_roles`` outer
        loop in ``covenant_role_specialty_power_term`` must sum across roles, not just
        within one role's row set (#2443 spec's Testing section: "multi-row + multi-role
        sums")."""
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        role_a = self._engage_role()
        role_b = self._engage_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role_a, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role_b, function=TechniqueFunction.WEAKEN, multiplier_tenths=15
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        # role_a: 10*10/10=10, role_b: 10*15/10=15 -> 10 + 15 = 25
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 25)

    def test_sub_role_row_adds_to_anchor_row(self):
        """A qualifying COVENANT_ROLE thread promotes the engaged role to its sub-role
        (per ``currently_engaged_roles``'s resolution — the membership row stays on the
        parent). The specialty term must then sum BOTH the parent's row and the
        resolved sub-role's own row, not replace one with the other (#2443 spec §3)."""
        from world.covenants.factories import (
            CovenantRoleFactory,
            SubroleCovenantRoleFactory,
        )
        from world.magic.constants import TargetKind
        from world.magic.factories import (
            ResonanceFactory,
            TechniqueFactory,
            TechniqueFunctionTagFactory,
            ThreadFactory,
        )
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        resonance = ResonanceFactory()
        parent = CovenantRoleFactory(sword_weight=0, shield_weight=0, crown_weight=1)
        sub_role = SubroleCovenantRoleFactory(
            parent_role=parent, resonance=resonance, unlock_thread_level=3
        )
        self._engage_role(role=parent)  # membership row stays on the parent
        ThreadFactory(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent,
            target_trait=None,
            level=10,
        )
        self.character.threads.invalidate()
        self.character.covenant_roles.invalidate()

        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=parent, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=sub_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=5
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        # anchor row (parent, 10*10/10=10) + sub-role's own row (10*5/10=5) = 15
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 15)

    def test_non_engaged_role_returns_zero(self):
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        role = self._engage_role(engaged=False)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=15
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 0)

    def test_retired_threads_excluded(self):
        from django.utils import timezone

        from world.magic.factories import (
            TechniqueFactory,
            TechniqueFunctionTagFactory,
            ThreadFactory,
        )
        from world.magic.services.power_terms import covenant_role_specialty_power_term

        self._thread(level=10)
        ThreadFactory(owner=self.sheet, level=100, retired_at=timezone.now())  # ignored
        role = self._engage_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        # Only the level-10 thread counts: 10*10/10 = 10, not (110)*10/10 = 110.
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 10)

    def test_specialty_at_default_multiplier_not_more_than_blend_at_weight_one(self):
        """Ratified 0.5-1.0x-of-baseline frame: specialty <= blend for the same character
        when blend weight is 1.0 and specialty uses the default 1.0x multiplier (#2443)."""
        from world.covenants.factories import CovenantRoleFactory
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
        from world.magic.services.power_terms import (
            covenant_role_blend_power_term,
            covenant_role_specialty_power_term,
        )

        self._thread(level=10)
        role = CovenantRoleFactory(sword_weight=1, shield_weight=0, crown_weight=0)
        self._engage_role(role=role)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory(archetype_alignment="sword")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)

        blend = covenant_role_blend_power_term(self._ctx(technique))
        specialty = covenant_role_specialty_power_term(self._ctx(technique))
        self.assertLessEqual(specialty, blend)


class TotalThreadLevelAcrossAllKindsTests(TestCase):
    """total_thread_level_across_all_kinds sums raw levels across thread kinds (#2529)."""

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_sums_across_thread_kinds_and_ignores_retired(self):
        from django.utils import timezone

        from world.magic.factories import ThreadFactory
        from world.magic.services.threads import total_thread_level_across_all_kinds

        ThreadFactory(owner=self.sheet, level=4)  # TRAIT (default kind)
        ThreadFactory(owner=self.sheet, level=6, as_technique_thread=True)
        ThreadFactory(owner=self.sheet, level=100, retired_at=timezone.now())  # ignored
        self.assertEqual(total_thread_level_across_all_kinds(self.sheet), 10)

    def test_empty_returns_zero(self):
        from world.magic.services.threads import total_thread_level_across_all_kinds

        self.assertEqual(total_thread_level_across_all_kinds(self.sheet), 0)


class VowSituationalPowerTermTests(TestCase):
    """vow_situational_power_term: per-vow situational-perk POWER_BONUS (#2536, Task 4).

    Built in ``setUp`` rather than ``setUpTestData`` — factories here create
    Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same
    rationale as ``test_perk_resolution.py``/``test_perk_evaluators.py``.
    """

    def setUp(self):
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique=None, situation_ctx=None, target_sheet=None):
        from world.magic.services.power_terms import PowerTermContext

        return PowerTermContext(
            sheet=self.sheet,
            technique=technique,
            applicable_threads=[],
            situation_ctx=situation_ctx,
            target_sheet=target_sheet,
        )

    def _thread(self, level):
        from world.magic.factories import ThreadFactory

        return ThreadFactory(owner=self.sheet, level=level)

    def _engage_role(self, *, sheet=None, engaged=True, covenant=None, role=None):
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        role = role or CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet or self.sheet,
            covenant=covenant or CovenantFactory(),
            covenant_role=role,
            engaged=engaged,
        )
        return role

    def _combat_room_with_positions(self):
        from evennia import create_object

        from world.areas.positioning.services import connect_positions, create_position

        room = create_object("typeclasses.rooms.Room", key="VowPerkCombatRoom", nohome=True)
        pos_a = create_position(room, "pos_a")
        pos_b = create_position(room, "pos_b")
        connect_positions(pos_a, pos_b, is_passable=True)
        return room, pos_a, pos_b

    def test_no_technique_returns_zero(self):
        from world.magic.services.power_terms import vow_situational_power_term

        self._thread(level=10)
        self._engage_role()
        self.assertEqual(vow_situational_power_term(self._ctx(None)), 0)

    def test_no_engaged_roles_returns_zero(self):
        from world.magic.services.power_terms import vow_situational_power_term

        self._thread(level=10)
        technique = TechniqueFactory()
        self.assertEqual(vow_situational_power_term(self._ctx(technique)), 0)

    def test_perk_fires_with_combat_situation_ctx_exact_arithmetic(self):
        """AT_RANGE (a combat-positioning situation) holds; the fired perk's
        magnitude scales by the subject's total thread level, int-truncated —
        7 * 13 / 10 = 9.1 -> 9 (mirrors covenant_role_specialty_power_term's
        truncation style)."""
        from world.areas.positioning.services import place_in_position
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            EngagementLockFactory,
        )
        from world.combat.models import CombatEncounter
        from world.combat.round_context import CombatRoundContext
        from world.covenants.factories import (
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.services.power_terms import vow_situational_power_term
        from world.scenes.factories import SceneFactory

        room, pos_a, pos_b = self._combat_room_with_positions()
        self.character.location = room
        self.character.save()
        place_in_position(self.character, pos_a)

        scene = SceneFactory(location=room)
        encounter = CombatEncounter.objects.create(scene=scene, room=room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

        opponent = CombatOpponentFactory(encounter=encounter)
        place_in_position(opponent.objectdb, pos_b)  # not adjacent -> AT_RANGE
        EngagementLockFactory(encounter=encounter, participant=participant, opponent=opponent)

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=13,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)

        self._thread(level=7)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, situation_ctx=CombatRoundContext(participant))
        self.assertEqual(vow_situational_power_term(ctx), 9)

    def test_situations_unmet_returns_zero(self):
        """Same perk as above, but the opponent shares the subject's position
        (IN_MELEE, not AT_RANGE) -> the perk's base situation never holds."""
        from world.areas.positioning.services import place_in_position
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            EngagementLockFactory,
        )
        from world.combat.models import CombatEncounter
        from world.combat.round_context import CombatRoundContext
        from world.covenants.factories import (
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.services.power_terms import vow_situational_power_term
        from world.scenes.factories import SceneFactory

        room, pos_a, _pos_b = self._combat_room_with_positions()
        self.character.location = room
        self.character.save()
        place_in_position(self.character, pos_a)

        scene = SceneFactory(location=room)
        encounter = CombatEncounter.objects.create(scene=scene, room=room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

        opponent = CombatOpponentFactory(encounter=encounter)
        place_in_position(opponent.objectdb, pos_a)  # adjacent -> IN_MELEE, not AT_RANGE
        EngagementLockFactory(encounter=encounter, participant=participant, opponent=opponent)

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=13,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)

        self._thread(level=7)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, situation_ctx=CombatRoundContext(participant))
        self.assertEqual(vow_situational_power_term(ctx), 0)

    def test_non_combat_cast_with_db_state_situation_still_fires(self):
        """DURING_NEGOTIATION is a DB-state situation (an active Scene, no combat
        resolution) -> fires even with ``situation_ctx=None``."""
        from evennia import create_object

        from world.covenants.factories import (
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.services.power_terms import vow_situational_power_term
        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="VowPerkNegotiationRoom", nohome=True)
        self.character.location = room
        self.character.save()
        SceneFactory(location=room)

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.DURING_NEGOTIATION)

        self._thread(level=5)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, situation_ctx=None)
        # 5 * 20 / 10 = 10
        self.assertEqual(vow_situational_power_term(ctx), 10)

    def test_ally_beneficiary_perk_boosts_subject_cast(self):
        """A COVENANT_ALLIES perk held by a co-present covenant-mate in
        the same encounter, fires on the SUBJECT's cast (scaled by the SUBJECT's
        own thread level, not the mate's)."""
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.combat.round_context import CombatRoundContext
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            VowSituationalPerkFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
        from world.magic.services.power_terms import vow_situational_power_term

        covenant = CovenantFactory()
        mate_role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        subject_role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        mate_sheet = CharacterSheetFactory()

        encounter = CombatEncounterFactory()
        subject_participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=mate_sheet)

        # Subject needs SOME engaged role (in this covenant) before an ally's
        # perk can reach them at all — see applicable_perks' _ally_candidates.
        self._engage_role(sheet=self.sheet, covenant=covenant, role=subject_role)
        CharacterCovenantRoleFactory(
            character_sheet=mate_sheet, covenant=covenant, covenant_role=mate_role, engaged=True
        )

        VowSituationalPerkFactory(
            covenant_role=mate_role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=10,
        )

        self._thread(level=6)  # subject's own thread level, not the mate's
        technique = TechniqueFactory()
        ctx = self._ctx(technique, situation_ctx=CombatRoundContext(subject_participant))
        # 6 * 10 / 10 = 6 -- proves the mate's COVENANT_ALLIES perk fired for the subject
        self.assertEqual(vow_situational_power_term(ctx), 6)

    def _favorably_disposed_setup(self, *, disposed: bool):
        """Shared rig for the two target-keyed tests below: a TARGET_FAVORABLY_DISPOSED
        perk on the subject's engaged role, plus (when ``disposed``) an NPCStanding row
        recording the target's affection toward the subject at/above the perk's
        threshold. Returns the target CharacterSheet."""
        from world.covenants.factories import (
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.npc_services.factories import NPCStandingFactory

        target_sheet = CharacterSheetFactory()

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=14,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_FAVORABLY_DISPOSED)

        if disposed:
            NPCStandingFactory(
                persona=self.sheet.primary_persona,
                npc_persona=target_sheet.primary_persona,
                affection=1,
            )

        return target_sheet

    def test_target_keyed_perk_fires_when_target_threaded(self):
        """TARGET_FAVORABLY_DISPOSED (a target-keyed situation) fires for POWER_BONUS
        once ``target_sheet`` is threaded onto the context (#2536, Task 4 review
        fix — previously hard-inert with ``target=None`` always passed to
        ``applicable_perks``). 5 * 14 / 10 = 7.0 -> 7."""
        from world.magic.services.power_terms import vow_situational_power_term

        target_sheet = self._favorably_disposed_setup(disposed=True)
        self._thread(level=5)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, target_sheet=target_sheet)
        self.assertEqual(vow_situational_power_term(ctx), 7)

    def test_target_keyed_perk_returns_zero_without_target(self):
        """Same TARGET_FAVORABLY_DISPOSED perk + the disposition row that would make
        it fire, but no ``target_sheet`` threaded onto the context (the non-combat
        cast shape) -> the situation evaluates False (per ``SituationContext``'s
        "missing field -> False" convention), not an exception, and the perk
        contributes 0."""
        from world.magic.services.power_terms import vow_situational_power_term

        self._favorably_disposed_setup(disposed=True)
        self._thread(level=5)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, target_sheet=None)
        self.assertEqual(vow_situational_power_term(ctx), 0)

    def test_fired_perk_announced_exactly_once(self):
        """Wiring + no-double-announce proof (#2536 Task 6): calling
        ``vow_situational_power_term`` ONCE for a resolution where one perk
        fires calls ``announce_fired_perks`` exactly once, with exactly that
        one firing — ``_derive_power``'s single call to this provider (per its
        own docstring) is why the announce call site inside this provider
        cannot double-announce."""
        from unittest.mock import patch

        from world.areas.positioning.services import place_in_position
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            EngagementLockFactory,
        )
        from world.combat.models import CombatEncounter
        from world.combat.round_context import CombatRoundContext
        from world.covenants.factories import (
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.services.power_terms import vow_situational_power_term
        from world.scenes.factories import SceneFactory

        room, pos_a, pos_b = self._combat_room_with_positions()
        self.character.location = room
        self.character.save()
        place_in_position(self.character, pos_a)

        scene = SceneFactory(location=room)
        encounter = CombatEncounter.objects.create(scene=scene, room=room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

        opponent = CombatOpponentFactory(encounter=encounter)
        place_in_position(opponent.objectdb, pos_b)  # not adjacent -> AT_RANGE
        EngagementLockFactory(encounter=encounter, participant=participant, opponent=opponent)

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=13,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)

        self._thread(level=7)
        technique = TechniqueFactory()
        ctx = self._ctx(technique, situation_ctx=CombatRoundContext(participant))

        with patch("world.covenants.perks.services.announce_fired_perks") as mock_announce:
            self.assertEqual(vow_situational_power_term(ctx), 9)

        assert mock_announce.call_count == 1
        (fired_arg,), kwargs = mock_announce.call_args
        assert len(fired_arg) == 1
        assert fired_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet
        assert kwargs["location"] == room
