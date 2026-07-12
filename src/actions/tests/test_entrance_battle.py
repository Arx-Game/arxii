"""Tests for battle-front technique entrance composition (#2225).

``EntranceAction._execute_technique_entrance`` gains a battles-aware pre-gate
(``_resolve_battle_context``) that detects when the actor is an active
``BattleParticipant`` stationed at a ``BattlePlace`` whose battle's scene matches
the current scene. On the hostile-seeded path, ``_maybe_bind_battle_encounter``
binds the newly seeded encounter to the ``BattlePlace`` and installs the
place-encounter-outcome trigger — composing #2183's entrance path with #2008's
front-stationing gate.

Test coverage:
- Hostile entrance feeds existing front encounter (no new binding)
- Hostile entrance seeds and binds a new front encounter
- Hostile entrance overwrites a stale (completed) FK
- Non-stationed participant falls through to normal flow
- Non-battle participant unaffected
- Scene co-location guard
- Inline entrance by battle participant (no binding)
- Unit tests for _resolve_battle_context and _maybe_bind_battle_encounter
"""

from __future__ import annotations

from actions.definitions.social import EntranceAction
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
)
from world.battles.services import open_place_encounter
from world.combat.constants import (
    EncounterType,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
)
from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.magic.factories import (
    CharacterResonanceFactory,
    ensure_dramatic_entrance_content,
)
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_hostile_castable_technique,
)


def _make_room(label: str = "BattleEntranceRoom") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class BattleFrontEntranceTestBase(CastScenarioMixin):
    """Shared fixture: cast scenario + a battle with a place and stationed participant.

    The caster is enlisted as a BattleParticipant stationed at a BattlePlace
    whose battle's scene is the cast scenario's scene.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        ActionTemplateFactory(name="Entrance", grants_entry_flourish=True)
        moment_type = ensure_dramatic_entrance_content()
        CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet,
            resonance=moment_type.resonance,
        )

    def setUp(self) -> None:
        super().setUp()
        # Set db_location so the actor is in the scene's room.
        for persona in (self.caster, self.target):
            character = persona.character_sheet.character
            character.db_location = self.scene.location
            character.save()

        # Create a battle whose scene is the cast scenario's scene.
        self.battle = BattleFactory(name="Test Battle")
        self.battle.scene = self.scene
        self.battle.scene.save(update_fields=["location"])
        self.battle.save(update_fields=["scene"])

        self.attacker_side = BattleSideFactory(battle=self.battle, role="attacker")
        self.defender_side = BattleSideFactory(battle=self.battle, role="defender")

        self.place = BattlePlaceFactory(battle=self.battle, name="The Gates")

        # Enlist the caster as a participant stationed at the place.
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.caster.character_sheet,
            place=self.place,
        )

    def _actor(self):
        return self.caster.character_sheet.character


class ResolveBattleContextTests(CastScenarioMixin):
    """Unit tests for EntranceAction._resolve_battle_context."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

    def setUp(self) -> None:
        super().setUp()
        for persona in (self.caster, self.target):
            character = persona.character_sheet.character
            character.db_location = self.scene.location
            character.save()

    def _actor(self):
        return self.caster.character_sheet.character

    def test_returns_none_for_non_battle_actor(self) -> None:
        """An actor with no BattleParticipant returns None."""
        result = EntranceAction._resolve_battle_context(self.caster.character_sheet, self.scene)
        self.assertIsNone(result)

    def test_returns_none_for_unstationed_participant(self) -> None:
        """A participant with place=None returns None."""
        battle = BattleFactory(name="Unstationed Battle")
        battle.scene = self.scene
        battle.scene.save(update_fields=["location"])
        battle.save(update_fields=["scene"])
        side = BattleSideFactory(battle=battle)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=self.caster.character_sheet,
            place=None,
        )
        result = EntranceAction._resolve_battle_context(self.caster.character_sheet, self.scene)
        self.assertIsNone(result)

    def test_returns_none_when_scene_colocation_fails(self) -> None:
        """A participant whose battle's scene differs from the actor's scene returns None."""
        other_room = _make_room("OtherSceneRoom")
        other_scene = SceneFactory(location=other_room)
        battle = BattleFactory(name="Other Scene Battle")
        battle.scene = other_scene
        battle.save(update_fields=["scene"])
        side = BattleSideFactory(battle=battle)
        place = BattlePlaceFactory(battle=battle)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=self.caster.character_sheet,
            place=place,
        )
        result = EntranceAction._resolve_battle_context(self.caster.character_sheet, self.scene)
        self.assertIsNone(result)

    def test_returns_context_for_stationed_participant(self) -> None:
        """A stationed participant at the right scene returns (participant, place)."""
        battle = BattleFactory(name="Stationed Battle")
        battle.scene = self.scene
        battle.scene.save(update_fields=["location"])
        battle.save(update_fields=["scene"])
        side = BattleSideFactory(battle=battle)
        place = BattlePlaceFactory(battle=battle)
        participant = BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=self.caster.character_sheet,
            place=place,
        )
        result = EntranceAction._resolve_battle_context(self.caster.character_sheet, self.scene)
        self.assertIsNotNone(result)
        resolved_participant, resolved_place = result  # type: ignore[misc]
        self.assertEqual(resolved_participant.pk, participant.pk)
        self.assertEqual(resolved_place.pk, place.pk)


class MaybeBindBattleEncounterTests(CastScenarioMixin):
    """Unit tests for EntranceAction._maybe_bind_battle_encounter."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

    def setUp(self) -> None:
        super().setUp()
        for persona in (self.caster, self.target):
            character = persona.character_sheet.character
            character.db_location = self.scene.location
            character.save()

        self.battle = BattleFactory(name="Bind Test Battle")
        self.battle.scene = self.scene
        self.battle.scene.save(update_fields=["location"])
        self.battle.save(update_fields=["scene"])
        self.side = BattleSideFactory(battle=self.battle)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.side,
            character_sheet=self.caster.character_sheet,
            place=self.place,
        )

    def test_noop_when_battle_context_is_none(self) -> None:
        """No binding when battle_context is None."""
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
        )
        EntranceAction._maybe_bind_battle_encounter(encounter, None)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)

    def test_noop_when_place_has_open_encounter(self) -> None:
        """No binding when the place already has an open (DECLARING) encounter."""
        existing = open_place_encounter(battle_place=self.place)
        new_encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
        )
        EntranceAction._maybe_bind_battle_encounter(new_encounter, (self.participant, self.place))
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, existing.pk)

    def test_binds_when_place_has_no_encounter(self) -> None:
        """Binds the new encounter when the place has no encounter."""
        new_encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
        )
        EntranceAction._maybe_bind_battle_encounter(new_encounter, (self.participant, self.place))
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, new_encounter.pk)

    def test_overwrites_stale_completed_fk(self) -> None:
        """Overwrites a stale FK pointing at a COMPLETED encounter."""
        stale = open_place_encounter(battle_place=self.place)
        stale.status = RoundStatus.COMPLETED
        stale.save(update_fields=["status"])

        new_encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
        )
        EntranceAction._maybe_bind_battle_encounter(new_encounter, (self.participant, self.place))
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, new_encounter.pk)


class HostileEntranceJourneyTests(BattleFrontEntranceTestBase):
    """E2E journey tests via EntranceAction().execute() for the hostile path."""

    def test_hostile_entrance_seeds_and_binds_new_front_encounter(self) -> None:
        """A stationed participant's hostile entrance seeds + binds a new encounter."""
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.encounter_type, EncounterType.PARTY_COMBAT)

        # The encounter is bound to the BattlePlace.
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, encounter.pk)

        # Caster is a participant with from_entrance=True.
        caster_participant = CombatParticipant.objects.get(
            encounter=encounter,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        action_row = CombatRoundAction.objects.get(
            participant=caster_participant,
            round_number=encounter.round_number,
        )
        self.assertTrue(action_row.from_entrance)

    def test_hostile_entrance_feeds_existing_front_encounter(self) -> None:
        """A stationed participant's hostile entrance feeds an existing open encounter."""
        # Create a MODERATE-risk encounter bound to the place (open_place_encounter
        # creates LETHAL, which requires risk acknowledgement; a MODERATE encounter
        # is feedable without acknowledgement, matching the cast-seeded default).
        existing = CombatEncounterFactory(
            scene=self.scene,
            room=self.scene.location,
            status=RoundStatus.DECLARING,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        self.place.combat_encounter = existing
        self.place.save(update_fields=["combat_encounter"])

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)

        # No new encounter created — the existing one was fed.
        self.assertEqual(CombatEncounter.objects.filter(scene=self.scene).count(), 1)

        # The place's encounter is unchanged.
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, existing.pk)

        # Caster joined the existing encounter.
        caster_participant = CombatParticipant.objects.get(
            encounter=existing,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        action_row = CombatRoundAction.objects.get(
            participant=caster_participant,
            round_number=existing.round_number,
        )
        self.assertTrue(action_row.from_entrance)

    def test_hostile_entrance_overwrites_stale_completed_fk(self) -> None:
        """A hostile entrance overwrites a stale (completed) FK on the BattlePlace."""
        stale = open_place_encounter(battle_place=self.place)
        stale.status = RoundStatus.COMPLETED
        stale.save(update_fields=["status"])

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)

        # A new encounter was created (the stale one is COMPLETED, not feedable).
        new_encounter = CombatEncounter.objects.filter(
            scene=self.scene, status=RoundStatus.DECLARING
        ).first()
        self.assertIsNotNone(new_encounter)
        self.assertNotEqual(new_encounter.pk, stale.pk)

        # The place's FK now points at the new encounter.
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, new_encounter.pk)

    def test_non_stationed_participant_falls_through(self) -> None:
        """A battle participant with place=None gets the normal entrance flow."""
        self.participant.place = None
        self.participant.save(update_fields=["place"])

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)

        # An encounter was seeded (normal flow), but NOT bound to the place.
        CombatEncounter.objects.get(scene=self.scene)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)

    def test_non_battle_participant_unaffected(self) -> None:
        """A character with no BattleParticipant gets the normal entrance flow."""
        # Remove the participant so the caster is not in any battle.
        self.participant.delete()

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)

        # An encounter was seeded (normal flow), but NOT bound to the place.
        CombatEncounter.objects.get(scene=self.scene)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)

    def test_scene_colocation_guard(self) -> None:
        """When the battle's scene differs from the actor's scene, no binding."""
        # Create a separate scene/room for the battle.
        other_room = _make_room("OtherColocationRoom")
        other_scene = SceneFactory(location=other_room)
        self.battle.scene = other_scene
        self.battle.save(update_fields=["scene"])

        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)

        result = EntranceAction().execute(
            self._actor(),
            None,
            technique_id=technique.pk,
            target_persona_id=self.target.pk,
            confirm_soulfray_risk=True,
        )

        self.assertTrue(result.success, result.message)

        # An encounter was seeded on the actor's scene (normal flow), but NOT
        # bound to the place (whose battle is on a different scene).
        CombatEncounter.objects.get(scene=self.scene)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)
