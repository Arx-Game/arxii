"""The canonical affinities as the game finds them: seeded fresh, or renamed by mistake (#4681).

Two things the aura rework depends on that no per-app test shows end to end:

* On a database seeded the way the Big Button seeds it, a Fall converts a character's
  resonance and a cast of Abyssal resonance accrues corruption. Both read values the seed
  writes (the six conversion pairs, the three corruption coefficients).
* Renaming a canonical affinity row (Celestial, Primal, Abyssal) is not survivable: the
  getters raise once the cached rows are gone, which is what a process restart does.
"""

from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.constants import GainSource
from world.magic.exceptions import AffinityNotConfigured
from world.magic.factories import (
    CharacterAuraFactory,
    ResonanceFactory,
    TechniqueFactory,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    CharacterResonance,
    FallRedemptionRecord,
    ResonanceConversion,
)
from world.magic.services.aura import starting_aura_shares
from world.magic.services.corruption import accrue_corruption_for_cast
from world.magic.services.fall_redemption import perform_fall
from world.magic.services.resonance import grant_resonance
from world.magic.types.techniques import AnimaCostResult, ResonanceInvolvement, TechniqueUseResult
from world.seeds.game_content.magic import _seed_affinity_interactions, seed_canonical_affinities


@override_settings(SEED_SAMPLE_CONTENT=True)
class FallAndCorruptionOnAFreshlySeededDatabase(TestCase):
    """Nothing is made by a factory except the character and her resonances."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        seed_canonical_affinities()
        _seed_affinity_interactions()
        self.celestial = Affinity.objects.get(name="Celestial")
        self.primal = Affinity.objects.get(name="Primal")
        self.abyssal = Affinity.objects.get(name="Abyssal")

    def test_a_fall_converts_her_resonance_by_the_seeded_pair(self) -> None:
        bene = ResonanceFactory(name="Bene", affinity=self.celestial)
        praedari = ResonanceFactory(name="Praedari", affinity=self.primal)
        ResonanceConversion.objects.create(
            source_resonance=bene, target_affinity=self.primal, target_resonance=praedari
        )
        sheet = CharacterSheetFactory()
        set_aura_split(
            CharacterAuraFactory(character=sheet), celestial="50", primal="45", abyssal="5"
        )
        grant_resonance(sheet, bene, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(sheet, praedari, 100, source=GainSource.STAFF_GRANT)

        result = perform_fall(sheet, target_affinity=self.primal)

        # The seeded Celestial -> Primal pair converts at 1.20.
        record = FallRedemptionRecord.objects.get(character_sheet=sheet)
        self.assertEqual(str(record.multiplier), "1.20")
        self.assertEqual(record.conversion_type, "FALL")
        self.assertEqual(
            CharacterResonance.objects.get(character_sheet=sheet, resonance=praedari).balance,
            220,
        )
        self.assertEqual(result.conversion_type, "FALL")

    def test_casting_abyssal_resonance_accrues_corruption(self) -> None:
        resonance = ResonanceFactory(name="Hollow", affinity=self.abyssal)
        template = ConditionTemplateFactory(
            name="Corruption (Hollow)", has_progression=True, corruption_resonance=resonance
        )
        for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
            ConditionStageFactory(
                condition=template, stage_order=order, severity_threshold=threshold
            )
        use = TechniqueUseResult(
            anima_cost=AnimaCostResult(
                base_cost=2, effective_cost=2, control_delta=0, current_anima=10, deficit=0
            ),
            technique=TechniqueFactory(level=1),
            was_deficit=False,
            was_mishap=False,
            was_audere=False,
            resonance_involvements=(
                ResonanceInvolvement(
                    resonance=resonance, stat_bonus_contribution=5, thread_pull_resonance_spent=0
                ),
            ),
        )

        summary = accrue_corruption_for_cast(
            caster_sheet=CharacterSheetFactory(), technique_use_result=use
        )

        # Seeded Abyssal coefficient 10 (tenths) x tier 1 coefficient 10 (tenths) x 5 = 5.
        self.assertEqual(len(summary.per_resonance), 1)
        self.assertEqual(summary.per_resonance[0].amount_applied, 5)


class RenamingACanonicalAffinity(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        with override_settings(SEED_SAMPLE_CONTENT=True):
            seed_canonical_affinities()
        self.addCleanup(Affinity.objects.clear_cache)

    def test_after_a_restart_the_getter_and_the_starting_aura_raise(self) -> None:
        self.assertEqual(Affinity.objects.get_primal_affinity().name, "Primal")

        primal = Affinity.objects.get(name="Primal")
        primal.name = "Wild"
        primal.save()
        Affinity.objects.clear_cache()  # a process restart drops the cached rows

        with self.assertRaises(AffinityNotConfigured) as getter:
            Affinity.objects.get_primal_affinity()
        with self.assertRaises(AffinityNotConfigured) as starting:
            starting_aura_shares(None)  # what character creation calls for a fresh aura
        for raised in (getter.exception, starting.exception):
            self.assertEqual(str(raised), "No Affinity row named 'Primal' is configured.")
