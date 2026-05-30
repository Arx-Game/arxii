"""Integration: round resolution broadcasts ACTION + OUTCOME interactions.

Drives a full ``resolve_round`` over a 1-PC / 1-mook encounter (mirroring the
proven setup in ``test_round_orchestrator``) and asserts that resolution both
persists a Narrator-authored OUTCOME ``Interaction`` and pushes interactions to
the room over the WebSocket broadcast path.
"""

from decimal import Decimal
from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
    EncounterStatus,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    CombatOpponentAction,
    CombatRoundAction,
)
from world.combat.services import resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.vitals.models import CharacterVitals


class OutcomeBroadcastTest(TestCase):
    """Round resolution creates + broadcasts ACTION/OUTCOME interactions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _setup_encounter(self):
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=30)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="OutcomeBroadcastRoom",
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
        )
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)

        return encounter

    def test_resolution_creates_and_broadcasts_outcome(self) -> None:
        encounter = self._setup_encounter()

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        with mock.patch("world.scenes.interaction_services._broadcast_to_location") as broadcast:
            resolve_round(encounter, offense_check_fn=mock_check_fn)

        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists()
        assert broadcast.called
