"""Readied ultimates follow Audere; only the combat declaration admits one (#4098)."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from actions.constants import ActionBackend
from actions.player_interface import get_player_actions
from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import ConditionInstanceFactory
from world.magic.audere import end_audere
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    KnownUltimateFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.magic.seeds_cast import ensure_technique_cast_content
from world.mechanics.constants import EngagementType
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


class ReadiedLifecycleTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.audere, _ = wire_audere_power_multipliers()
        AudereThresholdFactory()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=self.sheet, engagement_type=EngagementType.COMBAT)
        self.known = KnownUltimateFactory(character=self.sheet, readied=True)

    def test_end_audere_clears_readied(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        end_audere(self.character)
        self.assertFalse(KnownUltimate.objects.get(pk=self.known.pk).readied)

    def test_accept_clears_stale_readied(self) -> None:
        from world.magic.audere import offer_audere

        offer_audere(self.character, accept=True)
        self.assertFalse(KnownUltimate.objects.get(pk=self.known.pk).readied)


class CombatCastPathTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.audere, _ = wire_audere_power_multipliers()
        template = ensure_technique_cast_content()
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=self.sheet, engagement_type=EngagementType.COMBAT)
        self.ultimate = UltimateTechniqueFactory(action_template=template)

    def _combat_ids(self) -> dict[int, bool]:
        return {
            a.ref.technique_id: a.is_ultimate
            for a in get_player_actions(self.character)
            if a.backend == ActionBackend.COMBAT and a.ref.technique_id is not None
        }

    def test_readied_ultimate_offered_in_audere(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=True)
        self.assertEqual(self._combat_ids().get(self.ultimate.pk), True)

    def test_known_but_not_readied_not_offered(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=False)
        self.assertNotIn(self.ultimate.pk, self._combat_ids())

    def test_readied_but_outside_audere_not_offered(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=True)
        self.assertNotIn(self.ultimate.pk, self._combat_ids())

    def test_readied_ultimate_not_offered_outside_combat_declaration(self) -> None:
        """Controller ruling: only the combat declaration path admits an ultimate.

        Same readied pick, same active Audere -- the only difference is the
        encounter is not in a DECLARING round, so this is not a live combat
        declaration (e.g. the round already resolved/ended).
        """
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=True)
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        self.assertNotIn(self.ultimate.pk, self._combat_ids())

    def test_telnet_cast_resolves_readied_ultimate_by_name(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=True)
        cmd = _make_cmd(self.character, self.ultimate.name)
        cmd._technique_name = self.ultimate.name
        self.assertEqual(cmd._resolve_technique(), self.ultimate)

    def test_telnet_cast_does_not_resolve_ultimate_outside_combat_declaration(self) -> None:
        """Controller ruling: the scene cast (no active DECLARING participant) must
        not resolve an ultimate by name, even while it is readied."""
        from commands.exceptions import CommandError

        ConditionInstanceFactory(target=self.character, condition=self.audere)
        KnownUltimateFactory(character=self.sheet, technique=self.ultimate, readied=True)
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        cmd = _make_cmd(self.character, self.ultimate.name)
        cmd._technique_name = self.ultimate.name
        with self.assertRaises(CommandError):
            cmd._resolve_technique()
