"""Tests for the combat-side entrance-seeding pieces (#2183 Task 2 / Task 5).

- ``seed_or_feed_encounter_from_benign_intervention``: the benign sibling of
  ``seed_or_feed_encounter_from_cast`` — a protective entrance cast landing on
  an already-embattled ally seats the caster in the fight, with no opponent
  row, no stakes lock, and no FOCUSED declaration.
- ``seed_or_feed_encounter_from_cast(..., from_entrance=True)``: stamps
  ``CombatRoundAction.from_entrance`` on the caster's declared round action,
  so a later task can fire recognition when the declared cast resolves.
- Task 5: a declared FOCUSED cast whose ``CombatRoundAction.from_entrance`` is
  True fires the dramatic-moment suggestion at round resolution, once the real
  success level is known; a ``from_entrance=False`` declaration fires none.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_round
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    ensure_dramatic_entrance_content,
)
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.vitals.models import CharacterVitals


class SeedOrFeedEncounterFromBenignInterventionTests(EvenniaTestCase):
    """Integration tests for the benign-intervention join service."""

    @staticmethod
    def _make_sheets():
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
    def _make_declaring_encounter():
        from world.combat.constants import EncounterType, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.scenes.constants import RoundStatus

        return CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            round_number=1,
        )

    def _intervene(self, caster, target, scene):
        from world.combat.cast_seed import seed_or_feed_encounter_from_benign_intervention

        return seed_or_feed_encounter_from_benign_intervention(
            caster_sheet=caster,
            target_sheet=target,
            scene=scene,
        )

    def test_benign_intervention_seats_caster(self):
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatParticipantFactory
        from world.combat.models import (
            CombatOpponent,
            CombatParticipant,
            EncounterRiskAcknowledgement,
        )

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=target,
            status=ParticipantStatus.ACTIVE,
        )

        with patch("world.combat.cast_seed.activate_stakes_for_scene") as mock_activate_stakes:
            participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNotNone(participant)
        self.assertIsInstance(participant, CombatParticipant)
        self.assertEqual(participant.character_sheet, caster)
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)
        self.assertEqual(participant.encounter, encounter)

        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter,
                character_sheet=caster,
            ).exists()
        )
        self.assertFalse(CombatOpponent.objects.filter(encounter=encounter).exists())
        mock_activate_stakes.assert_not_called()

    def test_benign_intervention_ally_opponent(self):
        from world.combat.constants import CombatAllegiance, OpponentStatus
        from world.combat.factories import CombatOpponentFactory

        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        CombatOpponentFactory(
            encounter=encounter,
            objectdb_id=target.character.pk,
            allegiance=CombatAllegiance.ALLY,
            status=OpponentStatus.ACTIVE,
        )

        participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNotNone(participant)
        self.assertEqual(participant.character_sheet, caster)

    def test_benign_intervention_no_encounter_returns_none(self):
        from world.scenes.factories import SceneFactory

        caster, target = self._make_sheets()
        scene = SceneFactory()

        participant = self._intervene(caster, target, scene)

        self.assertIsNone(participant)

    def test_benign_intervention_target_not_embattled_returns_none(self):
        caster, target = self._make_sheets()
        encounter = self._make_declaring_encounter()
        # Encounter is live, but the target has no participant/opponent row.

        participant = self._intervene(caster, target, encounter.scene)

        self.assertIsNone(participant)


class SeedOrFeedEncounterFromCastEntranceMarkerTests(EvenniaTestCase):
    """Tests for the ``from_entrance`` marker on the hostile-cast declaration path."""

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
    def _make_scene_with_room():
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="Entrance Cast Room", nohome=True)
        scene = SceneFactory(location=room)
        return scene, room

    def test_hostile_seed_marks_from_entrance(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import CombatParticipant, CombatRoundAction

        caster, target = self._make_caster_and_target()
        technique = self._make_damage_technique()
        scene, room = self._make_scene_with_room()

        encounter = seed_or_feed_encounter_from_cast(
            caster_sheet=caster,
            target_sheet=target,
            technique=technique,
            scene=scene,
            room=room,
            from_entrance=True,
        )

        caster_part = CombatParticipant.objects.get(encounter=encounter, character_sheet=caster)
        action = CombatRoundAction.objects.get(
            participant=caster_part,
            round_number=encounter.round_number,
        )
        self.assertTrue(action.from_entrance)

    def test_hostile_seed_from_entrance_defaults_false(self):
        from world.combat.cast_seed import seed_or_feed_encounter_from_cast
        from world.combat.models import CombatParticipant, CombatRoundAction

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

        caster_part = CombatParticipant.objects.get(encounter=encounter, character_sheet=caster)
        action = CombatRoundAction.objects.get(
            participant=caster_part,
            round_number=encounter.round_number,
        )
        self.assertFalse(action.from_entrance)


class EntranceDeclarationSuggestsOnResolutionTests(TestCase):
    """A ``from_entrance=True`` declared cast fires the suggestion at round resolution.

    Mirrors the proven 1-PC / 1-mook setup in ``test_outcome_broadcast.py``; the only
    addition is the ``from_entrance`` marker and the Grand-Entrance dramatic-moment
    content + claimed resonance.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        cls.moment_type = ensure_dramatic_entrance_content()

    def _setup_encounter(self, *, from_entrance: bool):
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
        )
        sheet = CharacterSheetFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=self.moment_type.resonance,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="EntranceSuggestionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
            from_entrance=from_entrance,
        )
        return encounter, sheet

    def test_from_entrance_declaration_suggests_on_resolution(self) -> None:
        encounter, sheet = self._setup_encounter(from_entrance=True)

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=3)

        resolve_round(encounter, offense_check_fn=mock_check_fn)

        self.assertTrue(DramaticMomentSuggestion.objects.filter(character_sheet=sheet).exists())

    def test_non_entrance_declaration_suggests_nothing(self) -> None:
        encounter, sheet = self._setup_encounter(from_entrance=False)

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=3)

        resolve_round(encounter, offense_check_fn=mock_check_fn)

        self.assertFalse(DramaticMomentSuggestion.objects.filter(character_sheet=sheet).exists())
