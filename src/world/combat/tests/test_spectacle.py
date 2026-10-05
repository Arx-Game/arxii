from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatAllegiance,
    OpponentStatus,
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
        self.assertIn(self.persona.name, result.credit_line)
        self.assertIn("Audere", result.credit_line)
        self.assertIn("falter", result.credit_line)
        self.assertIn("take heart", result.credit_line)
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
