"""Telnet-driven clash commit E2E (#1451): clash → ClashContributionDeclaration → resolve_round.

Proves that the full pipeline works:
  CmdClashCommit.func()
    → dispatch_player_action(COMBAT, clash_id=...)
    → _dispatch_clash_contribution()
    → declare_clash_contribution() [writes ClashContributionDeclaration]
  resolve_round(encounter)
    → _resolve_clashes()
    → run_clash_round() → commit_to_clash()
    → ClashContribution rows persisted with correct anima_committed

Setup mirrors the existing CombatCastTelnetE2ETests but adds a ClashFactory and
the CmdClashCommit command under test.

SQLite tier: runs cleanly.  No apply_condition / DISTINCT ON / AreaClosure queries
on this path, so no @tag("postgres") is required.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdClashCommit
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    ClashStatus,
    OpponentTier,
)
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import ClashContribution, ClashContributionDeclaration
from world.combat.services import resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.seeds_cast import ensure_technique_cast_content
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


def _make_clash_cmd(caller: ObjectDB, args: str) -> CmdClashCommit:
    """Build a CmdClashCommit instance wired to *caller* with *args*."""
    cmd = CmdClashCommit()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"clash {args}"
    cmd.cmdname = "clash"
    return cmd


class CombatClashTelnetE2ETests(TestCase):
    """Telnet clash command drives declare → ClashContributionDeclaration → resolve_round.

    Uses setUp (not setUpTestData) for ObjectDB objects: Django's setUpTestData
    deepcopy machinery cannot copy DbHolder / SharedMemoryModel instances.

    SQLite tier: passes cleanly.  No DISTINCT ON or AreaClosure materialized view
    on this hot path, so no @tag("postgres") is required.
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel identity-map cache to prevent PK recycling
        # from a prior test leaking stale instances.
        idmapper_models.flush_cache()

        # -- Clash/strain singletons (required by resolve_round → _resolve_clashes) --
        ClashConfigFactory()
        StrainConfigFactory()

        # -- Damage multiplier rows (required by resolve_round for PC action resolution) --
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # -- ActionTemplate: required so commit_to_clash can resolve check_type --
        self.action_template = ensure_technique_cast_content()

        # -- Encounter: DECLARING so dispatch_player_action accepts a declaration --
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # -- Threat pool for the mook opponent --
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)

        # -- NPC opponent to attach the Clash to --
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        self.opponent_name = self.opponent.name

        # -- PC participant: sheet → character → vitals/anima/engagement/room --
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )
        self.character = self.sheet.character
        # Give the character enough anima to commit strain=3 on top of technique cost.
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=30,
            maximum=30,
        )
        CharacterEngagementFactory(character=self.character)

        # Place the character in a room so location-dependent queries don't fail.
        room = ObjectDB.objects.create(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = room
        self.character.save()

        # -- Technique: clash_capable=True so commit_to_clash accepts it --
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="Clash E2E", base_power=None),
            intensity=1,
            control=1,
            anima_cost=2,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
            clash_capable=True,
        )

        # -- CharacterTechnique: required for _resolve_technique_id lookup --
        CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.technique,
        )

        # -- Active Clash against the opponent --
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )

        # -- CheckOutcome: real DB row for ClashContribution.check_outcome FK --
        self.check_outcome = CheckOutcomeFactory(name="Success E2E", success_level=2)

    def test_clash_command_writes_declaration_with_strain(self) -> None:
        """clash <opp> with <tech> strain=3 → ClashContributionDeclaration(strain_commitment=3)."""
        cmd = _make_clash_cmd(
            self.character,
            f"{self.opponent_name} with {self.technique.name} strain=3",
        )
        cmd.func()

        decl = ClashContributionDeclaration.objects.get(
            participant=self.participant,
            clash=self.clash,
            round_number=1,
        )
        self.assertEqual(
            decl.strain_commitment,
            3,
            "ClashContributionDeclaration.strain_commitment should equal the declared value",
        )
        self.assertEqual(
            decl.technique_id,
            self.technique.pk,
            "ClashContributionDeclaration.technique should be the declared technique",
        )

    def test_clash_command_default_strain_zero(self) -> None:
        """clash <opp> with <technique> (no strain) → strain_commitment=0."""
        cmd = _make_clash_cmd(
            self.character,
            f"{self.opponent_name} with {self.technique.name}",
        )
        cmd.func()

        decl = ClashContributionDeclaration.objects.get(
            participant=self.participant,
            clash=self.clash,
            round_number=1,
        )
        self.assertEqual(
            decl.strain_commitment,
            0,
            "Default strain_commitment should be 0 when strain= is omitted",
        )

    def test_clash_command_declaration_then_resolve_round_writes_contribution(self) -> None:
        """clash → declare → resolve_round → ClashContribution.anima_committed == strain.

        Drives the full pipeline from telnet command through round resolution and
        asserts that the persisted ClashContribution row carries the declared
        strain_commitment value as its anima_committed amount.
        """
        strain = 3
        cmd = _make_clash_cmd(
            self.character,
            f"{self.opponent_name} with {self.technique.name} strain={strain}",
        )
        cmd.func()

        # Verify the bridge row exists before round resolution.
        self.assertEqual(
            ClashContributionDeclaration.objects.filter(
                participant=self.participant,
                clash=self.clash,
                round_number=1,
            ).count(),
            1,
            "ClashContributionDeclaration must exist before resolve_round",
        )

        # Resolve the round — mock perform_check at the source module to return
        # a real CheckOutcome so aggregate_clash_round can assign it to the
        # ClashContribution.check_outcome FK (which requires a CheckOutcome instance).
        mock_check_result = MagicMock()
        mock_check_result.success_level = 2
        mock_check_result.outcome = self.check_outcome
        with patch("world.checks.services.perform_check", return_value=mock_check_result):
            resolve_round(self.encounter)

        # Bridge rows are deleted after resolution — verify cleanup.
        self.assertEqual(
            ClashContributionDeclaration.objects.filter(
                encounter=self.encounter,
                round_number=1,
            ).count(),
            0,
            "ClashContributionDeclaration rows must be deleted after resolve_round",
        )

        # The persisted ClashContribution audit row must reflect the strain commitment.
        contribution = ClashContribution.objects.get(
            clash_round__clash=self.clash,
            clash_round__round_number=1,
            character=self.sheet,
        )
        self.assertEqual(
            contribution.anima_committed,
            strain,
            "ClashContribution.anima_committed must equal the declared strain_commitment",
        )

    def test_clash_command_rejects_unknown_opponent(self) -> None:
        """clash with non-existent opponent name raises CommandError on _execute."""
        from commands.exceptions import CommandError

        cmd = _make_clash_cmd(
            self.character,
            f"NoSuchOpponent with {self.technique.name}",
        )
        # CommandError is caught by func() and forwarded to caller.msg(); test via _execute().
        with self.assertRaises(CommandError):
            cmd._execute()

    def test_clash_command_rejects_unknown_technique(self) -> None:
        """clash with unknown technique name raises CommandError on _execute."""
        from commands.exceptions import CommandError

        cmd = _make_clash_cmd(
            self.character,
            f"{self.opponent_name} with NoSuchTechnique",
        )
        # CommandError is caught by func() and forwarded to caller.msg(); test via _execute().
        with self.assertRaises(CommandError):
            cmd._execute()
