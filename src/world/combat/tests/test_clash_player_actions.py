"""Tests for Task 7.2: clash opportunities surfaced in get_player_actions.

Covers:
- (a) No active clashes → no clash-backed PlayerActions emitted.
- (b) One active clash → two PlayerActions (FOCUSED + PASSIVE).
- (c) Two active clashes → four PlayerActions (2 × FOCUSED + 2 × PASSIVE).
- (d) Already-declared: if the PC has a ClashContributionDeclaration for the
  clash this round, both slot descriptors are still emitted (v1 behavior: no
  suppression; the UI can highlight the already-chosen slot).
- (e) RESOLVED clash → not in get_player_actions.
- (f) Clash in a different encounter → does not appear for this PC.

ActionRef encoding contract:
  Each clash-contribution PlayerAction carries
  ActionRef(backend=COMBAT, clash_id=<pk>, clash_action_slot=<slot value>).
  No technique_id.  A future dispatcher can decode (clash_id, action_slot) from
  ref.clash_id and ref.clash_action_slot directly.
"""

from __future__ import annotations

import django.test

from actions.constants import ActionBackend
from world.combat.constants import ClashActionSlot, ClashStatus, EncounterStatus, ParticipantStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.models import ClashContributionDeclaration
from world.magic.factories import TechniqueFactory


def _clash_contribution_actions_for(character: object) -> list:
    """Return only the clash-contribution COMBAT PlayerActions for *character*.

    Uses get_player_actions end-to-end and filters to COMBAT actions that carry
    a clash_id (i.e. clash-contribution descriptors, not technique declarations).
    """
    from actions.player_interface import get_player_actions

    all_actions = get_player_actions(character)  # type: ignore[arg-type]
    return [
        a for a in all_actions if a.backend == ActionBackend.COMBAT and a.ref.clash_id is not None
    ]


class ClashPlayerActionsNoClashesTests(django.test.TestCase):
    """No active clashes → no clash PlayerActions."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character

    def test_no_active_clashes_returns_no_clash_actions(self) -> None:
        """Encounter with no active clashes → get_player_actions has no clash-backed actions."""
        clash_actions = _clash_contribution_actions_for(self.character)
        self.assertEqual(
            clash_actions,
            [],
            "No clash actions expected when the encounter has no active clashes",
        )


class ClashPlayerActionsOneClashTests(django.test.TestCase):
    """One active clash → two PlayerActions (FOCUSED + PASSIVE)."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character
        cls.clash = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )

    def test_active_clash_emits_focused_only(self) -> None:
        """One active clash → one FOCUSED PlayerAction (PASSIVE deprecated per spec)."""
        clash_actions = _clash_contribution_actions_for(self.character)

        slots = {a.ref.clash_action_slot for a in clash_actions}
        self.assertEqual(
            len(clash_actions),
            1,
            f"Expected 1 clash action (FOCUSED only), got {len(clash_actions)}",
        )
        self.assertEqual(slots, {ClashActionSlot.FOCUSED})

    def test_clash_actions_reference_correct_clash(self) -> None:
        """All clash-contribution actions reference the active clash by clash_id."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for action in clash_actions:
            self.assertEqual(
                action.ref.clash_id,
                self.clash.pk,
                f"ref.clash_id mismatch: expected {self.clash.pk}, got {action.ref.clash_id}",
            )

    def test_clash_actions_backend_is_combat(self) -> None:
        """All clash-contribution actions have backend=COMBAT."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for action in clash_actions:
            self.assertEqual(action.backend, ActionBackend.COMBAT)

    def test_clash_actions_have_no_technique_id(self) -> None:
        """Clash-contribution ActionRefs have no technique_id (slot-only refs)."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for action in clash_actions:
            self.assertIsNone(
                action.ref.technique_id,
                "Clash-contribution ActionRef must not carry a technique_id",
            )

    def test_clash_actions_check_type_is_none(self) -> None:
        """check_type is None for clash contributions — chosen at declaration time."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for action in clash_actions:
            self.assertIsNone(
                action.check_type,
                "Clash-contribution PlayerAction.check_type must be None",
            )

    def test_clash_actions_prerequisite_met(self) -> None:
        """v1: prerequisite_met is always True, prerequisite_reasons always empty."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for action in clash_actions:
            self.assertTrue(action.prerequisite_met)
            self.assertEqual(action.prerequisite_reasons, [])


class ClashPlayerActionsTwoClashesTests(django.test.TestCase):
    """Two active clashes → four PlayerActions (2 × FOCUSED + 2 × PASSIVE)."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character

        cls.clash_a = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )
        cls.clash_b = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )

    def test_two_active_clashes_emit_two_focused_actions(self) -> None:
        """Two active clashes → 2 clash-contribution PlayerActions (FOCUSED-only)."""
        clash_actions = _clash_contribution_actions_for(self.character)
        self.assertEqual(
            len(clash_actions),
            2,
            f"Expected 2 clash actions (2 clashes × FOCUSED), got {len(clash_actions)}",
        )

    def test_both_clash_ids_represented(self) -> None:
        """Both clash PKs appear in the emitted actions."""
        clash_actions = _clash_contribution_actions_for(self.character)
        clash_ids = {a.ref.clash_id for a in clash_actions}
        self.assertIn(self.clash_a.pk, clash_ids)
        self.assertIn(self.clash_b.pk, clash_ids)

    def test_focused_slot_only_per_clash(self) -> None:
        """For each clash, exactly one FOCUSED descriptor is emitted (PASSIVE deprecated)."""
        clash_actions = _clash_contribution_actions_for(self.character)
        for clash in (self.clash_a, self.clash_b):
            clash_slots = {
                a.ref.clash_action_slot for a in clash_actions if a.ref.clash_id == clash.pk
            }
            self.assertEqual(
                clash_slots,
                {ClashActionSlot.FOCUSED},
                f"Clash {clash.pk} must emit exactly one FOCUSED slot",
            )


class ClashPlayerActionsAlreadyDeclaredTests(django.test.TestCase):
    """PC with an existing ClashContributionDeclaration still sees the FOCUSED descriptor.

    Combat-resolution-loop spec: clashes are committed via the focused
    action only — there is no PASSIVE slot. A PC with an existing
    declaration still sees the FOCUSED descriptor so they can re-declare
    (changing the technique or strain) until the round resolves.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=2,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character
        cls.clash = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )

    def test_already_declared_pc_still_sees_focused_slot(self) -> None:
        """v1: FOCUSED descriptor is still emitted even when a declaration exists.

        Design choice: no suppression at the read path. The frontend handles
        highlighting the active declaration and the service layer enforces
        uniqueness at write time.
        """
        technique = TechniqueFactory()
        ClashContributionDeclaration.objects.create(
            encounter=self.encounter,
            round_number=self.encounter.round_number,
            participant=self.participant,
            clash=self.clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=technique,
            strain_commitment=0,
        )

        clash_actions = _clash_contribution_actions_for(self.character)
        self.assertEqual(
            len(clash_actions),
            1,
            "FOCUSED descriptor must still appear after a declaration is on file",
        )
        self.assertEqual(clash_actions[0].ref.clash_action_slot, ClashActionSlot.FOCUSED)


class ClashPlayerActionsResolvedClashTests(django.test.TestCase):
    """RESOLVED clash does not appear in get_player_actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character
        ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.RESOLVED,
        )

    def test_resolved_clash_does_not_appear(self) -> None:
        """A RESOLVED clash must not produce PlayerActions."""
        clash_actions = _clash_contribution_actions_for(self.character)
        self.assertEqual(
            clash_actions,
            [],
            "RESOLVED clash must not appear in get_player_actions",
        )


class ClashPlayerActionsOtherEncounterTests(django.test.TestCase):
    """Clashes in another PC's encounter do not leak into this PC's action list."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()

        # PC A — the character under test
        cls.encounter_a = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant_a = CombatParticipantFactory(
            encounter=cls.encounter_a,
            status=ParticipantStatus.ACTIVE,
        )
        cls.character_a = cls.participant_a.character_sheet.character

        # PC B — a different PC in a different encounter with an active clash
        encounter_b = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        ClashFactory(encounter=encounter_b, status=ClashStatus.ACTIVE)

    def test_clash_in_different_encounter_does_not_appear(self) -> None:
        """Clashes in encounter_b must not surface in PC A's action list."""
        clash_actions = _clash_contribution_actions_for(self.character_a)
        self.assertEqual(
            clash_actions,
            [],
            "Clash from another encounter must not appear in this PC's action list",
        )


class ClashPlayerActionsDeclarationClosedTests(django.test.TestCase):
    """Clash contribution actions are not emitted when the declaration window is closed.

    Verifies that _clash_contribution_actions respects the same is_declaration_open
    gate as _combat_actions.  During RESOLVING and BETWEEN_ROUNDS phases the window
    is closed and no clash contribution descriptors should surface, even if active
    clashes exist in the encounter.
    """

    def _make_encounter_with_active_clash(self, status: str) -> object:
        """Create an encounter in *status* with an ACTIVE participant and an ACTIVE clash.

        Returns the participant's character ObjectDB.
        """
        encounter = CombatEncounterFactory(status=status, round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        ClashFactory(encounter=encounter, status=ClashStatus.ACTIVE)
        return participant.character_sheet.character

    def test_no_clash_actions_when_resolving(self) -> None:
        """Encounter in RESOLVING → is_declaration_open is False → no clash contribution actions."""
        ClashConfigFactory()
        character = self._make_encounter_with_active_clash(EncounterStatus.RESOLVING)
        clash_actions = _clash_contribution_actions_for(character)
        self.assertEqual(
            clash_actions,
            [],
            "Clash contribution actions must not appear when encounter is RESOLVING",
        )

    def test_no_clash_actions_when_between_rounds(self) -> None:
        """Encounter in BETWEEN_ROUNDS → is_declaration_open is False → no clash actions."""
        ClashConfigFactory()
        character = self._make_encounter_with_active_clash(EncounterStatus.BETWEEN_ROUNDS)
        clash_actions = _clash_contribution_actions_for(character)
        self.assertEqual(
            clash_actions,
            [],
            "Clash contribution actions must not appear when encounter is BETWEEN_ROUNDS",
        )
