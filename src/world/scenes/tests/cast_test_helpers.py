"""Shared FactoryBoy helpers for standalone-cast test suites.

These helpers are imported by ``test_cast_services.py``, ``test_cast_integration.py``,
and ``test_action_views.py`` to avoid copy-pasting technique factories and the
"CheckSystem + room + scene + two personas + anima + vitals" fixture that every
cast test needs.

Rule: keep this module to pure setup helpers. Assertions belong in the test files.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from actions.factories import ActionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Persona
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Technique factories
# ---------------------------------------------------------------------------


def make_benign_castable_technique() -> Technique:
    """A non-hostile, standalone-castable technique (binary effect, no damage, has template).

    Readable as seed data: "a technique with a binary (on/off) effect and no
    damage — safe to cast at any target, including another PC."
    """
    return TechniqueFactory(
        effect_type=BinaryEffectTypeFactory(),
        damage_profile=False,
        action_template=ActionTemplateFactory(),
    )


def make_hostile_castable_technique() -> Technique:
    """A hostile (damage-profile) standalone-castable technique.

    Readable as seed data: "a technique that deals damage — triggers combat
    seeding when aimed at another PC."

    Default TechniqueFactory has base_power=10 which auto-seeds a damage
    profile → is_technique_hostile() returns True.
    """
    return TechniqueFactory(action_template=ActionTemplateFactory())


def make_castable_technique(*, hostile: bool = False) -> Technique:
    """Return a castable technique, hostile or benign per the *hostile* flag.

    Convenience wrapper used by the API-layer tests that need a single call site.
    """
    if hostile:
        return make_hostile_castable_technique()
    return make_benign_castable_technique()


def grant_technique(persona: Persona, technique: Technique) -> None:
    """Grant *technique* to *persona*'s CharacterSheet so the knows-check passes."""
    CharacterTechniqueFactory(character=persona.character_sheet, technique=technique)


# ---------------------------------------------------------------------------
# Shared base class — CheckSystem + room + scene + two personas + anima + vitals
# ---------------------------------------------------------------------------


class CastScenarioMixin(TestCase):
    """Shared fixture: check system, room, scene, two personas with anima + vitals.

    Subclasses must call ``super().setUpTestData()`` (or call
    ``_setup_cast_scenario(cls, room_key=...)`` from their own
    ``setUpTestData``).  The ``setUp`` / ``tearDown`` pair patches
    ``award_kudos`` for the duration of each test method.

    Class attributes set:
        cls.scene        — SceneFactory instance in the cast room
        cls.caster       — PersonaFactory instance (has anima + vitals)
        cls.target       — PersonaFactory instance (has vitals)
    """

    scene: object
    caster: Persona
    target: Persona

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()  # type: ignore[misc]
        cls._setup_cast_scenario(room_key="Cast Test Room")

    @classmethod
    def _setup_cast_scenario(cls, *, room_key: str = "Cast Test Room") -> None:
        CheckSystemSetupFactory.create()
        room = create_object("typeclasses.rooms.Room", key=room_key, nohome=True)
        cls.scene = SceneFactory(location=room)

        cls.caster = PersonaFactory()
        cls.target = PersonaFactory()

        # Anima so use_technique can deduct costs without crashing.
        CharacterAnimaFactory(
            character=cls.caster.character_sheet.character,
            current=20,
            maximum=30,
        )
        # Vitals for both personas — combat seeding reads max_health.
        for persona in (cls.caster, cls.target):
            CharacterVitals.objects.create(
                character_sheet=persona.character_sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )

    def setUp(self) -> None:
        # award_kudos would hit the DB for KudosSourceCategory which may not be
        # seeded in the fast tier. Patch it for all cast tests.
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()
