"""Tests for seed_or_feed_encounter_from_cast (#772 Task 6).

A HOSTILE standalone cast at another PC seeds (or feeds) a combat encounter,
turning the cast into the caster's opening declaration. These tests verify the
seeding/feeding behaviour and the opponent-kwarg derivation from the target's
CharacterSheet, reusing the existing combat services (add_participant,
join_encounter, add_opponent, begin_declaration_phase, declare_action).
"""

from evennia.utils.test_resources import EvenniaTestCase


class OpponentKwargsFromSheetTests(EvenniaTestCase):
    """Unit tests for the _opponent_kwargs_from_sheet helper."""

    def test_kwargs_pull_real_values_from_target_sheet(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.cast_seed import _opponent_kwargs_from_sheet
        from world.combat.constants import OpponentTier
        from world.vitals.models import CharacterVitals

        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=42,
            max_health=88,
            base_max_health=88,
        )

        kwargs = _opponent_kwargs_from_sheet(sheet)

        self.assertEqual(kwargs["max_health"], 88)
        self.assertEqual(kwargs["tier"], OpponentTier.ELITE)
        self.assertEqual(kwargs["existing_objectdb"], sheet.character)
        # Name comes from the in-world character key.
        self.assertEqual(kwargs["name"], sheet.character.key)

    def test_kwargs_default_max_health_when_no_vitals_row(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.cast_seed import _opponent_kwargs_from_sheet

        sheet = CharacterSheetFactory()
        kwargs = _opponent_kwargs_from_sheet(sheet)

        # No vitals row -> a positive fallback, never zero (PositiveIntegerField,
        # and a zero-HP opponent would be instantly defeated).
        self.assertGreater(kwargs["max_health"], 0)


class SeedOrFeedEncounterFromCastTests(EvenniaTestCase):
    """Integration tests for the seeding/feeding service."""

    @staticmethod
    def _make_caster_and_target():
        from world.character_sheets.factories import CharacterSheetFactory
        from world.vitals.models import CharacterVitals

        caster = CharacterSheetFactory()
        target = CharacterSheetFactory()
        for sheet in (caster, target):
            CharacterVitals.objects.create(
                character_sheet=sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )
        return caster, target

    @staticmethod
    def _make_damage_technique():
        # Default TechniqueFactory: PHYSICAL action_category, EffectType with
        # base_power -> auto-seeded damage profile, no condition_applications.
        # That is exactly a "pure-damage technique" which declare_action requires
        # to target an opponent.
        from world.magic.factories import TechniqueFactory

        return TechniqueFactory()

    @staticmethod
    def _make_scene_with_room():
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="Cast Room", nohome=True)
        scene = SceneFactory(location=room)
        return scene, room

    def test_seeds_new_encounter_when_none_exists(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.constants import EncounterStatus
        from world.combat.models import (
            CombatOpponent,
            CombatParticipant,
            CombatRoundAction,
        )

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        encounter.refresh_from_db()
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)
        self.assertEqual(encounter.scene, scene)

        # Caster is a participant.
        caster_part = CombatParticipant.objects.get(encounter=encounter, character_sheet=caster)

        # Target represented as a PvP opponent backed by its own ObjectDB.
        opponent = CombatOpponent.objects.get(encounter=encounter)
        self.assertEqual(opponent.objectdb, target.character)
        self.assertFalse(opponent.objectdb_is_ephemeral)

        # The cast became the caster's opening declaration this round.
        action = CombatRoundAction.objects.get(
            participant=caster_part,
            round_number=encounter.round_number,
        )
        self.assertEqual(action.focused_action, technique)
        self.assertEqual(action.focused_opponent_target, opponent)

    def test_feeds_existing_active_encounter(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.constants import EncounterStatus, EncounterType, RiskLevel
        from world.combat.models import CombatEncounter

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        existing = CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=EncounterStatus.BETWEEN_ROUNDS,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        # Fed, not recreated.
        self.assertEqual(encounter.pk, existing.pk)
        self.assertEqual(CombatEncounter.objects.filter(scene=scene).count(), 1)
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)
