"""The Abyssal temptation: a cast pulling no thread is stronger in a kindled resonance (#5231).

Ysmay is mostly Primal (80 Primal, 20 Abyssal, settled the same). Her Gift's thread holds a
Primal resonance, Warmth, which leads, and an Abyssal one, Praedari, and she holds both. A GM
kindles Praedari at the "Blazing" strength (the third strength row), whose cast power this
journey sets to 6, and the Abyssal affinity's kindled boost to 150 percent. She casts a benign
technique on herself through the web cast endpoint, naming the resonance to work it in.

Hand-worked from the spec (a kindled cast adds the strength's cast power times the affinity's
boost percent, divided by 100, rounded down):

* Worked in Praedari, the cast's power ledger has a "kindled cast power" line of
  6 * 150 // 100 = 9.
* Worked in Warmth, which is not kindled, the ledger has no such line, and its total is
  exactly 9 lower than the Praedari cast's.
* Worked in Praedari with a thread pulled at tier 1, the ledger has no such line: a cast gets
  the pull or the kindled boost, not both.
"""

from __future__ import annotations

from actions.factories import ActionTemplateFactory
from commands import pending_actions
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import PathFactory
from world.combat.constants import ActionCategory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
    ensure_conversion_pairs,
)
from world.magic.models import Affinity, KindledStrengthTier
from world.magic.services.kindling import kindle_by_gm
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
        self.abyssal.kindled_boost_percent = 150
        self.abyssal.save()
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
        blazing.save()

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
            character_sheet=self.sheet, resonance=self.warmth, balance=10, lifetime_earned=10
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.praedari, balance=10, lifetime_earned=10
        )
        # Warmth is listed first, so it leads the Gift's thread.
        provision_latent_gift_thread(self.sheet, self.gift, resonances=[self.warmth, self.praedari])
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=self.skill)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)
        self.ysmay.weaving_unlocks.invalidate()
        self.strand = weave_thread(
            self.sheet, TargetKind.TRAIT, self.skill, self.praedari, name="Praedari Strand"
        )
        kindle_by_gm(
            sheet=self.sheet,
            resonance=self.praedari,
            tier=blazing,
            scene=self.scene,
            gm=None,
        )
        # The scene's anti-spam memory is process-wide and keyed by sheet pk.
        pending_actions._LAST_ACTED.clear()
        self.addCleanup(pending_actions._LAST_ACTED.clear)

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

    @staticmethod
    def line(ledger: dict, label: str) -> int:
        """The amount of the ledger's line called ``label``; 0 when it has none."""
        return sum(entry["amount"] for entry in ledger["entries"] if entry["source_label"] == label)

    def test_a_cast_worked_in_her_kindled_abyssal_resonance_reads_the_kindled_line(self) -> None:
        abyssal_cast = self.cast(self.praedari)
        primal_cast = self.cast(self.warmth)

        self.assertEqual(self.line(abyssal_cast, KINDLED_LINE), 9)  # 6 * 150 // 100
        self.assertEqual(self.line(primal_cast, KINDLED_LINE), 0)
        self.assertEqual(abyssal_cast["total"] - primal_cast["total"], 9)

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
