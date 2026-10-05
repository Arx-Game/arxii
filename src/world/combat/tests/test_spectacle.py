from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatAllegiance,
    OpponentStatus,
    OpponentTier,
    SpectacleKind,
    SpectacleReaction,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    SpectacleReactionLineFactory,
)
from world.combat.models import SpectacleConfig
from world.combat.morale import OpponentMoraleState
from world.combat.spectacle import (
    apply_spectacle,
    classify_cast,
    is_devastating,
    spectacle_hit,
)
from world.magic.factories import TechniqueFactory
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory


class SpectacleHitTests(SimpleTestCase):
    cfg = SpectacleConfig()

    def hit(self, kind, sl, caster, opp, morale=True):
        return spectacle_hit(
            config=self.cfg,
            kind=kind,
            success_level=sl,
            caster_level=caster,
            opponent_level=opp,
            has_morale=morale,
        )

    def test_audere_entry(self):
        self.assertEqual(self.hit(SpectacleKind.AUDERE_ENTRY, 0, 6, 3), 31)
        self.assertEqual(self.hit(SpectacleKind.AUDERE_ENTRY, 0, 6, 9), 18)
        self.assertEqual(self.hit(SpectacleKind.AUDERE_ENTRY, 0, 6, 6, morale=False), 12)

    def test_ultimate_scales_with_success(self):
        self.assertEqual(self.hit(SpectacleKind.ULTIMATE, 2, 6, 3), 57)
        self.assertEqual(self.hit(SpectacleKind.ULTIMATE, 2, 6, 9), 34)

    def test_floor_and_truncation(self):
        self.assertEqual(self.hit(SpectacleKind.CROSSING, 0, 2, 30), 15)
        self.assertEqual(self.hit(SpectacleKind.CROSSING, 0, 7, 6), 60)

    def test_mindless_never_zero(self):
        cfg = SpectacleConfig(mindless_percent=0)
        hit = spectacle_hit(
            config=cfg,
            kind=SpectacleKind.AUDERE_ENTRY,
            success_level=0,
            caster_level=6,
            opponent_level=6,
            has_morale=False,
        )
        self.assertEqual(hit, 1)


class ClassifyCastTests(SimpleTestCase):
    cfg = SpectacleConfig()

    def classify(self, ultimate, intensity, success):
        return classify_cast(
            technique=SimpleNamespace(is_ultimate=ultimate),
            runtime_intensity=intensity,
            success_level=success,
            config=self.cfg,
        )

    def test_ultimate_at_any_success(self):
        self.assertEqual(self.classify(True, 1, 0), SpectacleKind.ULTIMATE)

    def test_critical(self):
        self.assertEqual(self.classify(False, 6, 5), SpectacleKind.CRITICAL_TECHNIQUE)

    def test_below_thresholds(self):
        self.assertIsNone(self.classify(False, 6, 4))
        self.assertIsNone(self.classify(False, 5, 9))


class IsDevastatingTests(SimpleTestCase):
    cfg = SpectacleConfig()

    def test_threshold(self):
        self.assertTrue(
            is_devastating(damage_by_opponent={1: 40}, health_before={1: 100}, config=self.cfg)
        )
        self.assertFalse(
            is_devastating(damage_by_opponent={1: 39}, health_before={1: 100}, config=self.cfg)
        )

    def test_overkill_counts_only_health(self):
        self.assertFalse(
            is_devastating(
                damage_by_opponent={1: 30},
                health_before={1: 10, 2: 90},
                config=self.cfg,
            )
        )

    def test_empty_health(self):
        self.assertFalse(
            is_devastating(damage_by_opponent={1: 30}, health_before={}, config=self.cfg)
        )


class ApplySpectacleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SpectacleConfig.objects.get_or_create(pk=1)
        OpponentTierTemplateFactory(has_morale=True)
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(scene=cls.scene)
        cls.caster = CharacterSheetFactory()
        cls.persona = cls.caster.primary_persona
        cls.bandit_1 = CombatOpponentFactory(
            encounter=cls.encounter, level=3, morale=70, max_morale=70, name="bandit"
        )
        cls.bandit_2 = CombatOpponentFactory(
            encounter=cls.encounter, level=3, morale=70, max_morale=70, name="bandit"
        )
        cls.captain = CombatOpponentFactory(
            encounter=cls.encounter, level=9, morale=70, max_morale=70, name="captain"
        )
        cls.ally = CombatOpponentFactory(
            encounter=cls.encounter,
            allegiance=CombatAllegiance.ALLY,
            level=3,
            morale=30,
            max_morale=70,
            name="hound",
        )

    def setUp(self):
        # The identity map outlives a rolled-back test; put the cached rows back.
        for opp, morale in (
            (self.bandit_1, 70),
            (self.bandit_2, 70),
            (self.captain, 70),
            (self.ally, 30),
        ):
            opp.morale = morale
            opp.creature_template = None
            opp.save(update_fields=["morale", "creature_template"])
        patcher = patch("world.combat.spectacle.get_character_path_level", return_value=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_spectacle(self, **kwargs):
        defaults = {
            "encounter": self.encounter,
            "caster_sheet": self.caster,
            "kind": SpectacleKind.AUDERE_ENTRY,
            "display_name": "Audere",
        }
        defaults.update(kwargs)
        return apply_spectacle(**defaults)

    def reload(self, *opponents):
        for opp in opponents:
            opp.refresh_from_db()

    def test_audere_entry_morale_and_credit(self):
        result = self.run_spectacle()
        self.reload(self.bandit_1, self.bandit_2, self.captain, self.ally)
        self.assertEqual(self.bandit_1.morale, 70 - 31)
        self.assertEqual(self.bandit_2.morale, 70 - 31)
        self.assertEqual(self.captain.morale, 70 - 18)
        self.assertEqual(self.ally.morale, 30 + 25 * 50 // 100)
        states = {s.opponent_id: s.after for s in result.shifts}
        self.assertEqual(states[self.bandit_1.pk], OpponentMoraleState.FALTER)
        self.assertEqual(states[self.captain.pk], OpponentMoraleState.STEADY)
        self.assertEqual(
            result.credit_line,
            f"The bandit falter before {self.persona.name}'s Audere. "
            "The captain holds. The hound takes heart.",
        )
        self.assertEqual(result.heartened_ids, (self.ally.pk,))

    def test_repeat_changes_nothing(self):
        self.run_spectacle()
        again = self.run_spectacle()
        self.reload(self.bandit_1)
        self.assertEqual(again.credit_line, "")
        self.assertEqual(again.shifts, ())
        self.assertEqual(self.bandit_1.morale, 70 - 31)

    def test_same_technique_as_ultimate_then_critical_is_once(self):
        technique = TechniqueFactory()
        self.run_spectacle(
            kind=SpectacleKind.ULTIMATE, technique=technique, witnesses=[self.bandit_1]
        )
        self.reload(self.bandit_1)
        morale = self.bandit_1.morale
        again = self.run_spectacle(
            kind=SpectacleKind.CRITICAL_TECHNIQUE,
            technique=technique,
            success_level=5,
            witnesses=[self.bandit_1],
        )
        self.reload(self.bandit_1)
        self.assertEqual(again.shifts, ())
        self.assertEqual(self.bandit_1.morale, morale)

    def test_different_caster_still_lands(self):
        self.run_spectacle()
        other = CharacterSheetFactory()
        result = self.run_spectacle(caster_sheet=other)
        self.assertEqual(len(result.shifts), 3)

    def test_flavour_without_gm(self):
        SpectacleReactionLineFactory(
            reaction=SpectacleReaction.FALTERING, text="They back away from <actor>."
        )
        result = self.run_spectacle()
        self.assertEqual(result.flavour_line, f"They back away from {self.persona.name}.")

    def test_flavour_silent_with_gm(self):
        SpectacleReactionLineFactory(reaction=SpectacleReaction.FALTERING, text="x")
        SceneGMParticipationFactory(scene=self.scene, account=AccountFactory())
        self.scene.__dict__.pop("participations_cached", None)
        result = self.run_spectacle()
        self.assertEqual(result.flavour_line, "")
        self.assertTrue(result.credit_line)

    def test_kind_specific_beats_blank(self):
        SpectacleReactionLineFactory(reaction=SpectacleReaction.FALTERING, text="generic")
        SpectacleReactionLineFactory(
            reaction=SpectacleReaction.FALTERING,
            kind=SpectacleKind.AUDERE_ENTRY,
            text="specific",
        )
        self.assertEqual(self.run_spectacle().flavour_line, "specific")

    def test_creature_specific_beats_generic(self):
        template = CreatureTemplateFactory()
        self.bandit_1.creature_template = template
        self.bandit_1.save(update_fields=["creature_template"])
        SpectacleReactionLineFactory(
            reaction=SpectacleReaction.FALTERING, kind=SpectacleKind.AUDERE_ENTRY, text="kind"
        )
        SpectacleReactionLineFactory(
            reaction=SpectacleReaction.FALTERING, creature_template=template, text="creature"
        )
        result = self.run_spectacle(witnesses=[self.bandit_1])
        self.assertEqual(result.flavour_line, "creature")

    def test_explicit_witnesses_only(self):
        self.run_spectacle(witnesses=[self.bandit_1])
        self.reload(self.bandit_1, self.bandit_2)
        self.assertEqual(self.bandit_1.morale, 70 - 31)
        self.assertEqual(self.bandit_2.morale, 70)

    def test_inactive_never_shaken(self):
        fled = CombatOpponentFactory(
            encounter=self.encounter,
            level=3,
            morale=70,
            max_morale=70,
            status=OpponentStatus.FLED,
        )
        self.run_spectacle(witnesses=[fled])
        fled.refresh_from_db()
        self.assertEqual(fled.morale, 70)


class SpectacleCreditLineTests(TestCase):
    """The credit line names each group with the state it actually reached (demo Screens 1-2)."""

    @classmethod
    def setUpTestData(cls):
        SpectacleConfig.objects.get_or_create(pk=1)
        OpponentTierTemplateFactory(has_morale=True)
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(scene=cls.scene)
        cls.caster = CharacterSheetFactory()
        cls.persona = cls.caster.primary_persona
        bandits = CreatureTemplateFactory(name="bridge bandits")
        captain = CreatureTemplateFactory(name="bandit captain")
        militia = CreatureTemplateFactory(name="village militia")
        cls.bandits = [
            CombatOpponentFactory(
                encounter=cls.encounter,
                level=3,
                morale=70,
                max_morale=70,
                creature_template=bandits,
            )
            for _ in range(2)
        ]
        cls.captain = CombatOpponentFactory(
            encounter=cls.encounter, level=9, morale=70, max_morale=70, creature_template=captain
        )
        cls.militia = [
            CombatOpponentFactory(
                encounter=cls.encounter,
                allegiance=CombatAllegiance.ALLY,
                level=3,
                morale=30,
                max_morale=70,
                creature_template=militia,
            )
            for _ in range(2)
        ]

    def setUp(self):
        for opp in (*self.bandits, self.captain):
            opp.morale = 70
            opp.save(update_fields=["morale"])
        for ally in self.militia:
            ally.morale = 30
            ally.save(update_fields=["morale"])
        patcher = patch("world.combat.spectacle.get_character_path_level", return_value=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_spectacle(self, **kwargs):
        defaults = {
            "encounter": self.encounter,
            "caster_sheet": self.caster,
            "kind": SpectacleKind.AUDERE_ENTRY,
            "display_name": "surge into Audere",
        }
        defaults.update(kwargs)
        return apply_spectacle(**defaults)

    def test_screen_1_captain_who_held_is_not_credited_a_falter(self):
        result = self.run_spectacle()
        self.assertEqual(
            result.credit_line,
            f"The bridge bandits falter before {self.persona.name}'s surge into Audere. "
            "The bandit captain holds. The village militia take heart.",
        )

    def test_screen_2_bandits_break_and_captain_falters(self):
        result = self.run_spectacle(
            kind=SpectacleKind.ULTIMATE,
            display_name="Pyre of the Last Gate",
            success_level=3,
            technique=TechniqueFactory(),
        )
        states = {s.opponent_id: s.after for s in result.shifts}
        self.assertEqual(states[self.bandits[0].pk], OpponentMoraleState.BREAK)
        self.assertEqual(states[self.captain.pk], OpponentMoraleState.FALTER)
        self.assertEqual(
            result.credit_line,
            f"The bridge bandits break before {self.persona.name}'s Pyre of the Last Gate. "
            "The bandit captain falters. The village militia take heart.",
        )

    def test_only_shaken_names_the_display(self):
        result = self.run_spectacle(witnesses=[self.captain])
        self.assertEqual(
            result.credit_line,
            f"The bandit captain is shaken by {self.persona.name}'s surge into Audere. "
            "The village militia take heart.",
        )

    def test_ally_at_full_morale_is_not_heartened(self):
        full, rising = self.militia
        full.morale = 70
        full.save(update_fields=["morale"])
        rising.morale = 65
        rising.save(update_fields=["morale"])
        result = self.run_spectacle()
        full.refresh_from_db()
        rising.refresh_from_db()
        self.assertEqual(full.morale, 70)
        self.assertEqual(rising.morale, 70)  # clamped at max_morale
        self.assertEqual(result.heartened_ids, (rising.pk,))
        self.assertTrue(result.credit_line.endswith("The village militia takes heart."))

    def test_no_ally_rose_no_take_heart(self):
        for ally in self.militia:
            ally.morale = 70
            ally.save(update_fields=["morale"])
        result = self.run_spectacle()
        self.assertEqual(result.heartened_ids, ())
        self.assertNotIn("heart", result.credit_line)

    def test_heartened_flavour_plays_without_gm(self):
        SpectacleReactionLineFactory(
            reaction=SpectacleReaction.HEARTENED, text="The <group> cheer <actor>'s <display>."
        )
        result = self.run_spectacle()
        self.assertEqual(
            result.heartened_line,
            f"The village militia cheer {self.persona.name}'s surge into Audere.",
        )
        self.assertIn(result.heartened_line, result.lines)

    def test_heartened_flavour_silent_with_gm(self):
        SpectacleReactionLineFactory(reaction=SpectacleReaction.HEARTENED, text="cheer")
        SceneGMParticipationFactory(scene=self.scene, account=AccountFactory())
        self.scene.__dict__.pop("participations_cached", None)
        result = self.run_spectacle()
        self.assertEqual(result.heartened_line, "")

    def test_broken_flavour_names_the_groups_that_broke(self):
        SpectacleReactionLineFactory(reaction=SpectacleReaction.BROKEN, text="The <group> run.")
        result = self.run_spectacle(
            kind=SpectacleKind.ULTIMATE,
            display_name="Pyre of the Last Gate",
            success_level=3,
            technique=TechniqueFactory(),
        )
        self.assertEqual(result.flavour_line, "The bridge bandits run.")

    def test_mindless_witness_takes_half_never_zero(self):
        OpponentTierTemplateFactory(tier=OpponentTier.ELITE, has_morale=False)
        skeleton = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.ELITE,
            level=3,
            morale=70,
            max_morale=70,
        )
        self.run_spectacle(witnesses=[skeleton])
        skeleton.refresh_from_db()
        self.assertEqual(skeleton.morale, 70 - 31 * 50 // 100)

    def test_mindless_witness_far_outclassing_still_loses_one(self):
        config = SpectacleConfig.load()
        previous = config.minimum_percent
        config.minimum_percent = 1
        config.save(update_fields=["minimum_percent"])

        def restore():
            config.minimum_percent = previous
            config.save(update_fields=["minimum_percent"])

        self.addCleanup(restore)
        OpponentTierTemplateFactory(tier=OpponentTier.ELITE, has_morale=False)
        lich = CombatOpponentFactory(
            encounter=self.encounter, tier=OpponentTier.ELITE, level=40, morale=70, max_morale=70
        )
        self.run_spectacle(kind=SpectacleKind.DEVASTATING_ACTION, witnesses=[lich])
        lich.refresh_from_db()
        self.assertEqual(lich.morale, 69)
