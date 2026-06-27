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

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdDeclareTechnique
from commands.combat_maneuvers import CmdCombat
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
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
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.factories import (
    BuffPassiveTechniqueFactory,
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.seeds_cast import ensure_technique_cast_content
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_cmd(caller: ObjectDB, args: str) -> CmdDeclareTechnique:
    """Build a CmdDeclareTechnique instance wired to *caller* with *args*."""
    cmd = CmdDeclareTechnique()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    return cmd


def _make_combat_cmd(caller: ObjectDB, args: str) -> CmdCombat:
    """Build a bare ``combat`` command against *caller* and capture its output."""
    cmd = CmdCombat()
    cmd.args = args
    cmd.raw_string = f"combat {args}".strip()
    cmd.caller = caller
    cmd.account = None
    captured: list[str] = []
    cmd.msg = lambda msg="", **kwargs: captured.append(str(msg))  # noqa: ARG005
    cmd._captured = captured  # type: ignore[attr-defined]
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
            status=RoundStatus.DECLARING,
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

    def test_cast_declares_secondary_action(self) -> None:
        """cast <technique> secondary → CombatRoundAction.physical_passive = technique.

        The setUp technique has action_category=PHYSICAL, so 'secondary' maps to
        CombatActionSlot.PASSIVE_PHYSICAL → physical_passive slot.
        """
        cmd = _make_cmd(self.character, f"{self.technique.name} secondary")
        cmd.func()
        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            action.physical_passive_id,
            self.technique.pk,
            "physical_passive should be the PHYSICAL technique declared with 'secondary'",
        )
        self.assertIsNone(
            action.focused_action_id,
            "focused_action must be null when declared as secondary",
        )

    def test_cast_beneficial_technique_targets_ally(self) -> None:
        """Casting a buff at an ally routes to focused_ally_target_id.

        BuffPassiveTechniqueFactory with buff_condition__target_kind="ally" produces
        a technique whose derive_target_relationship() returns ALLY, so the 'at <name>'
        target is resolved as a CombatParticipant (ally) instead of a CombatOpponent.
        """
        # Create a second PC participant (the ally).
        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
        )

        # Author a buff technique that derives ALLY targeting.
        # effect_type must have base_power=None so is_technique_hostile() returns
        # False (non-null base_power marks an offensive effect → ENEMY relationship).
        buff = BuffPassiveTechniqueFactory(
            gift=GiftFactory(),
            action_template=self.action_template,
            effect_type=EffectTypeFactory(name="Buff E2E", base_power=None),
            buff_condition__target_kind="ally",
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=buff)

        # Drive the telnet command: cast <buff> at <ally character key>.
        cmd = _make_cmd(
            self.character,
            f"{buff.name} at {ally_sheet.character.key}",
        )
        cmd.func()

        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            action.focused_ally_target_id,
            ally_participant.pk,
            "focused_ally_target should be the ally CombatParticipant",
        )
        self.assertIsNone(
            action.focused_opponent_target_id,
            "focused_opponent_target must be null when technique targets an ally",
        )

    # -- #1454: player-chosen soulfray-accept + fury decisions ---------------

    @staticmethod
    def _soulfray_warning():
        """A non-lethal soulfray warning for the declaration-time gate."""
        from world.magic.types.techniques import SoulfrayWarning

        return SoulfrayWarning(
            stage_name="Stage One",
            stage_description="Your soul frays at the edges.",
            has_death_risk=False,
        )

    def test_decline_soulfray_aborts_cast_then_free_redeclare(self) -> None:
        """A soulfray-risky cast asks first; declining records nothing and frees the turn."""
        from commands.pending_actions import peek_pending
        from world.magic.offer_handlers import SoulfrayPendingHandler

        # Soulfray warning present → the cast must prompt, not record a declaration.
        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=self._soulfray_warning(),
        ):
            _make_cmd(self.character, f"{self.technique.name} at {self.opponent_name}").func()

        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=1).exists(),
            "a soulfray-risky cast must not record a declaration before the player accepts",
        )
        self.assertIsNotNone(
            peek_pending(self.sheet.pk),
            "a PendingCast must be registered while awaiting accept/decline",
        )

        # Decline → pending cleared, still no declaration, anima untouched.
        SoulfrayPendingHandler().decline(offer=None, caller=self.character)
        self.assertIsNone(peek_pending(self.sheet.pk))
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=1).exists(),
        )
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 20, "declining must not spend anima")

        # Free re-declare: the round slot is still open, so a (now non-risky) cast records.
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            _make_cmd(self.character, f"{self.technique.name} at {self.opponent_name}").func()
        self.assertTrue(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=1).exists(),
            "after declining, the player may still declare an action this round",
        )

    def test_accept_soulfray_resolves_cast(self) -> None:
        """Accepting a soulfray-risky cast records confirm=True and resolves with damage."""
        from world.magic.offer_handlers import SoulfrayPendingHandler

        with patch(
            "world.magic.services.soulfray.get_soulfray_warning",
            return_value=self._soulfray_warning(),
        ):
            _make_cmd(self.character, f"{self.technique.name} at {self.opponent_name}").func()
            # Accept re-dispatches with confirm_soulfray_risk=True → records the declaration.
            SoulfrayPendingHandler().accept(offer=None, caller=self.character, args="")

        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertTrue(
            action.confirm_soulfray_risk,
            "accepting soulfray must record confirm_soulfray_risk=True on the declaration",
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        self.anima.refresh_from_db()
        self.assertLess(self.anima.current, 20, "an accepted risky cast spends anima")
        self.opponent.refresh_from_db()
        self.assertLess(self.opponent.health, self.opponent.max_health)

    def test_fury_commitment_realized_and_audited(self) -> None:
        """A telnet-declared fury tier + anchor is recorded, realized, and audited."""
        from world.magic.factories import FuryConfigFactory, FuryTierFactory

        FuryConfigFactory()
        tier = FuryTierFactory()
        anchor_sheet = CharacterSheetFactory()

        # Declare through the real telnet command: cast ... fury=<tier> anchor=<name>.
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            _make_cmd(
                self.character,
                f"{self.technique.name} at {self.opponent_name} "
                f"fury={tier.name} anchor={anchor_sheet.character.db_key}",
            ).func()

        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.fury_commitment_id, tier.pk, "fury tier recorded on declaration")
        self.assertEqual(action.fury_anchor_id, anchor_sheet.pk, "fury anchor recorded")

        # Resolve: bond gives a real provocation cap; control check succeeds (no Berserk).
        with (
            patch("world.combat.services.perform_check") as mock_offense,
            patch("world.magic.services.fury.get_relationship_tier", return_value=2),
            patch("world.checks.services.perform_check") as mock_control,
        ):
            mock_offense.return_value = MagicMock(success_level=2)
            mock_control.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        self.anima.refresh_from_db()
        self.assertLess(self.anima.current, 20, "a fury cast still spends anima")
        self.opponent.refresh_from_db()
        self.assertLess(self.opponent.health, self.opponent.max_health)

        action.refresh_from_db()
        self.assertIsNotNone(action.interaction, "resolved action should have an interaction")
        self.assertEqual(
            action.interaction.fury_committed_id,
            tier.pk,
            "the realized fury tier must be recorded on the interaction audit",
        )

    @tag("postgres")
    def test_fury_lost_control_applies_berserk(self) -> None:
        """When the control-retention check fails, Fury applies Berserk in combat.

        Tagged postgres: applying a condition exercises apply_condition, which uses
        a PG-only DISTINCT ON that NotSupportedErrors on the SQLite fast tier.
        """
        from world.conditions.models import ConditionInstance
        from world.magic.factories import (
            BerserkConditionTemplateFactory,
            FuryConfigFactory,
            FuryTierFactory,
        )

        FuryConfigFactory()
        BerserkConditionTemplateFactory()  # seed the Berserk ConditionTemplate
        tier = FuryTierFactory()
        anchor_sheet = CharacterSheetFactory()

        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            _make_cmd(
                self.character,
                f"{self.technique.name} at {self.opponent_name} "
                f"fury={tier.name} anchor={anchor_sheet.character.db_key}",
            ).func()

        with (
            patch("world.combat.services.perform_check") as mock_offense,
            patch("world.magic.services.fury.get_relationship_tier", return_value=2),
            patch("world.checks.services.perform_check") as mock_control,
        ):
            mock_offense.return_value = MagicMock(success_level=2)
            # Below the tier's lucid_grade_floor (2) → control lost → Berserk applied.
            mock_control.return_value = MagicMock(success_level=1)
            resolve_round(self.encounter)

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.character,
                condition__name="Berserk",
            ).exists(),
            "losing control to fury must apply a Berserk condition to the caster",
        )

    def test_combat_hub_shows_anima_and_omits_absent_lines(self) -> None:
        """Bare ``combat`` shows anima; soulfray/fury/Berserk are absent → omitted."""
        cmd = _make_combat_cmd(self.character, "")
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            cmd.func()
        out = "\n".join(cmd._captured)
        self.assertIn("Anima: 20/20", out)
        self.assertNotIn("Soulfray:", out)
        self.assertNotIn("Fury:", out)
        self.assertNotIn("Berserk:", out)

    def test_combat_hub_shows_soulfray_stage_with_death_risk(self) -> None:
        """When get_soulfray_warning returns a stage, the hub shows it + death risk."""
        from world.magic.types.techniques import SoulfrayWarning

        warning = SoulfrayWarning(
            stage_name="Frayed", stage_description="edges fraying", has_death_risk=True
        )
        cmd = _make_combat_cmd(self.character, "")
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=warning):
            cmd.func()
        out = "\n".join(cmd._captured)
        self.assertIn("Anima: 20/20", out)
        self.assertIn("Soulfray: Frayed", out)
        self.assertIn("death risk", out)

    def test_combat_hub_shows_committed_fury(self) -> None:
        """A declared fury tier + anchor surfaces on the combat hub (pre-resolve)."""
        from world.magic.factories import FuryConfigFactory, FuryTierFactory

        FuryConfigFactory()
        tier = FuryTierFactory()
        anchor_sheet = CharacterSheetFactory()

        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            _make_cmd(
                self.character,
                f"{self.technique.name} at {self.opponent_name} "
                f"fury={tier.name} anchor={anchor_sheet.character.db_key}",
            ).func()

        cmd = _make_combat_cmd(self.character, "")
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            cmd.func()
        out = "\n".join(cmd._captured)
        self.assertIn("Fury:", out)
        self.assertIn(str(tier.depth), out)
        self.assertIn(anchor_sheet.character.db_key, out)
        self.assertIn("retained", out)  # no Berserk yet → control retained
        self.assertNotIn("Berserk:", out)

    @tag("postgres")
    def test_combat_hub_shows_berserk_after_lost_control(self) -> None:
        """After fury loses control, the hub shows Berserk + rounds remaining."""
        from world.magic.factories import (
            BerserkConditionTemplateFactory,
            FuryConfigFactory,
            FuryTierFactory,
        )

        FuryConfigFactory()
        BerserkConditionTemplateFactory()
        tier = FuryTierFactory()
        anchor_sheet = CharacterSheetFactory()

        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            _make_cmd(
                self.character,
                f"{self.technique.name} at {self.opponent_name} "
                f"fury={tier.name} anchor={anchor_sheet.character.db_key}",
            ).func()

        with (
            patch("world.combat.services.perform_check") as mock_offense,
            patch("world.magic.services.fury.get_relationship_tier", return_value=2),
            patch("world.checks.services.perform_check") as mock_control,
        ):
            mock_offense.return_value = MagicMock(success_level=2)
            # Below lucid_grade_floor → control lost → Berserk applied.
            mock_control.return_value = MagicMock(success_level=1)
            resolve_round(self.encounter)

        # The encounter left DECLARING after resolve_round. Open a fresh
        # DECLARING round so the participant is active again and the hub can
        # surface the persistent Berserk condition.
        begin_declaration_phase(self.encounter)

        cmd = _make_combat_cmd(self.character, "")
        with patch("world.magic.services.soulfray.get_soulfray_warning", return_value=None):
            cmd.func()
        out = "\n".join(cmd._captured)
        self.assertIn("Berserk:", out)
        self.assertIn("active", out)
