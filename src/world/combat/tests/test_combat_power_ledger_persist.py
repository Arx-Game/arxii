"""The per-cast power ledger persists onto a combat damage-path ACTION interaction.

Mirrors ResolveRoundBasicTests in test_round_orchestrator.py: a single PC casts a
damage-dealing technique at a mook through resolve_round (the production driver).
After resolution, the PC's CombatRoundAction is linked to an ACTION-mode
Interaction and the transient PowerLedger has been copied onto it as
InteractionPowerLedgerEntry rows.
"""

from __future__ import annotations

from decimal import Decimal
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
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.constants import PowerStage
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.vitals.models import CharacterVitals


class CombatPowerLedgerPersistTests(TestCase):
    """A resolved damage-path cast writes ledger rows onto its ACTION interaction."""

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
        """1 PC, 1 mook, declaration phase, full magic-pipeline requirements."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=30)
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
            db_key="TestRoomLedger",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        return encounter, participant, opponent, action

    def test_power_ledger_persisted_on_action_interaction(self) -> None:
        encounter, _participant, _opponent, action = self._setup_encounter()

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        resolve_round(encounter, offense_check_fn=mock_check_fn)

        action.refresh_from_db()
        assert action.interaction_id is not None
        rows = list(action.interaction.power_ledger_entries.all())
        assert rows, "expected persisted power-ledger rows on the ACTION interaction"
        assert rows[0].stage == PowerStage.BASE
