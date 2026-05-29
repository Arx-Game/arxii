"""End-to-end capability-gated agency integration tests (#595).

Exercises the full new model through a combat round:

1. Unconscious PC (awareness=0) → can_act False → cannot declare.
2. Dying PC (Bleeding-Out, awareness intact) → can_act True → can still declare.
3. Terminal-stage Bleeding-Out + forced failing resist → advance_bleed_out sets
   life_state=DEAD.
4. Encounter loss when every active PC is down (none can_act).

Tiering
-------
- Unconscious (non-progressive) tests: SQLite-compatible.
- Bleeding-Out (progressive → DISTINCT ON) tests: @tag("postgres").
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, EncounterStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import _check_encounter_completion, declare_action
from world.conditions.constants import (
    FoundationalCapability,
)
from world.conditions.factories import (
    BleedingOutConditionFactory,
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionStageFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import apply_condition
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals
from world.vitals.services import advance_bleed_out, can_act

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _seed_awareness_capability() -> world.conditions.models.CapabilityType:  # type: ignore[name-defined]
    """Get-or-create AWARENESS capability with innate_baseline=1."""
    return CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)


def _make_alive_vitals(sheet: world.character_sheets.models.CharacterSheet) -> CharacterVitals:  # type: ignore[name-defined]
    """Create a full-health, ALIVE vitals row for *sheet*."""
    return CharacterVitals.objects.create(
        character_sheet=sheet,
        health=100,
        max_health=100,
        base_max_health=100,
        life_state=CharacterLifeState.ALIVE,
    )


def _make_declaring_setup(
    *,
    num_participants: int = 1,
) -> tuple:
    """Return (encounter, participants, opponent) in DECLARING status.

    participants is a list of length *num_participants*.
    Each participant has alive vitals already created.
    """
    encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
    participants = []
    for _ in range(num_participants):
        participant = CombatParticipantFactory(encounter=encounter)
        _make_alive_vitals(participant.character_sheet)
        participants.append(participant)
    opponent = CombatOpponentFactory(encounter=encounter)
    return encounter, participants, opponent


def _unconscious_condition() -> world.conditions.models.ConditionTemplate:  # type: ignore[name-defined]
    """Build an Unconscious condition that zeroes AWARENESS capability."""
    awareness = _seed_awareness_capability()
    condition = UnconsciousConditionFactory()
    ConditionCapabilityEffectFactory(
        condition=condition,
        capability=awareness,
        value=-100,
    )
    return condition


# ---------------------------------------------------------------------------
# Part A — Unconscious PC cannot declare (SQLite-compatible)
# ---------------------------------------------------------------------------


class UnconsciousAgencyTests(TestCase):
    """Unconscious PC (awareness zeroed) → can_act False → declare blocked.

    Unconscious is non-progressive → no DISTINCT ON → SQLite-safe.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.effect_attack = EffectTypeFactory(name="Attack-Agency", base_power=10)

    def test_unconscious_cannot_act(self) -> None:
        """Applying Unconscious (awareness=0) sets can_act to False."""
        _, participants, _ = _make_declaring_setup()
        participant = participants[0]
        character = participant.character_sheet.character

        condition = _unconscious_condition()
        apply_condition(target=character, condition=condition)

        self.assertFalse(can_act(character))

    def test_unconscious_cannot_declare(self) -> None:
        """An Unconscious participant is blocked from declaring an action."""
        _, participants, opponent = _make_declaring_setup()
        participant = participants[0]
        character = participant.character_sheet.character

        condition = _unconscious_condition()
        apply_condition(target=character, condition=condition)

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_attack)
        with self.assertRaisesRegex(ValueError, "dead or incapacitated"):
            declare_action(
                participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=opponent,
            )

    def test_alive_and_aware_can_declare(self) -> None:
        """Baseline: an ALIVE + aware PC can declare without error."""
        _seed_awareness_capability()
        _, participants, opponent = _make_declaring_setup()
        participant = participants[0]

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_attack)
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertEqual(action.focused_action_id, technique.pk)


# ---------------------------------------------------------------------------
# Part B — Dying PC (Bleeding-Out) keeps awareness → still can declare
# ---------------------------------------------------------------------------


@tag("postgres")
class DyingAgencyTests(TestCase):
    """Dying-but-conscious PC (Bleeding-Out, awareness intact) can still declare.

    Bleeding-Out is progressive → apply_condition uses DISTINCT ON → @tag("postgres").
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.effect_attack = EffectTypeFactory(name="Attack-Dying", base_power=10)

    def _apply_bleed_out(self, character: evennia.objects.models.ObjectDB) -> None:  # type: ignore[name-defined]
        """Apply a single-stage Bleeding-Out condition to *character*."""
        bleed_out = BleedingOutConditionFactory()
        ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Bleeding",
            rounds_to_next=None,
        )
        result = apply_condition(target=character, condition=bleed_out)
        self.assertTrue(result.success, "Expected Bleeding-Out apply to succeed")

    def test_dying_character_can_still_act(self) -> None:
        """Bleeding-Out does NOT impair awareness → can_act returns True."""
        _seed_awareness_capability()
        _, participants, _ = _make_declaring_setup()
        character = participants[0].character_sheet.character

        self._apply_bleed_out(character)

        self.assertTrue(
            can_act(character),
            "Dying character with awareness must still be able to act",
        )

    def test_dying_character_can_declare(self) -> None:
        """A dying-but-conscious PC declares an action successfully."""
        _seed_awareness_capability()
        _, participants, opponent = _make_declaring_setup()
        participant = participants[0]

        self._apply_bleed_out(participant.character_sheet.character)

        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_attack)
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertEqual(action.focused_action_id, technique.pk)


# ---------------------------------------------------------------------------
# Part C — Terminal bleed-out failure → life_state=DEAD
# ---------------------------------------------------------------------------


@tag("postgres")
class BleedOutProgressionTests(TestCase):
    """advance_bleed_out at the terminal stage with a failing resist → DEAD.

    Bleeding-Out is progressive → @tag("postgres").
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.fail_outcome = CheckOutcomeFactory(name="bleed-fail", success_level=-1)
        cls.pass_outcome = CheckOutcomeFactory(name="bleed-pass", success_level=1)
        cls.resist_check = CheckTypeFactory(name="bleed-resist")

    def _build_terminal_bleed_out(self) -> world.conditions.models.ConditionTemplate:  # type: ignore[name-defined]
        """Create a Bleeding-Out template with exactly one stage (terminal by definition)."""
        bleed_out = BleedingOutConditionFactory()
        ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Critical Bleed",
            rounds_to_next=None,
            resist_check_type=self.resist_check,
            resist_difficulty=10,
        )
        return bleed_out

    def test_terminal_stage_failure_marks_dead(self) -> None:
        """Failing the resist at a terminal stage sets life_state=DEAD."""
        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = _make_alive_vitals(sheet)

        bleed_out = self._build_terminal_bleed_out()
        apply_result = apply_condition(target=character, condition=bleed_out)
        self.assertTrue(apply_result.success)

        with force_check_outcome(self.fail_outcome):
            died = advance_bleed_out(character)

        self.assertTrue(died, "advance_bleed_out must return True when terminal stage fails")
        vitals.refresh_from_db()
        self.assertEqual(
            vitals.life_state,
            CharacterLifeState.DEAD,
            "life_state must be DEAD after terminal bleed-out failure",
        )

    def test_terminal_stage_failure_blocks_can_act(self) -> None:
        """After bleed-out death, can_act returns False."""
        sheet = CharacterSheetFactory()
        character = sheet.character
        _make_alive_vitals(sheet)
        _seed_awareness_capability()

        bleed_out = self._build_terminal_bleed_out()
        apply_condition(target=character, condition=bleed_out)

        with force_check_outcome(self.fail_outcome):
            advance_bleed_out(character)

        self.assertFalse(can_act(character))

    def test_terminal_stage_success_keeps_alive(self) -> None:
        """Passing the resist at a terminal stage does NOT kill the character."""
        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = _make_alive_vitals(sheet)

        bleed_out = self._build_terminal_bleed_out()
        apply_condition(target=character, condition=bleed_out)

        with force_check_outcome(self.pass_outcome):
            died = advance_bleed_out(character)

        self.assertFalse(died)
        vitals.refresh_from_db()
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

    def test_non_terminal_stage_failure_advances_stage(self) -> None:
        """Failing at a non-terminal stage advances the instance, does not kill."""
        bleed_out = BleedingOutConditionFactory()
        stage1 = ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Bleeding",
            rounds_to_next=2,
            resist_check_type=self.resist_check,
            resist_difficulty=10,
        )
        stage2 = ConditionStageFactory(
            condition=bleed_out,
            stage_order=2,
            name="Critical",
            rounds_to_next=None,
            resist_check_type=self.resist_check,
            resist_difficulty=15,
        )

        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = _make_alive_vitals(sheet)
        apply_condition(target=character, condition=bleed_out)

        # Verify instance starts at stage 1
        instance = ConditionInstance.objects.get(target=character, condition=bleed_out)
        self.assertEqual(instance.current_stage, stage1)

        with force_check_outcome(self.fail_outcome):
            died = advance_bleed_out(character)

        self.assertFalse(died, "Non-terminal failure must not kill")
        instance.refresh_from_db()
        self.assertEqual(instance.current_stage, stage2, "Stage must advance to stage 2")
        vitals.refresh_from_db()
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)


# ---------------------------------------------------------------------------
# Part D — Encounter loss when all PCs are down
# ---------------------------------------------------------------------------


class EncounterLossWhenAllPCsDownTests(TestCase):
    """Encounter loss when no active PC can_act.

    Uses Unconscious (non-progressive) to avoid DISTINCT ON → SQLite-safe.
    """

    def _setup_encounter_with_active_opponent(self) -> tuple:
        """Return (encounter, participants) — opponent still active."""
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        _make_alive_vitals(participant.character_sheet)
        # Opponent remains active (not defeated)
        CombatOpponentFactory(encounter=encounter)
        return encounter, participant

    def test_encounter_not_lost_while_pc_can_act(self) -> None:
        """When at least one PC can_act, encounter completion is not triggered by PC loss."""
        _seed_awareness_capability()
        encounter, _ = self._setup_encounter_with_active_opponent()

        self.assertFalse(
            _check_encounter_completion(encounter),
            "Encounter must not complete while a PC can still act",
        )

    def test_encounter_lost_when_all_pcs_unconscious(self) -> None:
        """When every active PC is Unconscious (can_act False), encounter is lost."""
        encounter, participant = self._setup_encounter_with_active_opponent()
        character = participant.character_sheet.character

        condition = _unconscious_condition()
        apply_condition(target=character, condition=condition)

        self.assertFalse(can_act(character), "Pre-condition: PC must be incapacitated")
        self.assertTrue(
            _check_encounter_completion(encounter),
            "Encounter must be marked complete when all PCs cannot act",
        )

    def test_encounter_not_lost_when_dying_but_conscious(self) -> None:
        """A dying-but-conscious PC (Bleeding-Out, awareness intact) keeps the encounter alive.

        Uses direct ConditionInstance creation (bypassing apply_condition) to avoid the
        PG-only DISTINCT ON path so this test stays SQLite-compatible while still
        asserting the dying-but-conscious semantics.
        """
        _seed_awareness_capability()
        encounter, participant = self._setup_encounter_with_active_opponent()
        character = participant.character_sheet.character

        # Create Bleeding-Out template via factory (supplies the required category FK),
        # then insert a ConditionInstance directly — skips apply_condition's DISTINCT ON.
        bleed_out_template = BleedingOutConditionFactory()
        ConditionInstance.objects.create(
            target=character,
            condition=bleed_out_template,
            current_stage=None,
            stacks=1,
            severity=1,
        )

        self.assertTrue(can_act(character), "Dying-but-conscious PC must still be able to act")
        self.assertFalse(
            _check_encounter_completion(encounter),
            "Encounter must not complete while dying PC can still act",
        )
