"""Tests for get_player_actions and dispatch_player_action — unified player-action interfaces.

Covers:
- (a) CHALLENGE backend: character with matching capability in a room with an active challenge.
- (b) COMBAT backend: character who is an ACTIVE participant in a DECLARING encounter.
- (c) REGISTRY backend: registry actions are currently excluded (no check_type).
- (d) Recomputed each call: a new challenge instance added between calls appears on second call.
- (e) dispatch_player_action: immediate CHALLENGE → resolve_challenge runs (side effect visible).
- (f) dispatch_player_action: immediate REGISTRY → action.run() invoked (result returned).
- (g) dispatch_player_action: DECLARING round + COMBAT ref → deferred via record_declaration.
- (h) dispatch_player_action: DECLARING round + CHALLENGE ref → deferred (no resolve_challenge).
- (i) dispatch_player_action: stale/unknown ref → ActionDispatchError(UNKNOWN_ACTION_REF).
"""

from __future__ import annotations

from unittest.mock import patch

import django.test
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import CapabilityTypeFactory
from world.fatigue.constants import EffortLevel
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Set character location via raw DB update and patch the Python instance.

    Uses a queryset update to bypass Evennia's at_db_location_postsave hook
    (which requires contents_cache to be initialized).  Then patches the in-memory
    instance so subsequent reads of ``character.db_location`` return the room.

    Returns the same character instance with ``db_location`` patched.
    """
    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    # Patch the in-memory instance so the cached attribute is correct.
    # SharedMemoryModel identity map would return the stale Python object, so we
    # update it directly rather than re-fetching (which would return the same
    # stale cached instance).
    character.db_location = room
    return character


def _make_challenge_setup(sheet: object, room: ObjectDB) -> tuple:
    """Wire capability + challenge + approach + technique grant so the character
    (identified by *sheet*) can act on an active challenge in *room*.

    Returns (challenge_instance, approach, capability, check_type).
    """
    from world.magic.factories import (
        CharacterTechniqueFactory,
        TechniqueCapabilityGrantFactory,
        TechniqueFactory,
    )

    check_type = CheckTypeFactory()
    capability = CapabilityTypeFactory()
    prop = PropertyFactory()

    app = ApplicationFactory(capability=capability, target_property=prop)
    template = ChallengeTemplateFactory()
    template.properties.add(prop)

    approach = ChallengeApproachFactory(
        challenge_template=template,
        application=app,
        check_type=check_type,
        action_template=None,  # plain approach — no override
    )
    challenge_instance = ChallengeInstance.objects.create(
        template=template,
        location=room,
        target_object=room,
        is_active=True,
        is_revealed=True,
    )

    # Give the character a technique that grants the capability
    technique = TechniqueFactory(damage_profile=False)
    TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
    CharacterTechniqueFactory(character=sheet, technique=technique)

    return challenge_instance, approach, capability, check_type


# ---------------------------------------------------------------------------
# Test: CHALLENGE backend
# ---------------------------------------------------------------------------


_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)


class TestGetPlayerActionsChallengeBackend(django.test.TestCase):
    """Character with matching capability in a room with an active challenge.

    Patches _get_difficulty_indicator_for_check to return MODERATE (not IMPOSSIBLE)
    so test characters without full trait setup still produce actions.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDB.objects.create(db_key="ChallengeRoom")
        cls.sheet = CharacterSheetFactory()
        # Set character location (bypasses Evennia's at_db_location_postsave hook).
        cls.character = _set_character_location(cls.sheet.character, cls.room)

        cls.challenge_instance, cls.approach, cls.capability, cls.check_type = (
            _make_challenge_setup(cls.sheet, cls.room)
        )

    def setUp(self) -> None:
        # Test characters have no traits → difficulty is IMPOSSIBLE without the patch.
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_includes_challenge_player_action(self) -> None:
        """get_player_actions returns a CHALLENGE PlayerAction for a matching approach."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        challenge_actions = [a for a in actions if a.backend == ActionBackend.CHALLENGE]
        self.assertTrue(
            len(challenge_actions) >= 1,
            f"Expected at least 1 CHALLENGE action, got: {challenge_actions}",
        )

    def test_challenge_action_has_correct_check_type_instance(self) -> None:
        """The CHALLENGE PlayerAction carries the CheckType instance, not a string."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        challenge_actions = [a for a in actions if a.backend == ActionBackend.CHALLENGE]
        self.assertTrue(len(challenge_actions) >= 1)
        action = challenge_actions[0]
        from world.checks.models import CheckType

        self.assertIsInstance(action.check_type, CheckType)
        self.assertEqual(action.check_type.pk, self.check_type.pk)

    def test_plain_approach_has_no_action_template(self) -> None:
        """A plain (no override) approach yields PlayerAction.action_template = None."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        challenge_actions = [a for a in actions if a.backend == ActionBackend.CHALLENGE]
        self.assertTrue(len(challenge_actions) >= 1)
        action = challenge_actions[0]
        self.assertIsNone(action.action_template)

    def test_challenge_ref_fields(self) -> None:
        """CHALLENGE ActionRef has correct challenge_instance_id and approach_id."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        challenge_actions = [a for a in actions if a.backend == ActionBackend.CHALLENGE]
        self.assertTrue(len(challenge_actions) >= 1)
        ref = challenge_actions[0].ref
        self.assertEqual(ref.backend, ActionBackend.CHALLENGE)
        self.assertEqual(ref.challenge_instance_id, self.challenge_instance.pk)
        self.assertEqual(ref.approach_id, self.approach.pk)


# ---------------------------------------------------------------------------
# Test: COMBAT backend
# ---------------------------------------------------------------------------


class TestGetPlayerActionsCombatBackend(django.test.TestCase):
    """Character who is ACTIVE in a DECLARING encounter with a declarable technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

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

        # Give the participant a technique with an action_template
        cls.check_type = CheckTypeFactory()
        cls.template = ActionTemplateFactory(check_type=cls.check_type)
        cls.technique = TechniqueFactory(
            damage_profile=False,
            action_template=cls.template,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

    def test_includes_combat_player_action(self) -> None:
        """get_player_actions returns a COMBAT PlayerAction when character is declaring."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertTrue(
            len(combat_actions) >= 1,
            f"Expected at least 1 COMBAT action, got {combat_actions}",
        )

    def test_combat_action_has_correct_check_type_instance(self) -> None:
        """COMBAT PlayerAction.check_type comes from technique.action_template.check_type."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertTrue(len(combat_actions) >= 1)
        action = combat_actions[0]
        from world.checks.models import CheckType

        self.assertIsInstance(action.check_type, CheckType)
        self.assertEqual(action.check_type.pk, self.check_type.pk)

    def test_combat_action_has_action_template(self) -> None:
        """COMBAT PlayerAction.action_template is the technique's action_template."""
        from actions.models import ActionTemplate
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertTrue(len(combat_actions) >= 1)
        action = combat_actions[0]
        self.assertIsInstance(action.action_template, ActionTemplate)
        self.assertEqual(action.action_template.pk, self.template.pk)

    def test_combat_ref_has_technique_id(self) -> None:
        """COMBAT ActionRef has technique_id set."""
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertTrue(len(combat_actions) >= 1)
        ref = combat_actions[0].ref
        self.assertEqual(ref.backend, ActionBackend.COMBAT)
        self.assertEqual(ref.technique_id, self.technique.pk)

    def test_technique_without_action_template_excluded(self) -> None:
        """A technique the character knows but without an action_template is excluded."""
        from actions.player_interface import get_player_actions
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        # Technique with NO action_template — not combat-usable
        non_combat_technique = TechniqueFactory(damage_profile=False, action_template=None)
        CharacterTechniqueFactory(character=self.sheet, technique=non_combat_technique)

        actions = get_player_actions(self.character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        technique_ids = [a.ref.technique_id for a in combat_actions]
        self.assertNotIn(
            non_combat_technique.pk,
            technique_ids,
            "Technique without action_template must not appear in COMBAT actions",
        )
        # The combat-usable technique from setUpTestData still appears
        self.assertIn(self.technique.pk, technique_ids)


# ---------------------------------------------------------------------------
# Test: COMBAT backend — declaration window closed (RESOLVING / BETWEEN_ROUNDS)
# ---------------------------------------------------------------------------


class TestGetPlayerActionsCombatWindowClosed(django.test.TestCase):
    """COMBAT actions are not surfaced when the declaration window is closed."""

    def _make_participant_with_technique(self, status: str) -> tuple:
        """Create an encounter in *status* with an ACTIVE participant who has a combat technique.

        Returns (character ObjectDB, technique).
        """
        from actions.factories import ActionTemplateFactory
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        encounter = CombatEncounterFactory(status=status, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        sheet = participant.character_sheet
        character = sheet.character

        check_type = CheckTypeFactory()
        template = ActionTemplateFactory(check_type=check_type)
        technique = TechniqueFactory(damage_profile=False, action_template=template)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        return character, technique

    def test_no_combat_actions_when_resolving(self) -> None:
        """Encounter in RESOLVING → is_declaration_open is False → no COMBAT actions."""
        from actions.player_interface import get_player_actions

        character, _technique = self._make_participant_with_technique(EncounterStatus.RESOLVING)
        actions = get_player_actions(character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertEqual(
            combat_actions,
            [],
            "COMBAT actions must not appear when encounter is RESOLVING",
        )

    def test_no_combat_actions_when_between_rounds(self) -> None:
        """Encounter in BETWEEN_ROUNDS → is_declaration_open is False → no COMBAT actions."""
        from actions.player_interface import get_player_actions

        character, _technique = self._make_participant_with_technique(
            EncounterStatus.BETWEEN_ROUNDS
        )
        actions = get_player_actions(character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertEqual(
            combat_actions,
            [],
            "COMBAT actions must not appear when encounter is BETWEEN_ROUNDS",
        )


# ---------------------------------------------------------------------------
# Test: COMBAT backend — no active combat
# ---------------------------------------------------------------------------


class TestGetPlayerActionsCombatAbsentWhenNotInCombat(django.test.TestCase):
    """Character with no active combat → no COMBAT PlayerActions."""

    def test_no_combat_actions_without_encounter(self) -> None:
        from actions.factories import ActionTemplateFactory
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        sheet = CharacterSheetFactory()
        character = sheet.character

        check_type = CheckTypeFactory()
        template = ActionTemplateFactory(check_type=check_type)
        technique = TechniqueFactory(damage_profile=False, action_template=template)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        from actions.player_interface import get_player_actions

        actions = get_player_actions(character)
        combat_actions = [a for a in actions if a.backend == ActionBackend.COMBAT]
        self.assertEqual(combat_actions, [])


# ---------------------------------------------------------------------------
# Test: REGISTRY backend — currently excluded (no check_type)
# ---------------------------------------------------------------------------


class TestGetPlayerActionsRegistryBackend(django.test.TestCase):
    """Registry actions without a check_type are excluded from the merged list."""

    def test_registry_actions_excluded_when_no_check_type(self) -> None:
        """All current registry actions have no ActionTemplate/check_type → excluded."""
        from actions.player_interface import get_player_actions

        sheet = CharacterSheetFactory()
        character = sheet.character

        actions = get_player_actions(character)
        # No REGISTRY actions should appear because none of the current registry
        # actions have an associated ActionTemplate/check_type.
        registry_actions = [a for a in actions if a.backend == ActionBackend.REGISTRY]
        self.assertEqual(
            registry_actions,
            [],
            "Registry actions without check_type should be excluded",
        )


# ---------------------------------------------------------------------------
# Test: recomputed each call (no caching)
# ---------------------------------------------------------------------------


class TestGetPlayerActionsRecomputedEachCall(django.test.TestCase):
    """get_player_actions is recomputed on every call — new challenges appear."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import (
            CharacterTechniqueFactory,
            TechniqueCapabilityGrantFactory,
            TechniqueFactory,
        )

        cls.room = ObjectDB.objects.create(db_key="RecomputeRoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = _set_character_location(cls.sheet.character, cls.room)

        # Set up a capability the character has
        cls.check_type = CheckTypeFactory()
        cls.capability = CapabilityTypeFactory()
        cls.prop = PropertyFactory()
        cls.app = ApplicationFactory(capability=cls.capability, target_property=cls.prop)

        # Template that uses this capability via the approach
        cls.template = ChallengeTemplateFactory()
        cls.template.properties.add(cls.prop)
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.app,
            check_type=cls.check_type,
            action_template=None,
        )

        # Give character the technique grant
        technique = TechniqueFactory(damage_profile=False)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cls.capability, base_value=5
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=technique)

    def setUp(self) -> None:
        # Test characters have no traits → difficulty is IMPOSSIBLE without the patch.
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_new_challenge_appears_on_second_call(self) -> None:
        """Adding a new ChallengeInstance between calls causes it to appear on 2nd call."""
        from actions.player_interface import get_player_actions

        # First call — no challenges in the room
        actions_before = get_player_actions(self.character)
        challenge_before = [a for a in actions_before if a.backend == ActionBackend.CHALLENGE]
        self.assertEqual(len(challenge_before), 0, "Should be no challenges before creation")

        # Add a challenge instance in the room
        new_ci = ChallengeInstance.objects.create(
            template=self.template,
            location=self.room,
            target_object=self.room,
            is_active=True,
            is_revealed=True,
        )

        try:
            # Second call — new challenge should appear
            actions_after = get_player_actions(self.character)
            challenge_after = [a for a in actions_after if a.backend == ActionBackend.CHALLENGE]
            self.assertTrue(
                len(challenge_after) >= 1,
                "New challenge should appear on second call",
            )
            ci_ids = [a.ref.challenge_instance_id for a in challenge_after]
            self.assertIn(new_ci.pk, ci_ids)
        finally:
            new_ci.delete()


# ---------------------------------------------------------------------------
# Test: _get_character_sheet — no sheet → empty list
# ---------------------------------------------------------------------------


class TestGetPlayerActionsNoCharacterSheet(django.test.TestCase):
    """Character with no CharacterSheet yields an empty action list.

    Verifies that narrowing ``except Exception`` → ``except AttributeError`` in
    ``_get_character_sheet`` still correctly handles the "no sheet" case.
    Django's ``RelatedObjectDoesNotExist`` is a subclass of ``AttributeError``,
    so the narrowed handler is sufficient.
    """

    def test_character_without_sheet_returns_empty_list(self) -> None:
        """get_player_actions returns [] when the character has no CharacterSheet."""
        from actions.player_interface import get_player_actions

        # Create a bare ObjectDB with no CharacterSheet attached.
        character = ObjectDB.objects.create(db_key="SheetlessCharacter")
        try:
            actions = get_player_actions(character)
            self.assertEqual(
                actions,
                [],
                "Character with no CharacterSheet should produce no actions",
            )
        finally:
            character.delete()


# ---------------------------------------------------------------------------
# Tests: dispatch_player_action
# ---------------------------------------------------------------------------


class TestDispatchPlayerActionChallengeImmediate(django.test.TestCase):
    """No round context + CHALLENGE ref → resolve_challenge runs immediately.

    Side-effect verified via a patched resolve_challenge that creates a
    CharacterChallengeRecord manually (to confirm the right arguments flow through).
    We patch resolve_challenge rather than running it end-to-end because the full
    pipeline requires a ResultChart — tested separately in test_challenge_resolution.py.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDB.objects.create(db_key="DispatchChallengeRoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = _set_character_location(cls.sheet.character, cls.room)

        cls.challenge_instance, cls.approach, cls.capability, cls.check_type = (
            _make_challenge_setup(cls.sheet, cls.room)
        )

    def setUp(self) -> None:
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def _make_resolve_challenge_patch(self) -> object:
        """Return a patch for resolve_challenge that creates a CharacterChallengeRecord.

        This lets us assert the routing reached resolve_challenge with the correct
        challenge_instance and approach, without needing a full ResultChart setup.
        """
        from unittest.mock import MagicMock, patch

        from world.mechanics.models import CharacterChallengeRecord
        from world.mechanics.types import ChallengeResolutionResult

        def _fake_resolve(character, challenge_instance, approach, capability_source):  # type: ignore[no-untyped-def]
            CharacterChallengeRecord.objects.create(
                character=character,
                challenge_instance=challenge_instance,
                approach=approach,
            )
            return MagicMock(spec=ChallengeResolutionResult)

        return patch(
            "world.mechanics.challenge_resolution.resolve_challenge",
            side_effect=_fake_resolve,
        )

    def test_immediate_challenge_creates_record(self) -> None:
        """CHALLENGE dispatch with no round context routes to resolve_challenge (side-effect)."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef
        from world.mechanics.models import CharacterChallengeRecord

        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )
        with self._make_resolve_challenge_patch():
            result = dispatch_player_action(self.character, ref, {})

        self.assertFalse(result.deferred, "Should be immediate, not deferred")
        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=self.character,
                challenge_instance=self.challenge_instance,
            ).exists(),
            "CharacterChallengeRecord must exist after immediate challenge resolution",
        )

    def test_immediate_challenge_returns_typed_result(self) -> None:
        """CHALLENGE dispatch result is a DispatchResult with correct backend."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef, DispatchResult

        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )
        with self._make_resolve_challenge_patch():
            result = dispatch_player_action(self.character, ref, {})

        self.assertIsInstance(result, DispatchResult)
        self.assertEqual(result.backend, ActionBackend.CHALLENGE)


class TestDispatchPlayerActionRegistryImmediate(django.test.TestCase):
    """No round context + REGISTRY ref → action.run() invoked; result returned."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def test_registry_action_invoked_and_result_returned(self) -> None:
        """REGISTRY dispatch runs the action and returns a DispatchResult."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef, DispatchResult

        # Use "look" — a real registry key that works in test contexts.
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="look")
        result = dispatch_player_action(self.character, ref, {})

        self.assertIsInstance(result, DispatchResult)
        self.assertFalse(result.deferred)
        self.assertEqual(result.backend, ActionBackend.REGISTRY)

    def test_unknown_registry_key_raises_dispatch_error(self) -> None:
        """An unknown registry key → ActionDispatchError(UNKNOWN_ACTION_REF)."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="nonexistent_key_xyz")
        with self.assertRaises(ActionDispatchError) as cm:
            dispatch_player_action(self.character, ref, {})

        self.assertEqual(cm.exception.code, ActionDispatchError.UNKNOWN_ACTION_REF)


class TestDispatchPlayerActionCombatDeferred(django.test.TestCase):
    """Active DECLARING encounter + COMBAT ref → deferred via record_declaration.

    Assert: CombatRoundAction row exists; result is deferred.
    A second COMBAT dispatch overwrites (exactly one declaration — mutual exclusion).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
        from world.vitals.constants import CharacterStatus
        from world.vitals.models import CharacterVitals

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

        CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )

        cls.check_type = CheckTypeFactory()
        cls.template = ActionTemplateFactory(check_type=cls.check_type)
        # TechniqueFactory(damage_profile=False) avoids base_power requirement
        cls.technique = TechniqueFactory(damage_profile=False, action_template=cls.template)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        from world.magic.factories import EffectTypeFactory

        no_power_effect_type = EffectTypeFactory(base_power=None)
        cls.technique.effect_type = no_power_effect_type
        cls.technique.save()

    def test_combat_dispatch_deferred_creates_round_action(self) -> None:
        """COMBAT dispatch with open declaration window defers and creates CombatRoundAction."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef, DispatchResult
        from world.combat.models import CombatRoundAction

        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=self.technique.pk)
        result = dispatch_player_action(self.character, ref, {"effort_level": EffortLevel.MEDIUM})

        self.assertIsInstance(result, DispatchResult)
        self.assertTrue(result.deferred, "COMBAT dispatch in DECLARING round must be deferred")
        self.assertEqual(result.backend, ActionBackend.COMBAT)
        self.assertTrue(
            CombatRoundAction.objects.filter(
                participant=self.participant,
                round_number=self.encounter.round_number,
            ).exists(),
            "CombatRoundAction must exist after COMBAT declaration dispatch",
        )

    def test_second_combat_dispatch_overwrites_first(self) -> None:
        """A second COMBAT dispatch for the same round replaces the first (mutual exclusion)."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef
        from world.combat.models import CombatRoundAction

        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=self.technique.pk)
        dispatch_player_action(self.character, ref, {"effort_level": EffortLevel.MEDIUM})
        dispatch_player_action(self.character, ref, {"effort_level": EffortLevel.HIGH})

        # Still exactly one row after two declarations
        count = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).count()
        self.assertEqual(count, 1, "Exactly one CombatRoundAction must exist after two dispatches")


class TestDispatchPlayerActionChallengeDeferred(django.test.TestCase):
    """Active DECLARING encounter + CHALLENGE ref → deferred; resolve_challenge NOT called.

    Assert: RoundChallengeDeclaration row exists; no CharacterChallengeRecord.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.vitals.constants import CharacterStatus
        from world.vitals.models import CharacterVitals

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

        CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
            status=CharacterStatus.ALIVE,
        )

        # Put the character in the room with the challenge
        cls.room = ObjectDB.objects.create(db_key="DeferredChallengeRoom")
        _set_character_location(cls.character, cls.room)

        cls.challenge_instance, cls.approach, cls.capability, cls.check_type = (
            _make_challenge_setup(cls.sheet, cls.room)
        )

    def setUp(self) -> None:
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_challenge_dispatch_deferred_creates_bridge_row(self) -> None:
        """CHALLENGE dispatch in DECLARING round → deferred + RoundChallengeDeclaration row."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef, DispatchResult
        from world.combat.models import RoundChallengeDeclaration
        from world.mechanics.models import CharacterChallengeRecord

        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )
        result = dispatch_player_action(self.character, ref, {})

        self.assertIsInstance(result, DispatchResult)
        self.assertTrue(result.deferred, "CHALLENGE dispatch in DECLARING round must be deferred")
        self.assertEqual(result.backend, ActionBackend.CHALLENGE)

        # Bridge row must exist
        self.assertTrue(
            RoundChallengeDeclaration.objects.filter(
                encounter=self.encounter,
                round_number=self.encounter.round_number,
                participant=self.participant,
            ).exists(),
            "RoundChallengeDeclaration must exist after deferred CHALLENGE dispatch",
        )

        # resolve_challenge must NOT have run — no CharacterChallengeRecord
        self.assertFalse(
            CharacterChallengeRecord.objects.filter(
                character=self.character,
                challenge_instance=self.challenge_instance,
            ).exists(),
            "CharacterChallengeRecord must NOT exist — challenge was deferred, not resolved",
        )


class TestDispatchPlayerActionUnknownRef(django.test.TestCase):
    """Unknown/stale ref → ActionDispatchError(UNKNOWN_ACTION_REF)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDB.objects.create(db_key="StaleRefRoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = _set_character_location(cls.sheet.character, cls.room)

    def setUp(self) -> None:
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_stale_challenge_ref_raises_unknown(self) -> None:
        """A CHALLENGE ref with ids that match no current availability → UNKNOWN_ACTION_REF."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        # Valid ActionRef shape, but pointing at challenge/approach not in current availability
        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=99999,
            approach_id=99999,
        )
        with self.assertRaises(ActionDispatchError) as cm:
            dispatch_player_action(self.character, ref, {})

        self.assertEqual(cm.exception.code, ActionDispatchError.UNKNOWN_ACTION_REF)

    def test_stale_combat_ref_raises_unknown(self) -> None:
        """A COMBAT ref with no active encounter → UNKNOWN_ACTION_REF."""
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        # No active encounter for this character
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=99999)
        with self.assertRaises(ActionDispatchError) as cm:
            dispatch_player_action(self.character, ref, {})

        self.assertEqual(cm.exception.code, ActionDispatchError.UNKNOWN_ACTION_REF)
