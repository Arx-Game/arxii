"""Telnet-driven combat cast E2E (#1330 L0): cast command → resolve_round → use_technique.

Proves that the full pipeline works:
  CmdDeclareTechnique.func()
    → dispatch_player_action(COMBAT)
    → CombatRoundContext.record_declaration()
    → declare_action() [writes CombatRoundAction]
  resolve_round(encounter)
    → resolve_combat_technique()
    → use_technique() [deducts anima, applies damage]

Setup mirrors _setup_pc_attacking_mook from
world/combat/tests/test_combat_magic_integration.py but builds the encounter
in DECLARING status (dispatch_player_action requires is_declaration_open=True)
and wires a CharacterTechnique row so the command can resolve the technique by name.

SQLite tier: runs cleanly.  The dispatch path through get_player_actions()
→ _combat_actions() does not trigger DISTINCT ON or the AreaClosure materialized
view in this scenario (no apply_condition calls on the DECLARING-phase hot path),
so no @tag("postgres") is required.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    EncounterStatus,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
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
from world.vitals.models import CharacterVitals


def _make_cmd(caller: ObjectDB, args: str) -> CmdDeclareTechnique:
    """Build a CmdDeclareTechnique instance wired to *caller* with *args*."""
    cmd = CmdDeclareTechnique()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    return cmd


class CombatCastTelnetE2ETests(TestCase):
    """Telnet cast command drives declare → resolve_round → damage pipeline.

    Uses setUp (not setUpTestData) for ObjectDB objects: Django's setUpTestData
    deepcopy machinery cannot copy DbHolder / SharedMemoryModel instances (would
    raise copy.Error in CI shard runs — see project memory).

    SQLite tier: passes cleanly.  The dispatch path through get_player_actions()
    → _combat_actions() does not trigger DISTINCT ON or the AreaClosure
    materialized view in this scenario (no apply_condition calls on the
    DECLARING-phase hot path), so no @tag("postgres") is required.
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel identity-map cache to prevent PK recycling
        # from a prior test leaking stale instances (see project memory).
        idmapper_models.flush_cache()

        # -- Damage multiplier rows (needed for resolve_round to deal damage) --
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # -- ActionTemplate: required so _combat_actions surfaces the technique --
        self.action_template = ensure_technique_cast_content()

        # -- Encounter: DECLARING so dispatch_player_action accepts a declaration --
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )

        # -- Threat pool for the mook opponent --
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=30)

        # -- Mook opponent --
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
        # CharacterAnima.character FK → ObjectDB (the game object, not the sheet)
        self.character = self.sheet.character
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )
        CharacterEngagementFactory(character=self.character)

        # Place the character in a room so location-dependent queries don't fail.
        room = ObjectDB.objects.create(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = room
        self.character.save()

        # -- Technique: must have action_template so _combat_actions surfaces it --
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="Attack E2E", base_power=20),
            intensity=5,
            control=10,
            anima_cost=10,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )

        # -- CharacterTechnique: links the sheet to the technique --
        # Required for both:
        #   • CmdDeclareTechnique._resolve_technique_id (looks up by name on
        #     CharacterTechnique rows filtered by character=caller.sheet_data)
        #   • _combat_actions (filters CharacterTechnique.objects.filter(
        #       character=sheet, technique__action_template__isnull=False))
        CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.technique,
        )

    def test_cast_command_declares_then_resolves_and_deducts_anima(self) -> None:
        """cast → declaration row → resolve_round → damage applied + anima spent."""
        anima_before = self.anima.current

        # Step 1: drive the telnet command (declares via dispatch_player_action).
        cmd = _make_cmd(
            self.character,
            f"{self.technique.name} at {self.opponent_name}",
        )
        cmd.func()

        # Step 2: assert a CombatRoundAction row was recorded for this participant + round.
        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            action.focused_action_id,
            self.technique.pk,
            "focused_action should be the declared technique",
        )

        # Step 3: resolve the round (patching perform_check to return SL=2).
        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        # Step 4a: anima was spent (current < before).
        # effective cost = max(anima_cost - (control - intensity), 0)
        #                = max(10 - (10 - 5), 0) = 5 > 0, so deduction is guaranteed.
        self.anima.refresh_from_db()
        self.assertLess(
            self.anima.current,
            anima_before,
            "anima must be deducted: effective cost=5 (anima_cost=10, control=10, intensity=5)",
        )

        # Step 4b: the mook took damage.
        self.opponent.refresh_from_db()
        self.assertLess(
            self.opponent.health,
            self.opponent.max_health,
            "opponent health should have decreased after resolve_round",
        )

    def test_round_declaration_honors_action_slot_kwarg(self) -> None:
        """round_declaration uses action_slot kwarg to select the physical passive slot.

        Drives CastTechniqueAction.round_declaration() with action_slot="passive-physical"
        and a PHYSICAL technique, then asserts:
        - The recorded CombatRoundAction row has physical_passive=technique.
        - focused_action is null (passive slots never touch the focused slot).
        - action_slot is NOT in decl_kwargs (it belongs only on the ActionRef).
        """
        from actions.constants import CombatActionSlot
        from actions.definitions.cast import CastTechniqueAction
        from world.combat.round_context import CombatRoundContext

        action = CastTechniqueAction()
        ctx = CombatRoundContext(self.participant)

        # round_declaration with passive-physical slot
        result = action.round_declaration(
            ctx,
            technique_id=self.technique.pk,
            action_slot=CombatActionSlot.PASSIVE_PHYSICAL,
        )

        # Must return a (PlayerAction, decl_kwargs) tuple — not None
        self.assertIsNotNone(result, "expected a declaration tuple from round_declaration")
        player_action, decl_kwargs = result

        # action_slot must NOT be in decl_kwargs — it belongs on the ref only
        self.assertNotIn(
            "action_slot",
            decl_kwargs,
            "action_slot must not be forwarded into decl_kwargs",
        )

        # The ActionRef must carry the correct slot
        self.assertEqual(
            player_action.ref.action_slot,
            CombatActionSlot.PASSIVE_PHYSICAL,
            "ActionRef.action_slot should be PASSIVE_PHYSICAL",
        )

        # Record the declaration and verify the DB row
        ctx.record_declaration(self.sheet, player_action, decl_kwargs)

        row = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            row.physical_passive_id,
            self.technique.pk,
            "physical_passive should be the declared technique",
        )
        self.assertIsNone(
            row.focused_action_id,
            "focused_action should be null when declaring into a passive slot",
        )
