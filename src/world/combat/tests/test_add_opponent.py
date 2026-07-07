"""Tests for the add_opponent service with ObjectDB linkage."""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase

from world.areas.positioning.services import position_of


class AddOpponentTests(EvenniaTestCase):
    def test_add_opponent_creates_ephemeral_objectdb(self):
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        opp = add_opponent(
            encounter,
            name="Goblin",
            tier="mook",
            max_health=20,
            threat_pool=pool,
        )
        self.assertTrue(opp.objectdb_is_ephemeral)
        self.assertIsNotNone(opp.objectdb)
        self.assertEqual(opp.objectdb.location, encounter.room)

    def test_add_opponent_with_persona_uses_persona_objectdb(self):
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        opp = add_opponent(
            encounter,
            name="Lord X",
            tier="boss",
            max_health=100,
            threat_pool=pool,
            persona=persona,
        )
        self.assertFalse(opp.objectdb_is_ephemeral)
        self.assertEqual(opp.objectdb, persona.character_sheet.character)

    def test_add_opponent_with_existing_objectdb_marks_non_ephemeral(self):
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        existing = create_object(
            "typeclasses.characters.Character", key="Pre-existing", nohome=True
        )
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        opp = add_opponent(
            encounter,
            name="Pre-existing",
            tier="elite",
            max_health=50,
            threat_pool=pool,
            existing_objectdb=existing,
        )
        self.assertFalse(opp.objectdb_is_ephemeral)
        self.assertEqual(opp.objectdb, existing)

    def test_add_opponent_with_position_places_objectdb(self):
        """Task 3 (#2005): passing position= places the resolved objectdb there."""
        from world.areas.positioning.services import create_position
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        position = create_position(encounter.room, "spawn_pos")

        opp = add_opponent(
            encounter,
            name="Positioned Goblin",
            tier="mook",
            max_health=20,
            threat_pool=pool,
            position=position,
        )
        self.assertEqual(position_of(opp.objectdb), position)

    def test_add_opponent_cross_room_position_raises_before_persisting_opponent(self):
        """Task 4 fold-in (#2005): a cross-room position must not orphan an opponent row."""
        from world.areas.positioning.exceptions import PositionError
        from world.areas.positioning.services import create_position
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.models import CombatOpponent
        from world.combat.services import add_opponent

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        other_room = create_object("typeclasses.rooms.Room", key="OtherRoom", nohome=True)
        position = create_position(other_room, "elsewhere")

        with self.assertRaises(PositionError):
            add_opponent(
                encounter,
                name="Misplaced Goblin",
                tier="mook",
                max_health=20,
                threat_pool=pool,
                position=position,
            )

        self.assertFalse(
            CombatOpponent.objects.filter(encounter=encounter, name="Misplaced Goblin").exists()
        )

    def test_add_opponent_without_position_leaves_objectdb_unplaced(self):
        """Backward compat: omitted position= leaves the opponent unplaced."""
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()

        opp = add_opponent(
            encounter,
            name="Unplaced Goblin",
            tier="mook",
            max_health=20,
            threat_pool=pool,
        )
        self.assertIsNone(position_of(opp.objectdb))

    def test_add_opponent_raises_when_no_room_for_ephemeral(self):
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        encounter = CombatEncounterFactory(room=None)
        pool = ThreatPoolFactory()
        with self.assertRaises(ValueError):
            add_opponent(
                encounter,
                name="Goblin",
                tier="mook",
                max_health=10,
                threat_pool=pool,
            )


class AddOpponentTypeclassGuardTests(EvenniaTestCase):
    def test_existing_objectdb_must_be_character_typeclass(self):
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent

        # Plain Object typeclass — not a Character
        plain = create_object("typeclasses.objects.Object", key="Item", nohome=True)
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()

        with self.assertRaises(TypeError):
            add_opponent(
                encounter,
                name="Bad",
                tier="elite",
                max_health=50,
                threat_pool=pool,
                existing_objectdb=plain,
            )
