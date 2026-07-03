"""Telnet E2E: battle lifecycle journey (#1592).

Drives the full stage→declare→resolve→conclude flow through CmdBattle, asserting
DB state after each step and telnet feedback via caller.msg MagicMock.

Journey outline:
  1. GM opens a round  (``battle round``).
  2. Two defender PCs each declare a strike against the enemy unit
     (``battle declare strike <unit> with <technique>``).
  3. GM resolves the round (``battle resolve``), which casts each declared
     technique through the real magic envelope (``use_technique``); ``perform_check``
     is patched so the underlying check is deterministic:
     - PC1 succeeds (``success_level=5``) → enemy unit loses 50 strength,
       defender side gains 25 VP.
     - PC2 fails (``success_level=-3``) → PC2 takes 11 damage.
  4. The defender side's VP (25) reaches its ``victory_threshold`` (25), so the
     resolve action auto-concludes the battle.

All assertions run on the SQLite fast tier — no ``@tag("postgres")`` needed
because no progressive-condition / ``DISTINCT ON`` path is touched here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from commands.battle import CmdBattle
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    BattleActionKind,
    BattleActionScope,
    BattleSideRole,
)
from world.battles.models import BattleActionDeclaration, BattleRound
from world.battles.services import add_side, add_unit, create_battle, enlist_participant
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory
from world.weather.factories import WeatherTypeFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(label: str = "BattleE2ERoom") -> object:
    """Create a Room ObjectDB in the identity map."""
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_gm_actor(db_key: str, room: object, account: object) -> object:
    """Create a staff-account-linked character.

    ``account.is_staff`` is True, so ``_actor_may_gm_battle`` short-circuits
    without needing a scene.is_gm SceneParticipation.
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char


def _make_pc(db_key: str, room: object) -> tuple[object, object]:
    """Create a PC character with a sheet and vitals in *room*.

    Returns (character, character_sheet).
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
    return char, sheet


def _run(caller: object, args: str = "") -> None:
    """Instantiate CmdBattle, wire caller/args, call func() immediately.

    Sets ``caller.msg`` to a fresh MagicMock before each call so the
    assertion site can inspect the single most-recent message.
    """
    cmd = CmdBattle()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"battle {args}".strip()
    caller.msg = MagicMock()
    cmd.func()


def _stub_check(success_level: int) -> MagicMock:
    """Return a MagicMock resembling a CheckResult with *success_level*."""
    result = MagicMock()
    result.success_level = success_level
    return result


# ---------------------------------------------------------------------------
# E2E journey
# ---------------------------------------------------------------------------


class BattleTelnetE2EJourneyTest(TestCase):
    """Full battle lifecycle journey through telnet CmdBattle.

    Uses a low ``victory_threshold`` (25 VP) so that one successful strike
    at ``success_level=5`` (→ 25 VP) triggers auto-conclude at resolve time.
    """

    def setUp(self) -> None:
        # Room — all actors located here so _active_battle_in_room finds the battle.
        self.room = _make_room()

        # Castable technique (real action_template) shared by both PCs — required by
        # declare_battle_action (Task 3) and cast through use_technique at resolve time
        # (Task 6/7).
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )

        # GM actor — staff account so _actor_may_gm_battle returns True immediately.
        self.gm_account = AccountFactory(username="e2e_gm_account", is_staff=True)
        self.gm_char = _make_gm_actor("e2e_gm", self.room, self.gm_account)

        # Battle located in the test room.
        self.battle = create_battle(name="E2E Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        # Two sides: enemy attackers, defender PCs.
        # Low victory_threshold so one success_level=5 strike reaches it.
        # victory_threshold = success_level(5) * STRIKE_VP_PER_LEVEL(5) = 25
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(
            battle=self.battle,
            role=BattleSideRole.DEFENDER,
            victory_threshold=25,
        )

        # Enemy unit on the attacker side — the target of PC strikes.
        self.enemy_unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Iron Vanguard",
            descriptor="soldiers",
            strength=100,
        )

        # Two PC participants on the defender side.
        self.pc1_char, self.pc1_sheet = _make_pc("e2e_pc1", self.room)
        self.pc2_char, self.pc2_sheet = _make_pc("e2e_pc2", self.room)

        # Both PCs know the shared technique and have anima to cast it.
        CharacterTechniqueFactory(character=self.pc1_sheet, technique=self.technique)
        CharacterTechniqueFactory(character=self.pc2_sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.pc1_char, current=20, maximum=30)
        CharacterAnimaFactory(character=self.pc2_char, current=20, maximum=30)

        self.pc1_participant = enlist_participant(
            battle=self.battle,
            character_sheet=self.pc1_sheet,
            side=self.defender_side,
        )
        self.pc2_participant = enlist_participant(
            battle=self.battle,
            character_sheet=self.pc2_sheet,
            side=self.defender_side,
        )

    # -----------------------------------------------------------------------
    # Full journey in one test to match the E2E contract.
    # -----------------------------------------------------------------------

    def test_full_battle_lifecycle(self) -> None:
        """stage→declare(×2)→resolve(patched)→auto-conclude."""

        # ----------------------------------------------------------------
        # Step 1: GM opens a round.
        # ----------------------------------------------------------------
        _run(self.gm_char, "round")

        battle_round = BattleRound.objects.filter(
            battle=self.battle,
            status=RoundStatus.DECLARING,
        ).first()
        self.assertIsNotNone(
            battle_round,
            "A DECLARING BattleRound should exist after 'battle round'.",
        )
        self.assertEqual(battle_round.round_number, 1)

        self.gm_char.msg.assert_called()
        gm_open_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("1", gm_open_msg, "'Round 1 begins' feedback expected")

        # ----------------------------------------------------------------
        # Step 2: Both PCs declare a strike on the enemy unit.
        # ----------------------------------------------------------------
        _run(self.pc1_char, f"declare strike Iron Vanguard with {self.technique.name}")
        pc1_declare_msg = self.pc1_char.msg.call_args[0][0]
        self.assertIn("declare", pc1_declare_msg.lower())

        _run(self.pc2_char, f"declare strike Iron Vanguard with {self.technique.name}")

        declarations = BattleActionDeclaration.objects.filter(battle_round=battle_round)
        self.assertEqual(declarations.count(), 2, "Both PCs should have a declaration.")
        self.assertTrue(
            declarations.filter(
                participant=self.pc1_participant,
                action_kind=BattleActionKind.STRIKE,
                target_unit=self.enemy_unit,
            ).exists(),
            "PC1 declaration should exist.",
        )
        self.assertTrue(
            declarations.filter(
                participant=self.pc2_participant,
                action_kind=BattleActionKind.STRIKE,
                target_unit=self.enemy_unit,
            ).exists(),
            "PC2 declaration should exist.",
        )

        # ----------------------------------------------------------------
        # Step 3: GM resolves with patched perform_check.
        #
        # BattleActionDeclaration.Meta.ordering = ["battle_round", "participant"]
        # Participants are ordered by ["battle", "character_sheet"].
        # pc1_sheet was created before pc2_sheet → pc1 pk < pc2 pk → pc1 first.
        #
        # Call 1 → pc1 succeeds (success_level=5): unit loses strength, VP awarded.
        # Call 2 → pc2 fails  (success_level=-3): pc2 health debited.
        # ----------------------------------------------------------------
        check_side_effects = [
            _stub_check(5),  # pc1 — STRIKE success
            _stub_check(-3),  # pc2 — failure → damage
        ]
        with patch(
            "world.battles.resolution.perform_check",
            side_effect=check_side_effects,
        ):
            _run(self.gm_char, "resolve")

        # ----------------------------------------------------------------
        # Step 4: Assertions.
        # ----------------------------------------------------------------

        # Enemy unit strength: 100 − (5 × STRIKE_ATTRITION_PER_LEVEL) = 100 − 50 = 50.
        self.enemy_unit.refresh_from_db()
        expected_attrition = 5 * STRIKE_ATTRITION_PER_LEVEL
        self.assertEqual(
            self.enemy_unit.strength,
            100 - expected_attrition,
            f"Enemy unit strength should be {100 - expected_attrition}.",
        )

        # Defender side VP: 5 × STRIKE_VP_PER_LEVEL = 25.
        self.defender_side.refresh_from_db()
        expected_vp = 5 * STRIKE_VP_PER_LEVEL
        self.assertEqual(
            self.defender_side.victory_points,
            expected_vp,
            f"Defender side should have {expected_vp} VP.",
        )

        # PC2 health: 100 − (BASE_FAILURE_DAMAGE + abs(−3)) = 100 − 11 = 89.
        pc2_vitals = self.pc2_sheet.vitals
        pc2_vitals.refresh_from_db()
        expected_damage = BASE_FAILURE_DAMAGE + 3
        self.assertEqual(
            pc2_vitals.health,
            100 - expected_damage,
            "Failing PC (PC2) should have taken damage.",
        )

        # PC1 health: unchanged (success path, no damage).
        pc1_vitals = self.pc1_sheet.vitals
        pc1_vitals.refresh_from_db()
        self.assertEqual(
            pc1_vitals.health,
            100,
            "Successful PC (PC1) should not have taken damage.",
        )

        # ----------------------------------------------------------------
        # Step 5: Auto-conclude (victory_points ≥ victory_threshold triggers
        # check_victory inside ResolveBattleRoundAction.execute).
        # ----------------------------------------------------------------
        self.battle.refresh_from_db()
        self.assertTrue(
            self.battle.is_concluded,
            "Battle should be auto-concluded after VP reached the threshold.",
        )

        self.battle.scene.refresh_from_db()
        self.assertFalse(
            self.battle.scene.is_active,
            "The backing scene should be inactive after battle conclusion.",
        )

        # GM received a conclude message from the resolve action.
        gm_resolve_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn(
            "concludes",
            gm_resolve_msg.lower(),
            "GM should see a battle-concluded message.",
        )

    # -----------------------------------------------------------------------
    # #1794 modifier-stack proof: a fresh test method so it doesn't disturb the
    # full-lifecycle journey's VP/attrition arithmetic above.
    # -----------------------------------------------------------------------

    def test_property_terrain_quality_modifiers_change_strike_check(self) -> None:
        """A FLYING-affine technique striking an ELITE unit that carries the FLYING
        property while standing in DIFFICULT terrain nets a combined modifier from
        all three sources — proving the full Property-keyed stack (#1794) wires
        end-to-end through the real telnet path, not just resolution.py's unit tests.
        """
        from world.battles.constants import TerrainType, UnitQuality
        from world.battles.models import TechniquePropertyAffinity, TerrainPropertyEffect
        from world.battles.services import add_place
        from world.mechanics.factories import PropertyFactory

        flying = PropertyFactory(name="flying")
        place = add_place(battle=self.battle, name="The Mire", terrain_type=TerrainType.DIFFICULT)
        unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Wyvern Riders",
            quality=UnitQuality.ELITE,
            place=place,
            properties=[flying],
        )
        TechniquePropertyAffinity.objects.create(
            technique=self.technique, property=flying, modifier=25
        )
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=flying, modifier=15
        )

        _run(self.gm_char, "round")

        with patch(
            "world.battles.resolution.perform_check",
            return_value=_stub_check(5),
        ) as mock_check:
            _run(self.pc1_char, f"declare strike {unit.name} with {self.technique.name}")
            _run(self.gm_char, "resolve")

        # property(+25) + terrain(+15) + quality(ELITE=-20) + commander(0) + posture(0)
        expected_stack = 25 + 15 + (-20) + 0 + 0
        mock_check.assert_called_once()
        called_kwargs = mock_check.call_args.kwargs
        self.assertEqual(called_kwargs["extra_modifiers"], expected_stack)

    # -----------------------------------------------------------------------
    # #1715 final-review finding: prove SET_ENVIRONMENT through the real
    # telnet seam (CmdBattle -> DeclareBattleActionAction), not just the
    # service-layer tests in test_environmental_effects.py.
    # -----------------------------------------------------------------------

    def test_set_environment_battle_scope_through_telnet(self) -> None:
        """PC1 casts a BATTLE-scope SET_ENVIRONMENT via ``battle declare
        set_environment with <technique>``, resolved through the real
        ``CmdBattle`` -> ``DeclareBattleActionAction.run()`` dispatch — the
        same seam every other declare kind is proven through — and the cast
        weather lands on ``Battle.weather_override``.

        A fresh test method so it doesn't disturb the full-lifecycle
        journey's VP/attrition arithmetic above.
        """
        # BATTLE scope requires an engaged SUPREME command_tier on the
        # declarant's side's covenant (same gate as SIDE scope, #1710/#1715).
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save()
        rank = CovenantRankFactory(covenant=covenant)
        role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="env-e2e-supreme",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.pc1_sheet,
            covenant_role=role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        weather_type = WeatherTypeFactory()
        env_technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=weather_type
        )
        CharacterTechniqueFactory(character=self.pc1_sheet, technique=env_technique)

        # ------------------------------------------------------------
        # Step 1: GM opens a round.
        # ------------------------------------------------------------
        _run(self.gm_char, "round")
        battle_round = BattleRound.objects.get(battle=self.battle, status=RoundStatus.DECLARING)

        # ------------------------------------------------------------
        # Step 2: PC1 declares SET_ENVIRONMENT at BATTLE scope through the
        # real telnet command — no direct declare_battle_action() call.
        # ------------------------------------------------------------
        _run(self.pc1_char, f"declare set_environment with {env_technique.name}")
        declare_msg = self.pc1_char.msg.call_args[0][0]
        self.assertIn("declare", declare_msg.lower())

        declaration = BattleActionDeclaration.objects.get(
            battle_round=battle_round,
            participant=self.pc1_participant,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
        )
        self.assertEqual(declaration.scope, BattleActionScope.BATTLE)
        self.assertEqual(declaration.technique_id, env_technique.pk)

        # ------------------------------------------------------------
        # Step 3: GM resolves the round with a patched deterministic check.
        # ------------------------------------------------------------
        with patch(
            "world.battles.resolution.perform_check",
            return_value=_stub_check(2),
        ):
            _run(self.gm_char, "resolve")

        # ------------------------------------------------------------
        # Step 4: the cast weather landed on the battle-wide override.
        # ------------------------------------------------------------
        self.battle.refresh_from_db()
        self.assertEqual(
            self.battle.weather_override_id,
            weather_type.pk,
            "BATTLE-scope SET_ENVIRONMENT cast through telnet should set Battle.weather_override.",
        )
