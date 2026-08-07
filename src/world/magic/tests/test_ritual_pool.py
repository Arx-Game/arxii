"""Ritual anima pool contributions + the pool gate (#3001). SQLite tier."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import AnimaContributionKind
from world.magic.exceptions import RitualPoolError
from world.magic.factories import RitualFactory, RitualSessionFactory
from world.magic.models.anima import CharacterAnima
from world.magic.models.ritual_pool import RitualAnimaContribution
from world.magic.services.ritual_pool import (
    contribute_channel,
    contribute_gash,
    contribute_prick,
    contribute_sacrifice,
    pool_total,
    resolve_pool_gate,
)


def _anima(sheet, *, current=10, maximum=10, glut=0):
    anima, _ = CharacterAnima.objects.update_or_create(
        character=sheet,
        defaults={"current": current, "maximum": maximum, "glut": glut},
    )
    return anima


class ContributionTests(TestCase):
    def setUp(self):
        self.ritual = RitualFactory(anima_requirement=50)
        self.session = RitualSessionFactory(ritual=self.ritual)
        self.sheet = CharacterSheetFactory()

    def test_channel_deducts_and_records(self):
        _anima(self.sheet, current=30, maximum=100)
        row = contribute_channel(
            ritual=self.ritual, contributor_sheet=self.sheet, amount=20, session=self.session
        )
        self.assertEqual(row.kind, AnimaContributionKind.CHANNEL)
        self.assertEqual(row.amount, 20)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 10)
        self.assertEqual(pool_total(self.session), 20)

    def test_channel_clamps_to_available(self):
        _anima(self.sheet, current=5, maximum=100)
        row = contribute_channel(
            ritual=self.ritual, contributor_sheet=self.sheet, amount=20, session=self.session
        )
        self.assertEqual(row.amount, 5)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 0)

    def test_channel_with_nothing_raises(self):
        _anima(self.sheet, current=0)
        with self.assertRaises(RitualPoolError):
            contribute_channel(
                ritual=self.ritual, contributor_sheet=self.sheet, amount=5, session=self.session
            )

    def test_prick_gives_one_anima_and_trivial_damage(self):
        _anima(self.sheet, current=10)
        with (
            patch("world.vitals.services.apply_clamped_chronic_damage") as damage,
            patch("world.magic.services.ritual_pool._apply_contributor_fatigue") as fatigue,
        ):
            row = contribute_prick(
                ritual=self.ritual, contributor_sheet=self.sheet, session=self.session
            )
        self.assertEqual(row.kind, AnimaContributionKind.PRICK)
        self.assertEqual(row.amount, 1)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 9)
        damage.assert_called_once_with(self.sheet, 1)
        fatigue.assert_called_once()

    def test_gash_scales_with_level_and_wounds(self):
        _anima(self.sheet, current=100, maximum=100)
        with (
            patch("world.magic.services.ritual_pool._roll_gash", return_value=15) as roll,
            patch("world.magic.services.ritual_pool._contributor_level", return_value=3),
            patch("world.vitals.services.apply_clamped_chronic_damage") as damage,
            patch("world.magic.services.ritual_pool._apply_contributor_fatigue"),
        ):
            row = contribute_gash(
                ritual=self.ritual, contributor_sheet=self.sheet, session=self.session
            )
        roll.assert_called_once_with(3)
        self.assertEqual(row.amount, 15)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 85)
        damage.assert_called_once_with(self.sheet, 15)

    def test_sacrifice_drains_victim_wholesale(self):
        victim = CharacterSheetFactory()
        _anima(victim, current=7, maximum=10)
        with patch("world.magic.services.ritual_pool._apply_contributor_fatigue"):
            row = contribute_sacrifice(
                ritual=self.ritual,
                sacrificer_sheet=self.sheet,
                victim_sheet=victim,
                session=self.session,
            )
        self.assertEqual(row.kind, AnimaContributionKind.SACRIFICE)
        self.assertEqual(row.amount, 7)
        self.assertEqual(row.victim, victim)
        self.assertFalse(row.was_lethal)
        self.assertEqual(CharacterAnima.objects.get(character=victim).current, 0)

    def test_lethal_sacrifice_yields_death_harvest_and_taint(self):
        victim = CharacterSheetFactory()
        _anima(victim, current=3, maximum=10)
        with (
            patch("world.magic.services.ritual_pool._apply_contributor_fatigue"),
            patch("world.magic.services.feeding._maybe_kill_npc_victim", return_value=True) as kill,
            patch("world.magic.services.feeding.grant_blood_taint") as taint,
        ):
            row = contribute_sacrifice(
                ritual=self.ritual,
                sacrificer_sheet=self.sheet,
                victim_sheet=victim,
                lethal=True,
                session=self.session,
            )
        kill.assert_called_once()
        taint.assert_called_once()
        self.assertTrue(row.was_lethal)
        self.assertEqual(row.amount, 200)  # 20 x maximum 10

    def test_refused_kill_falls_back_to_survivable_drain(self):
        victim = CharacterSheetFactory()
        _anima(victim, current=4, maximum=10)
        with (
            patch("world.magic.services.ritual_pool._apply_contributor_fatigue"),
            patch("world.magic.services.feeding._maybe_kill_npc_victim", return_value=False),
            patch("world.magic.services.feeding.grant_blood_taint") as taint,
        ):
            row = contribute_sacrifice(
                ritual=self.ritual,
                sacrificer_sheet=self.sheet,
                victim_sheet=victim,
                lethal=True,
                session=self.session,
            )
        taint.assert_not_called()
        self.assertFalse(row.was_lethal)
        self.assertEqual(row.amount, 4)

    def test_contributions_survive_session_deletion(self):
        _anima(self.sheet, current=30, maximum=100)
        contribute_channel(
            ritual=self.ritual, contributor_sheet=self.sheet, amount=10, session=self.session
        )
        self.session.delete()
        # Read raw column values: the idmapper instance keeps a stale cached
        # relation object after SET_NULL, so assert on the DB row itself.
        session_id, ritual_id = RitualAnimaContribution.objects.values_list(
            "session_id", "ritual_id"
        ).get()
        self.assertIsNone(session_id)
        self.assertEqual(ritual_id, self.ritual.pk)


class HedgeVisibilityTests(TestCase):
    """#3001: ritual_visible_to — one predicate for browse and perform."""

    def test_hedge_ritual_visible_to_anyone(self):
        from world.magic.services.ritual_pool import ritual_visible_to

        sheet = CharacterSheetFactory()  # no CharacterAura row = quiescent
        ritual = RitualFactory(hedge_accessible=True)
        self.assertTrue(ritual_visible_to(sheet, ritual))

    def test_deep_ritual_hidden_from_quiescent(self):
        from world.magic.services.ritual_pool import ritual_visible_to

        sheet = CharacterSheetFactory()
        ritual = RitualFactory(hedge_accessible=False)
        self.assertFalse(ritual_visible_to(sheet, ritual))

    def test_deep_ritual_visible_with_magical_profile(self):
        from world.magic.factories import CharacterAuraFactory
        from world.magic.services.ritual_pool import ritual_visible_to

        aura = CharacterAuraFactory()
        ritual = RitualFactory(hedge_accessible=False)
        self.assertTrue(ritual_visible_to(aura.character, ritual))

    def test_perform_action_enforces_the_predicate(self):
        from actions.definitions.ritual import PerformRitualAction
        from world.magic.constants import RitualExecutionKind

        sheet = CharacterSheetFactory()
        ritual = RitualFactory(
            hedge_accessible=False,
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )
        result = PerformRitualAction().run(sheet.character, ritual=ritual)
        self.assertFalse(result.success)
        self.assertIn("closed to you", result.message)


class PoolGateTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()

    def test_folk_rite_always_proceeds(self):
        ritual = RitualFactory(anima_requirement=0)
        gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=0)
        self.assertTrue(gate.proceeded)
        self.assertFalse(gate.spectacular)

    def test_met_requirement_proceeds(self):
        ritual = RitualFactory(anima_requirement=50)
        gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=50)
        self.assertTrue(gate.proceeded)
        self.assertFalse(gate.spectacular)

    def test_double_fill_is_spectacular(self):
        ritual = RitualFactory(anima_requirement=50)
        gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=100)
        self.assertTrue(gate.proceeded)
        self.assertTrue(gate.spectacular)

    def test_deficit_without_check_config_fails_closed(self):
        ritual = RitualFactory(anima_requirement=50)
        gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=10)
        self.assertFalse(gate.proceeded)
        self.assertEqual(gate.deficit, 40)

    def test_deficit_rolls_the_ritual_check_with_a_bump(self):
        from world.magic.factories import RitualCheckConfigFactory

        config = RitualCheckConfigFactory()
        ritual = config.ritual
        ritual.anima_requirement = 50
        ritual.save(update_fields=["anima_requirement"])

        class _Result:
            success_level = 1

        with patch("world.checks.services.perform_check", return_value=_Result()) as check:
            gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=25)
        self.assertTrue(gate.proceeded)
        # deficit 25 of 50 -> bump ceil(3 * 25/50) = 2 over base difficulty 3.
        self.assertEqual(check.call_args.args[2], 5)

    def test_failed_deficit_check_fizzles(self):
        from world.magic.factories import RitualCheckConfigFactory

        config = RitualCheckConfigFactory()
        ritual = config.ritual
        ritual.anima_requirement = 50
        ritual.save(update_fields=["anima_requirement"])

        class _Result:
            success_level = 0

        with patch("world.checks.services.perform_check", return_value=_Result()):
            gate = resolve_pool_gate(ritual=ritual, performer_sheet=self.sheet, pool=25)
        self.assertFalse(gate.proceeded)
