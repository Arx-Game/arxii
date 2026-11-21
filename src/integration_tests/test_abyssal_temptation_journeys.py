"""The Abyssal temptation: reaching for a kindled Abyssal resonance pays and warns (#5231).

Ysmay is mostly Primal (80 Primal, 20 Abyssal; her resonances' lifetime earnings are 80 and 20,
so any earning keeps her aura under 50 percent Abyssal). Her Gift's thread holds a Primal
resonance, Warmth, which leads, and an Abyssal one, Praedari. Her own feeling kindles Praedari
at the "Blazing" strength (the third strength row). She casts a benign technique on herself
through the web cast endpoint, naming the resonance to work it in. Numbers this journey sets:

* Blazing: cast power 6, earn percent 100. Abyssal: kindled boost 150, earn rate 150, corruption
  coefficient 10. Primal: kindled boost 100, earn rate 100, corruption coefficient 0.
* A Success earns a kindled deed 10. The kindling config pays all of it at once
  (instant percent 100) and sets half aside to claim.
* Corruption config: tier 1 coefficient 10, light part 10 percent below an Abyssal share of 50.
  The technique is tier 1 with intensity 20, and a cast worked in a resonance puts its whole
  intensity on that resonance.

Hand-worked from the spec:

* Power: a kindled cast adds cast power times the affinity's boost percent, divided by 100,
  rounded down: 6 * 150 // 100 = 9. Worked in Praedari the ledger has a "kindled cast power"
  line of 9. Worked in Warmth, which is not kindled, it has none, and its total is exactly 9
  lower.
* Earning: the deed is decided by the deed, not by the resonance the cast was worked in
  (ruling 12), so both casts earn the kindled Praedari: 10 * 100 // 100 = 10, then Abyssal's
  rate 10 * 150 // 100 = 15. The Primal resonance earns nothing, as no situation of hers
  is fed. At Primal's rate of 100 the same deed would have been 10.
* Corruption: ordinary tick 20 * (10 / 10) * (10 / 10) = 20 on Praedari (Abyssal, tier 1). She
  is 20 percent Abyssal, under 50, so she takes the light 10 percent: 20 * 10 / 100 = 2,
  rounded up once to 2. Worked in Warmth (coefficient 0) the cast adds no corruption.
* A cast that pulls a thread gets the pull and not the kindled boost.
"""

from __future__ import annotations

from actions.factories import ActionTemplateFactory
from commands import pending_actions
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import PathFactory
from world.combat.constants import ActionCategory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.constants import EffectKind, GainSource, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    KindlingConfigFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
    ensure_conversion_pairs,
    kindle_resonance,
)
from world.magic.models import (
    Affinity,
    CharacterResonance,
    KindledDeedAward,
    KindledStrengthTier,
    ResonanceGrant,
)
from world.magic.services.corruption import get_corruption_config
from world.magic.services.threads import weave_thread
from world.magic.specialization.services import provision_latent_gift_thread
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.factories import SceneFactory
from world.skills.factories import SkillFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CharacterTraitValue, CheckOutcome, PointConversionRange, TraitType
from world.vitals.models import CharacterVitals

CAST_URL = "/api/action-requests/cast/"
KINDLED_LINE = "kindled cast power"


class TheAbyssalTemptation(JourneyCase):
    """Ysmay casts in Warmth, in Praedari, and in Praedari with a pulled thread."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        _celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        self.set_the_affinity_numbers()
        Affinity.objects.clear_cache()
        self.warmth = ResonanceFactory(name="Warmth", affinity=self.primal)
        self.praedari = ResonanceFactory(name="Praedari", affinity=self.abyssal)
        self.skill = SkillFactory()
        self.path = PathFactory(style=TechniqueStyleFactory(skill=self.skill))
        self.room = self.make_room("The Lantern")
        self.scene = SceneFactory(room=self.room)

        cast_check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=cast_check, trait=StatTraitFactory(), weight=1)
        self.gift = GiftFactory()
        self.technique = TechniqueFactory(
            gift=self.gift,
            intensity=20,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=cast_check),
        )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.praedari,
            tier=1,
            flat_bonus_amount=2,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        blazing = KindledStrengthTier.objects.get(rank=3)
        blazing.cast_power = 6
        blazing.earn_percent = 100
        blazing.save()
        success = CheckOutcome.objects.get(name="Success")
        KindledDeedAward.objects.update_or_create(outcome_tier=success, defaults={"amount": 10})
        KindlingConfigFactory(instant_percent=100, claim_percent=50)
        self.assertEqual(self.technique.tier, 1)
        self.make_the_corruption_condition()

        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.skill, value=10)
        CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.warmth, balance=10, lifetime_earned=80
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.praedari, balance=10, lifetime_earned=20
        )
        # Warmth is listed first, so it leads the Gift's thread.
        provision_latent_gift_thread(self.sheet, self.gift, resonances=[self.warmth, self.praedari])
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=self.skill)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)
        self.ysmay.weaving_unlocks.invalidate()
        self.strand = weave_thread(
            self.sheet, TargetKind.TRAIT, self.skill, self.praedari, name="Praedari Strand"
        )
        # Her own feeling kindles Praedari at Blazing, through a real own-feeling situation
        # that any act she makes while bearing it feeds.
        kindle_resonance(self.sheet, self.praedari, blazing)
        # The scene's anti-spam memory is process-wide and keyed by sheet pk.
        pending_actions._LAST_ACTED.clear()
        self.addCleanup(pending_actions._LAST_ACTED.clear)

    def set_the_affinity_numbers(self) -> None:
        for affinity, boost, rate, coefficient in (
            (self.primal, 100, 100, 0),
            (self.abyssal, 150, 150, 10),
        ):
            affinity.kindled_boost_percent = boost
            affinity.earn_rate_percent = rate
            affinity.corruption_coefficient = coefficient
            affinity.save()
        Affinity.objects.clear_cache()
        corruption = get_corruption_config()
        corruption.tier_1_coefficient = 10
        corruption.light_corruption_percent = 10
        corruption.full_corruption_from_share = 50
        corruption.save()

    def make_the_corruption_condition(self) -> None:
        """The condition Praedari's corruption lives in, as the accrual service finds it."""
        template = ConditionTemplateFactory(
            name="Corruption (Praedari)", has_progression=True, corruption_resonance=self.praedari
        )
        for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
            ConditionStageFactory(
                condition=template, stage_order=order, severity_threshold=threshold
            )

    def cast(self, resonance, **body) -> dict:
        """Cast the technique on herself worked in ``resonance``; the response's result."""
        pending_actions._LAST_ACTED.clear()
        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.api(self.account_of(self.ysmay)).post(
                CAST_URL,
                {
                    "scene": self.scene.pk,
                    "initiator_persona": self.sheet.primary_persona.pk,
                    "technique_id": self.technique.pk,
                    "preferred_resonance_id": resonance.pk,
                    **body,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()["result"]["power_ledger"]

    def corruption(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).corruption_current

    def earned(self, resonance) -> int:
        """What kindled deeds have earned her in ``resonance`` so far, as the ledger holds it."""
        return sum(
            ResonanceGrant.objects.filter(
                character_sheet=self.sheet, resonance=resonance, source=GainSource.KINDLED_DEED
            ).values_list("amount", flat=True)
        )

    @staticmethod
    def line(ledger: dict, label: str) -> int:
        """The amount of the ledger's line called ``label``; 0 when it has none."""
        return sum(entry["amount"] for entry in ledger["entries"] if entry["source_label"] == label)

    def test_reaching_for_her_kindled_abyssal_resonance_is_stronger_earns_fast_and_warns(
        self,
    ) -> None:
        praedari_before = self.corruption(self.praedari)
        warmth_corruption_before = self.corruption(self.warmth)

        abyssal_cast = self.cast(self.praedari)

        # Stronger: the kindled line is 6 * 150 // 100 = 9.
        self.assertEqual(self.line(abyssal_cast, KINDLED_LINE), 9)
        # Earns at Abyssal's rate: the deed's 10 * 100 // 100 = 10, times 150 percent = 15.
        self.assertEqual(self.earned(self.praedari), 15)
        # Warns, lightly: ceil(20 * 10 / 100) = 2.
        self.assertEqual(self.corruption(self.praedari) - praedari_before, 2)

        earned_before = self.earned(self.praedari)
        praedari_before = self.corruption(self.praedari)

        primal_cast = self.cast(self.warmth)

        # No kindled line, and a total exactly the 9 lower.
        self.assertEqual(self.line(primal_cast, KINDLED_LINE), 0)
        self.assertEqual(abyssal_cast["total"] - primal_cast["total"], 9)
        # No corruption on either resonance from a cast worked in Primal.
        self.assertEqual(self.corruption(self.praedari), praedari_before)
        self.assertEqual(self.corruption(self.warmth), warmth_corruption_before)
        # The deed decides what is earned, not the resonance the cast was worked in: the same
        # kindled Praedari earns the same 15 again, and the Primal resonance earns nothing.
        self.assertEqual(self.earned(self.praedari) - earned_before, 15)
        self.assertEqual(self.earned(self.warmth), 0)

    def test_a_kindled_cast_that_pulls_a_thread_gains_no_cast_bonus(self) -> None:
        ledger = self.cast(
            self.praedari,
            pull={
                "resonance_id": self.praedari.pk,
                "tier": 1,
                "thread_ids": [self.strand.pk],
            },
        )

        self.assertEqual(self.line(ledger, KINDLED_LINE), 0)
        # The pull did land: the thread's own line is on the ledger.
        self.assertGreater(self.line(ledger, "thread power"), 0)
