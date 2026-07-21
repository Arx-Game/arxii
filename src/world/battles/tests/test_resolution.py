"""Tests for the battle declaration + resolution engine (Task 6).

Uses patched perform_check to control success/failure deterministically.
All tests run on the SQLite fast tier (no progressive conditions).
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER,
    BATTLE_POSTURE_VP_MULTIPLIER,
    RALLY_MORALE_PER_LEVEL,
    RALLY_VP,
    REPEL_DEFENSE_BONUS,
    REPEL_VP,
    ROUT_MORALE_PER_LEVEL,
    ROUT_VP_PER_LEVEL,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    BattleActionKind,
    BattleActionScope,
    BattleParticipantStatus,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.exceptions import (
    BattleError,
    CannotStrikeOwnSideError,
    FortificationAlreadyBreachedError,
    FortificationOwnershipMismatchError,
    FortificationTargetRequiredError,
    InsufficientCommandTierError,
    MissingScopeTargetError,
    NoCommandHierarchyError,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
    FortificationFactory,
)
from world.battles.models import TechniquePropertyAffinity, TerrainPropertyEffect
from world.battles.services import (
    add_place,
    add_side,
    add_unit,
    begin_battle_round,
    declare_battle_action,
    enlist_participant,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.types import CheckResult
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.mechanics.factories import PropertyFactory
from world.military.factories import MilitaryUnitFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory, ensure_surrounded_content


def _success_result(level: int = 5) -> types.SimpleNamespace:
    """Stub CheckResult with a positive success_level (pass)."""
    return types.SimpleNamespace(success_level=level)


def _failure_result(level: int = -3) -> types.SimpleNamespace:
    """Stub CheckResult with a non-positive success_level (fail)."""
    return types.SimpleNamespace(success_level=level)


class BattleTechniqueResolverTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

    def test_resolve_battle_technique_returns_check_result(self) -> None:
        from world.battles.resolution import resolve_battle_technique
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )

        battle = create_battle(name="Resolver Unit Test Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        fake_result = CheckResult(
            check_type=self.technique.action_template.check_type,
            outcome=None,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch("world.battles.resolution.perform_check", return_value=fake_result):
            check_result = resolve_battle_technique(declaration=declaration)

        self.assertIs(check_result, fake_result)

    def test_resolve_battle_technique_rolls_personal_check_when_provisioned(self) -> None:
        """#2014: a provisioned caster's battle technique cast rolls THEIR check,
        not the technique's action_template check_type — mirrors
        world.combat.tests.test_clash_commit.CommitToClashTests
        .test_commit_rolls_personal_check_when_provisioned.

        Patches ``world.battles.resolution.perform_check`` (not
        ``world.checks.services.perform_check``) because ``resolution.py`` imports
        ``perform_check`` at module scope (``from world.checks.services import
        perform_check``) rather than re-importing it inside the function on every
        call the way ``world.combat.clash`` does — patching the services module
        would not intercept the module-level-bound name in ``resolution``.
        """
        from evennia.accounts.models import AccountDB

        from world.battles.resolution import resolve_battle_technique
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )
        from world.checks.test_helpers import force_check_outcome
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import RitualCheckConfigFactory
        from world.magic.models.rituals import Ritual
        from world.traits.factories import CheckOutcomeFactory

        account = AccountDB.objects.create(username=f"battle_resolution_cc_{id(self)}")
        ritual = Ritual.objects.create(
            name=f"battle_resolution_cc_ritual_{id(self)}",
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        config = RitualCheckConfigFactory(ritual=ritual)
        self.sheet.character.db_account = account
        self.sheet.character.save(update_fields=["db_account"])

        battle = create_battle(name="Resolver Personal Check Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        success_outcome = CheckOutcomeFactory(name="battle_resolution_cc_success", success_level=1)

        captured = []
        from world.checks.services import perform_check as real_perform_check

        def recording_perform_check(objectdb, check_type, **kwargs):
            captured.append(check_type)
            return real_perform_check(objectdb, check_type, **kwargs)

        with (
            force_check_outcome(success_outcome),
            patch("world.battles.resolution.perform_check", recording_perform_check),
        ):
            resolve_battle_technique(declaration=declaration)

        self.assertEqual(captured, [config.check_type])
        self.assertNotEqual(config.check_type, self.technique.action_template.check_type)


class BattleActionKindCheckBonusScopingTests(TestCase):
    """A CHECK_BONUS perk scoped to ``battle_action_kind=ROUT`` fires on a ROUT
    declaration's check and not on a RALLY declaration's (#2536 slice 3 Battle
    wiring — ``BattleTechniqueResolver.__call__`` threads
    ``situation_ctx=SituationContext(battle_action_kind=declaration.action_kind)``
    into ``perform_check``).
    """

    def setUp(self) -> None:
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            VowSituationalPerkFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
        from world.magic.factories import ThreadFactory

        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            battle_action_kind=BattleActionKind.ROUT,
        )
        ThreadFactory(owner=self.sheet, level=10)

    def test_check_bonus_fires_on_matching_action_kind_only(self) -> None:
        from world.battles.resolution import resolve_battle_technique
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )
        from world.checks.services import perform_check as real_perform_check
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="BattleScopeSuccess", success_level=3)

        battle = create_battle(name="Battle Scope Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)

        captured: dict[str, int] = {}

        def _capture(action_kind: str, label: str) -> None:
            declaration = declare_battle_action(
                participant=participant,
                action_kind=action_kind,
                technique=self.technique,
            )
            totals: list[int] = []

            def _spy(*args, **kwargs):
                result = real_perform_check(*args, **kwargs)
                totals.append(result.total_points)
                return result

            with (
                force_check_outcome(success),
                patch("world.battles.resolution.perform_check", side_effect=_spy),
            ):
                resolve_battle_technique(declaration=declaration)
            captured[label] = totals[0]

        # Same participant/place across both declarations — redeclare updates
        # action_kind in place (declare_battle_action's update_or_create), so
        # every other modifier-stack input (unit=None, place, commander, posture)
        # stays byte-identical between the two calls; only battle_action_kind
        # (and therefore the CHECK_BONUS scope match) differs.
        _capture(BattleActionKind.ROUT, "rout")
        _capture(BattleActionKind.RALLY, "rally")

        # magnitude_tenths=10 * thread level=10 / 10 == 10 (mirrors #2536 slice 3
        # Court wiring's world.missions.tests.test_mission_perk_scoping calibration).
        self.assertEqual(captured["rout"], captured["rally"] + 10)


class DeclareBattleActionTests(TestCase):
    def setUp(self) -> None:
        from actions.factories import ActionTemplateFactory
        from world.battles.services import create_battle
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        self.battle = create_battle(name="Declaration Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.sheet = CharacterSheetFactory()
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )
        self.unit_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.unit = add_unit(
            battle=self.battle,
            side=self.unit_side,
            name="Enemy Archers",
            descriptor="archers",
        )
        self.battle_round = begin_battle_round(battle=self.battle)
        # Castable technique (action_template set) for the happy-path declarations
        # below; test_declare_raises_when_technique_has_no_action_template covers
        # the bare-technique (no action_template) rejection path separately.
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def test_declare_strike_action(self) -> None:
        from world.battles.services import declare_battle_action

        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        self.assertEqual(declaration.participant, self.participant)
        self.assertEqual(declaration.action_kind, BattleActionKind.STRIKE)
        self.assertEqual(declaration.technique, self.technique)
        self.assertEqual(declaration.target_unit, self.unit)
        self.assertFalse(declaration.resolved)

    def test_declare_support_action(self) -> None:
        from world.battles.services import declare_battle_action

        # Ally participant on the same side
        ally_sheet = CharacterSheetFactory()
        ally = enlist_participant(battle=self.battle, character_sheet=ally_sheet, side=self.side)
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
            target_ally=ally,
        )

        self.assertEqual(declaration.action_kind, BattleActionKind.SUPPORT)
        self.assertEqual(declaration.target_ally, ally)

    def test_redeclare_updates_existing(self) -> None:
        """A second declare in the same round replaces the first."""
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        self.assertEqual(declaration.action_kind, BattleActionKind.STRIKE)
        # Only one declaration per (round, participant)
        self.assertEqual(self.battle_round.declarations.count(), 1)

    def test_declare_raises_when_no_open_round(self) -> None:
        from world.battles.exceptions import RoundNotOpenError
        from world.battles.services import declare_battle_action

        # Complete the round to close declarations
        self.battle_round.status = RoundStatus.COMPLETED
        self.battle_round.save()

        with self.assertRaises(RoundNotOpenError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
            )

    def test_declare_raises_when_character_does_not_know_technique(self) -> None:
        from world.battles.exceptions import CharacterDoesNotKnowTechniqueError
        from world.battles.services import declare_battle_action
        from world.magic.factories import TechniqueFactory

        unknown_technique = TechniqueFactory()
        with self.assertRaises(CharacterDoesNotKnowTechniqueError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=unknown_technique,
                target_unit=self.unit,
            )

    def test_declare_raises_when_technique_has_no_action_template(self) -> None:
        from world.battles.exceptions import TechniqueNotBattleReadyError
        from world.battles.services import declare_battle_action
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        # Default TechniqueFactory leaves action_template unset (None).
        bare_technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.sheet, technique=bare_technique)
        with self.assertRaises(TechniqueNotBattleReadyError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=bare_technique,
                target_unit=self.unit,
            )

    def test_repel_requires_place_scope(self) -> None:
        from world.battles.exceptions import PlaceScopeRequiredError
        from world.battles.services import declare_battle_action

        with self.assertRaises(PlaceScopeRequiredError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.REPEL,
                technique=self.technique,
            )

    def test_hold_requires_place_scope(self) -> None:
        from world.battles.exceptions import PlaceScopeRequiredError
        from world.battles.services import declare_battle_action

        with self.assertRaises(PlaceScopeRequiredError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.HOLD,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=self.side,
            )

    def test_repel_with_place_scope_and_target_succeeds(self) -> None:
        from world.battles.services import declare_battle_action

        # PLACE scope requires an engaged command-hierarchy tier (#1710); grant
        # self.participant a SUBORDINATE role on a covenant fielding self.side
        # so the authorization check in _validate_command_scope passes.
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save()
        rank = CovenantRankFactory(covenant=covenant)
        role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="repel-place-scope-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        place = BattlePlaceFactory(battle=self.battle)
        decl = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.REPEL,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )
        self.assertEqual(decl.action_kind, BattleActionKind.REPEL)
        self.assertEqual(decl.target_place_id, place.pk)


class DeclareBattleActionFortificationTests(TestCase):
    """BREACH/FORTIFY target validation on declare_battle_action (#1713)."""

    def setUp(self) -> None:
        from actions.factories import ActionTemplateFactory
        from world.battles.services import create_battle
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        self.battle = create_battle(name="Fortification Declaration Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.attacker_sheet = CharacterSheetFactory()
        self.defender_sheet = CharacterSheetFactory()
        self.attacker_participant = enlist_participant(
            battle=self.battle, character_sheet=self.attacker_sheet, side=self.attacker_side
        )
        self.defender_participant = enlist_participant(
            battle=self.battle, character_sheet=self.defender_sheet, side=self.defender_side
        )
        self.place = BattlePlaceFactory(battle=self.battle)
        self.fort = FortificationFactory(place=self.place, defending_side=self.defender_side)
        self.battle_round = begin_battle_round(battle=self.battle)
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.attacker_sheet, technique=self.technique)
        CharacterTechniqueFactory(character=self.defender_sheet, technique=self.technique)

    def test_breach_requires_target_fortification(self) -> None:
        with self.assertRaises(FortificationTargetRequiredError):
            declare_battle_action(
                participant=self.attacker_participant,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
            )

    def test_fortify_requires_target_fortification(self) -> None:
        with self.assertRaises(FortificationTargetRequiredError):
            declare_battle_action(
                participant=self.defender_participant,
                action_kind=BattleActionKind.FORTIFY,
                technique=self.technique,
            )

    def test_breach_own_fortification_raises(self) -> None:
        with self.assertRaises(FortificationOwnershipMismatchError):
            declare_battle_action(
                participant=self.defender_participant,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
                target_fortification=self.fort,
            )

    def test_fortify_enemy_fortification_raises(self) -> None:
        with self.assertRaises(FortificationOwnershipMismatchError):
            declare_battle_action(
                participant=self.attacker_participant,
                action_kind=BattleActionKind.FORTIFY,
                technique=self.technique,
                target_fortification=self.fort,
            )

    def test_breach_already_breached_raises(self) -> None:
        self.fort.breached = True
        self.fort.save(update_fields=["breached"])
        with self.assertRaises(FortificationAlreadyBreachedError):
            declare_battle_action(
                participant=self.attacker_participant,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
                target_fortification=self.fort,
            )

    def test_fortify_already_breached_raises(self) -> None:
        self.fort.breached = True
        self.fort.save(update_fields=["breached"])
        with self.assertRaises(FortificationAlreadyBreachedError):
            declare_battle_action(
                participant=self.defender_participant,
                action_kind=BattleActionKind.FORTIFY,
                technique=self.technique,
                target_fortification=self.fort,
            )

    def test_valid_breach_declares_successfully(self) -> None:
        declaration = declare_battle_action(
            participant=self.attacker_participant,
            action_kind=BattleActionKind.BREACH,
            technique=self.technique,
            target_fortification=self.fort,
        )
        self.assertEqual(declaration.action_kind, BattleActionKind.BREACH)
        self.assertEqual(declaration.target_fortification_id, self.fort.pk)

    def test_valid_fortify_declares_successfully(self) -> None:
        declaration = declare_battle_action(
            participant=self.defender_participant,
            action_kind=BattleActionKind.FORTIFY,
            technique=self.technique,
            target_fortification=self.fort,
        )
        self.assertEqual(declaration.action_kind, BattleActionKind.FORTIFY)
        self.assertEqual(declaration.target_fortification_id, self.fort.pk)


class ScopePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.battle = BattleFactory()
        cls.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        cls.side = BattleSideFactory(battle=cls.battle, covenant=cls.covenant)
        cls.no_covenant_side = BattleSideFactory(battle=cls.battle, role=BattleSideRole.DEFENDER)
        cls.rank = CovenantRankFactory(covenant=cls.covenant)
        cls.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        cls.supreme_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="scope-test-supreme",
        )

    def _enlist(self, side):
        sheet = CharacterSheetFactory()
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        participant = BattleParticipantFactory(battle=self.battle, side=side, character_sheet=sheet)
        BattleRoundFactory(battle=self.battle, status=RoundStatus.DECLARING)
        return participant, sheet

    def test_side_scope_requires_supreme_command(self) -> None:
        participant, _sheet = self._enlist(self.side)
        with self.assertRaises(InsufficientCommandTierError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=self.side,
            )

    def test_side_scope_allowed_for_engaged_supreme_commander(self) -> None:
        participant, sheet = self._enlist(self.side)
        membership = CharacterCovenantRole.objects.create(
            character_sheet=sheet,
            covenant_role=self.supreme_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        # Target the enemy side, not the commander's own side (#1710 Finding 2:
        # STRIKE against target_side == participant's own side is rejected).
        decl = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            scope=BattleActionScope.SIDE,
            target_side=self.no_covenant_side,
        )
        self.assertEqual(decl.scope, BattleActionScope.SIDE)

    def test_side_scope_rejected_with_no_covenant_on_side(self) -> None:
        participant, _sheet = self._enlist(self.no_covenant_side)
        with self.assertRaises(NoCommandHierarchyError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=self.no_covenant_side,
            )

    def test_unit_scope_unaffected_by_command_tier(self) -> None:
        participant, _sheet = self._enlist(self.side)
        unit = BattleUnitFactory(battle=self.battle, side=self.side)
        decl = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )
        self.assertEqual(decl.scope, BattleActionScope.UNIT)

    def _enlist_with_engaged_supreme_command(self, side):
        """Enlist a participant on *side* holding an engaged SUPREME command tier.

        Isolates the missing-target / own-side checks below from the separate
        command-tier check (_validate_command_scope), which is covered by the
        tests above.
        """
        participant, sheet = self._enlist(side)
        membership = CharacterCovenantRole.objects.create(
            character_sheet=sheet,
            covenant_role=self.supreme_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        return participant

    def test_side_scope_missing_target_raises(self) -> None:
        participant = self._enlist_with_engaged_supreme_command(self.side)
        with self.assertRaises(MissingScopeTargetError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=None,
            )

    def test_place_scope_missing_target_raises(self) -> None:
        participant = self._enlist_with_engaged_supreme_command(self.side)
        with self.assertRaises(MissingScopeTargetError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                scope=BattleActionScope.PLACE,
                target_place=None,
            )

    def test_side_scope_strike_own_side_raises(self) -> None:
        participant = self._enlist_with_engaged_supreme_command(self.side)
        with self.assertRaises(CannotStrikeOwnSideError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=self.side,
            )

    def test_side_scope_rout_own_side_raises(self) -> None:
        """ROUT excludes the caster's own side at resolution (#1712's
        _resolve_rout_success), so declare-time must reject it too — the same
        guard as STRIKE (#1710 Finding 2)."""
        participant = self._enlist_with_engaged_supreme_command(self.side)
        with self.assertRaises(CannotStrikeOwnSideError):
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.ROUT,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_side=self.side,
            )


class ComputeUnitStatusTests(TestCase):
    def test_destroyed_only_from_zero_strength(self) -> None:
        from world.battles.constants import BattleUnitStatus
        from world.battles.resolution import _compute_unit_status

        self.assertEqual(_compute_unit_status(0, 100), BattleUnitStatus.DESTROYED)
        # Zero morale never destroys — it routs, since strength is still nonzero.
        self.assertEqual(_compute_unit_status(50, 0), BattleUnitStatus.ROUTED)

    def test_routed_from_either_axis(self) -> None:
        from world.battles.constants import (
            ROUTED_MORALE_THRESHOLD,
            ROUTED_STRENGTH_THRESHOLD,
            BattleUnitStatus,
        )
        from world.battles.resolution import _compute_unit_status

        self.assertEqual(
            _compute_unit_status(ROUTED_STRENGTH_THRESHOLD, 100), BattleUnitStatus.ROUTED
        )
        self.assertEqual(
            _compute_unit_status(100, ROUTED_MORALE_THRESHOLD), BattleUnitStatus.ROUTED
        )

    def test_active_when_both_axes_healthy(self) -> None:
        from world.battles.constants import BattleUnitStatus
        from world.battles.resolution import _compute_unit_status

        self.assertEqual(_compute_unit_status(100, 100), BattleUnitStatus.ACTIVE)


class ResolveBattleRoundSuccessTests(TestCase):
    """STRIKE success: unit strength drops, side VP increases, no PC damage."""

    def setUp(self) -> None:
        from world.battles.services import create_battle
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Resolution Success Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Skeleton Horde",
            descriptor="undead",
            strength=100,
        )

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_strike_success_reduces_unit_strength_and_awards_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        success_level = 5
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            result = resolve_battle_round(battle_round=self.battle_round)

        self.unit.refresh_from_db()
        expected_attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
        self.assertEqual(self.unit.strength, 100 - expected_attrition)

        self.attacker_side.refresh_from_db()
        expected_vp = success_level * STRIKE_VP_PER_LEVEL
        self.assertEqual(self.attacker_side.victory_points, expected_vp)

        self.assertIn(self.attacker_side.pk, result.vp_awarded)
        self.assertEqual(result.vp_awarded[self.attacker_side.pk], expected_vp)

        # Round should be COMPLETED
        self.battle_round.refresh_from_db()
        self.assertEqual(self.battle_round.status, RoundStatus.COMPLETED)

        # Health should be unchanged (success)
        vitals = self.sheet.vitals
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100)

    def test_strike_success_marks_declaration_resolved(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result()
            resolve_battle_round(battle_round=self.battle_round)

        declare.refresh_from_db()
        self.assertTrue(declare.resolved)
        self.assertGreater(declare.success_level, 0)

    def test_side_scope_strike_attrites_every_unit_on_target_side(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_strike_success

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        unit_a = BattleUnitFactory(
            battle=battle, side=side, military_unit=MilitaryUnitFactory(strength=100)
        )
        unit_b = BattleUnitFactory(
            battle=battle, side=side, military_unit=MilitaryUnitFactory(strength=100)
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            action_kind=BattleActionKind.STRIKE,
            scope=BattleActionScope.SIDE,
            target_side=side,
        )
        result = BattleRoundResult()

        _resolve_strike_success(declaration, result, success_level=2)

        unit_a.refresh_from_db()
        unit_b.refresh_from_db()
        self.assertEqual(unit_a.strength, 100 - 2 * STRIKE_ATTRITION_PER_LEVEL)
        self.assertEqual(unit_b.strength, 100 - 2 * STRIKE_ATTRITION_PER_LEVEL)

    def test_side_scope_strike_excludes_casters_own_side_unit(self) -> None:
        """STRIKE at SIDE/PLACE scope must never attrite the caster's own side (#1710).

        Defensive regression: even if a declaration is (mis)constructed with
        target_side equal to the declaring participant's own side, the resolver
        must filter that unit out rather than attrite it (friendly fire).
        """
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_strike_success

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        own_unit = BattleUnitFactory(
            battle=battle, side=side, military_unit=MilitaryUnitFactory(strength=100)
        )
        participant = BattleParticipantFactory(battle=battle, side=side)
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            scope=BattleActionScope.SIDE,
            target_side=side,
        )
        result = BattleRoundResult()

        _resolve_strike_success(declaration, result, success_level=2)

        own_unit.refresh_from_db()
        self.assertEqual(own_unit.strength, 100)
        self.assertNotIn(side.pk, result.vp_awarded)

    def test_strike_success_still_routes_when_morale_already_low(self) -> None:
        """A unit already broken on morale (from a prior ROUT, say) should flip to
        ROUTED from a STRIKE hit too small to cross the strength threshold alone."""
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        self.unit.military_unit.morale = 20  # already below ROUTED_MORALE_THRESHOLD (25)
        self.unit.military_unit.save(update_fields=["morale"])

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(1)  # small hit: 10 attrition, strength 90
            resolve_battle_round(battle_round=self.battle_round)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.strength, 90)  # well above ROUTED_STRENGTH_THRESHOLD
        self.assertEqual(self.unit.status, BattleUnitStatus.ROUTED)  # but morale forces it


class ResolveBattleRoundSupportTests(TestCase):
    """SUPPORT success: side VP increases by SUPPORT_VP."""

    def setUp(self) -> None:
        from world.battles.services import create_battle
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Support Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_support_success_awards_support_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result()
            resolve_battle_round(battle_round=self.battle_round)

        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, SUPPORT_VP)


class RoutResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.attacker_side)
        self.enemy_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            military_unit=MilitaryUnitFactory(strength=100, morale=70),
        )

    def test_rout_success_damages_morale_and_awards_vp(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rout_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.ROUT,
            target_unit=self.enemy_unit,
        )
        result = BattleRoundResult()

        _resolve_rout_success(declaration, result, success_level=3)

        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.enemy_unit.morale, 70 - 3 * ROUT_MORALE_PER_LEVEL)
        self.assertEqual(self.enemy_unit.strength, 100)  # ROUT never touches strength

        self.attacker_side.refresh_from_db()
        self.assertEqual(self.attacker_side.victory_points, 3 * ROUT_VP_PER_LEVEL)

    def test_rout_can_flip_unit_to_routed(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rout_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.ROUT,
            target_unit=self.enemy_unit,
        )
        result = BattleRoundResult()

        _resolve_rout_success(declaration, result, success_level=5)  # 75 morale damage

        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.enemy_unit.morale, 0)
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.ROUTED)
        self.assertIn(self.enemy_unit.pk, result.units_routed)

    def test_rout_excludes_casters_own_side(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rout_success

        own_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.attacker_side,
            military_unit=MilitaryUnitFactory(strength=100, morale=70),
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.ROUT,
            scope=BattleActionScope.SIDE,
            target_side=self.attacker_side,
        )
        result = BattleRoundResult()

        _resolve_rout_success(declaration, result, success_level=3)

        own_unit.refresh_from_db()
        self.assertEqual(own_unit.morale, 70)  # untouched
        self.assertNotIn(self.attacker_side.pk, result.vp_awarded)


class RallyResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)

    def test_rally_success_restores_morale_and_awards_flat_vp(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rally_success

        unit = BattleUnitFactory(
            battle=self.battle,
            side=self.side,
            military_unit=MilitaryUnitFactory(strength=100, morale=10),
            status=BattleUnitStatus.ROUTED,
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.RALLY,
            target_unit=unit,
        )
        result = BattleRoundResult()

        _resolve_rally_success(declaration, result, success_level=2)

        unit.refresh_from_db()
        self.assertEqual(unit.morale, 10 + 2 * RALLY_MORALE_PER_LEVEL)
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)

        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, RALLY_VP)

    def test_rally_clamps_morale_at_max(self) -> None:
        from world.battles.constants import MAX_MORALE
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rally_success

        unit = BattleUnitFactory(
            battle=self.battle,
            side=self.side,
            military_unit=MilitaryUnitFactory(morale=95),
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.RALLY,
            target_unit=unit,
        )
        result = BattleRoundResult()

        _resolve_rally_success(declaration, result, success_level=5)

        unit.refresh_from_db()
        self.assertEqual(unit.morale, MAX_MORALE)

    def test_rally_cannot_recover_a_unit_routed_by_low_strength(self) -> None:
        """RALLY only recovers units broken by morale collapse, not attrition."""
        from world.battles.constants import MAX_MORALE
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rally_success

        unit = BattleUnitFactory(
            battle=self.battle,
            side=self.side,
            military_unit=MilitaryUnitFactory(strength=20, morale=70),
            status=BattleUnitStatus.ROUTED,
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.RALLY,
            target_unit=unit,
        )
        result = BattleRoundResult()

        _resolve_rally_success(declaration, result, success_level=5)

        unit.refresh_from_db()
        self.assertEqual(unit.morale, MAX_MORALE)  # morale side is fully healed...
        # ...but strength still holds it back
        self.assertEqual(unit.status, BattleUnitStatus.ROUTED)

    def test_rally_excludes_enemy_units(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rally_success

        enemy_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        enemy_unit = BattleUnitFactory(
            battle=self.battle,
            side=enemy_side,
            military_unit=MilitaryUnitFactory(morale=10),
            status=BattleUnitStatus.ROUTED,
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.RALLY,
            scope=BattleActionScope.SIDE,
            target_side=enemy_side,
        )
        result = BattleRoundResult()

        _resolve_rally_success(declaration, result, success_level=3)

        enemy_unit.refresh_from_db()
        self.assertEqual(enemy_unit.morale, 10)  # untouched
        self.assertNotIn(self.side.pk, result.vp_awarded)

    def test_place_scope_rally_reaches_routed_units(self) -> None:
        """_scope_target_units(include_routed=True) must include ROUTED units, not
        just ACTIVE ones — RALLY's whole purpose is reaching already-broken units."""
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_rally_success

        place = BattlePlaceFactory(battle=self.battle)
        routed_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.side,
            place=place,
            military_unit=MilitaryUnitFactory(morale=10),
            status=BattleUnitStatus.ROUTED,
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.RALLY,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )
        result = BattleRoundResult()

        _resolve_rally_success(declaration, result, success_level=2)

        routed_unit.refresh_from_db()
        self.assertEqual(routed_unit.morale, 10 + 2 * RALLY_MORALE_PER_LEVEL)


class RepelResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.defender_side)

    def test_repel_success_raises_place_defense_bonus_and_awards_vp(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_repel_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.REPEL,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )
        result = BattleRoundResult()
        place_defense_bonus: dict[int, int] = {}

        _resolve_repel_success(declaration, result, place_defense_bonus)

        self.assertEqual(place_defense_bonus[self.place.pk], REPEL_DEFENSE_BONUS)
        self.defender_side.refresh_from_db()
        self.assertEqual(self.defender_side.victory_points, REPEL_VP)

    def test_repel_declared_this_round_reduces_strike_attrition_same_round(self) -> None:
        """End-to-end through resolve_battle_round: a REPEL at a place must resolve
        before an enemy STRIKE against a unit there in the same round (#1712)."""
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        defender_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            place=self.place,
            military_unit=MilitaryUnitFactory(strength=100),
        )
        attacker_participant = BattleParticipantFactory(battle=self.battle, side=self.attacker_side)
        # The REPEL declarant is created *after* attacker_participant, so it has a
        # higher pk. BattleActionDeclaration.Meta.ordering sorts by (battle_round,
        # participant) — i.e. by participant pk — so without this ordering, the
        # DB's default retrieval order would already put STRIKE (lower pk) ahead
        # of REPEL (higher pk), same as the resolution the sort is meant to
        # enforce. Only resolve_battle_round's explicit REPEL-first
        # `.sort(...)` — not incidental pk/insertion order — can make the
        # assertion below pass (#1712 final review Finding 2). self.participant
        # is intentionally unused here: it's created in setUp (before this
        # method runs) and would always sort first regardless of the sort call.
        repel_participant = BattleParticipantFactory(battle=self.battle, side=self.defender_side)
        technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=repel_participant.character_sheet, technique=technique)
        CharacterTechniqueFactory(
            character=attacker_participant.character_sheet, technique=technique
        )
        CharacterAnimaFactory(character=repel_participant.character_sheet.character)
        CharacterAnimaFactory(character=attacker_participant.character_sheet.character)
        battle_round = begin_battle_round(battle=self.battle)

        # PLACE scope requires an engaged command-hierarchy tier (#1710); grant
        # repel_participant a SUBORDINATE role on a covenant fielding self.defender_side
        # so the authorization check in _validate_command_scope passes.
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save()
        rank = CovenantRankFactory(covenant=covenant)
        role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="repel-e2e-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=repel_participant.character_sheet,
            covenant_role=role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        # Declare STRIKE before REPEL (opposite of resolution order) so that only
        # resolve_battle_round's explicit REPEL-first sort — not incidental
        # declaration-insertion order — can make the assertion below pass
        # (#1712 final review Finding 2).
        declare_battle_action(
            participant=attacker_participant,
            action_kind=BattleActionKind.STRIKE,
            technique=technique,
            target_unit=defender_unit,
        )
        declare_battle_action(
            participant=repel_participant,
            action_kind=BattleActionKind.REPEL,
            technique=technique,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(2)  # both declarations succeed
            resolve_battle_round(battle_round=battle_round)

        defender_unit.refresh_from_db()
        expected_attrition = max(0, 2 * STRIKE_ATTRITION_PER_LEVEL - REPEL_DEFENSE_BONUS)
        self.assertEqual(defender_unit.strength, 100 - expected_attrition)


class HoldResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.enemy_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)

    def test_hold_captures_uncontrolled_place_and_awards_capture_vp(self) -> None:
        from world.battles.constants import HOLD_CAPTURE_VP
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_hold_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.HOLD,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )
        result = BattleRoundResult()

        _resolve_hold_success(declaration, result)

        self.place.refresh_from_db()
        self.assertEqual(self.place.controlled_by_id, self.side.pk)
        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, HOLD_CAPTURE_VP)

    def test_hold_sustains_already_controlled_place_with_smaller_vp(self) -> None:
        from world.battles.constants import HOLD_SUSTAIN_VP
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_hold_success

        self.place.controlled_by = self.side
        self.place.save(update_fields=["controlled_by"])
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.HOLD,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )
        result = BattleRoundResult()

        _resolve_hold_success(declaration, result)

        self.place.refresh_from_db()
        self.assertEqual(self.place.controlled_by_id, self.side.pk)  # unchanged
        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, HOLD_SUSTAIN_VP)

    def test_hold_captures_from_enemy_control(self) -> None:
        from world.battles.constants import HOLD_CAPTURE_VP
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_hold_success

        self.place.controlled_by = self.enemy_side
        self.place.save(update_fields=["controlled_by"])
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.HOLD,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )
        result = BattleRoundResult()

        _resolve_hold_success(declaration, result)

        self.place.refresh_from_db()
        self.assertEqual(self.place.controlled_by_id, self.side.pk)
        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, HOLD_CAPTURE_VP)

    def test_hold_declared_this_round_captures_place_end_to_end(self) -> None:
        """End-to-end through resolve_battle_round: a HOLD declaration dispatched by
        _dispatch_success_handler must actually capture the place and award VP (#1712)."""
        from world.battles.constants import BATTLE_POSTURE_VP_MULTIPLIER, HOLD_CAPTURE_VP
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.participant.character_sheet, technique=technique)
        CharacterAnimaFactory(character=self.participant.character_sheet.character)
        battle_round = begin_battle_round(battle=self.battle)

        # PLACE scope requires an engaged command-hierarchy tier (#1710); grant
        # self.participant a SUBORDINATE role on a covenant fielding self.side
        # so the authorization check in _validate_command_scope passes.
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save()
        rank = CovenantRankFactory(covenant=covenant)
        role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="hold-e2e-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.participant.character_sheet,
            covenant_role=role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.HOLD,
            technique=technique,
            scope=BattleActionScope.PLACE,
            target_place=self.place,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(2)
            resolve_battle_round(battle_round=battle_round)

        self.place.refresh_from_db()
        self.assertEqual(self.place.controlled_by_id, self.side.pk)
        self.side.refresh_from_db()
        expected_vp = round(
            HOLD_CAPTURE_VP * BATTLE_POSTURE_VP_MULTIPLIER.get(self.side.posture, 1.0)
        )
        self.assertEqual(self.side.victory_points, expected_vp)


class BreachResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.attacker_side)
        self.fort = FortificationFactory(
            place=self.place, defending_side=self.defender_side, integrity=25, max_integrity=100
        )

    def test_breach_attrites_integrity_and_awards_vp(self) -> None:
        from world.battles.constants import BREACH_INTEGRITY_PER_LEVEL, BREACH_VP_PER_LEVEL
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_breach_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.BREACH,
            target_fortification=self.fort,
        )
        result = BattleRoundResult()

        _resolve_breach_success(declaration, result, success_level=1)

        self.fort.refresh_from_db()
        self.assertEqual(self.fort.integrity, 25 - BREACH_INTEGRITY_PER_LEVEL)
        self.assertFalse(self.fort.breached)

        self.attacker_side.refresh_from_db()
        self.assertEqual(self.attacker_side.victory_points, BREACH_VP_PER_LEVEL)
        self.assertEqual(result.vp_awarded[self.attacker_side.pk], BREACH_VP_PER_LEVEL)

    def test_breach_to_zero_sets_breached(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_breach_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.BREACH,
            target_fortification=self.fort,
        )
        result = BattleRoundResult()

        _resolve_breach_success(declaration, result, success_level=3)  # 3*10=30 > 25

        self.fort.refresh_from_db()
        self.assertEqual(self.fort.integrity, 0)
        self.assertTrue(self.fort.breached)


class BreachEjectsVehicleOccupantsTests(TestCase):
    """Hull breach ejects embarked occupants and clears their place (#1714)."""

    def setUp(self) -> None:
        from world.battles.services import create_battle, create_battle_vehicle

        self.battle = create_battle(name="Hull Breach Ejection Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.attacker_sheet = CharacterSheetFactory()
        self.attacker_participant = enlist_participant(
            battle=self.battle, character_sheet=self.attacker_sheet, side=self.attacker_side
        )

        self.vehicle = create_battle_vehicle(
            battle=self.battle, side=self.defender_side, place_name="The Gull"
        )
        self.fort = self.vehicle.place.fortifications.get()

        self.passenger = BattleParticipantFactory(
            battle=self.battle, side=self.defender_side, place=self.vehicle.place
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.attacker_sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.attacker_sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_breach_to_zero_ejects_embarked_participant(self) -> None:
        from world.battles.resolution import resolve_battle_round

        declare_battle_action(
            participant=self.attacker_participant,
            action_kind=BattleActionKind.BREACH,
            technique=self.technique,
            target_fortification=self.fort,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(12)  # 12*10=120 >= 120 hull integrity
            resolve_battle_round(battle_round=self.battle_round)

        self.fort.refresh_from_db()
        self.assertTrue(self.fort.breached)

        self.passenger.refresh_from_db()
        self.assertIsNone(self.passenger.place)


class StrikeDestroysLivingMountEjectsOccupantsTests(TestCase):
    """A living-mount BattleVehicle (dragon/kraken) has no hull Fortification to
    BREACH — destruction routes through its own BattleUnit hitting strength 0 via
    STRIKE instead (#1714)."""

    def setUp(self) -> None:
        from world.battles.services import create_battle, create_battle_vehicle

        self.battle = create_battle(name="Dragon Rider Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.attacker_sheet = CharacterSheetFactory()
        self.attacker_participant = enlist_participant(
            battle=self.battle, character_sheet=self.attacker_sheet, side=self.attacker_side
        )

        self.vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.defender_side,
            place_name="The Wyrm",
            vehicle_kind=VehicleKind.DRAGON,
            is_structural=False,
        )
        self.rider = BattleParticipantFactory(
            battle=self.battle, side=self.defender_side, place=self.vehicle.place
        )

        # Drive the mount's own unit down near death so a single STRIKE success
        # finishes it off (default strength=100; STRIKE_ATTRITION_PER_LEVEL=10).
        self.vehicle.unit.military_unit.strength = 5
        self.vehicle.unit.military_unit.save(update_fields=["strength"])

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.attacker_sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.attacker_sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_strike_destroys_living_mount_ejects_rider(self) -> None:
        from world.battles.resolution import resolve_battle_round

        declare_battle_action(
            participant=self.attacker_participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.vehicle.unit,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(5)  # 5*10=50 >= strength 5
            resolve_battle_round(battle_round=self.battle_round)

        self.vehicle.unit.refresh_from_db()
        self.assertEqual(self.vehicle.unit.status, BattleUnitStatus.DESTROYED)

        self.rider.refresh_from_db()
        self.assertIsNone(self.rider.place)


class FortifyResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)
        self.fort = FortificationFactory(
            place=self.place, defending_side=self.side, integrity=50, max_integrity=100
        )

    def test_fortify_restores_integrity_and_awards_flat_vp(self) -> None:
        from world.battles.constants import FORTIFY_INTEGRITY_PER_LEVEL, FORTIFY_VP
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_fortify_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.FORTIFY,
            target_fortification=self.fort,
        )
        result = BattleRoundResult()

        _resolve_fortify_success(declaration, result, success_level=1)

        self.fort.refresh_from_db()
        self.assertEqual(self.fort.integrity, 50 + FORTIFY_INTEGRITY_PER_LEVEL)

        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, FORTIFY_VP)
        self.assertEqual(result.vp_awarded[self.side.pk], FORTIFY_VP)

    def test_fortify_caps_at_max_integrity(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory
        from world.battles.resolution import BattleRoundResult, _resolve_fortify_success

        declaration = BattleActionDeclarationFactory(
            battle_round__battle=self.battle,
            participant=self.participant,
            action_kind=BattleActionKind.FORTIFY,
            target_fortification=self.fort,
        )
        result = BattleRoundResult()

        _resolve_fortify_success(declaration, result, success_level=10)  # would overshoot

        self.fort.refresh_from_db()
        self.assertEqual(self.fort.integrity, self.fort.max_integrity)


class ResolveBattleRoundFailureTests(TestCase):
    """STRIKE failure: PC health debited."""

    def setUp(self) -> None:
        from world.battles.services import create_battle
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Failure Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Zombie Wall",
            descriptor="undead",
        )
        self.battle_round = begin_battle_round(battle=self.battle)

    def test_failure_debits_pc_health(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=self.battle_round)

        self.vitals.refresh_from_db()
        expected_damage = BASE_FAILURE_DAMAGE + abs(failure_level)
        self.assertEqual(self.vitals.health, 100 - expected_damage)

        # VP should be unchanged (failure)
        self.attacker_side.refresh_from_db()
        self.assertEqual(self.attacker_side.victory_points, 0)

        # Unit strength should be unchanged (failure)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.strength, 100)

    def test_failure_records_success_level(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        decl = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )
        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=self.battle_round)

        decl.refresh_from_db()
        self.assertTrue(decl.resolved)
        self.assertEqual(decl.success_level, failure_level)


class BattleRoundAudereWiringTests(TestCase):
    """Proves resolve_battle_round routes through use_technique, which fires the
    Audere Majora hook (Step 8c) automatically — no battle-specific wiring needed.
    """

    def setUp(self) -> None:
        from world.battles.services import create_battle
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory
        from world.traits.factories import CheckSystemSetupFactory

        CheckSystemSetupFactory.create()

        self.battle = create_battle(name="Audere Wiring Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(),
            damage_profile=False,
            intensity=5,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_resolve_battle_round_calls_audere_majora_hook(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        # maybe_create_audere_majora_offer is imported function-locally inside
        # use_technique (world/magic/services/techniques.py:1094), not at module
        # level — repo convention for lazy imports is to patch the ORIGIN module
        # so the call-time `from X import Y` re-binds to the patched callable
        # (see reference-module-import-breaks-origin-patch memory).
        with patch("world.magic.audere_majora.maybe_create_audere_majora_offer") as mock_audere:
            resolve_battle_round(battle_round=self.battle_round)

        mock_audere.assert_called_once()
        called_character, called_intensity = mock_audere.call_args[0]
        self.assertEqual(called_character, self.sheet.character)
        self.assertEqual(called_intensity, self.technique.intensity)


class IsolationAndMobilityTests(TestCase):
    def test_is_isolated_true_with_no_ally_at_place(self) -> None:
        from world.battles.resolution import _is_isolated
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Isolation Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        sheet = CharacterSheetFactory()
        participant = enlist_participant(
            battle=battle, character_sheet=sheet, side=side, place=place
        )
        assert _is_isolated(participant) is True

    def test_is_isolated_false_with_ally_at_same_place(self) -> None:
        from world.battles.resolution import _is_isolated
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Isolation Test 2")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        p1 = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=side, place=place
        )
        enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=side, place=place
        )
        assert _is_isolated(p1) is False


class SelectSurroundedTerminalPoolTests(TestCase):
    def test_routes_to_enemy_pool_when_no_pc_opposes_at_place(self) -> None:
        from world.battles.resolution import select_surrounded_terminal_pool
        from world.battles.services import add_place, create_battle
        from world.vitals.factories import ensure_surrounded_content

        content = ensure_surrounded_content()
        battle = create_battle(name="Routing Test")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        participant = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=attacker, place=place
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
        assert pool == content["pools"]["surrounded_terminal_enemy"]

    def test_routes_to_pvp_pool_when_opposing_pc_present_at_place(self) -> None:
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.battles.resolution import select_surrounded_terminal_pool
        from world.battles.services import add_place, create_battle
        from world.vitals.factories import ensure_surrounded_content

        content = ensure_surrounded_content()
        battle = create_battle(name="Routing Test 2")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defender = add_side(battle=battle, role=BattleSideRole.DEFENDER)
        place = add_place(battle=battle, name="The Gates")
        participant = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=attacker, place=place
        )
        # A bare CharacterSheetFactory() character has db_account=None (NPC by
        # convention — see world/vitals/peril_resolution.py:is_pc_source); attach a
        # real account so this participant is classified as an opposing PC.
        pc_character = CharacterFactory()
        pc_character.db_account = AccountFactory()
        pc_character.save()
        enlist_participant(
            battle=battle,
            character_sheet=CharacterSheetFactory(character=pc_character),
            side=defender,
            place=place,
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
        assert pool == content["pools"]["surrounded_terminal_pvp"]


class EntryRollTests(TestCase):
    def setUp(self) -> None:
        self.content = ensure_surrounded_content()

    @tag("postgres")
    def test_isolated_failure_can_apply_surrounded(self) -> None:
        """With the check patched to force the Failure tier, an isolated STRIKE
        failure applies Surrounded via the entry pool's 'surrounded' row.

        PG-only (@tag("postgres")): this test exercises the real production
        _maybe_apply_surrounded -> apply_condition path, which routes through
        _build_bulk_context's PG-only DISTINCT ON query and errors on the SQLite
        fast tier (same known trap Task 3's regression test and Task 7's
        EscalationTickTests fixture route around — here the call is inside the
        code under test, so it can't be avoided). Verify via
        `just test-parity world.battles` or CI's Postgres shard, not
        `just test-fast`.
        """
        from world.battles.constants import BattleActionKind, BattleSideRole
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_place,
            add_side,
            add_unit,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )
        from world.conditions.services import get_active_conditions

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        technique = TechniqueFactory(action_template=ActionTemplateFactory(), damage_profile=False)
        CharacterTechniqueFactory(character=sheet, technique=technique)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=30)

        battle = create_battle(name="Entry Roll Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        unit = add_unit(battle=battle, side=side, name="Foes", descriptor="infantry")
        participant = enlist_participant(
            battle=battle, character_sheet=sheet, side=side, place=place
        )
        battle_round = begin_battle_round(battle=battle)
        declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=technique,
            target_unit=unit,
        )

        # Two DISTINCT perform_check call sites are involved and must be patched
        # separately: (1) resolve_battle_technique's own STRIKE check (patched directly
        # by replacing resolve_battle_technique itself, same as the existing
        # test_resolution.py convention); (2) the entry roll's check, which runs through
        # select_consequence -> world.checks.consequence_resolution.perform_check (a
        # DIFFERENT imported name than world.battles.resolution.perform_check — patching
        # the wrong one silently no-ops the entry roll). Force the entry roll's outcome
        # tier to Failure so it lands in the pool's "surrounded" row.
        from world.traits.models import CheckOutcome

        failure_outcome = CheckOutcome.objects.get(name="Failure")
        entry_check_result = MagicMock(outcome=failure_outcome, success_level=-1)

        with (
            patch(
                "world.battles.resolution.resolve_battle_technique",
                return_value=_failure_result(-10),
            ),
            patch(
                "world.checks.consequence_resolution.perform_check",
                return_value=entry_check_result,
            ),
        ):
            resolve_battle_round(battle_round=battle_round)

        instance = get_active_conditions(
            sheet.character, condition=self.content["condition"]
        ).first()
        assert instance is not None
        assert instance.current_stage.stage_order == 1


class EscalationTickTests(TestCase):
    def setUp(self) -> None:
        self.content = ensure_surrounded_content()

    def _surrounded_participant(self, battle, side):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        participant = enlist_participant(battle=battle, character_sheet=sheet, side=side)
        # Build the ConditionInstance directly rather than via apply_condition, which
        # routes through _build_bulk_context's PG-only DISTINCT ON query and errors on
        # the SQLite fast tier (known trap — see world/vitals/tests/test_bleed_out.py's
        # module docstring and Task 3's AdvanceStagedPerilTests, which hit this first).
        from world.conditions.factories import ConditionInstanceFactory

        ConditionInstanceFactory(
            target=sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )
        return participant

    def test_surrounded_participant_who_declared_escalates(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
        )
        from world.conditions.services import get_active_conditions

        battle = create_battle(name="Escalation Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = self._surrounded_participant(battle, side)
        technique = TechniqueFactory(action_template=ActionTemplateFactory(), damage_profile=False)
        CharacterTechniqueFactory(character=participant.character_sheet, technique=technique)
        CharacterAnimaFactory(
            character=participant.character_sheet.character, current=20, maximum=30
        )
        battle_round = begin_battle_round(battle=battle)
        declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=technique,
        )

        with (
            patch(
                "world.battles.resolution.resolve_battle_technique",
                return_value=_success_result(3),
            ),
            patch("world.vitals.services.perform_check", return_value=_failure_result(-1)),
        ):
            resolve_battle_round(battle_round=battle_round)

        instance = get_active_conditions(
            participant.character_sheet.character, condition=self.content["condition"]
        ).first()
        assert instance.current_stage.stage_order == 2  # advanced from 1

    def test_surrounded_participant_who_did_not_declare_holds_when_knob_off(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import add_side, begin_battle_round, create_battle
        from world.conditions.services import get_active_conditions

        battle = create_battle(name="Escalation Hold Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = self._surrounded_participant(battle, side)
        battle_round = begin_battle_round(battle=battle)
        # No declaration this round; battle.afk_peril_override defaults False.

        with patch("world.vitals.services.perform_check", return_value=_failure_result(-1)):
            resolve_battle_round(battle_round=battle_round)

        instance = get_active_conditions(
            participant.character_sheet.character, condition=self.content["condition"]
        ).first()
        assert instance.current_stage.stage_order == 1  # held, did not advance

    def test_surrounded_participant_who_did_not_declare_escalates_when_knob_on(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import add_side, begin_battle_round, create_battle
        from world.conditions.services import get_active_conditions

        battle = create_battle(name="Escalation Override Test")
        battle.afk_peril_override = True
        battle.save(update_fields=["afk_peril_override"])
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = self._surrounded_participant(battle, side)
        battle_round = begin_battle_round(battle=battle)

        with patch("world.vitals.services.perform_check", return_value=_failure_result(-1)):
            resolve_battle_round(battle_round=battle_round)

        instance = get_active_conditions(
            participant.character_sheet.character, condition=self.content["condition"]
        ).first()
        assert instance.current_stage.stage_order == 2


class RescueResolutionTests(TestCase):
    def setUp(self) -> None:
        self.content = ensure_surrounded_content()

    def test_successful_rescue_clears_surrounded(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )
        from world.conditions.factories import ConditionInstanceFactory
        from world.conditions.services import get_active_conditions

        battle = create_battle(name="Rescue Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        victim_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=victim_sheet)
        victim = enlist_participant(battle=battle, character_sheet=victim_sheet, side=side)
        # Direct ConditionInstance creation, not apply_condition — apply_condition routes
        # through _build_bulk_context's PG-only DISTINCT ON query and errors on the
        # SQLite fast tier (same known trap as Task 7's fixture; RESCUE's own
        # remove_condition call, exercised below, does NOT hit this path, so this test
        # stays SQLite-safe once setup avoids apply_condition).
        ConditionInstanceFactory(
            target=victim_sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )

        rescuer_sheet = CharacterSheetFactory()
        rescuer = enlist_participant(battle=battle, character_sheet=rescuer_sheet, side=side)
        technique = TechniqueFactory(action_template=ActionTemplateFactory(), damage_profile=False)
        CharacterTechniqueFactory(character=rescuer_sheet, technique=technique)
        CharacterAnimaFactory(character=rescuer_sheet.character, current=20, maximum=30)

        battle_round = begin_battle_round(battle=battle)
        declare_battle_action(
            participant=rescuer,
            action_kind=BattleActionKind.RESCUE,
            technique=technique,
            target_ally=victim,
        )

        with patch(
            "world.battles.resolution.resolve_battle_technique",
            return_value=_success_result(3),
        ):
            resolve_battle_round(battle_round=battle_round)

        assert not get_active_conditions(
            victim_sheet.character, condition=self.content["condition"]
        ).exists()

    def test_place_scope_rescue_clears_surrounded_for_every_ally_at_place(self) -> None:
        from world.battles.factories import (
            BattleActionDeclarationFactory,
            BattlePlaceFactory,
        )
        from world.battles.resolution import _resolve_rescue_success
        from world.conditions.factories import ConditionInstanceFactory
        from world.conditions.services import get_active_conditions

        battle = BattleFactory()
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        ally_a = BattleParticipantFactory(battle=battle, side=side, place=place)
        ally_b = BattleParticipantFactory(battle=battle, side=side, place=place)
        # The declaring (rescuing) participant must be on the SAME side as the allies
        # it rescues — _resolve_rescue_success (#1710 friendly-fire fix) restricts
        # scope fan-out to declaration.participant.side_id.
        rescuer = BattleParticipantFactory(battle=battle, side=side, place=place)
        # ConditionInstanceFactory direct creation, not apply_condition — apply_condition
        # routes through _build_bulk_context's PG-only DISTINCT ON query for progressive
        # conditions (Surrounded is progressive) and errors on the SQLite fast tier (same
        # trap noted above for test_successful_rescue_clears_surrounded).
        ConditionInstanceFactory(
            target=ally_a.character_sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )
        ConditionInstanceFactory(
            target=ally_b.character_sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            participant=rescuer,
            action_kind=BattleActionKind.RESCUE,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )

        _resolve_rescue_success(declaration)

        assert not get_active_conditions(
            ally_a.character_sheet.character, condition=self.content["condition"]
        ).exists()
        assert not get_active_conditions(
            ally_b.character_sheet.character, condition=self.content["condition"]
        ).exists()

    def test_place_scope_rescue_excludes_enemy_participant_at_place(self) -> None:
        """RESCUE at PLACE scope must never clear Surrounded from an enemy (#1710).

        A shared front (BattlePlace) can hold both sides' participants. The
        rescuer's own-side ally should be cleared; an enemy participant Surrounded
        at the same place must be left alone (clearing it would help the enemy).
        """
        from world.battles.factories import (
            BattleActionDeclarationFactory,
            BattlePlaceFactory,
        )
        from world.battles.resolution import _resolve_rescue_success
        from world.conditions.factories import ConditionInstanceFactory
        from world.conditions.services import get_active_conditions

        battle = BattleFactory()
        place = BattlePlaceFactory(battle=battle)
        friendly_side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        enemy_side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        ally = BattleParticipantFactory(battle=battle, side=friendly_side, place=place)
        rescuer = BattleParticipantFactory(battle=battle, side=friendly_side, place=place)
        enemy = BattleParticipantFactory(battle=battle, side=enemy_side, place=place)
        ConditionInstanceFactory(
            target=ally.character_sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )
        ConditionInstanceFactory(
            target=enemy.character_sheet.character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][0],
        )
        declaration = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            participant=rescuer,
            action_kind=BattleActionKind.RESCUE,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )

        _resolve_rescue_success(declaration)

        assert not get_active_conditions(
            ally.character_sheet.character, condition=self.content["condition"]
        ).exists()
        assert get_active_conditions(
            enemy.character_sheet.character, condition=self.content["condition"]
        ).exists()


class PropertyAffinityModifierTests(TestCase):
    def test_returns_zero_when_no_match(self) -> None:
        from world.battles.resolution import _property_affinity_modifier

        technique = TechniqueFactory()
        unit = BattleUnitFactory()
        self.assertEqual(_property_affinity_modifier(technique, unit), 0)

    def test_returns_authored_modifier(self) -> None:
        from world.battles.resolution import _property_affinity_modifier

        technique = TechniqueFactory()
        unit = BattleUnitFactory()
        flying = PropertyFactory(name="flying")
        unit.military_unit.properties.add(flying)
        TechniquePropertyAffinity.objects.create(technique=technique, property=flying, modifier=15)
        self.assertEqual(_property_affinity_modifier(technique, unit), 15)

    def test_sums_across_multiple_matching_properties(self) -> None:
        from world.battles.resolution import _property_affinity_modifier

        technique = TechniqueFactory()
        unit = BattleUnitFactory()
        flying = PropertyFactory(name="flying")
        metal_clad = PropertyFactory(name="metal-clad")
        unit.military_unit.properties.set([flying, metal_clad])
        TechniquePropertyAffinity.objects.create(technique=technique, property=flying, modifier=15)
        TechniquePropertyAffinity.objects.create(
            technique=technique, property=metal_clad, modifier=-5
        )
        self.assertEqual(_property_affinity_modifier(technique, unit), 10)


class TerrainPropertyModifierTests(TestCase):
    def test_returns_zero_when_no_place(self) -> None:
        from world.battles.resolution import _terrain_property_modifier

        unit = BattleUnitFactory()
        self.assertEqual(_terrain_property_modifier(None, unit), 0)

    def test_returns_authored_modifier(self) -> None:
        from world.battles.resolution import _terrain_property_modifier

        place = BattlePlaceFactory(terrain_type=TerrainType.DIFFICULT)
        unit = BattleUnitFactory()
        aquatic = PropertyFactory(name="aquatic")
        unit.military_unit.properties.add(aquatic)
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=aquatic, modifier=20
        )
        self.assertEqual(_terrain_property_modifier(place, unit), 20)

    def test_sums_across_multiple_matching_properties(self) -> None:
        from world.battles.resolution import _terrain_property_modifier

        place = BattlePlaceFactory(terrain_type=TerrainType.DIFFICULT)
        unit = BattleUnitFactory()
        aquatic = PropertyFactory(name="aquatic")
        heavily_armored = PropertyFactory(name="heavily-armored")
        unit.military_unit.properties.set([aquatic, heavily_armored])
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=aquatic, modifier=20
        )
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=heavily_armored, modifier=-8
        )
        self.assertEqual(_terrain_property_modifier(place, unit), 12)


class QualityModifierTests(TestCase):
    def test_maps_quality_to_modifier(self) -> None:
        from world.battles.resolution import _quality_modifier

        self.assertEqual(_quality_modifier(UnitQuality.ELITE), -20)
        self.assertEqual(_quality_modifier(UnitQuality.TRAINED), 0)


class CommanderBonusForSideAtPlaceTests(TestCase):
    def test_zero_when_no_commanded_unit_present(self) -> None:
        from world.battles.resolution import commander_bonus_for_side_at_place

        battle = create_battle_for_test()
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        self.assertEqual(commander_bonus_for_side_at_place(side, place), 0)

    def test_returns_max_across_commanders(self) -> None:
        from world.battles.resolution import commander_bonus_for_side_at_place
        from world.battles.services import add_unit

        battle = create_battle_for_test()
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        weak_commander = CharacterSheetFactory()
        strong_commander = CharacterSheetFactory()
        add_unit(battle=battle, side=side, name="Unit A", place=place, commander=weak_commander)
        add_unit(battle=battle, side=side, name="Unit B", place=place, commander=strong_commander)

        # world.battles.resolution.commander_bonus_for_side_at_place does a
        # function-local `from world.mechanics.services import get_modifier_total`
        # — the name is never bound at `world.battles.resolution` module scope, so
        # patching it there raises AttributeError (verified empirically). Per this
        # repo's lazy-import-then-patch-origin convention, patch the ORIGIN instead.
        with patch(
            "world.mechanics.services.get_modifier_total",
            side_effect=lambda character, _target: 5 if character == weak_commander else 12,
        ):
            bonus = commander_bonus_for_side_at_place(side, place)

        self.assertEqual(bonus, 12)


def create_battle_for_test():
    from world.battles.services import create_battle

    return create_battle(name="Modifier Stack Test Battle")


class BattleTechniqueResolverModifierStackTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

    def test_sums_property_terrain_quality_posture_into_extra_modifiers(self) -> None:
        from world.battles.resolution import BattleTechniqueResolver
        from world.battles.services import (
            add_place,
            add_side,
            add_unit,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
            set_battle_side_posture,
        )
        from world.mechanics.factories import PropertyFactory

        battle = create_battle(name="Full Stack Test")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defender = add_side(battle=battle, role=BattleSideRole.DEFENDER)
        set_battle_side_posture(side=attacker, posture=BattlePosture.AGGRESSIVE)

        place = add_place(battle=battle, name="The Marsh", terrain_type=TerrainType.DIFFICULT)
        flying = PropertyFactory(name="flying")
        unit = add_unit(
            battle=battle,
            side=defender,
            name="Heavy Cavalry",
            quality=UnitQuality.ELITE,
            place=place,
            properties=[flying],
        )
        TechniquePropertyAffinity.objects.create(
            technique=self.technique, property=flying, modifier=10
        )
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=flying, modifier=20
        )

        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=attacker)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )

        resolver = BattleTechniqueResolver(
            character=self.sheet.character, technique=self.technique, declaration=declaration
        )
        fake_result = _success_result()
        # Expected: property(+10) + terrain(+20) + quality(ELITE=-20)
        #   + posture(AGGRESSIVE=-5) + commander(0, none assigned) = 5
        expected_total = 10 + 20 + (-20) + (-5) + 0
        with patch(
            "world.battles.resolution.perform_check", return_value=fake_result
        ) as mock_check:
            resolver(power=0, ledger=None, extra_modifiers=0)

        mock_check.assert_called_once()
        _called_args, called_kwargs = mock_check.call_args
        self.assertEqual(called_kwargs["extra_modifiers"], expected_total)

    def test_includes_nonzero_commander_bonus_in_extra_modifiers(self) -> None:
        """A commander assigned to a unit on the acting participant's own side/place
        contributes a nonzero commander term into extra_modifiers (final-review
        finding: the property/terrain/quality/posture full-stack test above
        always has commander=0 since no commander is ever assigned there).

        Property/terrain/quality are isolated to 0 by using a ``target_unit``
        with no authored ``TechniquePropertyAffinity``/``TerrainPropertyEffect``
        rows, default TRAINED quality, and default BALANCED posture — so the
        commander term is the only nonzero contributor and is exactly the patched
        ``get_modifier_total`` return value.
        """
        from world.battles.resolution import BattleTechniqueResolver
        from world.battles.services import (
            add_place,
            add_side,
            add_unit,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )

        battle = create_battle(name="Commander Bonus Stack Test")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defender = add_side(battle=battle, role=BattleSideRole.DEFENDER)

        place = add_place(battle=battle, name="The Field")
        commander = CharacterSheetFactory()
        add_unit(battle=battle, side=attacker, name="Vanguard", place=place, commander=commander)
        target_unit = add_unit(battle=battle, side=defender, name="Line Infantry", place=place)

        participant = enlist_participant(
            battle=battle, character_sheet=self.sheet, side=attacker, place=place
        )
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=target_unit,
        )

        resolver = BattleTechniqueResolver(
            character=self.sheet.character, technique=self.technique, declaration=declaration
        )
        fake_result = _success_result()
        # property(0, no authored row) + terrain(0, OPEN default, no row)
        #   + quality(TRAINED=0) + posture(BALANCED=0) + commander(8) = 8
        expected_total = 8
        # See CommanderBonusForSideAtPlaceTests.test_returns_max_across_commanders:
        # get_modifier_total is imported function-local inside
        # commander_bonus_for_side_at_place, so patch the origin, not
        # world.battles.resolution.
        with (
            patch("world.mechanics.services.get_modifier_total", return_value=8),
            patch("world.battles.resolution.perform_check", return_value=fake_result) as mock_check,
        ):
            resolver(power=0, ledger=None, extra_modifiers=0)

        mock_check.assert_called_once()
        self.assertEqual(mock_check.call_args.kwargs["extra_modifiers"], expected_total)

    def test_zero_stack_for_support_declaration_with_no_target_unit(self) -> None:
        """A SUPPORT declaration has no target_unit — the stack degrades to just
        posture + commander (both 0 by default here), proving no AttributeError
        when target_unit is None.
        """
        from world.battles.resolution import BattleTechniqueResolver
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )

        battle = create_battle(name="Support No-Unit Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        resolver = BattleTechniqueResolver(
            character=self.sheet.character, technique=self.technique, declaration=declaration
        )
        with patch(
            "world.battles.resolution.perform_check", return_value=_success_result()
        ) as mock_check:
            resolver(power=0, ledger=None, extra_modifiers=0)

        mock_check.assert_called_once()
        self.assertEqual(mock_check.call_args.kwargs["extra_modifiers"], 0)


class PostureVpScalingTests(TestCase):
    def setUp(self) -> None:
        self.battle = create_battle_for_test()
        self.attacker = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

    def test_aggressive_posture_scales_up_strike_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_unit,
            declare_battle_action,
            enlist_participant,
            set_battle_side_posture,
        )

        set_battle_side_posture(side=self.attacker, posture=BattlePosture.AGGRESSIVE)
        unit = add_unit(battle=self.battle, side=self.defender, name="Foes")
        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker
        )
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )

        success_level = 5
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            resolve_battle_round(battle_round=battle_round)

        self.attacker.refresh_from_db()
        base_vp = success_level * STRIKE_VP_PER_LEVEL
        expected_vp = round(base_vp * BATTLE_POSTURE_VP_MULTIPLIER[BattlePosture.AGGRESSIVE])
        self.assertEqual(self.attacker.victory_points, expected_vp)

    def test_defensive_posture_reduces_failure_damage(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_unit,
            declare_battle_action,
            enlist_participant,
            set_battle_side_posture,
        )

        set_battle_side_posture(side=self.attacker, posture=BattlePosture.DEFENSIVE)
        unit = add_unit(battle=self.battle, side=self.defender, name="Foes")
        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker
        )
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )

        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=battle_round)

        vitals = self.sheet.vitals
        vitals.refresh_from_db()
        expected_damage = (
            BASE_FAILURE_DAMAGE
            + abs(failure_level)
            + BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER[BattlePosture.DEFENSIVE]
        )
        self.assertEqual(vitals.health, 100 - expected_damage)


class ResolveBattleRoundClimacticMomentBlockTests(TestCase):
    def test_blocks_when_active_participant_mid_crossing(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.magic.factories import wire_audere_power_multipliers
        from world.magic.tests.majora_fixtures import build_crossing_world

        wire_audere_power_multipliers()
        (_character, mid_crossing_sheet, _threshold, _prospect, _puissant, _offer) = (
            build_crossing_world(5, "_battleresolveblock")
        )
        battle_round = BattleRoundFactory()
        side = BattleSideFactory(battle=battle_round.battle)
        BattleParticipantFactory(
            battle=battle_round.battle,
            side=side,
            character_sheet=mid_crossing_sheet,
            status=BattleParticipantStatus.ACTIVE,
        )

        with self.assertRaises(BattleError):
            resolve_battle_round(battle_round=battle_round)

    def test_does_not_block_when_no_one_mid_crossing(self) -> None:
        from world.battles.resolution import resolve_battle_round

        battle_round = BattleRoundFactory()
        side = BattleSideFactory(battle=battle_round.battle)
        sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=battle_round.battle,
            side=side,
            character_sheet=sheet,
            status=BattleParticipantStatus.ACTIVE,
        )

        resolve_battle_round(battle_round=battle_round)  # Must not raise BattleError.
