"""Unit tests for CmdCombat — the ``combat <subverb>`` namespace (#1453, #1452).

Verify subverb routing, REGISTRY ref construction, name-argument resolution, and
the bare-``combat`` status hub, mirroring the mock-caller style of
``test_combat_commands.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.combat_maneuvers import CmdCombat
from commands.exceptions import CommandError
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import PendingOpponentAttack

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdCombat:
    cmd = CmdCombat()
    cmd.caller = MagicMock()
    cmd.args = args
    cmd.raw_string = f"combat {args}"
    cmd.cmdname = "combat"
    return cmd


class CmdCombatRoutingTests(TestCase):
    def test_flee_builds_registry_ref(self) -> None:
        cmd = _make_cmd("flee")
        cmd._subverb = "flee"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_flee")

    def test_yield_reuses_existing_yield_action(self) -> None:
        cmd = _make_cmd("yield")
        cmd._subverb = "yield"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.registry_key, "yield")

    def test_use_builds_registry_ref(self) -> None:
        cmd = _make_cmd("use potion")
        cmd._subverb = "use"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_use")

    def test_charge_builds_registry_ref(self) -> None:
        cmd = _make_cmd("charge Orc with Strike")
        cmd._subverb = "charge"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_charge")

    def test_joust_builds_registry_ref(self) -> None:
        cmd = _make_cmd("joust with Lance Strike")
        cmd._subverb = "joust"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_joust")

    def test_engage_builds_registry_ref(self) -> None:
        cmd = _make_cmd("engage Orc")
        cmd._subverb = "engage"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_engage")

    def test_disengage_builds_registry_ref(self) -> None:
        cmd = _make_cmd("disengage")
        cmd._subverb = "disengage"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "combat_disengage")

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_flee_dispatches_registry_ref_through_func(self) -> None:
        cmd = _make_cmd("flee")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You flee."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()
        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "combat_flee")
        self.assertEqual(kwargs, {})

    def test_bare_combat_shows_status_hub(self) -> None:
        cmd = _make_cmd("")
        with (
            patch.object(cmd, "_combat_participant_or_none", return_value=None) as participant,
            patch.object(cmd, "_render_resource_state", return_value=[]) as resources,
        ):
            cmd.func()
        # Outside combat the hub calls the resource readout collaborator with
        # no participant/action and still prints the actions header.
        participant.assert_called_once()
        resources.assert_called_once_with(None, None)
        cmd.caller.msg.assert_called_once()
        self.assertIn("Combat actions", cmd.caller.msg.call_args.args[0])

    def test_bare_combat_lists_pending_windups(self) -> None:
        cmd = _make_cmd("")
        participant = MagicMock()
        participant.encounter.round_number = 2
        pending = MagicMock()
        pending.target_id = 1
        pending.opponent.name = "Ogre"
        pending.target.character_sheet.character = "Kira"
        pending.resolves_round = 3
        pending.called_out = True
        pending.downgrades = 1
        with (
            patch.object(cmd, "_combat_participant_or_none", return_value=participant),
            patch.object(cmd, "_render_resource_state", return_value=[]),
            patch("world.combat.models.CombatRoundAction.objects") as actions,
            patch.object(cmd, "_pending_windups", return_value=[pending]),
        ):
            actions.select_related.return_value.filter.return_value.first.return_value = None
            cmd.func()
        text = cmd.caller.msg.call_args.args[0]
        self.assertIn("Wind-ups", text)
        self.assertIn("Ogre -> Kira, lands in 1 (called out, 1 stagger)", text)


class CmdCombatPendingWindupsQueryTests(TestCase):
    """DB-backed coverage of `_pending_windups`' scope/select_related/order (#3572).

    The mock-based hub test above never exercises the real ORM query. This
    covers encounter scoping, `select_related` (via a zero-query assertion on
    the nested attributes the render step reads), and the `resolves_round,
    id` ordering.
    """

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=2)
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=pool)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter, threat_pool=pool, name="Ogre"
        )
        self.target = CombatParticipantFactory(encounter=self.encounter)

    def _pending(self, encounter: object, **overrides: object) -> PendingOpponentAttack:
        fields = {
            "encounter": encounter,
            "opponent": self.opponent,
            "threat_entry": self.entry,
            "target": self.target,
            "declared_round": 1,
            "resolves_round": 2,
        }
        fields.update(overrides)
        return PendingOpponentAttack.objects.create(**fields)

    def test_scopes_to_encounter_and_orders_by_round_then_id(self) -> None:
        row_round_4 = self._pending(self.encounter, resolves_round=4)
        row_round_2_first = self._pending(self.encounter, resolves_round=2)
        row_round_2_second = self._pending(self.encounter, resolves_round=2)
        other_encounter = CombatEncounterFactory()
        self._pending(other_encounter, declared_round=0, resolves_round=1)

        result = CmdCombat._pending_windups(self.encounter)

        self.assertEqual(result, [row_round_2_first, row_round_2_second, row_round_4])
        # select_related("opponent", "target__character_sheet__character") must
        # make these nested reads free (no N+1 per wind-up row).
        with self.assertNumQueries(0):
            _ = result[0].opponent.name
            _ = str(result[0].target.character_sheet.character)


class CmdCombatRenderWindupLinesTests(TestCase):
    """DB-backed coverage of `_render_windup_lines`' formatting branches (#3572)."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=2)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=pool)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter, threat_pool=pool, name="Ogre"
        )
        self.target = CombatParticipantFactory(encounter=self.encounter)

    def _pending(self, **overrides: object) -> PendingOpponentAttack:
        fields = {
            "encounter": self.encounter,
            "opponent": self.opponent,
            "threat_entry": self.entry,
            "target": self.target,
            "declared_round": 1,
            "resolves_round": 2,
        }
        fields.update(overrides)
        return PendingOpponentAttack.objects.create(**fields)

    def test_render_covers_zero_round_plural_stagger_no_notes_and_no_target(self) -> None:
        # resolves_round == the current round, no notes: "lands this round", no "(...)".
        lands_now = self._pending(resolves_round=2, called_out=False, downgrades=0)
        # Plural stagger count, no called-out note.
        staggers = self._pending(resolves_round=5, called_out=False, downgrades=2)
        # Room-targeting (target=None): "no one in particular".
        no_target = self._pending(target=None, resolves_round=3)

        lines = CmdCombat._render_windup_lines(
            self.participant,
            [lands_now, staggers, no_target],
        )

        target_name = str(self.target.character_sheet.character)
        self.assertEqual(
            lines,
            [
                "|wWind-ups|n:",
                f"  Ogre -> {target_name}, lands this round",
                f"  Ogre -> {target_name}, lands in 3 (2 staggers)",
                "  Ogre -> no one in particular, lands in 1",
            ],
        )


class CmdCombatArgResolutionTests(TestCase):
    def test_cover_resolves_ally_kwarg(self) -> None:
        cmd = _make_cmd("cover Bob")
        cmd._subverb, cmd._rest = "cover", "Bob"
        with patch.object(cmd, "_resolve_ally_pk", return_value=5):
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"ally_participant_id": 5})

    def test_cover_without_ally_raises(self) -> None:
        cmd = _make_cmd("cover")
        cmd._subverb, cmd._rest = "cover", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_interpose_without_ally_passes_none(self) -> None:
        cmd = _make_cmd("interpose")
        cmd._subverb, cmd._rest = "interpose", ""
        self.assertEqual(cmd.resolve_action_args(), {"ally_participant_id": None})

    def test_interpose_soulfray_token_sets_consent(self) -> None:
        cmd = _make_cmd("interpose Kira with Aegis Field soulfray")
        with (
            patch.object(cmd, "_resolve_ally_pk", return_value=5),
            patch.object(cmd, "_find_technique_id", return_value=7),
        ):
            kwargs = cmd._resolve_interpose_args("Kira with Aegis Field soulfray")
        self.assertEqual(kwargs["ally_participant_id"], 5)
        self.assertEqual(kwargs["technique_id"], 7)
        self.assertTrue(kwargs["confirm_soulfray_risk"])

    def test_interpose_without_token_has_no_consent_key(self) -> None:
        cmd = _make_cmd("interpose")
        kwargs = cmd._resolve_interpose_args("")
        self.assertNotIn("confirm_soulfray_risk", kwargs)

    def test_combo_resolves_combo_kwarg(self) -> None:
        cmd = _make_cmd("combo Whirlwind")
        cmd._subverb, cmd._rest = "combo", "Whirlwind"
        with patch.object(cmd, "_resolve_combo_pk", return_value=3):
            kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"combo_id": 3})

    def test_flee_takes_no_args(self) -> None:
        cmd = _make_cmd("flee")
        cmd._subverb, cmd._rest = "flee", ""
        self.assertEqual(cmd.resolve_action_args(), {})

    def test_use_item_only_resolves_item_name(self) -> None:
        cmd = _make_cmd("use healing draught")
        cmd._subverb, cmd._rest = "use", "healing draught"
        self.assertEqual(cmd.resolve_action_args(), {"item_name": "healing draught"})

    def test_use_item_on_ally_resolves_target_kwarg(self) -> None:
        cmd = _make_cmd("use potion on Bob")
        cmd._subverb, cmd._rest = "use", "potion on Bob"
        with patch.object(
            cmd, "_resolve_use_item_target", return_value={"ally_participant_id": 5}
        ) as resolve_target:
            kwargs = cmd.resolve_action_args()
        resolve_target.assert_called_once_with("Bob")
        self.assertEqual(kwargs, {"item_name": "potion", "ally_participant_id": 5})

    def test_use_without_item_raises(self) -> None:
        cmd = _make_cmd("use")
        cmd._subverb, cmd._rest = "use", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_charge_resolves_opponent_and_technique(self) -> None:
        cmd = _make_cmd("charge Orc with Strike")
        cmd._subverb, cmd._rest = "charge", "Orc with Strike"
        with (
            patch.object(cmd, "_resolve_opponent_pk", return_value=9) as resolve_opp,
            patch.object(cmd, "_find_technique_id", return_value=4) as resolve_tech,
        ):
            kwargs = cmd.resolve_action_args()
        resolve_opp.assert_called_once_with("Orc")
        resolve_tech.assert_called_once_with("Strike")
        self.assertEqual(kwargs, {"opponent_id": 9, "technique_id": 4})

    def test_charge_without_with_clause_raises(self) -> None:
        cmd = _make_cmd("charge Orc")
        cmd._subverb, cmd._rest = "charge", "Orc"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_charge_without_opponent_raises(self) -> None:
        cmd = _make_cmd("charge with Strike")
        cmd._subverb, cmd._rest = "charge", "with Strike"
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_joust_resolves_technique_with_prefix(self) -> None:
        cmd = _make_cmd("joust with Lance Strike")
        cmd._subverb, cmd._rest = "joust", "with Lance Strike"
        with patch.object(cmd, "_find_technique_id", return_value=6) as resolve_tech:
            kwargs = cmd.resolve_action_args()
        resolve_tech.assert_called_once_with("Lance Strike")
        self.assertEqual(kwargs, {"technique_id": 6})

    def test_joust_resolves_bare_technique(self) -> None:
        cmd = _make_cmd("joust Lance Strike")
        cmd._subverb, cmd._rest = "joust", "Lance Strike"
        with patch.object(cmd, "_find_technique_id", return_value=6) as resolve_tech:
            kwargs = cmd.resolve_action_args()
        resolve_tech.assert_called_once_with("Lance Strike")
        self.assertEqual(kwargs, {"technique_id": 6})

    def test_joust_without_technique_raises(self) -> None:
        cmd = _make_cmd("joust")
        cmd._subverb, cmd._rest = "joust", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_engage_resolves_opponent_kwarg(self) -> None:
        cmd = _make_cmd("engage Orc")
        cmd._subverb, cmd._rest = "engage", "Orc"
        with patch.object(cmd, "_resolve_opponent_pk", return_value=9) as resolve_opp:
            kwargs = cmd.resolve_action_args()
        resolve_opp.assert_called_once_with("Orc")
        self.assertEqual(kwargs, {"opponent_id": 9})

    def test_engage_without_opponent_raises(self) -> None:
        cmd = _make_cmd("engage")
        cmd._subverb, cmd._rest = "engage", ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_disengage_takes_no_args(self) -> None:
        cmd = _make_cmd("disengage")
        cmd._subverb, cmd._rest = "disengage", ""
        self.assertEqual(cmd.resolve_action_args(), {})
