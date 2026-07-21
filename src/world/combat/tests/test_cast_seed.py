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

    def _seed(self, caster, target, technique, scene, room):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast

        return seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

    def test_seeds_new_encounter_when_none_exists(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import (
            CombatOpponent,
            CombatParticipant,
            CombatRoundAction,
        )
        from world.scenes.constants import RoundStatus

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
        self.assertEqual(encounter.status, RoundStatus.DECLARING)
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
        from world.combat.constants import EncounterType, RiskLevel
        from world.combat.models import CombatEncounter
        from world.scenes.constants import RoundStatus

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        existing = CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=RoundStatus.BETWEEN_ROUNDS,
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
        self.assertEqual(encounter.status, RoundStatus.DECLARING)

    def test_declaring_feed_reuses_existing_active_opponent(self):
        from world.combat.models import CombatOpponent, CombatRoundAction

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        first = self._seed(caster, target, technique, scene, room)
        self.assertEqual(CombatOpponent.objects.filter(encounter=first).count(), 1)

        # Encounter is now DECLARING; a second hostile cast at the same target
        # must reuse the existing opponent row, not violate the unique constraint.
        second = self._seed(caster, target, technique, scene, room)

        self.assertEqual(second.pk, first.pk)
        opponents = CombatOpponent.objects.filter(encounter=first)
        self.assertEqual(opponents.count(), 1)
        action = CombatRoundAction.objects.get(
            participant__character_sheet=caster, round_number=first.round_number
        )
        self.assertEqual(action.focused_opponent_target, opponents.get())

    def test_declaring_feed_updates_existing_declaration_in_place(self):
        from world.combat.models import CombatRoundAction

        caster, target = self._make_caster_and_target()
        first_technique = self._make_damage_technique()
        second_technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = self._seed(caster, target, first_technique, scene, room)
        self._seed(caster, target, second_technique, scene, room)

        actions = CombatRoundAction.objects.filter(
            participant__character_sheet=caster, round_number=encounter.round_number
        )
        self.assertEqual(actions.count(), 1)
        self.assertEqual(actions.get().focused_action, second_technique)

    def test_declaring_feed_joins_caster_not_yet_participating(self):
        from world.combat.models import CombatParticipant
        from world.scenes.constants import RoundStatus

        caster, target = self._make_caster_and_target()
        second_caster, _ = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = self._seed(caster, target, technique, scene, room)
        self.assertEqual(encounter.status, RoundStatus.DECLARING)

        # A different caster casts into the now-DECLARING encounter → joins it.
        self._seed(second_caster, target, technique, scene, room)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=encounter, character_sheet=second_caster
            ).exists()
        )

    def test_cross_encounter_retarget_creates_fresh_opponent_row(self):
        from world.combat.models import CombatOpponent
        from world.scenes.constants import RoundStatus

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        old = self._seed(caster, target, technique, scene, room)
        old.status = RoundStatus.COMPLETED
        old.save(update_fields=["status"])

        new = self._seed(caster, target, technique, scene, room)

        self.assertNotEqual(new.pk, old.pk)
        new_row = CombatOpponent.objects.get(encounter=new)
        self.assertEqual(new_row.objectdb, target.character)
        # The completed encounter was not fed; its historical row survives.
        old.refresh_from_db()
        self.assertEqual(old.status, RoundStatus.COMPLETED)
        self.assertTrue(CombatOpponent.objects.filter(encounter=old).exists())

    def test_defeated_target_in_same_encounter_raises(self):
        from world.combat.constants import OpponentStatus
        from world.combat.models import CombatOpponent

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = self._seed(caster, target, technique, scene, room)
        row = CombatOpponent.objects.get(encounter=encounter)
        row.status = OpponentStatus.DEFEATED
        row.save(update_fields=["status"])

        with self.assertRaises(ValueError):
            self._seed(caster, target, technique, scene, room)


class SeedOrFeedEncounterOpenedFromParleyTests(EvenniaTestCase):
    """``opened_from_parley`` stamping (#2536 slice 3, Task 4): a CREATE from an
    active non-Battle-backed Scene stamps True; feeding an existing encounter
    never flips it, regardless of the feeding scene's classification."""

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
        from world.magic.factories import TechniqueFactory

        return TechniqueFactory()

    @staticmethod
    def _make_scene_with_room(*, is_active=True):
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="Parley Cast Room", nohome=True)
        scene = SceneFactory(location=room, is_active=is_active)
        return scene, room

    def test_create_from_active_scene_stamps_opened_from_parley(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room(is_active=True)

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        self.assertTrue(encounter.opened_from_parley)

    def test_create_from_inactive_scene_leaves_flag_false(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room(is_active=False)

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        self.assertFalse(encounter.opened_from_parley)

    def test_create_from_battle_backed_scene_leaves_flag_false(self):
        from evennia import create_object

        from world.battles.factories import BattleFactory
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()

        # Battle scenes are location-less (ADR-0081, Battle.save()) — the `room`
        # kwarg below is only the CombatEncounter.room, unrelated to the battle
        # backing scene's (always-None) location.
        room = create_object("typeclasses.rooms.Room", key="Battle Cast Room", nohome=True)
        battle = BattleFactory()
        scene = battle.scene

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        self.assertFalse(encounter.opened_from_parley)

    def test_feeding_existing_encounter_never_flips_flag(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.constants import EncounterType, RiskLevel
        from world.combat.models import CombatEncounter
        from world.scenes.constants import RoundStatus

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room(is_active=True)

        existing = CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            opened_from_parley=False,
        )

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
        )

        self.assertEqual(encounter.pk, existing.pk)
        self.assertFalse(encounter.opened_from_parley)
