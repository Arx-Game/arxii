"""Berserk compulsion (#2845). SQLite tier — condition state is patched via
the compulsion lookups (apply_condition is PG-only); declaration plumbing is observed
at the ``_declare_rage_attack`` seam where full validation isn't the subject."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.compulsion import (
    berserk_rampage_window,
    compulsion_technique_for,
)
from world.magic.factories import EffectTypeFactory, TechniqueFactory
from world.magic.models.techniques import CharacterTechnique


@contextmanager
def _berserk_only(*characters):
    """Patch the compulsion lookups to find one only for the given characters."""
    pks = {c.pk for c in characters}

    def one(character, *_args):
        return (MagicMock(), MagicMock()) if character.pk in pks else None

    def many(found):
        return {c.pk: (MagicMock(), MagicMock()) for c in found if c.pk in pks}

    with (
        patch("world.combat.compulsion.active_compulsion", side_effect=one),
        patch("world.combat.compulsion.active_compulsions_for", side_effect=many),
    ):
        yield


class CompulsionTechniqueTest(TestCase):
    """Which technique the rage swings with, ranked over the whole technique list.

    A journey sees only the one technique a compelled attack used; the ranking cases
    (lighter over heavier, a harmless technique never chosen, none at all) are a pure
    selection over rows that no single fight can show side by side.
    """

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
                "world.combat.compulsion._in_uncompleted_encounter",
                return_value=True,
            ),
        ):
            berserk_rampage_window(self.character)
        room.msg_contents.assert_not_called()
