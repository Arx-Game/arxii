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
* A cast that pulls a thread gets the pull and not the kindled boost. The pulled thread is
  woven on the technique at level 10 (one rung, so a multiplier of 1) with a tier 1 intensity
  bump of 3: the ledger's "thread power" line is 3, the pull costs 1 Praedari, and the same
  cast's deed then earns 15: 10 - 1 + 15 = 24.
* In a fight a pull lasts the round but boosts only the casts its threads relate to. A cast
  with no pull in its round gets the kindled line (9). A cast whose round holds a pull on a
  thread of its own technique gets the pull's 3 and no kindled line. A cast whose round
  holds only a pull on a thread of another technique (it rode that technique's clash
  contribution) takes nothing from that pull, so it keeps the kindled line (9).
"""

from __future__ import annotations

from actions.factories import ActionTemplateFactory
from commands import pending_actions
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, ClashActionSlot, ClashStatus, OpponentTier
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatPull, CombatRoundAction
from world.combat.services import resolve_round
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.fatigue.constants import EffortLevel
from world.magic.constants import EffectKind, GainSource, PowerStage, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    KindlingConfigFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
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
from world.magic.specialization.services import provision_latent_gift_thread
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome, PointConversionRange, TraitType
from world.traits.services import ensure_canonical_check_outcome
from world.vitals.models import CharacterVitals

CAST_URL = "/api/action-requests/cast/"
KINDLED_LINE = "kindled cast power"


def _corruption_condition(resonance) -> None:
    """The condition a resonance's corruption lives in, as the accrual service finds it."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})", has_progression=True, corruption_resonance=resonance
    )
    for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
        ConditionStageFactory(condition=template, stage_order=order, severity_threshold=threshold)


def _author_the_pull(resonance) -> None:
    """A tier 1 pull costs 1 resonance and, on a thread of ``resonance``, adds 2 to the roll
    (a flat bonus) and 3 to the power (an intensity bump), at the multiplier of one rung."""
    ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
    ThreadPullEffectFactory(
        target_kind=TargetKind.TECHNIQUE,
        resonance=resonance,
        tier=1,
        min_thread_level=0,
        effect_kind=EffectKind.FLAT_BONUS,
        flat_bonus_amount=2,
    )
    ThreadPullEffectFactory(
        target_kind=TargetKind.TECHNIQUE,
        resonance=resonance,
        tier=1,
        min_thread_level=0,
        as_intensity_bump=True,
        intensity_bump_amount=3,
    )


def _thread_on(sheet, resonance, technique, name: str):
    """A thread woven on ``technique``; level 10 is stored x10, so it reads as one rung."""
    return ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_trait=None,
        target_technique=technique,
        level=10,
        name=name,
    )


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
        _author_the_pull(self.praedari)
        blazing = KindledStrengthTier.objects.get(rank=3)
        blazing.cast_power = 6
        blazing.earn_percent = 100
        blazing.save()
        success = CheckOutcome.objects.get(name="Success")
        KindledDeedAward.objects.update_or_create(outcome_tier=success, defaults={"amount": 10})
        KindlingConfigFactory(instant_percent=100, claim_percent=50)
        self.assertEqual(self.technique.tier, 1)
        _corruption_condition(self.praedari)

        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.warmth, balance=10, lifetime_earned=80
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.praedari, balance=10, lifetime_earned=20
        )
        # Warmth is listed first, so it leads the Gift's thread.
        provision_latent_gift_thread(self.sheet, self.gift, resonances=[self.warmth, self.praedari])
        self.strand = _thread_on(self.sheet, self.praedari, self.technique, "Praedari Strand")
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
        balance_before = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.praedari
        ).balance

        ledger = self.cast(
            self.praedari,
            pull={
                "tier": 1,
                "thread_ids": [self.strand.pk],
                "payers": {str(self.strand.pk): self.praedari.pk},
            },
        )

        self.assertEqual(self.line(ledger, KINDLED_LINE), 0)
        # The pull did land: its intensity bump of 3 is the ledger's "thread power" line, and
        # the paying resonance fell by the pull's cost of 1 before the deed's 15 arrived.
        self.assertEqual(self.line(ledger, "thread power"), 3)
        balance = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.praedari
        ).balance
        self.assertEqual(balance - balance_before, -1 + 15)


class TheAbyssalTemptationInAFight(JourneyCase):
    """Ysmay declares Shadow Step in a round, worked in her kindled Praedari."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        for name in CANONICAL_OUTCOME_LEVELS:  # a clash round grades its result on these
            ensure_canonical_check_outcome(name)
        ClashConfigFactory()
        _celestial, primal, abyssal = ensure_conversion_pairs()
        abyssal.kindled_boost_percent = 150
        abyssal.save()
        Affinity.objects.clear_cache()
        self.warmth = ResonanceFactory(name="Warmth", affinity=primal)
        self.praedari = ResonanceFactory(name="Praedari", affinity=abyssal)
        _corruption_condition(self.praedari)
        blazing = KindledStrengthTier.objects.get(rank=3)
        blazing.cast_power = 6
        blazing.save()

        room = self.make_room("The Ashen Court")
        SceneFactory(room=room)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=room
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        self.ysmay = self.make_player("Ysmay", room=room)
        self.sheet = self.ysmay.sheet_data
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        CharacterEngagementFactory(character=self.sheet)
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")

        gift = GiftFactory()
        self.shadow_step = self.technique("Shadow Step", gift)
        self.ember_lash = self.technique("Ember Lash", GiftFactory())
        for technique in (self.shadow_step, self.ember_lash):
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.warmth, balance=10, lifetime_earned=80
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.praedari, balance=10, lifetime_earned=20
        )
        provision_latent_gift_thread(self.sheet, gift, resonances=[self.warmth, self.praedari])
        _author_the_pull(self.praedari)
        self.shadow_thread = _thread_on(self.sheet, self.praedari, self.shadow_step, "Shadow")
        self.ember_thread = _thread_on(self.sheet, self.praedari, self.ember_lash, "Ember")
        kindle_resonance(self.sheet, self.praedari, blazing)

    @staticmethod
    def technique(name: str, gift):
        """A clash-capable technique rolled on its own check, one stat of its own."""
        check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check, trait=StatTraitFactory(), weight=1)
        return TechniqueFactory(
            name=name,
            gift=gift,
            intensity=10,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check),
            clash_capable=True,
        )

    def dispatch(self, ref: dict, kwargs: dict) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api(self.account_of(self.ysmay)).post(
                f"/api/actions/characters/{self.ysmay.pk}/dispatch/",
                {"ref": ref, "kwargs": kwargs},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)

    @staticmethod
    def pull_of(thread) -> dict:
        return {
            "pull_resonance_id": thread.resonance_id,
            "pull_tier": 1,
            "pull_thread_ids": [thread.pk],
        }

    def declare_shadow_step_in_praedari(self, **pull) -> None:
        self.dispatch(
            {"backend": "combat", "technique_id": self.shadow_step.pk, "action_slot": "focused"},
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.opponent.pk,
                "confirm_soulfray_risk": True,
                "preferred_resonance_id": self.praedari.pk,
                **pull,
            },
        )

    def put_a_pull_on_an_ember_lash_clash(self) -> None:
        """The pull rides her Ember Lash clash contribution, as the client sends it."""
        clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )
        self.dispatch(
            {
                "backend": "combat",
                "clash_id": clash.pk,
                "clash_action_slot": ClashActionSlot.FOCUSED,
            },
            {
                "technique_id": self.ember_lash.pk,
                "strain_commitment": 0,
                **self.pull_of(self.ember_thread),
            },
        )

    def resolve_and_read_the_cast(self) -> list[dict]:
        """Resolve the round; the power ledger the combat log shows for her Shadow Step."""
        resolve_round(self.encounter)
        action = CombatRoundAction.objects.get(participant__character_sheet=self.sheet)
        self.assertIsNotNone(action.interaction_id, "Her action left no log entry.")
        response = self.api(self.account_of(self.ysmay)).get(
            "/api/combat/action-outcome-details/",
            {"action_interaction_ids": str(action.interaction_id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data[0]["power_ledger"]["entries"]

    @staticmethod
    def line(entries: list[dict], label: str) -> int:
        return sum(row["amount"] for row in entries if row["source_label"] == label)

    @staticmethod
    def pull_lines(entries: list[dict]) -> list[int]:
        return [row["amount"] for row in entries if row["stage"] == PowerStage.COMBAT_PULL]

    def test_a_cast_in_a_round_with_no_pull_reads_the_kindled_line(self) -> None:
        self.declare_shadow_step_in_praedari()

        entries = self.resolve_and_read_the_cast()

        self.assertEqual(self.line(entries, KINDLED_LINE), 9)  # 6 * 150 // 100
        self.assertEqual(self.pull_lines(entries), [])

    def test_a_pull_on_a_thread_of_the_cast_takes_the_kindled_line_for_its_own(self) -> None:
        self.declare_shadow_step_in_praedari(**self.pull_of(self.shadow_thread))
        self.assertTrue(CombatPull.objects.filter(threads=self.shadow_thread).exists())

        entries = self.resolve_and_read_the_cast()

        self.assertEqual(self.line(entries, KINDLED_LINE), 0)
        self.assertEqual(self.pull_lines(entries), [3])  # the pull's intensity bump

    def test_a_pull_on_another_techniques_thread_leaves_the_kindled_line_in_place(self) -> None:
        self.declare_shadow_step_in_praedari()
        self.put_a_pull_on_an_ember_lash_clash()
        self.assertTrue(CombatPull.objects.filter(threads=self.ember_thread).exists())

        entries = self.resolve_and_read_the_cast()

        # The round holds a pull, but none of its threads relate to Shadow Step: it gives the
        # cast nothing, so it takes nothing: 6 * 150 // 100 = 9 stays.
        self.assertEqual(self.pull_lines(entries), [])
        self.assertEqual(self.line(entries, KINDLED_LINE), 9)
