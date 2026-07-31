"""Berserk compulsion (#2845). SQLite tier — condition state is patched via
``is_berserk`` (apply_condition is PG-only); declaration plumbing is observed
at the ``_declare_rage_attack`` seam where full validation isn't the subject."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.berserk_compulsion import (
    berserk_rampage_window,
    compulsion_technique_for,
    reject_if_berserk,
    select_berserk_actions,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.magic.factories import EffectTypeFactory, TechniqueFactory
from world.magic.models.techniques import CharacterTechnique


def _berserk_only(*characters):
    """Patch is_berserk to be True only for the given characters."""
    pks = {c.pk for c in characters}
    return patch(
        "world.combat.berserk_compulsion.is_berserk",
        side_effect=lambda c: c is not None and c.pk in pks,
    )


class CompulsionTechniqueTest(TestCase):
    def test_picks_the_simplest_damaging_technique(self):
        sheet = CharacterSheetFactory()
        heavy = TechniqueFactory(effect_type=EffectTypeFactory(base_power=8), level=5)
        light = TechniqueFactory(effect_type=EffectTypeFactory(base_power=2), level=1)
        harmless = TechniqueFactory(effect_type=EffectTypeFactory(base_power=None), level=1)
        for technique in (heavy, light, harmless):
            CharacterTechnique.objects.create(character=sheet, technique=technique)
        self.assertEqual(compulsion_technique_for(sheet), light)

    def test_no_damaging_technique_yields_none(self):
        sheet = CharacterSheetFactory()
        CharacterTechnique.objects.create(
            character=sheet,
            technique=TechniqueFactory(effect_type=EffectTypeFactory(base_power=None)),
        )
        self.assertIsNone(compulsion_technique_for(sheet))


class SelectBerserkActionsTest(TestCase):
    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.character = self.participant.character_sheet.character
        technique = TechniqueFactory(effect_type=EffectTypeFactory(base_power=3), level=1)
        CharacterTechnique.objects.create(
            character=self.participant.character_sheet, technique=technique
        )
        self.technique = technique

    def test_non_berserk_participants_are_left_alone(self):
        with (
            _berserk_only(),
            patch("world.combat.berserk_compulsion._declare_rage_attack") as declare,
        ):
            select_berserk_actions(self.encounter)
        declare.assert_not_called()

    def test_berserk_participant_gets_an_auto_attack(self):
        with (
            _berserk_only(self.character),
            patch("world.combat.berserk_compulsion._declare_rage_attack") as declare,
        ):
            select_berserk_actions(self.encounter)
        declare.assert_called_once()
        _participant, technique, target = declare.call_args.args
        self.assertEqual(technique, self.technique)
        self.assertEqual(target, self.opponent)

    def test_steered_rage_is_not_overridden(self):
        """A berserk participant who declared their own attack keeps it."""
        CombatRoundActionFactory(
            participant=self.participant, round_number=self.encounter.round_number
        )
        with (
            _berserk_only(self.character),
            patch("world.combat.berserk_compulsion._declare_rage_attack") as declare,
        ):
            select_berserk_actions(self.encounter)
        declare.assert_not_called()


class RejectIfBerserkTest(TestCase):
    def setUp(self):
        self.participant = CombatParticipantFactory()
        self.character = self.participant.character_sheet.character

    def test_berserk_cannot_disengage(self):
        with _berserk_only(self.character), self.assertRaises(ValueError) as caught:
            reject_if_berserk(self.participant, "flee")
        self.assertIn("rage does not retreat", str(caught.exception))

    def test_lucid_participant_passes(self):
        with _berserk_only():
            reject_if_berserk(self.participant, "flee")

    def test_flee_service_carries_the_guard(self):
        from world.combat.services import declare_flee

        with _berserk_only(self.character), self.assertRaises(ValueError) as caught:
            declare_flee(self.participant)
        self.assertIn("rage does not retreat", str(caught.exception))


class RampageWindowTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        technique = TechniqueFactory(effect_type=EffectTypeFactory(base_power=3), level=1)
        CharacterTechnique.objects.create(character=self.sheet, technique=technique)

    def _room_with(self, *contents):
        room = MagicMock()
        room.contents = [self.character, *contents]
        return room

    def test_lucid_character_never_rampages(self):
        room = self._room_with()
        with (
            _berserk_only(),
            patch.object(type(self.character), "location", room, create=True),
        ):
            berserk_rampage_window(self.character)
        room.msg_contents.assert_not_called()

    def test_no_target_vents_harmlessly(self):
        room = self._room_with()
        with (
            _berserk_only(self.character),
            patch.object(type(self.character), "location", room, create=True),
            patch(
                "world.scenes.interaction_services.get_active_scene",
                return_value=None,
            ),
        ):
            berserk_rampage_window(self.character)
        room.msg_contents.assert_called_once()

    def test_npc_present_seeds_the_encounter(self):
        npc_sheet = CharacterSheetFactory()
        npc = npc_sheet.character
        room = self._room_with(npc)
        scene = MagicMock()
        with (
            _berserk_only(self.character),
            patch.object(type(self.character), "location", room, create=True),
            patch.object(type(npc), "db_account", None, create=True),
            patch("world.vitals.services.can_act", return_value=True),
            patch(
                "world.scenes.interaction_services.get_active_scene",
                return_value=scene,
            ),
            patch("world.combat.cast_seed.seed_or_feed_encounter_from_cast") as seed,
        ):
            berserk_rampage_window(self.character)
        seed.assert_called_once()
        self.assertEqual(seed.call_args.kwargs["target_sheet"], npc_sheet)

    def test_already_fighting_defers_to_combat_compulsion(self):
        room = self._room_with()
        with (
            _berserk_only(self.character),
            patch.object(type(self.character), "location", room, create=True),
            patch(
                "world.combat.berserk_compulsion._in_uncompleted_encounter",
                return_value=True,
            ),
        ):
            berserk_rampage_window(self.character)
        room.msg_contents.assert_not_called()
