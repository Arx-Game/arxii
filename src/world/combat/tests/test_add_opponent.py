"""Tests for the add_opponent service with ObjectDB linkage."""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase


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

        existing = create_object("typeclasses.characters.Character", key="Pre-existing")
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
