"""Telnet-driven E2E: cast Summon Spirit → ally joins combat → damages enemy NPC (#1584 DoD).

Proves the full pipeline:
  CmdDeclareTechnique.func()
    → dispatch_player_action(COMBAT)
    → CombatRoundContext.record_declaration()
    → declare_action() [writes CombatRoundAction]
  resolve_round(encounter)  [round 1]
    → resolve_combat_technique()
    → use_technique() with SELF Summon Spirit technique
    → apply_technique_conditions() → bulk_apply_conditions()
    → CONDITION_APPLIED emitted
    → TriggerDefinition fires → summon_ally_on_condition adapter
    → summon_ally() → ALLY CombatOpponent created in encounter
  begin_declaration_phase(encounter)  [advance to round 2]
  select_npc_actions(encounter)
    → ALLY summon is ACTIVE with threat_pool → targets ENEMY opponent
  resolve_round(encounter)  [round 2]
    → _resolve_npc_action_on_opponent_target()
    → apply_damage_to_opponent() → enemy.health drops

Definition of Done for #1584: ``enemy.health < 50`` after round 2.

@tag("postgres") — REQUIRED.  ``apply_technique_conditions`` → ``bulk_apply_conditions``
uses a PG-only DISTINCT ON clause (NotSupportedError on SQLite).  This test is SKIPPED
on the SQLite fast tier and CI-gated.  Do not attempt to run it locally.

Round-advance sequence (verified against services.py):
  1. ``resolve_round`` transitions encounter DECLARING → BETWEEN_ROUNDS.
  2. ``begin_declaration_phase(encounter)`` transitions BETWEEN_ROUNDS → DECLARING,
     increments round_number.  The function always fetches the encounter fresh
     (select_for_update), so the stale Python object can be passed in.
  3. ``self.encounter.refresh_from_db()`` syncs the Python object so
     ``select_npc_actions`` (which reads encounter.status directly) sees DECLARING.
  4. ``select_npc_actions(encounter)`` builds CombatOpponentAction rows for the
     ALLY summon (targeting the ENEMY via combatants_hostile_to) and the ENEMY
     (targeting the PC caster).
  5. ``resolve_round(encounter)`` resolves all actions.

Mirror of setUp pattern from test_combat_cast_telnet_e2e.py.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatAllegiance,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatRoundAction
from world.combat.services import begin_declaration_phase, resolve_round, select_npc_actions
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.effect_palette_content import SUMMON_TECHNIQUE_NAME, ensure_effect_palette_content
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


@tag("postgres")
class SummonSpiritTelnetE2ETests(TestCase):
    """Cast Summon Spirit → ALLY CombatOpponent joins → damages ENEMY in round 2.

    This is the definition-of-done for #1584.  The whole-chain proof:
    a player casts a SELF effect technique, a reactive flow summons an ALLY
    combatant, and the next round that ally attacks and damages an ENEMY NPC.

    Uses setUp (not setUpTestData): ObjectDB / SharedMemoryModel instances
    cannot be deepcopied by Django's setUpTestData machinery (DbHolder is not
    deepcopyable — raises copy.Error in CI shard runs; see project memory).

    @tag("postgres") on the class: the cast path through
    apply_technique_conditions → bulk_apply_conditions uses a PG-only
    DISTINCT ON.  All tests in this class are SKIPPED on the SQLite fast tier.
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel identity-map cache to prevent PK recycling
        # from a prior test leaking stale instances (see project memory).
        idmapper_models.flush_cache()

        # -- Damage multiplier rows (needed for resolve_round to apply damage) --
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # -- ActionTemplate: required so _combat_actions surfaces the technique --
        ensure_technique_cast_content()

        # -- Summon Spirit technique + CONDITION_APPLIED wiring (Task 14a) --
        # ensure_effect_palette_content() seeds the full palette idempotently,
        # including the Summon Spirit Technique, its ThreatPool (base_damage=6),
        # the Summoning ConditionTemplate, the FlowDefinition → summon_ally_on_condition
        # adapter, and the TriggerDefinition on CONDITION_APPLIED.
        ensure_effect_palette_content()

        # -- Encounter: DECLARING so dispatch_player_action accepts a declaration --
        # CombatEncounterFactory always creates a room (lazy_attribute → create_object).
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # -- ENEMY mook with its own ThreatPool --
        enemy_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=enemy_pool, base_damage=30)
        self.enemy = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=enemy_pool,
            allegiance=CombatAllegiance.ENEMY,
        )

        # -- PC participant: sheet → character → vitals / anima / engagement / room --
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
        # CharacterAnima.character FK → ObjectDB (the game object, not the sheet).
        self.character = self.sheet.character
        CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )
        CharacterEngagementFactory(character=self.character)

        # Place the caster in the encounter's room.
        # summon_ally looks up the caster's CombatParticipant, finds the encounter,
        # and creates the ALLY CombatOpponent in that encounter.  The character
        # must be in the room so the cast command's location-dependent queries
        # (and DAMAGE_PRE_APPLY location check) don't fail.
        room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.character.location = room
        self.character.save()

        # -- Summon Spirit technique: seeded by ensure_effect_palette_content() --
        # Verify by name using the module-level constant (stable key).
        self.summon_tech = Technique.objects.get(name=SUMMON_TECHNIQUE_NAME)

        # Link the technique to the caster's sheet.
        # Required for CmdDeclareTechnique._resolve_technique_id (name lookup on
        # CharacterTechnique rows) and _combat_actions (filter by character).
        CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.summon_tech,
        )

    def test_summon_enters_combat_and_damages_enemy(self) -> None:
        """Cast Summon Spirit → ALLY joins → next round it damages the ENEMY NPC.

        Two-round flow:
          Round 1: cast Summon Spirit (SELF, no target) → CombatRoundAction recorded
                   → resolve_round → Summoning condition applied → CONDITION_APPLIED
                   → summon_ally_on_condition → ALLY CombatOpponent created.
          Round 2: begin_declaration_phase + select_npc_actions (ALLY targets ENEMY)
                   → resolve_round → _resolve_npc_action_on_opponent_target
                   → apply_damage_to_opponent → enemy.health < 50.
        """
        # --- Step 1: telnet cast command (SELF technique; no "at <target>") ---
        cmd = _make_cmd(self.character, self.summon_tech.name)
        cmd.func()

        # CombatRoundAction must be recorded for this participant in round 1.
        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=1,
        )
        self.assertEqual(
            action.focused_action_id,
            self.summon_tech.pk,
            "focused_action should be the Summon Spirit technique",
        )

        # --- Step 2: resolve round 1 (cast → Summoning condition → summon_ally) ---
        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        # --- Step 3: assert the ALLY CombatOpponent was created ---
        summon = CombatOpponent.objects.get(
            encounter=self.encounter,
            allegiance=CombatAllegiance.ALLY,
        )
        self.assertEqual(
            summon.summoned_by,
            self.sheet,
            "summoned_by must point at the caster's CharacterSheet",
        )
        self.assertTrue(
            summon.objectdb_is_ephemeral,
            "a summoned ally must be ephemeral (no pre-existing persona)",
        )

        # --- Step 4: advance to round 2 ---
        # begin_declaration_phase fetches the encounter fresh (select_for_update),
        # so the stale Python object is safe to pass in.  Afterwards we refresh
        # so that select_npc_actions (which reads encounter.status directly) sees
        # the updated status.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

        # --- Step 5: let the ALLY summon pick the ENEMY as its target ---
        # combatants_hostile_to(ALLY) → hostile to ENEMY opponents only.
        # select_npc_actions creates a CombatOpponentAction for the summon
        # pointing at self.enemy.
        select_npc_actions(self.encounter)

        # --- Step 6: resolve round 2 (summon attacks ENEMY) ---
        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = MagicMock(success_level=2)
            resolve_round(self.encounter)

        # --- Headline DoD: the summoned ally damaged the enemy NPC ---
        self.enemy.refresh_from_db()
        self.assertLess(
            self.enemy.health,
            50,
            "summoned ally should have damaged the ENEMY NPC in round 2",
        )
