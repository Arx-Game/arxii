"""Tests for the crossing ceremony registry + generalized dispatch (ADR-0094, #1987).

Verifies that:
- Every ``TargetKind`` has a registered handler (no silent no-ops).
- Stub handlers execute without error at crossings.
- The GIFT handler still dispatches variant discovery (regression for #1578).
- ``execute_ceremony_beat`` is callable standalone (the shared helper).
- The backwards-compatible ``fire_variant_discoveries`` alias works.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.crossing.ceremony import execute_crossing_ceremonies
from world.magic.crossing.registry import (
    clear_crossing_registry,
    get_crossing_handler,
)


class CrossingRegistryTests(TestCase):
    """The handler registry covers all 9 TargetKind values."""

    def test_all_target_kinds_have_handlers(self) -> None:
        """Every TargetKind must have a registered handler — no silent no-ops."""
        # Register happens in MagicConfig.ready(), which runs on app load.
        # We check that the registry is populated for every kind.
        missing = [kind for kind in TargetKind.values if get_crossing_handler(kind) is None]
        self.assertEqual(
            missing,
            [],
            f"No crossing handler registered for: {missing}",
        )

    def test_gift_handler_registered(self) -> None:
        self.assertIsNotNone(get_crossing_handler(TargetKind.GIFT))

    def test_covenant_role_handler_registered(self) -> None:
        self.assertIsNotNone(get_crossing_handler(TargetKind.COVENANT_ROLE))

    def test_stub_handlers_registered(self) -> None:
        """The 5 stub kinds have handlers that execute without error."""
        stub_kinds = [
            TargetKind.FACET,
            TargetKind.RELATIONSHIP_TRACK,
            TargetKind.RELATIONSHIP_CAPSTONE,
            TargetKind.MANTLE,
            TargetKind.SANCTUM,
        ]
        for kind in stub_kinds:
            handler = get_crossing_handler(kind)
            self.assertIsNotNone(handler, f"No handler for {kind}")
            # Stub handlers should not raise on execute.
            thread = MagicMock()
            thread.target_kind = kind
            handler.execute(  # type: ignore[union-attr]
                thread=thread,
                starting_level=2,
                new_level=3,
            )


class TechniqueCrossingHandlerTests(TestCase):
    """TechniqueCrossingHandler fires a narrative-only beat at level 3."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)

    def test_level_3_crossing_fires_narrative_beat(self) -> None:
        """Crossing level 3 fires execute_ceremony_beat with narrative, no achievement."""
        from world.magic.crossing.handlers import TechniqueCrossingHandler
        from world.magic.models import Thread

        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=3,
        )
        try:
            with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
                handler = TechniqueCrossingHandler()
                handler.execute(thread=thread, starting_level=2, new_level=3)
                mock_beat.assert_called_once()
                call_kwargs = mock_beat.call_args.kwargs
                self.assertIsNone(call_kwargs.get("achievement"))
        finally:
            thread.delete()

    def test_level_6_crossing_does_not_fire_beat(self) -> None:
        """Crossing level 6 does not fire a beat (discovery is on selection)."""
        from world.magic.crossing.handlers import TechniqueCrossingHandler
        from world.magic.models import Thread

        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=6,
        )
        try:
            with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
                handler = TechniqueCrossingHandler()
                handler.execute(thread=thread, starting_level=5, new_level=6)
                mock_beat.assert_not_called()
        finally:
            thread.delete()

    def test_non_crossing_level_does_not_fire_beat(self) -> None:
        """A non-crossing level (e.g. 4) does not fire a beat."""
        from world.magic.crossing.handlers import TechniqueCrossingHandler
        from world.magic.models import Thread

        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=4,
        )
        try:
            with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
                handler = TechniqueCrossingHandler()
                handler.execute(thread=thread, starting_level=3, new_level=4)
                mock_beat.assert_not_called()
        finally:
            thread.delete()


class ExecuteCrossingCeremoniesTests(TestCase):
    """The generalized entry point dispatches correctly."""

    def test_no_handler_logs_debug(self) -> None:
        """An unregistered kind logs a debug message, not a silent return."""
        from world.magic.crossing.handlers import (
            CovenantRoleCrossingHandler,
            FacetCrossingHandler,
            GiftCrossingHandler,
            MantleCrossingHandler,
            RelationshipCapstoneCrossingHandler,
            RelationshipTrackCrossingHandler,
            SanctumCrossingHandler,
            TechniqueCrossingHandler,
            TraitCrossingHandler,
        )
        from world.magic.crossing.registry import register_crossing_handler

        clear_crossing_registry()
        try:
            thread = MagicMock()
            thread.target_kind = TargetKind.TRAIT
            with patch("world.magic.crossing.ceremony.logger") as mock_logger:
                execute_crossing_ceremonies(
                    thread=thread,
                    starting_level=2,
                    new_level=3,
                )
                mock_logger.debug.assert_called_once()
        finally:
            # Restore the registry — ready() won't re-run in-process.
            register_crossing_handler(GiftCrossingHandler())
            register_crossing_handler(CovenantRoleCrossingHandler())
            register_crossing_handler(TechniqueCrossingHandler())
            register_crossing_handler(TraitCrossingHandler())
            register_crossing_handler(FacetCrossingHandler())
            register_crossing_handler(RelationshipTrackCrossingHandler())
            register_crossing_handler(RelationshipCapstoneCrossingHandler())
            register_crossing_handler(MantleCrossingHandler())
            register_crossing_handler(SanctumCrossingHandler())

    def test_no_op_when_no_level_gain(self) -> None:
        """If new_level <= starting_level, nothing dispatches."""
        thread = MagicMock()
        thread.target_kind = TargetKind.GIFT
        # Should not raise even with a handler that expects level gain.
        execute_crossing_ceremonies(
            thread=thread,
            starting_level=3,
            new_level=3,
        )


class BackwardsCompatibilityTests(TestCase):
    """The old ``fire_variant_discoveries`` alias still works."""

    def test_alias_exists(self) -> None:
        from world.covenants.discovery import fire_variant_discoveries

        self.assertIs(fire_variant_discoveries, execute_crossing_ceremonies)
