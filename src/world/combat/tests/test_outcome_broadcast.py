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

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
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
from world.scenes.constants import InteractionMode, RoundStatus
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

    def _setup_encounter(
        self, *, pc_hit_text: str = "", npc_hit_text: str = "", mook_health: int = 50
    ):
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=30, hit_narration=npc_hit_text)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=mook_health,
            max_health=mook_health,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        room = ObjectDBFactory(
            db_key="OutcomeBroadcastRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            hit_narration=pc_hit_text,
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
        # mook_health=15: the PC's 20-damage hit (SL=2, full multiplier) defeats
        # it this round, so the encounter actually completes as VICTORY and
        # reaches _broadcast_encounter_outcome -- the only caller of
        # broadcast_action_outcome that opts into deliver_telnet=True
        # (deliver_outcome_interaction, deferred to transaction.on_commit).
        # Without this, the round never completes and the test's own name
        # ("...and_broadcasts_outcome") is proven only by the unrelated,
        # always-synchronous per-action ACTION-interaction push (#4091 fix
        # round 3 -- caught as a false positive in round 2's review).
        encounter = self._setup_encounter(mook_health=15)

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        with (
            mock.patch("world.scenes.interaction_services._broadcast_to_location") as broadcast,
            self.captureOnCommitCallbacks(execute=True),
        ):
            resolve_round(encounter, offense_check_fn=mock_check_fn)

        # Narrowed to the TOP-LEVEL encounter-outcome row specifically (its
        # ceremonial headline, see _ENCOUNTER_OUTCOME_HEADLINES) -- every
        # per-action attack narration is ALSO mode=OUTCOME and ALSO pushed via
        # this same mocked _broadcast_to_location, so an unscoped id set would
        # pass even with the encounter-outcome push removed (the exact false
        # positive #4091 fix round 2's review caught here).
        encounter_outcome_ids = set(
            Interaction.objects.filter(
                mode=InteractionMode.OUTCOME, content__icontains="field falls silent"
            ).values_list("pk", flat=True)
        )
        assert encounter_outcome_ids
        assert any(
            call.args[1]["id"] in encounter_outcome_ids
            and call.args[1]["mode"] == InteractionMode.OUTCOME
            for call in broadcast.call_args_list
        ), broadcast.call_args_list

    def test_authored_technique_line_heads_the_pc_outcome(self) -> None:
        encounter = self._setup_encounter(pc_hit_text="{actor} hurls a spear of rime at {target}")

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        with mock.patch("world.scenes.interaction_services._broadcast_to_location"):
            resolve_round(encounter, offense_check_fn=mock_check_fn)

        lines = list(
            Interaction.objects.filter(mode=InteractionMode.OUTCOME).values_list(
                "content", flat=True
            )
        )
        authored = [line for line in lines if "hurls a spear of rime at" in line]
        assert authored, lines
        assert "{actor}" not in authored[0]
        assert "{target}" not in authored[0]
        assert " damage" in authored[0]

    def test_authored_threat_entry_line_heads_the_npc_outcome(self) -> None:
        encounter = self._setup_encounter(npc_hit_text="{actor} rakes {target} with its claws")

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        with mock.patch("world.scenes.interaction_services._broadcast_to_location"):
            resolve_round(encounter, offense_check_fn=mock_check_fn)

        lines = list(
            Interaction.objects.filter(mode=InteractionMode.OUTCOME).values_list(
                "content", flat=True
            )
        )
        authored = [line for line in lines if "rakes " in line and " with its claws" in line]
        assert authored, lines
        assert "{actor}" not in authored[0]
        assert "{target}" not in authored[0]
