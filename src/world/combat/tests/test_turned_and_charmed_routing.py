"""NPC routing by effective allegiance (#4091, Decisions 1-5)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory, CombatAllegiance, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import (
    CombatTechniqueResolver,
    _resolve_npc_action,
    combatants_hostile_to,
    select_npc_actions,
)
from world.conditions.constants import Allegiance
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.services import has_condition
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.types.power_ledger import PowerLedger
from world.scenes.constants import RoundStatus


class RoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Routing break")
        cls.charm = ConditionTemplateFactory(
            name="Routing charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        cls.turn = ConditionTemplateFactory(
            name="Routing turn",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.pc = CombatParticipantFactory(encounter=self.enc)
        self.a = CombatOpponentFactory(encounter=self.enc)
        self.b = CombatOpponentFactory(encounter=self.enc)
        for opp in (self.a, self.b):
            ThreatPoolEntryFactory(pool=opp.threat_pool)

    def _actions_for(self, opp):
        return [x for x in select_npc_actions(self.enc) if x.opponent_id == opp.pk]

    def test_charmed_attacks_enemy_never_pc(self):
        ConditionInstanceFactory(
            target=self.a.objectdb,
            condition=self.charm,
            source_character=self.pc.character_sheet.character,
        )
        actions = self._actions_for(self.a)
        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(list(action.targets.all()), [])
            self.assertEqual(list(action.opponent_targets.all()), [self.b])

    def test_charm_without_source_still_never_targets_pc(self):  # Review Focus 2
        ConditionInstanceFactory(target=self.a.objectdb, condition=self.charm)
        for action in self._actions_for(self.a):
            self.assertEqual(list(action.targets.all()), [])

    def test_turned_attacks_its_own_side(self):
        ConditionInstanceFactory(target=self.a.objectdb, condition=self.turn)
        actions = self._actions_for(self.a)
        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(list(action.targets.all()), [])
            self.assertEqual(list(action.opponent_targets.all()), [self.b])

    def test_enemy_ignores_turned_npc(self):
        ConditionInstanceFactory(target=self.a.objectdb, condition=self.turn)
        for action in self._actions_for(self.b):
            self.assertEqual(list(action.opponent_targets.all()), [])
            self.assertIn(self.pc, list(action.targets.all()))

    def test_ally_summon_targets_turned_and_enemy(self):
        ally = CombatOpponentFactory(encounter=self.enc, allegiance=CombatAllegiance.ALLY)
        ConditionInstanceFactory(target=self.a.objectdb, condition=self.turn)
        hostile = combatants_hostile_to(ally)["opponents"]
        self.assertCountEqual(hostile, [self.a, self.b])

    def test_opponent_pk_never_reads_participant_threat(self):
        # Threat-map pk collision: opponent targets must ignore participant threat maps.
        ConditionInstanceFactory(target=self.a.objectdb, condition=self.charm)
        actions = self._actions_for(self.a)
        self.assertTrue(all(a.opponent_targets.exists() for a in actions))


class ConditionsAppliedOnOpponentTargetTests(TestCase):
    """A charmed NPC's damaging hit applies the threat entry's conditions (#4091).

    Runs on SQLite: bulk_apply_conditions' DISTINCT ON read
    (``world/conditions/services.py``'s ``_build_bulk_context``) only fires for
    templates with ``has_progression=True``; both templates here use the factory
    default (``False``), so that PG-only path never runs.
    """

    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Routing break conditions")
        cls.charm = ConditionTemplateFactory(
            name="Routing charm conditions",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        cls.scorch = ConditionTemplateFactory(name="Routing scorch")

    def setUp(self):
        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.pc = CombatParticipantFactory(encounter=self.enc)
        self.a = CombatOpponentFactory(encounter=self.enc, health=50, max_health=50, soak_value=0)
        self.b = CombatOpponentFactory(encounter=self.enc, health=50, max_health=50, soak_value=0)
        self.entry = ThreatPoolEntryFactory(pool=self.a.threat_pool, base_damage=15)
        self.entry.conditions_applied.add(self.scorch)
        ThreatPoolEntryFactory(pool=self.b.threat_pool)

    def test_charmed_hit_applies_condition_to_opponent_target(self):
        ConditionInstanceFactory(
            target=self.a.objectdb,
            condition=self.charm,
            source_character=self.pc.character_sheet.character,
        )
        actions = select_npc_actions(self.enc)
        action = next(x for x in actions if x.opponent_id == self.a.pk)

        _resolve_npc_action(self.a, action, None, None)

        self.assertTrue(has_condition(self.b.objectdb, self.scorch))


class AreaSparesCharmedOpponentTests(TestCase):
    """A PC's AREA technique skips an effectively-charmed opponent (Decision 4, #4091)."""

    def setUp(self) -> None:
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.0"))

    def test_area_technique_skips_charmed_opponent(self) -> None:
        from actions.constants import ActionTargetType
        from world.character_sheets.factories import CharacterSheetFactory

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="RoutingAoEAttack", base_power=20),
            target_type=ActionTargetType.AREA,
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)

        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        charmed = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        enemy = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )

        check = CheckTypeFactory(name="Routing break aoe")
        charm = ConditionTemplateFactory(
            name="Routing charm aoe",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        ConditionInstanceFactory(target=charmed.objectdb, condition=charm)

        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=enemy,
            effort_level=EffortLevel.MEDIUM,
        )

        resolver = CombatTechniqueResolver(
            participant=participant,
            action=action,
            pull_flat_bonus=0,
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=CheckTypeFactory(),
            offense_check_fn=None,
        )

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            resolver(power=20, ledger=PowerLedger(entries=(), total=20))

        charmed.refresh_from_db()
        enemy.refresh_from_db()
        self.assertEqual(charmed.health, 50, "AREA must spare the charmed opponent")
        self.assertLess(enemy.health, 50, "AREA must still hit the hostile opponent")


class GMAppliedConditionRoutingTests(TestCase):
    """A GM-applied allegiance condition routes exactly like a cast one (User Story 6, #4091)."""

    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Routing break gm")
        cls.turn = ConditionTemplateFactory(
            name="Routing turn gm",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        from evennia_extensions.factories import AccountFactory, CharacterFactory

        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.pc = CombatParticipantFactory(encounter=self.enc)
        self.a = CombatOpponentFactory(encounter=self.enc)
        self.b = CombatOpponentFactory(encounter=self.enc)
        for opp in (self.a, self.b):
            ThreatPoolEntryFactory(pool=opp.threat_pool)

        self.gm_account = AccountFactory(username="routing_gm_action", is_staff=True)
        self.gm_actor = CharacterFactory(db_key="RoutingGMAction")
        self.gm_actor.db_account = self.gm_account
        self.gm_actor.save()

    def test_gm_applied_turn_routes_like_a_cast_condition(self):
        from actions.definitions.gm_adjudication import GMApplyConditionAction

        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.a.objectdb,
            condition_ref=self.turn.name,
        )
        self.assertTrue(result.success, result.message)

        actions = [x for x in select_npc_actions(self.enc) if x.opponent_id == self.a.pk]
        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(list(action.targets.all()), [])
            self.assertEqual(list(action.opponent_targets.all()), [self.b])


class CmdGMConditionRoutingTelnetTests(TestCase):
    """``gm condition`` dispatches GMApplyConditionAction, routing exactly like a cast one."""

    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Routing break telnet")
        cls.turn = ConditionTemplateFactory(
            name="Routing turn telnet",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.scenes.factories import PersonaFactory

        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        room = self.enc.room

        self.gm_account = AccountFactory(username="routing_gm_telnet", is_staff=True)
        self.gm_actor = CharacterFactory(db_key="RoutingGMTelnet", location=room)
        self.gm_actor.db_account = self.gm_account
        self.gm_actor.save()
        self.gm_actor.msg = MagicMock()

        persona = PersonaFactory(
            character_sheet__character__location=room,
            character_sheet__character__db_key="RoutingTelnetNPC",
        )
        self.a = CombatOpponentFactory(encounter=self.enc, persona=persona)
        self.b = CombatOpponentFactory(encounter=self.enc)
        for opp in (self.a, self.b):
            ThreatPoolEntryFactory(pool=opp.threat_pool)

    def _run_cmd(self, args: str) -> list[str]:
        from commands.gm_ops import CmdGMDashboard

        cmd = CmdGMDashboard()
        cmd.caller = self.gm_actor
        cmd.args = args
        cmd.raw_string = f"gm {args}".strip()
        cmd.func()
        return [str(c.args[0]) for c in self.gm_actor.msg.call_args_list if c.args]

    def test_gm_condition_turns_npc_and_it_routes_at_its_former_side(self):
        messages = self._run_cmd(f"condition {self.a.objectdb.key} condition={self.turn.name}")
        self.assertTrue(any(self.turn.name in m for m in messages))

        actions = [x for x in select_npc_actions(self.enc) if x.opponent_id == self.a.pk]
        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(list(action.targets.all()), [])
            self.assertEqual(list(action.opponent_targets.all()), [self.b])
