"""Tests for power-scoped modifiers and power-term providers feeding _derive_power (#634, #637)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
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
            pk=1, affinity_alignment_bonus=10, resonance_standing_bonus=2, resonance_standing_cap=50
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
