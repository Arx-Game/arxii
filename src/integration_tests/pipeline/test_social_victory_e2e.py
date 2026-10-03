"""Telnet-driven E2E: charm one bandit, parley the other -> social VICTORY (#4091).

Proves the won-over pipeline end to end, no enemy ever defeated:
  CmdDeclareTechnique.func()  [round 1]
    -> dispatch_player_action(COMBAT) -> declare_action() [writes CombatRoundAction]
  resolve_round(encounter)  [round 1]
    -> resolve_combat_technique() -> use_technique() with the Charming Word technique
    -> apply_technique_conditions() -> bulk_apply_conditions()
    -> Bandit A wears Charmed (effective allegiance -> ALLY_OF_CASTER)
  begin_declaration_phase(encounter)  [advance to round 2]
  ParleyAction().execute(...)  [round 2 — declares the parley maneuver on Bandit B]
  resolve_round(encounter)  [round 2]
    -> _resolve_parley() -> decisive success applies Calm (-> NEUTRAL) to Bandit B
    -> hostile_opponents_remain() is now False (ruling R1: both holds were applied
       at/after encounter.created_at) -> _check_encounter_completion -> VICTORY
    -> complete_encounter() -> stamp_won_over_opponents() stamps both WON_OVER
    -> _apply_opponent_aftermath_pools() fires both opponents' pools
    -> _broadcast_encounter_outcome() sends the won-over clause to the room,
       reaching the PC's own session.

Neither bandit is ever DEFEATED and neither ever acts (no select_npc_actions
call): this is a field won over, not fought down — the whole point of #4091.

@tag("postgres") — REQUIRED. The charm technique's TechniqueAppliedCondition
routes through apply_technique_conditions -> bulk_apply_conditions, which uses
a PG-only DISTINCT ON clause (NotSupportedError on SQLite). This test is
SKIPPED on the SQLite fast tier and CI-gated. Do not attempt to run it locally.

Mirror of setUp pattern from test_effect_summon_telnet_e2e.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings, tag
from evennia.objects.models import ObjectDB
from evennia.objects.objects import ObjectSessionHandler
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.combat_maneuvers import ParleyAction
from actions.factories import ConsequencePoolFactory
from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    FALTER_MORALE_THRESHOLD,
    PARLEY_DECISIVE_SUCCESS_LEVEL,
    CombatAllegiance,
    EncounterOutcome,
    OpponentStatus,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.social_combat_content import (
    CHARM_TECHNIQUE_NAME,
    ensure_social_combat_content,
)
from world.magic.factories import CharacterAnimaFactory
from world.magic.models import CharacterTechnique, Technique
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


def _patch_sessions(sessions_by_pk: dict) -> object:
    """Patch ``ObjectSessionHandler.all`` per-character (mirrors
    world/scenes/tests/test_outcome_delivery.py's helper of the same name)."""

    def _fake_all(handler: ObjectSessionHandler) -> list[object]:
        return sessions_by_pk.get(handler.obj.pk, [])

    return patch.object(ObjectSessionHandler, "all", _fake_all)


@tag("postgres")
@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_social_combat_content gates on #2698
class SocialVictoryTelnetE2ETests(TestCase):
    """Charm one bandit, parley the other -> VICTORY with no one defeated (#4091).

    Uses setUp (not setUpTestData): ObjectDB / SharedMemoryModel instances
    cannot be deepcopied by Django's setUpTestData machinery (DbHolder is not
    deepcopyable — raises copy.Error in CI shard runs; see project memory).

    @tag("postgres") on the class: the charm cast's condition-application path
    uses a PG-only DISTINCT ON. All tests in this class are SKIPPED on the
    SQLite fast tier.
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel identity-map cache to prevent PK recycling
        # from a prior test leaking stale instances (see project memory).
        idmapper_models.flush_cache()

        # -- ActionTemplate: required so _combat_actions surfaces the technique --
        self.action_template = ensure_technique_cast_content()

        # -- Social-combat content: Rally/Demoralize/Taunt/Parley CheckTypes,
        # the Inspired condition, and the Charming Word charm technique (#2015). --
        ensure_social_combat_content()
        self.charm_technique = Technique.objects.get(name=CHARM_TECHNIQUE_NAME)
        # The seed is content-repo-owned and carries no action_template; wire one
        # directly so the telnet cast command surfaces it (mirrors the pattern in
        # world/mechanics/tests/test_pipeline_integration.py).
        self.charm_technique.action_template = self.action_template
        self.charm_technique.save()

        # -- Encounter: DECLARING so dispatch_player_action accepts a declaration --
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # -- Two bandits, each with their own aftermath pool --
        self.bandit_a = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Bandit A",
            allegiance=CombatAllegiance.ENEMY,
            aftermath_pool=ConsequencePoolFactory(),
        )
        self.bandit_b = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Bandit B",
            allegiance=CombatAllegiance.ENEMY,
            aftermath_pool=ConsequencePoolFactory(),
        )

        # -- PC participant: sheet -> character -> vitals/anima/engagement/room --
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
        CharacterAnimaFactory(
            character=self.character.sheet_data,
            current=20,
            maximum=20,
        )
        CharacterEngagementFactory(character=self.character.sheet_data)

        # Place the caster in the encounter's room: the room-wide OUTCOME
        # broadcast at completion reaches every object in encounter.room.
        room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.character.location = room
        self.character.save()

        # Link the charm technique to the caster's sheet — required for
        # CmdDeclareTechnique._resolve_technique_id (name lookup) and
        # _combat_actions (filters CharacterTechnique by character).
        CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.charm_technique,
        )

    def test_charm_and_parley_end_in_social_victory(self) -> None:
        """Charm Bandit A, parley Bandit B -> both WON_OVER, VICTORY, no deaths.

        Round 1: cast Charming Word at Bandit A -> Charmed applied.
        Round 2: parley Bandit B (faltering morale meets the gate) -> decisive
                 success calms Bandit B -> no hostile opponents remain ->
                 resolve_round auto-completes the encounter as VICTORY.

        The PC's session is a bare telnet session (no webclient outputfunc):
        the final assertion proves the won-over clause reaches it as plain
        text via deliver_outcome_interaction's telnet-parity line (#3807),
        not merely the WebSocket ``interaction=`` payload (#4091 fix round 2).
        """
        self.character.msg = MagicMock()
        telnet_session = MagicMock()
        telnet_session.protocol_key = "telnet"

        # --- Round 1: telnet cast the charm technique at Bandit A ---
        cmd = _make_cmd(
            self.character,
            f"{self.charm_technique.name} at {self.bandit_a.name}",
        )
        cmd.func()

        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            action.focused_action_id,
            self.charm_technique.pk,
            "focused_action should be the declared Charming Word technique",
        )

        with patch("world.combat.services.perform_check") as mock_offense:
            mock_offense.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        # Bandit A's stored status/allegiance are untouched by the charm (D4) —
        # only its EFFECTIVE allegiance (derived from the Charmed condition) flips.
        self.bandit_a.refresh_from_db()
        self.assertEqual(self.bandit_a.status, OpponentStatus.ACTIVE)
        self.assertEqual(self.bandit_a.allegiance, CombatAllegiance.ENEMY)

        # The encounter must still be open: Bandit B is untouched and still hostile.
        self.encounter.refresh_from_db()
        self.assertNotEqual(self.encounter.status, RoundStatus.COMPLETED)

        # --- Round 2: advance, then parley Bandit B ---
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

        self.bandit_b.morale = FALTER_MORALE_THRESHOLD
        self.bandit_b.save(update_fields=["morale"])

        result = ParleyAction().execute(self.character, opponent_id=self.bandit_b.pk)
        self.assertTrue(result.success, result.message)

        with (
            patch("world.checks.services.perform_check") as mock_social,
            patch(
                "world.checks.consequence_resolution.apply_pool_deterministically",
                return_value=[],
            ) as mock_apply_pool,
            _patch_sessions({self.character.pk: [telnet_session]}),
            self.captureOnCommitCallbacks(execute=True),
        ):
            mock_social.return_value = MagicMock(success_level=PARLEY_DECISIVE_SUCCESS_LEVEL)
            resolve_round(self.encounter)

        # --- Headline DoD: social victory, both bandits won over, no violence ---
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.COMPLETED)
        self.assertEqual(self.encounter.outcome, EncounterOutcome.VICTORY)

        self.bandit_a.refresh_from_db()
        self.bandit_b.refresh_from_db()
        self.assertEqual(
            {self.bandit_a.status, self.bandit_b.status},
            {OpponentStatus.WON_OVER},
        )

        # --- Both opponents' aftermath pools fired (one call each) ---
        self.assertEqual(mock_apply_pool.call_count, 2)

        # --- The PC's bare telnet session received the won-over clause as
        # plain text (#3807 telnet parity) -- not merely the WebSocket
        # "interaction=" kwarg payload (#4091 fix round 2). ---
        text_calls = [
            call
            for call in self.character.msg.call_args_list
            if call.args and "interaction" not in call.kwargs
        ]
        self.assertTrue(text_calls, self.character.msg.call_args_list)
        won_over_text = " ".join(str(call.args[0]) for call in text_calls)
        self.assertIn("charmed", won_over_text)
        self.assertIn("calmed", won_over_text)
