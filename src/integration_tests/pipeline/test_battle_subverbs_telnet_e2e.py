"""Telnet E2E: battle declare subverbs — the coverage gap (#1328 Bucket C).

Companion to ``test_battle_telnet_e2e.py`` (which covers the strike + round
lifecycle + peril/rescue). This file covers the remaining ``battle declare``
subverbs that had no e2e test:

  - ``battle declare support <ally> with <technique>``
  - ``battle declare rescue <ally> with <technique>``
  - ``battle declare rout <unit> with <technique>``
  - ``battle declare rally <unit> with <technique>``
  - ``battle declare repel place <name> with <technique>``
  - ``battle declare hold place <name> with <technique>``
  - ``battle declare breach place <name> fortification <kind> with <technique>``
  - ``battle declare fortify place <name> fortification <kind> with <technique>``
  - ``battle declare set_environment with <technique>``
  - ``battle declare set_environment place <name> with <technique>``
  - ``battle conclude`` (GM force-conclude)

Each test creates a battle, opens a round, declares, and asserts the
BattleActionDeclaration row was written with the correct action_kind + target.
``perform_check`` is not patched — these tests verify the *declaration* path
(command → Action → DB row), not round resolution.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory, CharacterFactory
from integration_tests.pipeline.test_battle_telnet_e2e import (
    _make_pc,
    _make_room,
    _run,
)
from world.battles.constants import (
    BattleActionKind,
    BattleActionScope,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
)
from world.battles.factories import (
    FortificationFactory,
)
from world.battles.models import BattleActionDeclaration, BattleRound
from world.battles.services import (
    add_side,
    add_unit,
    create_battle,
    enlist_participant,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gm(room: object, account: object) -> object:
    """Create a GM character (staff account) in *room*."""
    char = CharacterFactory(db_key="BattleSubverbGM", location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data__account=account, end_date=None)
    return char


def _make_battle_with_round(room: object) -> tuple[object, object, object, object, object]:
    """Create a battle with two sides, a unit, and an open DECLARING round.

    Returns (gm_char, battle, attacker_side, defender_side, enemy_unit).
    """
    gm_account = AccountFactory(username="battle_subverb_gm", is_staff=True)
    gm_char = _make_gm(room, gm_account)

    battle = create_battle(name="Subverb E2E Battle")
    battle.scene.location = room
    battle.scene.save(update_fields=["location"])

    attacker_side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
    defender_side = add_side(battle=battle, role=BattleSideRole.DEFENDER)
    enemy_unit = add_unit(
        battle=battle, side=attacker_side, name="Vanguard", descriptor="soldiers", strength=100
    )

    # Open a round so declarations can be recorded.
    _run(gm_char, "round")
    return gm_char, battle, attacker_side, defender_side, enemy_unit


def _make_battle_pc(
    room: object,
    db_key: str,
    side: object,
    technique: object,
) -> tuple[object, object, object]:
    """Create a PC participant in *side* who knows *technique*.

    Returns (character, sheet, participant).
    """
    char, sheet = _make_pc(db_key, room)
    CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
    CharacterTechniqueFactory(character=sheet, technique=technique)
    CharacterAnimaFactory(character=char, current=20, maximum=30)
    participant = enlist_participant(battle=side.battle, character_sheet=sheet, side=side)
    return char, sheet, participant


def _grant_supreme_command_tier(participant: object, side: object) -> None:
    """Attach a BATTLE covenant with a SUPREME command-tier role to *side* + *participant*.

    REPEL/HOLD (PLACE scope) require SUBORDINATE or SUPREME; SET_ENVIRONMENT at
    BATTLE scope requires SUPREME. This helper wires the full chain:
    covenant → side.covenant → CovenantRole(command_tier=SUPREME) →
    engaged CharacterCovenantRole.
    """
    from world.covenants.constants import CovenantType
    from world.covenants.factories import (
        CharacterCovenantRoleFactory,
        CovenantFactory,
        CovenantRoleFactory,
    )

    covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
    side.covenant = covenant
    side.save(update_fields=["covenant"])

    role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
    role.command_tier = "supreme"
    role.save(update_fields=["command_tier"])

    CharacterCovenantRoleFactory(
        character_sheet=participant.character_sheet,
        covenant=covenant,
        covenant_role=role,
        engaged=True,
    )


def _last_declaration(battle_round: object) -> BattleActionDeclaration:
    """Return the most-recent BattleActionDeclaration for *battle_round*."""
    return BattleActionDeclaration.objects.filter(battle_round=battle_round).order_by("-pk").first()


# ---------------------------------------------------------------------------
# Journey — unit-scoped subverbs (rout, rally)
# ---------------------------------------------------------------------------


class BattleUnitScopedSubverbsE2ETest(TestCase):
    """rout + rally declarations through CmdBattle."""

    def setUp(self) -> None:
        self.room = _make_room("BattleSubverbRoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )
        self.battle_round = BattleRound.objects.filter(
            battle=self.battle, status=RoundStatus.DECLARING
        ).first()

        # A PC on the defender side who will declare.
        self.pc_char, self.pc_sheet, self.pc_participant = _make_battle_pc(
            self.room, "RoutPC", self.defender_side, self.technique
        )
        # A routed unit on the defender side (for rally).
        self.routed_unit = add_unit(
            battle=self.battle, side=self.defender_side, name="Broken Squad", descriptor="survivors"
        )
        self.routed_unit.status = BattleUnitStatus.ROUTED
        self.routed_unit.save(update_fields=["status"])

    def test_declare_rout_targets_enemy_unit(self) -> None:
        """battle declare rout <unit> with <technique> → ROUT declaration against the enemy unit."""
        _run(self.pc_char, f"declare rout Vanguard with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl, "a declaration should be recorded")
        self.assertEqual(decl.action_kind, BattleActionKind.ROUT)
        self.assertEqual(decl.target_unit, self.enemy_unit)
        self.pc_char.msg.assert_called()

    def test_declare_rally_targets_own_routed_unit(self) -> None:
        """battle declare rally <unit> → RALLY declaration against own routed unit."""
        _run(self.pc_char, f"declare rally Broken Squad with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.RALLY)
        self.assertEqual(decl.target_unit, self.routed_unit)


# ---------------------------------------------------------------------------
# Journey — ally-scoped subverbs (support, rescue)
# ---------------------------------------------------------------------------


class BattleAllyScopedSubverbsE2ETest(TestCase):
    """support + rescue declarations through CmdBattle."""

    def setUp(self) -> None:
        self.room = _make_room("BattleAllyRoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )
        self.battle_round = BattleRound.objects.filter(
            battle=self.battle, status=RoundStatus.DECLARING
        ).first()

        # Two PCs on the defender side — one declares, the other is the ally target.
        self.pc1_char, self.pc1_sheet, self.pc1_participant = _make_battle_pc(
            self.room, "Supporter", self.defender_side, self.technique
        )
        self.pc2_char, self.pc2_sheet, self.pc2_participant = _make_battle_pc(
            self.room, "AllyTarget", self.defender_side, self.technique
        )

    def test_declare_support_targets_ally(self) -> None:
        """battle declare support <ally> with <technique> → SUPPORT declaration against the ally."""
        _run(self.pc1_char, f"declare support AllyTarget with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.SUPPORT)
        self.assertEqual(decl.target_ally, self.pc2_participant)

    def test_declare_rescue_targets_ally(self) -> None:
        """battle declare rescue <ally> with <technique> → RESCUE declaration against the ally."""
        _run(self.pc1_char, f"declare rescue AllyTarget with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.RESCUE)
        self.assertEqual(decl.target_ally, self.pc2_participant)


# ---------------------------------------------------------------------------
# Journey — place-scoped subverbs (repel, hold)
# ---------------------------------------------------------------------------


class BattlePlaceScopedSubverbsE2ETest(TestCase):
    """repel + hold declarations through CmdBattle."""

    def setUp(self) -> None:
        self.room = _make_room("BattlePlaceRoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )
        self.battle_round = BattleRound.objects.filter(
            battle=self.battle, status=RoundStatus.DECLARING
        ).first()
        from world.battles.services import add_place

        self.place = add_place(battle=self.battle, name="The Pass")

        self.pc_char, self.pc_sheet, self.pc_participant = _make_battle_pc(
            self.room, "PlacePC", self.defender_side, self.technique
        )
        # REPEL/HOLD are PLACE-scope — require a SUBORDINATE or SUPREME command tier.
        _grant_supreme_command_tier(self.pc_participant, self.defender_side)

    def test_declare_repel_targets_place(self) -> None:
        """battle declare repel place <name> with <technique> → REPEL declaration (PLACE scope)."""
        _run(self.pc_char, f"declare repel place The Pass with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.REPEL)
        self.assertEqual(decl.target_place, self.place)
        self.assertEqual(decl.scope, BattleActionScope.PLACE)

    def test_declare_hold_targets_place(self) -> None:
        """battle declare hold place <name> with <technique> → HOLD declaration (PLACE scope)."""
        _run(self.pc_char, f"declare hold place The Pass with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.HOLD)
        self.assertEqual(decl.target_place, self.place)
        self.assertEqual(decl.scope, BattleActionScope.PLACE)


# ---------------------------------------------------------------------------
# Journey — fortification-scoped subverbs (breach, fortify)
# ---------------------------------------------------------------------------


class BattleFortificationSubverbsE2ETest(TestCase):
    """breach + fortify declarations through CmdBattle."""

    def setUp(self) -> None:
        self.room = _make_room("BattleFortRoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )
        self.battle_round = BattleRound.objects.filter(
            battle=self.battle, status=RoundStatus.DECLARING
        ).first()
        from world.battles.services import add_place

        self.place = add_place(battle=self.battle, name="The Gatehouse")

        # A wall fortification — defended by the defender side (so attackers breach it).
        self.wall = FortificationFactory(
            place=self.place,
            defending_side=self.defender_side,
            kind=FortificationKind.WALL,
        )

        # PC on the attacker side (breaches the enemy's wall).
        self.attacker_char, self.attacker_sheet, self.attacker_participant = _make_battle_pc(
            self.room, "Breacher", self.attacker_side, self.technique
        )
        # PC on the defender side (fortifies their own wall).
        self.defender_char, self.defender_sheet, self.defender_participant = _make_battle_pc(
            self.room, "Fortifier", self.defender_side, self.technique
        )

    def test_declare_breach_targets_fortification(self) -> None:
        """battle declare breach place <name> fortification <kind> → BREACH declaration."""
        _run(
            self.attacker_char,
            f"declare breach place The Gatehouse fortification wall with {self.technique.name}",
        )

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.BREACH)
        self.assertEqual(decl.target_fortification, self.wall)

    def test_declare_fortify_targets_fortification(self) -> None:
        """battle declare fortify place <name> fortification <kind> → FORTIFY declaration."""
        _run(
            self.defender_char,
            f"declare fortify place The Gatehouse fortification wall with {self.technique.name}",
        )

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.FORTIFY)
        self.assertEqual(decl.target_fortification, self.wall)


# ---------------------------------------------------------------------------
# Journey — set_environment (battle-scope + place-scope)
# ---------------------------------------------------------------------------


class BattleSetEnvironmentSubverbE2ETest(TestCase):
    """set_environment declarations through CmdBattle."""

    def setUp(self) -> None:
        self.room = _make_room("BattleEnvRoom")
        # set_environment requires a technique that carries target_weather_type.
        from world.weather.factories import WeatherTypeFactory

        self.weather_type = WeatherTypeFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(),
            damage_profile=False,
            target_weather_type=self.weather_type,
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )
        self.battle_round = BattleRound.objects.filter(
            battle=self.battle, status=RoundStatus.DECLARING
        ).first()
        from world.battles.services import add_place

        self.place = add_place(battle=self.battle, name="The Valley")

        self.pc_char, self.pc_sheet, self.pc_participant = _make_battle_pc(
            self.room, "WeatherPC", self.defender_side, self.technique
        )
        # SET_ENVIRONMENT at BATTLE scope requires SUPREME command tier;
        # PLACE scope requires SUBORDINATE or SUPREME.
        _grant_supreme_command_tier(self.pc_participant, self.defender_side)

    def test_declare_set_environment_battle_scope(self) -> None:
        """battle declare set_environment with <technique> → SET_ENVIRONMENT at BATTLE scope."""
        _run(self.pc_char, f"declare set_environment with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.SET_ENVIRONMENT)
        self.assertEqual(decl.scope, BattleActionScope.BATTLE)

    def test_declare_set_environment_place_scope(self) -> None:
        """battle declare set_environment place <name> → SET_ENVIRONMENT at PLACE scope."""
        _run(self.pc_char, f"declare set_environment place The Valley with {self.technique.name}")

        decl = _last_declaration(self.battle_round)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.action_kind, BattleActionKind.SET_ENVIRONMENT)
        self.assertEqual(decl.scope, BattleActionScope.PLACE)
        self.assertEqual(decl.target_place, self.place)


# ---------------------------------------------------------------------------
# Journey — conclude (GM force-conclude)
# ---------------------------------------------------------------------------


class BattleConcludeSubverbE2ETest(TestCase):
    """battle conclude → force-concludes the battle."""

    def setUp(self) -> None:
        self.room = _make_room("BattleConcludeRoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        self.gm_char, self.battle, self.attacker_side, self.defender_side, self.enemy_unit = (
            _make_battle_with_round(self.room)
        )

    def test_conclude_force_concludes_battle(self) -> None:
        """battle conclude → battle is concluded + scene inactive."""
        _run(self.gm_char, "conclude")

        self.battle.refresh_from_db()
        self.assertTrue(
            self.battle.is_concluded, "battle should be concluded after 'battle conclude'"
        )
        self.battle.scene.refresh_from_db()
        self.assertFalse(self.battle.scene.is_active, "scene should be inactive after conclusion")
        self.gm_char.msg.assert_called()
        msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("conclude", msg.lower())
