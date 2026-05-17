"""Tests for T9: resonance-alignment buff wired into Character movement/unpuppet hooks.

These tests verify that at_post_move, at_pre_move (destination=None path), and
at_post_unpuppet trigger the correct resonance-alignment service calls on the
Character typeclass, exercising the REAL hooks (not direct service calls).

Test structure
--------------
MovementHookAlignmentTest:
  (1) Character moves INTO an ALIGNED room → correct buff ConditionInstance applied
      (proves at_post_move fires refresh_resonance_alignment through the real hook)
  (2) Character moves OUT to a non-aligned room → buff removed
      (at_post_move on arrival at non-aligned room reconciles)
  (3) at_pre_move with destination=None → buff cleared
      (explicit clear for departure-to-no-room; the destination=None branch)
  (4) at_post_unpuppet → buff cleared
      (hook wired to clear_resonance_alignment)
  (5) A sheet-less object moving does NOT error
      (sheet_data guard works; non-PC objects are safe no-ops)
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    CharacterAuraFactory,
    ResonanceFactory,
)
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.services.gain import tag_room_resonance
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin


def _set_room_resonance_value(room_profile, resonance, value: int) -> None:
    """Tag the room with resonance and set the modifier value."""
    mod = tag_room_resonance(room_profile, resonance)
    mod.value = value
    mod.save(update_fields=["value"])


class MovementHookAlignmentTest(ResonanceCacheIsolationMixin, TestCase):
    """Tests that at_post_move and at_post_unpuppet hook into resonance-alignment service.

    Exercises REAL typeclass hooks (character.at_post_move, character.at_pre_move,
    character.at_post_unpuppet) — never calls the service directly.
    The hook exercises the full presence-tied buff reconcile end-to-end.
    """

    def setUp(self) -> None:
        super().setUp()  # clears manager caches — create cache-sensitive data AFTER

        # --- Affinities and resonances ---
        self.celestial = AffinityFactory(name="Celestial")
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        # --- ALIGNED diagonal interaction: Celestial caster in Celestial room ---
        self.aligned_interaction = AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # --- Boon tiers ---
        self.low_buff = ConditionTemplateFactory(name="CelestialWarmth_T9")
        self.high_buff = ConditionTemplateFactory(name="CelestialRadiance_T9")

        low_tier = ResonanceAlignmentBoonTier(
            affinity_interaction=self.aligned_interaction,
            min_magnitude=1,
            condition_template=self.low_buff,
        )
        low_tier.full_clean()
        low_tier.save()

        high_tier = ResonanceAlignmentBoonTier(
            affinity_interaction=self.aligned_interaction,
            min_magnitude=5,
            condition_template=self.high_buff,
        )
        high_tier.full_clean()
        high_tier.save()

        # --- Aligned room (celestial resonance = 1, magnitude stays low-band) ---
        self.aligned_room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.aligned_room_profile, self.celestial_resonance, 1)
        self.aligned_room = self.aligned_room_profile.objectdb

        # --- Non-aligned room (no resonance tagged) ---
        self.neutral_room_profile = RoomProfileFactory()
        # No resonance → inert → no buff
        self.neutral_room = self.neutral_room_profile.objectdb

        # --- Character with Celestial-dominant aura and sheet_data ---
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        CharacterAuraFactory(
            character=self.character,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )

    def _boon_condition_template_pks(self) -> set[int]:
        return {t.pk for t in ResonanceAlignmentBoonTier.objects.boon_condition_templates()}

    def _boon_instances_on(self, character: ObjectDB) -> list:
        boon_pks = self._boon_condition_template_pks()
        return list(
            ConditionInstance.objects.filter(
                target=character,
                condition__pk__in=boon_pks,
            )
        )

    def _place_in_room(self, room: ObjectDB) -> None:
        """Set character.location directly (bypasses hook — for setup only)."""
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])

    # -------------------------------------------------------------------------
    # Test 1: at_post_move into ALIGNED room → buff applied via hook
    # -------------------------------------------------------------------------
    def test_at_post_move_into_aligned_room_applies_buff(self) -> None:
        """Moving into an ALIGNED room fires at_post_move which applies the resonance buff.

        Calls at_post_move directly to simulate arrival (Evennia calls this after
        the move completes). Character.location is set to the aligned room first so
        the service sees the correct location.
        """
        # Place character in aligned room (the "destination" of the move)
        self._place_in_room(self.aligned_room)

        # Verify: no buff yet
        self.assertEqual(len(self._boon_instances_on(self.character)), 0)

        # Fire the hook — simulates post-move from neutral_room to aligned_room
        self.character.at_post_move(source_location=self.neutral_room)

        instances = self._boon_instances_on(self.character)
        self.assertEqual(
            len(instances),
            1,
            "Expected exactly one boon ConditionInstance after at_post_move into aligned room",
        )
        self.assertEqual(instances[0].condition_id, self.low_buff.pk)

    # -------------------------------------------------------------------------
    # Test 2: at_post_move into non-aligned room → buff removed
    # -------------------------------------------------------------------------
    def test_at_post_move_into_non_aligned_room_removes_buff(self) -> None:
        """Moving out of an aligned room into a non-aligned room removes the buff.

        Step 1: apply a buff (direct service call — setup only).
        Step 2: fire at_post_move for arrival in non-aligned room.
        The hook should clear the buff (destination is non-aligned → refresh inert).
        """
        from world.magic.services.resonance_environment import refresh_resonance_alignment

        # Setup: place in aligned room and apply buff directly
        self._place_in_room(self.aligned_room)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(
            len(self._boon_instances_on(self.character)), 1, "Expected buff after setup"
        )

        # Now move to non-aligned room and fire at_post_move
        self._place_in_room(self.neutral_room)
        self.character.at_post_move(source_location=self.aligned_room)

        instances = self._boon_instances_on(self.character)
        self.assertEqual(
            len(instances),
            0,
            "Expected buff removed after at_post_move into non-aligned room",
        )

    # -------------------------------------------------------------------------
    # Test 3: at_pre_move with destination=None → buff cleared
    # -------------------------------------------------------------------------
    def test_at_pre_move_destination_none_clears_buff(self) -> None:
        """at_pre_move with destination=None (departure to no location) clears the buff.

        This exercises the destination=None branch inserted between
        'if result is False: return False' and 'if origin is None: return True'.
        """
        from world.magic.services.resonance_environment import refresh_resonance_alignment

        # Setup: apply buff in aligned room
        self._place_in_room(self.aligned_room)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(
            len(self._boon_instances_on(self.character)), 1, "Expected buff after setup"
        )

        # Fire at_pre_move with destination=None
        result = self.character.at_pre_move(destination=None)

        # at_pre_move should still return True (not block the move)
        self.assertTrue(result)
        # Buff must be cleared
        instances = self._boon_instances_on(self.character)
        self.assertEqual(
            len(instances),
            0,
            "Expected buff cleared after at_pre_move(destination=None)",
        )

    # -------------------------------------------------------------------------
    # Test 3b: at_pre_move(destination=None) WITH an origin location
    #          → buff cleared AND MOVE_PRE_DEPART still emitted AND move allowed
    # -------------------------------------------------------------------------
    def test_at_pre_move_destination_none_with_origin_clears_buff_emits_predepart_and_allows(
        self,
    ) -> None:
        """destination=None while the character still HAS a location (origin is not None).

        Characterization test locking the correct contract of the destination=None
        branch in Character.at_pre_move. This is departure-to-nowhere from a real
        room (e.g. logout/despawn while on grid). All three guarantees must hold:

        1. The presence-tied resonance buff is CLEARED (the inserted clear runs).
        2. at_pre_move returns truthy (the move is ALLOWED, never blocked here).
        3. MOVE_PRE_DEPART is STILL emitted with destination=None and the real
           origin/character — proving the inserted clear is purely additive and
           does NOT short-circuit the pre-existing pre-depart emission. Adding a
           `return True` to the destination=None branch would suppress this
           emission on logout/despawn; that would be a regression and this test
           guards against it.
        """
        # Canonical emission-capture pattern (mirrors
        # flows/tests/test_typeclass_hooks/test_character_hooks.py): swap the
        # emit_event symbol where characters.py imported it.
        from flows.constants import EventName
        import flows.emit as emit_mod
        from flows.events.payloads import MovePreDepartPayload
        import typeclasses.characters as chars_mod
        from world.magic.services.resonance_environment import refresh_resonance_alignment

        captured: list[MovePreDepartPayload] = []
        original_emit = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.MOVE_PRE_DEPART:
                captured.append(payload)
            return original_emit(event_name, payload, **kwargs)

        # Setup: place in aligned room and apply the buff via the real service.
        self._place_in_room(self.aligned_room)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(
            len(self._boon_instances_on(self.character)), 1, "Expected buff after setup"
        )

        # Sanity: the character HAS a location (origin is not None) — this is the
        # path the existing destination=None test does NOT cover.
        self.assertIsNotNone(self.character.location)
        origin = self.character.location

        chars_mod.emit_event = capturing_emit
        try:
            result = self.character.at_pre_move(destination=None)
        finally:
            chars_mod.emit_event = original_emit

        # (2) The move is ALLOWED (truthy), not blocked.
        self.assertTrue(result)

        # (1) The buff was CLEARED by the inserted destination=None clear.
        self.assertEqual(
            len(self._boon_instances_on(self.character)),
            0,
            "Expected buff cleared after at_pre_move(destination=None) with an origin",
        )

        # (3) MOVE_PRE_DEPART was STILL emitted — the clear is purely additive
        #     and must not short-circuit the pre-existing pre-depart emission
        #     (logout/despawn must still notify reactive listeners).
        self.assertEqual(
            len(captured),
            1,
            "MOVE_PRE_DEPART must still be emitted on the destination=None path "
            "when the character has an origin (clear is additive, not a short-circuit)",
        )
        payload = captured[0]
        self.assertIs(payload.character, self.character)
        self.assertIs(payload.origin, origin)
        self.assertIsNone(payload.destination)

    # -------------------------------------------------------------------------
    # Test 4: at_post_unpuppet → buff cleared
    # -------------------------------------------------------------------------
    def test_at_post_unpuppet_clears_buff(self) -> None:
        """at_post_unpuppet clears the resonance buff."""
        from world.magic.services.resonance_environment import refresh_resonance_alignment

        # Setup: apply buff
        self._place_in_room(self.aligned_room)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(
            len(self._boon_instances_on(self.character)), 1, "Expected buff after setup"
        )

        # Fire at_post_unpuppet
        self.character.at_post_unpuppet(account=None, session=None)

        instances = self._boon_instances_on(self.character)
        self.assertEqual(len(instances), 0, "Expected buff cleared after at_post_unpuppet")

    # -------------------------------------------------------------------------
    # Test 5: sheet-less (non-PC) object moving does NOT error
    # -------------------------------------------------------------------------
    def test_sheetless_object_at_post_move_does_not_error(self) -> None:
        """A non-PC object with no CharacterSheet can at_post_move without raising."""
        # Create a Character typeclass object but do NOT give it a sheet
        bare_char = CharacterFactory()
        # No CharacterSheetFactory call — bare_char.sheet_data will raise DoesNotExist

        bare_char.db_location = self.aligned_room
        bare_char.save(update_fields=["db_location"])

        # Must not raise even though sheet_data is absent
        bare_char.at_post_move(source_location=self.neutral_room)

        # No ConditionInstances were created
        self.assertEqual(
            ConditionInstance.objects.filter(target=bare_char).count(),
            0,
        )

    def test_sheetless_object_at_post_unpuppet_does_not_error(self) -> None:
        """A non-PC object with no CharacterSheet can at_post_unpuppet without raising."""
        bare_char = CharacterFactory()

        # Must not raise
        bare_char.at_post_unpuppet(account=None, session=None)

        self.assertEqual(
            ConditionInstance.objects.filter(target=bare_char).count(),
            0,
        )
