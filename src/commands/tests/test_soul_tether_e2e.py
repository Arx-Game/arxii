"""Telnet soul-tether journey E2E (#1343).

Full PC-to-PC bond lifecycle driven by telnet commands — no HTTP client.
Proves CmdTether and CmdSineater converge on the same service seam as the
8 web APIViews.

Journey:
  1. Sinner runs ``tether burden Sineater resonance=... writeup=...``
     → CharacterRelationship.is_soul_tether=True + RELATIONSHIP_CAPSTONE Thread created
  2. Sinner runs ``tether entreat Sineater sins=3``
     → SineatingPendingOffer row created
  3. Sineater runs ``sineater consume Sinner``
     → offer consumed, hollow filled, offer row deleted
  4. Stage-advance offer seeded directly → Sineater runs ``sineater mire Sinner sins=2``
     → PendingStageAdvanceOffer row deleted, Strain added
  5. Sinner at corruption stage 3 → Sineater runs ``sineater rescue Sinner``
     → RescueOutcome returned, Sineater msg sent
  6. Sinner runs ``tether dissolve Sineater``
     → is_soul_tether=False

``_both_in_scene``, ``perform_check``, and ``emit_event`` are patched — same
boundary as ``test_soul_tether_flow.py`` — so the test is reproducible without
a running Twisted reactor or real scene participation rows.

Tagged ``@tag("postgres")`` because step 5's rescue calls ``apply_condition``
which uses ``DISTINCT ON`` (unsupported on SQLite).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from django.utils import timezone

from commands.social.soul_tether import CmdSineater, CmdTether
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
    with_corruption_at_stage,
)
from world.magic.models import Thread
from world.magic.models.soul_tether import PendingStageAdvanceOffer, SineatingPendingOffer
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTrackFactory
from world.relationships.models import CharacterRelationship
from world.scenes.factories import SceneFactory

_BOTH_IN_SCENE_PATH = "world.magic.services.soul_tether._both_in_scene"
_PERFORM_CHECK_PATH = "world.checks.services.perform_check"
_EMIT_EVENT_PATH = "world.magic.services.soul_tether.emit_event"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _set_abyssal_primary(sheet: object) -> None:
    char = sheet.character  # type: ignore[union-attr]
    try:
        aura = char.aura
        aura.celestial = Decimal("10.00")
        aura.primal = Decimal("10.00")
        aura.abyssal = Decimal("80.00")
        aura.save()
    except AttributeError:
        CharacterAuraFactory(
            character=char,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )


def _set_primal_primary(sheet: object) -> None:
    char = sheet.character  # type: ignore[union-attr]
    try:
        aura = char.aura
        aura.celestial = Decimal("10.00")
        aura.primal = Decimal("80.00")
        aura.abyssal = Decimal("10.00")
        aura.save()
    except AttributeError:
        CharacterAuraFactory(
            character=char,
            celestial=Decimal("10.00"),
            primal=Decimal("80.00"),
            abyssal=Decimal("10.00"),
        )


def _grant_track_unlock(sheet: object, track: object) -> object:
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    return CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _mock_check_result(success_level: int = 2) -> MagicMock:
    from world.traits.factories import CheckOutcomeFactory

    outcome = CheckOutcomeFactory(
        name=f"JourneyOutcome_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@tag("postgres")
class SoulTetherJourneyTests(TestCase):
    """Full bond lifecycle via telnet commands: burden→entreat→consume→mire→rescue→dissolve."""

    def setUp(self) -> None:
        # DbHolder trap: build all Evennia ObjectDB fixtures in setUp (not setUpTestData).
        wire_soul_tether_content()

        self.room = ObjectDBFactory(
            db_key="TetherJourneyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.sinner_char = ObjectDBFactory(
            db_key="Sinner",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.sineater_char = ObjectDBFactory(
            db_key="Sineater",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.sinner_sheet = CharacterSheetFactory(character=self.sinner_char)
        self.sineater_sheet = CharacterSheetFactory(character=self.sineater_char)

        _set_abyssal_primary(self.sinner_sheet)
        _set_primal_primary(self.sineater_sheet)

        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        # Sinner needs a CharacterResonance row for request_sineating validation.
        CharacterResonanceFactory(character_sheet=self.sinner_sheet, resonance=self.resonance)

        track = RelationshipTrackFactory()
        _grant_track_unlock(self.sinner_sheet, track)

        # Both directional relationship rows must pre-exist before formation.
        CharacterRelationshipFactory(
            source=self.sinner_sheet,
            target=self.sineater_sheet,
            is_pending=False,
        )
        CharacterRelationshipFactory(
            source=self.sineater_sheet,
            target=self.sinner_sheet,
            is_pending=False,
        )

        self.scene = SceneFactory(is_active=True, location=self.room)
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        # Patch _both_in_scene — no live SceneParticipation rows needed.
        both_patcher = patch(_BOTH_IN_SCENE_PATH, return_value=True)
        both_patcher.start()
        self.addCleanup(both_patcher.stop)

        # Patch perform_check — no real check infrastructure needed for rescue.
        check_patcher = patch(_PERFORM_CHECK_PATH, return_value=_mock_check_result(2))
        check_patcher.start()
        self.addCleanup(check_patcher.stop)

        # Patch emit_event — suppress the reactive pipeline (redirect/stage-advance).
        emit_patcher = patch(_EMIT_EVENT_PATH)
        emit_patcher.start()
        self.addCleanup(emit_patcher.stop)

    def _run(self, cmd_cls: type, caller: object, args: str = "") -> object:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}".strip()
        caller.msg = MagicMock()

        def _search(name: str, **_: object) -> object:
            if name == self.sinner_char.db_key:
                return self.sinner_char
            if name == self.sineater_char.db_key:
                return self.sineater_char
            return None

        caller.search = MagicMock(side_effect=_search)
        cmd.func()
        return cmd

    # ------------------------------------------------------------------
    # Happy-path lifecycle
    # ------------------------------------------------------------------

    def test_full_lifecycle(self) -> None:
        """Burden → entreat → consume → mire → rescue → dissolve."""
        # 1. Sinner forms the tether (burden = Sinner-initiated).
        self._run(
            CmdTether,
            self.sinner_char,
            (
                f"burden {self.sineater_char.db_key}"
                f" resonance={self.resonance.name}"
                f" writeup=A bond sealed in shadow and light."
            ),
        )
        rel = CharacterRelationship.objects.get(
            source=self.sinner_sheet,
            target=self.sineater_sheet,
            is_soul_tether=True,
        )
        self.assertEqual(rel.soul_tether_role, SoulTetherRole.SINNER)
        thread = Thread.objects.get(
            owner=self.sinner_sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            retired_at__isnull=True,
        )
        self.assertEqual(thread.resonance, self.resonance)

        # 2. Sinner entreats: request sineat.
        self._run(
            CmdTether,
            self.sinner_char,
            f"entreat {self.sineater_char.db_key} sins=3",
        )
        offer = SineatingPendingOffer.objects.get(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
        )
        self.assertGreater(offer.units_offered, 0)

        # 3. Sineater consumes (default: all offered).
        self._run(
            CmdSineater,
            self.sineater_char,
            f"consume {self.sinner_char.db_key}",
        )
        self.assertFalse(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

        # 4. Seed a PendingStageAdvanceOffer directly; Sineater pledges with mire.
        PendingStageAdvanceOffer.objects.create(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            relationship=rel,
            scene=self.scene,
            resonance=self.resonance,
            sinner_corruption_stage=2,
            commit_units_max=5,
            strain_cost_per_unit=1,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self._run(
            CmdSineater,
            self.sineater_char,
            f"mire {self.sinner_char.db_key} sins=2",
        )
        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

        # 5. Push Sinner to corruption stage 3; Sineater rescues.
        with_corruption_at_stage(self.sinner_sheet, self.resonance, stage=3)
        self._run(
            CmdSineater,
            self.sineater_char,
            f"rescue {self.sinner_char.db_key}",
        )
        self.sineater_char.msg.assert_called()

        # 6. Sinner dissolves the tether.
        self._run(
            CmdTether,
            self.sinner_char,
            f"dissolve {self.sineater_char.db_key}",
        )
        rel.refresh_from_db()
        self.assertFalse(rel.is_soul_tether)

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_burden_missing_writeup_sends_error(self) -> None:
        self._run(
            CmdTether,
            self.sinner_char,
            f"burden {self.sineater_char.db_key} resonance={self.resonance.name}",
        )
        msg = self.sinner_char.msg.call_args[0][0]
        self.assertIn("writeup", msg.lower())

    def test_entreat_no_active_scene_sends_error(self) -> None:
        # Form the tether first.
        self._run(
            CmdTether,
            self.sinner_char,
            (
                f"burden {self.sineater_char.db_key}"
                f" resonance={self.resonance.name}"
                f" writeup=Test bond."
            ),
        )
        # Remove character from room so _get_active_scene returns None.
        self.sinner_char.location = None
        self.sinner_char.save()
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        self._run(
            CmdTether,
            self.sinner_char,
            f"entreat {self.sineater_char.db_key} sins=3",
        )
        msg = self.sinner_char.msg.call_args[0][0]
        self.assertIn("active scene", msg.lower())

    def test_pleas_lists_pending_plea(self) -> None:
        # Form tether + entreat, then check pleas listing.
        self._run(
            CmdTether,
            self.sinner_char,
            (
                f"burden {self.sineater_char.db_key}"
                f" resonance={self.resonance.name}"
                f" writeup=Test bond."
            ),
        )
        self._run(
            CmdTether,
            self.sinner_char,
            f"entreat {self.sineater_char.db_key} sins=2",
        )
        self._run(CmdSineater, self.sineater_char, "pleas")
        msg = self.sineater_char.msg.call_args[0][0]
        self.assertIn("Sinner", msg)

    def test_consume_decline_with_sins_zero(self) -> None:
        # Form tether + entreat.
        self._run(
            CmdTether,
            self.sinner_char,
            (
                f"burden {self.sineater_char.db_key}"
                f" resonance={self.resonance.name}"
                f" writeup=Test bond."
            ),
        )
        self._run(
            CmdTether,
            self.sinner_char,
            f"entreat {self.sineater_char.db_key} sins=3",
        )
        # Decline with sins=0.
        self._run(
            CmdSineater,
            self.sineater_char,
            f"consume {self.sinner_char.db_key} sins=0",
        )
        msg = self.sineater_char.msg.call_args[0][0]
        self.assertIn("decline", msg.lower())
