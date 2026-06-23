"""Telnet-driven non-combat cast E2E (#1332): CmdAttempt → use_technique.

Proves the full pipeline:
  CmdAttempt.func()
    → request_technique_cast(scene, persona, technique)
    → _resolve_cast()
    → use_technique()
    → anima deducted, OUTCOME Interaction written to scene, TECHNIQUE_CAST emitted

Setup uses setUp (not setUpTestData) for all ObjectDB objects to avoid copy.Error
in CI shard runs (DbHolder deepcopy trap — see project memory).

perform_check is patched to return SL=2 (full success) for determinism,
matching the pattern in test_combat_cast_telnet_e2e.py.

SQLite tier: passes cleanly. The benign self-cast path through request_technique_cast
→ _resolve_cast → use_technique does not invoke DISTINCT ON (no apply_condition
on the self-cast benign path), so no @tag("postgres") is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia import create_object
from evennia.utils.idmapper import models as idmapper_models

from actions.factories import ActionTemplateFactory
from commands.magic import CmdAttempt
from flows.constants import EventName
from world.magic.factories import BinaryEffectTypeFactory, CharacterAnimaFactory, TechniqueFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Interaction
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


def _make_attempt_cmd(caller, args: str) -> CmdAttempt:
    """Build a CmdAttempt wired to *caller* with *args*."""
    cmd = CmdAttempt()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"attempt {args}"
    cmd.cmdname = "attempt"
    return cmd


class NoncombatCastTelnetE2ETests(TestCase):
    """CmdAttempt.func() drives the full non-combat cast pipeline.

    Uses setUp (not setUpTestData) for ObjectDB objects to avoid the
    DbHolder deepcopy trap in CI shard runs.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        self.room = create_object("typeclasses.rooms.Room", key="CastTestRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)

        self.persona = PersonaFactory()
        self.character = self.persona.character_sheet.character
        self.character.db_location = self.room
        self.character.save()

        # anima_cost=20 ensures effective_cost > 0 even with the unengaged social-safety
        # bonus (+10 control) applied by _get_social_safety_bonus(). Without this, the
        # delta formula floors at 0 and deduct_anima is called with 0 — no deduction.
        self.technique = TechniqueFactory(
            anima_cost=20,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        grant_technique(self.persona, self.technique)

        CharacterVitals.objects.create(
            character_sheet=self.persona.character_sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        self.anima = CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=30,
        )

        self._check_patcher = patch(
            "actions.services.perform_check",
            return_value=MagicMock(
                success_level=2,
                outcome=MagicMock(name="Success"),
                outcome_name="Success",
            ),
        )
        self._check_patcher.start()
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()

    def tearDown(self) -> None:
        self._check_patcher.stop()
        self._accrue_patcher.stop()

    def test_attempt_command_deducts_anima(self) -> None:
        """CmdAttempt drives use_technique which deducts anima."""
        anima_before = self.anima.current

        cmd = _make_attempt_cmd(self.character, self.technique.name)
        cmd.func()

        self.anima.refresh_from_db()
        self.assertLess(
            self.anima.current,
            anima_before,
            "anima.current must decrease: use_technique deducts the technique's anima cost",
        )

    def test_attempt_command_writes_outcome_interaction(self) -> None:
        """CmdAttempt causes a Narrator OUTCOME Interaction to be written to the scene."""
        cmd = _make_attempt_cmd(self.character, self.technique.name)
        cmd.func()

        self.assertTrue(
            Interaction.objects.filter(
                scene=self.scene,
                mode=InteractionMode.OUTCOME,
            ).exists(),
            "An OUTCOME Interaction must exist in the scene after a resolved cast",
        )

    def test_attempt_command_emits_technique_cast_event(self) -> None:
        """CmdAttempt causes TECHNIQUE_CAST to be emitted via emit_event.

        Patches world.magic.services.techniques.emit_event because techniques.py
        binds emit_event at import time; patching flows.emit.emit_event alone
        would not intercept calls made via that module-level binding.
        """
        from flows.emit import emit_event as _real_emit_event
        import world.magic.services.techniques as _techniques_mod

        with patch.object(
            _techniques_mod,
            "emit_event",
            wraps=_real_emit_event,
        ) as mock_emit:
            cmd = _make_attempt_cmd(self.character, self.technique.name)
            cmd.func()

        technique_cast_calls = [
            c for c in mock_emit.call_args_list if c.args and c.args[0] == EventName.TECHNIQUE_CAST
        ]
        self.assertTrue(
            len(technique_cast_calls) >= 1,
            f"emit_event must be called with TECHNIQUE_CAST; calls: {mock_emit.call_args_list}",
        )
