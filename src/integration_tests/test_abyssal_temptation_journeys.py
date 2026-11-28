"""The Abyssal temptation: reaching for a kindled Abyssal resonance is stronger and warns (#5231).

Ysmay is mostly Primal (80 Primal, 20 Abyssal; her resonances' lifetime earnings are 80 and 20,
so any earning keeps her aura under 50 percent Abyssal). Her Gift's thread holds a Primal
resonance, Warmth, which leads, and an Abyssal one, Praedari. Her own feeling kindles Praedari
at the "Blazing" strength (the third strength row). She casts a benign technique on herself
through the web cast endpoint, naming the resonance to work it in. Numbers this journey sets:

* Blazing: cast power 6, earn percent 100. Abyssal: kindled boost 150, earn rate 150, corruption
  coefficient 10. Primal: kindled boost 100, earn rate 100, corruption coefficient 0.
* A Success is an act worth 10 when her player marks it. A situation only suggests (#5327), so
  the cast writes the act down with a suggestion and pays nothing.
* Corruption config: tier 1 coefficient 10, light part 10 percent below an Abyssal share of 50.
  The technique is tier 1 with intensity 20, and a cast worked in a resonance puts its whole
  intensity on that resonance.

Hand-worked from the spec:

* Power: a kindled cast adds cast power times the affinity's boost percent, divided by 100,
  rounded down: 6 * 150 // 100 = 9. Worked in Praedari the ledger has a "kindled cast power"
  line of 9. Worked in Warmth, which is not kindled, it has none, and its total is exactly 9
  lower.
* Earning: the act is decided by the act, not by the resonance the cast was worked in
  (ruling 12), so both casts are written down with the kindled Praedari as their one
  suggestion, and neither pays a thing: a situation only suggests (#5327), and her player marks
  the act to be paid. The Primal resonance is not suggested, as no situation of hers is fed.
* Corruption: ordinary tick 20 * (10 / 10) * (10 / 10) = 20 on Praedari (Abyssal, tier 1). She
  is 20 percent Abyssal, under 50, so she takes the light 10 percent: 20 * 10 / 100 = 2,
  rounded up once to 2. Worked in Warmth (coefficient 0) the cast adds no corruption.
* A cast that pulls a thread gets the pull and the kindled boost, both: kindling's other
  benefits stack with a pull the same way, so the kindled cast power always applies. The
  pulled thread is woven on the technique at level 10 (one rung, so a multiplier of 1) with a
  tier 1 intensity bump of 3: the ledger's "thread power" line is 3 and its kindled line is
  still 9, and the pull costs 1 Praedari: 10 - 1 = 9, with nothing paid by the cast.
* The cast list: her Gift's thread holds Warmth (leading, so the default) and Praedari. Warmth
  is not kindled, so its strength is 0 and it has no strength word; Praedari is kindled at
  Blazing, so its strength is the 9 above. The one entry with the highest strength, above the
  default's 0, is Praedari, so it alone is "stronger". Only Praedari adds corruption (an
  Abyssal coefficient of 10; Primal's is 0). The same two entries come back in a fight.
* In a fight a pull lasts the round but boosts only the casts its threads relate to. A cast
  with no pull in its round gets the kindled line (9). A cast whose round holds a pull on a
  thread of its own technique gets the pull's 3 and the kindled line (9). A cast whose round
  holds only a pull on a thread of another technique (it rode that technique's clash
  contribution) takes nothing from that pull, so it has the kindled line (9) and no pull line.
"""

from __future__ import annotations

from django.urls import reverse

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
from world.magic.constants import EffectKind, PowerStage, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    KindledStrengthTierFactory,
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
    ResonanceGrant,
)
from world.magic.services.corruption import get_corruption_config
from world.magic.services.drift import get_drift_config
from world.magic.services.thread_rows import add_to_resonance_row, refresh_leading_resonance
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
PRAEDARI_COLOR = "#7A1F5C"


def _corruption_condition(resonance) -> None:
    """The condition a resonance's corruption lives in, as the accrual service finds it."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})", has_progression=True, corruption_resonance=resonance
    )
    for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
        ConditionStageFactory(condition=template, stage_order=order, severity_threshold=threshold)


def _author_the_pull(resonance) -> None:
    """A tier 1 pull costs 1 resonance and, on a thread of ``resonance``, adds 2 to the roll
    (a flat bonus) and 3 to the power (an intensity bump), at the multiplier of one rung.

    A pull effect is keyed on its target kind, resonance, tier and the thread level it needs, and
    only one row may hold a key, so the bump needs level 1 where the flat bonus needs none. The
    thread the journeys weave reads as level 10 and so qualifies for both."""
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
        min_thread_level=1,
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


class _AnAbyssalCasterInAScene(JourneyCase):
    """Ysmay in the Lantern, ready to cast through the web cast endpoint.

    Her own feeling kindles Praedari at Blazing unless a subclass sets ``kindle_praedari``
    false.
    """

    kindle_praedari = True
    # A technique holds one thread per owner, so a subclass that weaves its own thread on the
    # technique sets this false and the base weaves none.
    weave_strand = True

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
        self.praedari = ResonanceFactory(
            name="Praedari", affinity=self.abyssal, color_hex=PRAEDARI_COLOR
        )
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
        self.blazing = KindledStrengthTierFactory(
            rank=3, name="Blazing", cast_power=6, earn_percent=100
        )
        success = CheckOutcome.objects.get(name="Success")
        KindledDeedAward.objects.update_or_create(outcome_tier=success, defaults={"amount": 10})
        KindlingConfigFactory()
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
        if self.weave_strand:
            self.strand = _thread_on(self.sheet, self.praedari, self.technique, "Praedari Strand")
        # Her own feeling kindles Praedari at Blazing, through a real own-feeling situation
        # that any act she makes while bearing it feeds.
        if self.kindle_praedari:
            kindle_resonance(self.sheet, self.praedari, self.blazing)
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
        """What she has been paid in ``resonance`` so far, as the ledger holds it (a cast pays
        nothing, #5327)."""
        return sum(
            ResonanceGrant.objects.filter(
                character_sheet=self.sheet, resonance=resonance
            ).values_list("amount", flat=True)
        )

    def acts_listing(self) -> str:
        """What her player reads when she types ``acts``: each act and what it suggests."""
        return self.telnet(self.ysmay, "acts")

    @staticmethod
    def line(ledger: dict, label: str) -> int:
        """The amount of the ledger's line called ``label``; 0 when it has none."""
        return sum(entry["amount"] for entry in ledger["entries"] if entry["source_label"] == label)


class TheAbyssalTemptation(_AnAbyssalCasterInAScene):
    """Ysmay casts in Warmth, in Praedari, and in Praedari with a pulled thread."""

    def test_reaching_for_her_kindled_abyssal_resonance_is_stronger_and_warns_and_pays_nothing(
        self,
    ) -> None:
        praedari_before = self.corruption(self.praedari)
        warmth_corruption_before = self.corruption(self.warmth)

        abyssal_cast = self.cast(self.praedari)

        # Stronger: the kindled line is 6 * 150 // 100 = 9.
        self.assertEqual(self.line(abyssal_cast, KINDLED_LINE), 9)
        # Pays nothing: the cast is written down for her player to mark, with Praedari
        # suggested (#5327).
        self.assertEqual(self.earned(self.praedari), 0)
        listed = self.acts_listing()
        self.assertEqual(listed.count(f"{self.technique.name} on Ysmay ("), 1)
        self.assertIn("Praedari", listed)
        self.assertNotIn("Warmth", listed)
        # Warns, lightly: ceil(20 * 10 / 100) = 2.
        self.assertEqual(self.corruption(self.praedari) - praedari_before, 2)

        praedari_before = self.corruption(self.praedari)

        primal_cast = self.cast(self.warmth)

        # No kindled line, and a total exactly the 9 lower.
        self.assertEqual(self.line(primal_cast, KINDLED_LINE), 0)
        self.assertEqual(abyssal_cast["total"] - primal_cast["total"], 9)
        # No corruption on either resonance from a cast worked in Primal.
        self.assertEqual(self.corruption(self.praedari), praedari_before)
        self.assertEqual(self.corruption(self.warmth), warmth_corruption_before)
        # The act decides what is suggested, not the resonance the cast was worked in: the same
        # kindled Praedari is suggested again, and nothing is paid in Praedari or in Warmth.
        listed = self.acts_listing()
        self.assertEqual(listed.count(f"{self.technique.name} on Ysmay ("), 2)
        self.assertEqual(listed.count("Praedari"), 2)
        self.assertNotIn("Warmth", listed)
        self.assertEqual(self.earned(self.praedari), 0)
        self.assertEqual(self.earned(self.warmth), 0)

    def castable_entry(self) -> dict:
        """The technique's row in the scene's castable list, as the cast panel reads it."""
        response = self.api(self.account_of(self.ysmay)).get(
            "/api/action-requests/castable-techniques/",
            {"initiator_persona": self.sheet.primary_persona.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return next(row for row in response.json() if row["id"] == self.technique.pk)

    def test_the_cast_list_marks_the_kindled_abyssal_option_stronger_and_corrupting(self) -> None:
        options = self.castable_entry()["resonance_options"]

        # Leading resonance first: Warmth is the default, Praedari follows.
        self.assertEqual([o["name"] for o in options], ["Warmth", "Praedari"])
        warmth, praedari = options
        self.assertEqual(warmth["resonance_id"], self.warmth.pk)
        self.assertTrue(warmth["is_default"])
        self.assertIsNone(warmth["kindled_strength"])
        self.assertEqual(warmth["reasons"], [])
        self.assertFalse(warmth["stronger"])
        self.assertFalse(warmth["adds_corruption"])
        self.assertEqual(praedari["resonance_id"], self.praedari.pk)
        self.assertFalse(praedari["is_default"])
        self.assertEqual(praedari["kindled_strength"], "Blazing")
        self.assertTrue(praedari["reasons"])
        self.assertTrue(praedari["stronger"])
        self.assertTrue(praedari["adds_corruption"])
        # The colour is the staff-set one; only the strength word is sent, never a number.
        self.assertEqual(praedari["color_hex"], PRAEDARI_COLOR)
        self.assertEqual(warmth["color_hex"], "#8C8C8C")
        self.assertNotIn("kindled_cast_power", praedari)
        self.assertNotIn("cast_power", praedari)

    def test_a_kindled_cast_that_pulls_a_thread_gets_the_pull_and_the_cast_bonus(self) -> None:
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

        # Both lines are on the ledger: the pull's intensity bump of 3 is the "thread power"
        # line, and the kindled line stays 6 * 150 // 100 = 9 beside it. The paying resonance
        # fell by the pull's cost of 1, and the cast paid nothing back.
        self.assertEqual(self.line(ledger, "thread power"), 3)
        self.assertEqual(self.line(ledger, KINDLED_LINE), 9)
        balance = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.praedari
        ).balance
        self.assertEqual(balance - balance_before, -1)


class TheKindledPullInAScene(_AnAbyssalCasterInAScene):
    """A real pull in a scene, on a thread holding Warmth (Primal, leading) and Praedari.

    Numbers this journey sets: the thread is woven on the technique at level 25 and imbued 70
    Warmth and 30 Praedari, so Warmth leads and Praedari holds 30 of the 100 imbued. A thread
    level multiplier is the level divided by ten, rounded down. Warmth pays, and its perk is
    an intensity bump of 3, scaled by the multiplier. Warmth is kindled at a strength worth 10
    pull levels (Primal's boost is 100 percent), Praedari at Blazing, worth 12 (Abyssal's
    boost is 150 percent). The cast is worked in Warmth, which carries no cast power.

    Hand-worked from the spec:

    * Only Warmth kindled: its boost is 10 * 100 // 100 = 10, nothing else counts, so the
      thread reads 25 + 10 = 35, a multiplier of 3, and the ledger's "thread power" line is
      3 * 3 = 9.
    * Both kindled: Praedari's boost is 12 * 150 // 100 = 18, and 18 * 30 // 100 = 5 of it
      counts (its share of what was imbued), so the thread reads 25 + 10 + 5 = 40, a
      multiplier of 4, and the line is 3 * 4 = 12.
    """

    kindle_praedari = False
    weave_strand = False

    def setUp(self) -> None:
        super().setUp()
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.warmth,
            tier=1,
            min_thread_level=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        self.warm_tier = KindledStrengthTierFactory(rank=1, name="Faint", pull_levels=10)
        self.blazing = KindledStrengthTierFactory(
            rank=3, name="Blazing", cast_power=6, earn_percent=100, pull_levels=12
        )
        self.lantern = ThreadFactory(
            owner=self.sheet,
            resonance=self.warmth,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=25,
            name="Lantern Strand",
        )
        add_to_resonance_row(self.lantern, self.warmth, 70)
        add_to_resonance_row(self.lantern, self.praedari, 30)
        refresh_leading_resonance(self.lantern)
        self.ysmay.threads.invalidate()

    def pull_in_warmth(self) -> dict:
        """Cast in Warmth with a pull of the Lantern thread, Warmth paying; the power ledger."""
        return self.cast(
            self.warmth,
            pull={
                "tier": 1,
                "thread_ids": [self.lantern.pk],
                "payers": {str(self.lantern.pk): self.warmth.pk},
            },
        )

    def test_a_pull_with_both_resonances_kindled_adds_more_power_than_with_one(self) -> None:
        kindle_resonance(self.sheet, self.warmth, self.warm_tier)
        feeling_only = self.pull_in_warmth()

        kindle_resonance(self.sheet, self.praedari, self.blazing)
        both = self.pull_in_warmth()

        self.assertEqual(self.line(feeling_only, "thread power"), 9)
        self.assertEqual(self.line(both, "thread power"), 12)


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
        blazing = KindledStrengthTierFactory(rank=3, name="Blazing", cast_power=6)

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

    def test_the_combat_declaration_offers_the_same_options(self) -> None:
        response = self.api(self.account_of(self.ysmay)).get(
            reverse("actions:available-actions", kwargs={"character_id": self.ysmay.pk})
        )

        self.assertEqual(response.status_code, 200, response.content)
        by_technique = {
            row["ref"].get("technique_id"): row["cast_resonance_options"]
            for row in response.json()["results"]
            if row["ref"].get("technique_id") is not None
        }
        warmth, praedari = by_technique[self.shadow_step.pk]
        self.assertEqual([warmth["name"], praedari["name"]], ["Warmth", "Praedari"])
        self.assertTrue(warmth["is_default"])
        self.assertFalse(warmth["stronger"])
        self.assertFalse(warmth["adds_corruption"])
        self.assertEqual(praedari["resonance_id"], self.praedari.pk)
        self.assertEqual(praedari["kindled_strength"], "Blazing")
        self.assertTrue(praedari["reasons"])
        self.assertTrue(praedari["stronger"])
        self.assertTrue(praedari["adds_corruption"])
        # Ember Lash's Gift has no thread of hers and no listed resonance: nothing to choose.
        self.assertEqual(by_technique[self.ember_lash.pk], [])

    def test_a_cast_in_a_round_with_no_pull_reads_the_kindled_line(self) -> None:
        self.declare_shadow_step_in_praedari()

        entries = self.resolve_and_read_the_cast()

        self.assertEqual(self.line(entries, KINDLED_LINE), 9)  # 6 * 150 // 100
        self.assertEqual(self.pull_lines(entries), [])

    def test_a_pull_on_a_thread_of_the_cast_adds_its_line_beside_the_kindled_one(self) -> None:
        self.declare_shadow_step_in_praedari(**self.pull_of(self.shadow_thread))
        self.assertTrue(CombatPull.objects.filter(threads=self.shadow_thread).exists())

        entries = self.resolve_and_read_the_cast()

        # The pull's intensity bump is 3, and the kindled line is still 6 * 150 // 100 = 9.
        self.assertEqual(self.pull_lines(entries), [3])
        self.assertEqual(self.line(entries, KINDLED_LINE), 9)

    def test_a_pull_on_another_techniques_thread_leaves_the_kindled_line_in_place(self) -> None:
        self.declare_shadow_step_in_praedari()
        self.put_a_pull_on_an_ember_lash_clash()
        self.assertTrue(CombatPull.objects.filter(threads=self.ember_thread).exists())

        entries = self.resolve_and_read_the_cast()

        # The round holds a pull, but none of its threads relate to Shadow Step: it gives the
        # cast no pull line, and the kindled line is 6 * 150 // 100 = 9 as with no pull.
        self.assertEqual(self.pull_lines(entries), [])
        self.assertEqual(self.line(entries, KINDLED_LINE), 9)


PREVIEW_URL = "magic:thread-pull-preview"


class TheKindledPull(JourneyCase):
    """Ysmay pulls a thread that holds a feeling (Warmth, Primal) and a deed (Praedari, Abyssal).

    Numbers this journey sets: the thread reads 25 (a multiplier of 2), Warmth is authored a
    flat perk of 2, and a thread level multiplier is the level divided by ten, rounded down.
    Warmth is kindled at a strength worth 10 pull levels and Praedari at one worth 12; Primal's
    kindled boost is 100 percent and Abyssal's is 150. A resonance that is not the leader reads
    20 levels lower (the second-resonance step is set to 20, so Praedari reads 5).

    Hand-worked from the spec:

    * Nothing kindled: the thread reads 25, a multiplier of 2, and the perk is 2 * 2 = 4.
    * Only Warmth kindled: it adds 10 * 100 // 100 = 10, the thread reads 35, a multiplier of 3,
      and the perk is 2 * 3 = 6.
    * Both kindled, Praedari being 30 of the 100 imbued: Praedari's boost is
      12 * 150 // 100 = 18, and 18 * 30 // 100 = 5 of it counts. The thread reads
      25 + 10 + 5 = 40, a multiplier of 4, and the perk is 2 * 4 = 8.
    * The stronger payer: with both kindled, Warmth reads 40 and Praedari, reading 5, adds its
      own 18 and 10 * 70 // 100 = 7 of Warmth's, so 30. Warmth is strictly the highest and above
      its own 25, so it alone is marked. With nothing kindled nobody is marked.
    * Nothing imbued (both rows at 0): the second boost is 0 whatever is kindled, so Warmth
      reads 35 and its perk is 6 with Praedari kindled or not.
    """

    def setUp(self) -> None:
        super().setUp()
        _celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        for affinity, boost in ((self.primal, 100), (self.abyssal, 150)):
            affinity.kindled_boost_percent = boost
            affinity.save()
        Affinity.objects.clear_cache()
        drift = get_drift_config()
        drift.second_resonance_level_step = 20
        drift.save()
        self.warm_tier = KindledStrengthTierFactory(rank=1, name="Faint", pull_levels=10)
        self.blazing = KindledStrengthTierFactory(rank=3, name="Blazing", pull_levels=12)

        self.warmth = ResonanceFactory(name="Warmth", affinity=self.primal)
        self.praedari = ResonanceFactory(name="Praedari", affinity=self.abyssal)
        self.ysmay = self.make_player("Ysmay", room=self.make_room("The Lantern"))
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")
        for resonance in (self.warmth, self.praedari):
            CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance, balance=10)
        technique = TechniqueFactory(gift=GiftFactory())
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.warmth,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=2,
        )
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.warmth,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
            level=25,
            name="Lantern Strand",
        )

    def imbue_the_rows(self, warmth: int, praedari: int) -> None:
        """The thread's rows hold what was imbued: Warmth leads unless Praedari has more."""
        add_to_resonance_row(self.thread, self.warmth, warmth)
        add_to_resonance_row(self.thread, self.praedari, praedari)
        refresh_leading_resonance(self.thread)
        self.ysmay.threads.invalidate()

    def options(self) -> dict[str, dict]:
        """What the Pull threads dialog lists for the thread: one option per paying resonance."""
        response = self.api(self.account_of(self.ysmay)).post(
            reverse(PREVIEW_URL),
            {"character_sheet_id": self.sheet.pk, "tier": 1, "thread_ids": [self.thread.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        (pulled,) = response.json()["per_thread"]
        return {row["resonance_name"]: row for row in pulled["options"]}

    @staticmethod
    def perks(option: dict) -> list[int]:
        return [effect["scaled_value"] for effect in option["effects"]]

    def test_a_thread_pulled_with_both_resonances_kindled_previews_larger_perks(self) -> None:
        self.imbue_the_rows(warmth=70, praedari=30)

        plain = self.options()
        self.assertEqual(self.perks(plain["Warmth"]), [4])
        self.assertEqual([row["stronger"] for row in plain.values()], [False, False])

        kindle_resonance(self.sheet, self.warmth, self.warm_tier)
        feeling = self.options()
        self.assertEqual(feeling["Warmth"]["kindled_strength"], self.warm_tier.name)
        self.assertEqual(self.perks(feeling["Warmth"]), [6])
        self.assertTrue(feeling["Warmth"]["stronger"])
        self.assertFalse(feeling["Praedari"]["stronger"])

        kindle_resonance(self.sheet, self.praedari, self.blazing)
        both = self.options()
        self.assertEqual(both["Praedari"]["kindled_strength"], self.blazing.name)
        self.assertEqual(self.perks(both["Warmth"]), [8])
        self.assertGreater(self.perks(both["Warmth"])[0], self.perks(feeling["Warmth"])[0])
        # The thread's own read is unchanged: players never see the boosts.
        self.assertEqual(both["Warmth"]["level_read"], 25)
        self.assertTrue(both["Warmth"]["stronger"])
        self.assertFalse(both["Praedari"]["stronger"])

    def test_a_thread_with_nothing_imbued_adds_no_second_boost(self) -> None:
        self.imbue_the_rows(warmth=0, praedari=0)
        kindle_resonance(self.sheet, self.warmth, self.warm_tier)

        feeling_only = self.options()
        kindle_resonance(self.sheet, self.praedari, self.blazing)
        both = self.options()

        self.assertEqual(self.perks(feeling_only["Warmth"]), [6])
        self.assertEqual(self.perks(both["Warmth"]), self.perks(feeling_only["Warmth"]))
