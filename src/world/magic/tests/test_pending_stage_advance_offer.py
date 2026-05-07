"""Tests for PendingStageAdvanceOffer model, service integration, and viewset (Task 1.7).

Covers:
    1. Model uniqueness constraint — duplicate (sinner, sineater) pair
    2. soul_tether_stage_advance_prompt writes DB row with expected fields including expires_at
    3. resolve_stage_advance_prompt_from_db happy path with co-location + within TTL
    4. Stale on TTL expiry — raises StageAdvanceBonusError, deletes row, no state change
    5. Stale on sineater departure
    6. Stale on sinner departure
    7. resolve_stage_advance_prompt_from_db with no pending row
    8. Viewset returns own pending offers (scoped to caller as Sineater)
    9. Viewset auth required
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from world.magic.constants import TargetKind
from world.magic.exceptions import StageAdvanceBonusError
from world.magic.factories import (
    AffinityFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    CorruptionConditionTemplateFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.magic.models.soul_tether import PendingStageAdvanceOffer
from world.magic.services.soul_tether import (
    _STRAIN_SEVERITY_PER_UNIT,
    STAGE_ADVANCE_OFFER_TTL,
    _pending_stage_advance_offers,
    accept_soul_tether,
    resolve_stage_advance_prompt_from_db,
)
from world.magic.types.soul_tether import SoulTetherRole as SoulTetherRoleEnum
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import CharacterRelationship
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory

# =============================================================================
# Shared helpers (mirror test_soul_tether_subscribers.py patterns)
# =============================================================================


def _set_primary_affinity_abyssal(sheet: object) -> None:
    """Set the character's aura so Abyssal is the dominant affinity."""
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


def _set_primary_affinity_primal(sheet: object) -> None:
    """Set the character's aura so Primal is the dominant affinity."""
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


def _grant_relationship_track_unlock(sheet: object, track: object) -> None:
    """Give the character a RELATIONSHIP_TRACK CharacterThreadWeavingUnlock."""
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_tethered_pair_with_tenures(track=None):
    """Return (sinner_tenure, sineater_tenure, resonance) with an active Soul Tether.

    Both sides have RosterTenure rows (and thus AccountDB) for scene participation
    and viewset auth tests.
    """
    wire_soul_tether_content()
    if track is None:
        track = RelationshipTrackFactory()
    abyssal_affinity = AffinityFactory(name="Abyssal")
    resonance = ResonanceFactory(affinity=abyssal_affinity)

    sinner_tenure = RosterTenureFactory()
    sineater_tenure = RosterTenureFactory()
    sinner_sheet = sinner_tenure.roster_entry.character_sheet
    sineater_sheet = sineater_tenure.roster_entry.character_sheet

    _set_primary_affinity_abyssal(sinner_sheet)
    _set_primary_affinity_primal(sineater_sheet)
    _grant_relationship_track_unlock(sinner_sheet, track)

    CharacterRelationshipFactory(source=sinner_sheet, target=sineater_sheet, is_pending=False)
    CharacterRelationshipFactory(source=sineater_sheet, target=sinner_sheet, is_pending=False)

    accept_soul_tether(
        initiator_sheet=sinner_sheet,
        partner_sheet=sineater_sheet,
        sinner_role=SoulTetherRoleEnum.ABYSSAL,
        resonance=resonance,
        writeup="Bond for stage advance tests, at least twenty chars.",
        ritual_components=[],
    )

    # Seed the Sinner's CharacterResonance so corruption template work.
    CharacterResonanceFactory(character_sheet=sinner_sheet, resonance=resonance)

    return sinner_tenure, sineater_tenure, resonance


def _get_sinner_tether_thread(sinner_sheet: object, resonance: object) -> Thread:
    """Return the Sinner's RELATIONSHIP_CAPSTONE Thread for the given resonance."""
    return Thread.objects.get(
        owner=sinner_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        resonance=resonance,
        retired_at__isnull=True,
    )


def _seed_pending_offer(sinner_sheet, sineater_sheet, resonance, scene):
    """Directly create a PendingStageAdvanceOffer row for testing.

    ``scene`` is required — the field is NOT NULL and the co-location check at
    resolve time relies on it.  Uses update_or_create so repeated calls within
    a test safely replace the row.  Expires 120 seconds in the future (well
    within TTL).
    """
    rel = CharacterRelationship.objects.get(source=sinner_sheet, target=sineater_sheet)
    thread = _get_sinner_tether_thread(sinner_sheet, resonance)
    return PendingStageAdvanceOffer.objects.update_or_create(
        sinner_sheet=sinner_sheet,
        sineater_sheet=sineater_sheet,
        defaults={
            "relationship": rel,
            "scene": scene,
            "resonance": resonance,
            "sinner_corruption_stage": 1,
            "commit_units_max": thread.hollow_current,
            "strain_cost_per_unit": _STRAIN_SEVERITY_PER_UNIT,
            "expires_at": timezone.now() + timedelta(seconds=120),
        },
    )[0]


# =============================================================================
# Subscriber tests helper (firing via advance_condition_severity)
# =============================================================================


def _make_corruption_condition_with_resist(resonance: object) -> tuple:
    """Create a two-stage Corruption condition template with a resist check at stage 2.

    Returns (template, stage2, check_type).
    Stage1: severity_threshold=5, ADVANCE_AT_THRESHOLD (no resist).
    Stage2: severity_threshold=10, HOLD_OVERFLOW with a resist check.
    """
    from world.checks.factories import CheckTypeFactory
    from world.conditions.factories import (
        ConditionCategoryFactory,
        ConditionStageFactory,
        ConditionTemplateFactory,
    )
    from world.conditions.types import AdvancementResistFailureKind

    check_type = CheckTypeFactory()
    category = ConditionCategoryFactory()
    template = ConditionTemplateFactory(
        has_progression=True,
        category=category,
        corruption_resonance=resonance,
    )
    ConditionStageFactory(
        condition=template,
        stage_order=1,
        name="Sinful",
        severity_threshold=5,
        advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
        resist_check_type=None,
    )
    stage2 = ConditionStageFactory(
        condition=template,
        stage_order=2,
        name="Tainted",
        severity_threshold=10,
        advancement_resist_failure_kind=AdvancementResistFailureKind.HOLD_OVERFLOW,
        resist_check_type=check_type,
        resist_difficulty=15,
    )
    return template, stage2, check_type


def _make_check_result(success_level: int) -> object:
    result = MagicMock()
    result.success_level = success_level
    return result


# =============================================================================
# 1. Model uniqueness constraint
# =============================================================================


class PendingStageAdvanceOfferUniquenessTests(TestCase):
    """PendingStageAdvanceOffer.one_pending_stage_advance_per_pair constraint."""

    def test_duplicate_pair_raises_integrity_error(self) -> None:
        """Two rows with the same (sinner, sineater) violate the unique constraint."""
        from django.db import IntegrityError

        wire_soul_tether_content()
        track = RelationshipTrackFactory()
        resonance = ResonanceFactory()
        sinner_tenure = RosterTenureFactory()
        sineater_tenure = RosterTenureFactory()
        sinner_sheet = sinner_tenure.roster_entry.character_sheet
        sineater_sheet = sineater_tenure.roster_entry.character_sheet

        _set_primary_affinity_abyssal(sinner_sheet)
        _set_primary_affinity_primal(sineater_sheet)
        _grant_relationship_track_unlock(sinner_sheet, track)

        CharacterRelationshipFactory(source=sinner_sheet, target=sineater_sheet, is_pending=False)
        CharacterRelationshipFactory(source=sineater_sheet, target=sinner_sheet, is_pending=False)

        accept_soul_tether(
            initiator_sheet=sinner_sheet,
            partner_sheet=sineater_sheet,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=resonance,
            writeup="Bond for uniqueness constraint test, at least twenty chars.",
            ritual_components=[],
        )

        rel = CharacterRelationship.objects.get(source=sinner_sheet, target=sineater_sheet)
        scene = SceneFactory()

        PendingStageAdvanceOffer.objects.create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            relationship=rel,
            scene=scene,
            resonance=resonance,
            sinner_corruption_stage=1,
            commit_units_max=5,
            strain_cost_per_unit=_STRAIN_SEVERITY_PER_UNIT,
            expires_at=timezone.now() + timedelta(seconds=60),
        )

        with self.assertRaises(IntegrityError):
            PendingStageAdvanceOffer.objects.create(
                sinner_sheet=sinner_sheet,
                sineater_sheet=sineater_sheet,
                relationship=rel,
                scene=scene,
                resonance=resonance,
                sinner_corruption_stage=1,
                commit_units_max=3,
                strain_cost_per_unit=_STRAIN_SEVERITY_PER_UNIT,
                expires_at=timezone.now() + timedelta(seconds=60),
            )


# =============================================================================
# 2. soul_tether_stage_advance_prompt writes DB row
# =============================================================================


class SoulTetherStageAdvancePromptWritesPendingRowTests(TestCase):
    """soul_tether_stage_advance_prompt writes a PendingStageAdvanceOffer row (Task 1.7 Step 3)."""

    def setUp(self) -> None:
        from evennia.objects.models import ObjectDB

        wire_soul_tether_content()

        self.room = ObjectDB.objects.create(
            db_key="Room_SAPromptDB",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        sinner_tenure = RosterTenureFactory()
        sineater_tenure = RosterTenureFactory()
        self.sinner_sheet = sinner_tenure.roster_entry.character_sheet
        self.sineater_sheet = sineater_tenure.roster_entry.character_sheet
        self.sinner_account = sinner_tenure.player_data.account
        self.sineater_account = sineater_tenure.player_data.account

        _set_primary_affinity_abyssal(self.sinner_sheet)
        _set_primary_affinity_primal(self.sineater_sheet)
        _grant_relationship_track_unlock(self.sinner_sheet, self.track)
        CharacterRelationshipFactory(
            source=self.sinner_sheet, target=self.sineater_sheet, is_pending=False
        )
        CharacterRelationshipFactory(
            source=self.sineater_sheet, target=self.sinner_sheet, is_pending=False
        )
        accept_soul_tether(
            initiator_sheet=self.sinner_sheet,
            partner_sheet=self.sineater_sheet,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond for subscriber DB write test, at least twenty chars.",
            ritual_components=[],
        )
        CharacterResonanceFactory(character_sheet=self.sinner_sheet, resonance=self.resonance)

        # Pre-charge the Sinner's Thread Hollow.
        self.thread = _get_sinner_tether_thread(self.sinner_sheet, self.resonance)
        self.thread.hollow_current = 5
        self.thread.save()

        # Place both in the same room so the subscriber fires (room-proximity check).
        sinner_char = self.sinner_sheet.character
        sineater_char = self.sineater_sheet.character
        sinner_char.location = self.room
        sinner_char.save()
        sineater_char.location = self.room
        sineater_char.save()

        # Also create SceneParticipation so _find_shared_active_scene returns a scene
        # and the DB row is persisted (scene FK is NOT NULL).
        self.scene = SceneFactory()
        SceneParticipationFactory(scene=self.scene, account=self.sinner_account)
        SceneParticipationFactory(scene=self.scene, account=self.sineater_account)

        # Make a Corruption condition instance at stage 1, severity 7 (will cross 10 on +5).
        from world.conditions.factories import ConditionInstanceFactory

        template, _stage2, _check_type = _make_corruption_condition_with_resist(self.resonance)
        self.template = template
        self.condition_instance = ConditionInstanceFactory(
            condition=template,
            target=self.sinner_sheet.character,
            current_stage=template.stages.get(stage_order=1),
            severity=7,
        )
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    @patch("world.conditions.services.perform_check")
    def test_subscriber_writes_pending_row(self, mock_check: object) -> None:
        """Advancing severity over the stage threshold writes one PendingStageAdvanceOffer row."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

        advance_condition_severity(self.condition_instance, 5)  # 7+5=12, crosses threshold 10

        self.assertTrue(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

    @patch("world.conditions.services.perform_check")
    def test_pending_row_expires_at_within_ttl(self, mock_check: object) -> None:
        """The expires_at is approximately now + STAGE_ADVANCE_OFFER_TTL."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        before = timezone.now()
        advance_condition_severity(self.condition_instance, 5)
        after = timezone.now()

        row = PendingStageAdvanceOffer.objects.get(
            sinner_sheet=self.sinner_sheet, sineater_sheet=self.sineater_sheet
        )
        expected_min = before + STAGE_ADVANCE_OFFER_TTL
        expected_max = after + STAGE_ADVANCE_OFFER_TTL
        self.assertGreaterEqual(row.expires_at, expected_min)
        self.assertLessEqual(row.expires_at, expected_max)

    @patch("world.conditions.services.perform_check")
    def test_pending_row_has_correct_commit_units_max(self, mock_check: object) -> None:
        """commit_units_max equals the Sinner's hollow_current at prompt time."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        row = PendingStageAdvanceOffer.objects.get(
            sinner_sheet=self.sinner_sheet, sineater_sheet=self.sineater_sheet
        )
        self.assertEqual(row.commit_units_max, 5)  # Thread.hollow_current was 5

    @patch("world.conditions.services.perform_check")
    def test_pending_row_resonance_matches(self, mock_check: object) -> None:
        """PendingStageAdvanceOffer.resonance matches the Corruption condition's resonance."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        row = PendingStageAdvanceOffer.objects.get(
            sinner_sheet=self.sinner_sheet, sineater_sheet=self.sineater_sheet
        )
        self.assertEqual(row.resonance_id, self.resonance.pk)


# =============================================================================
# 2b. No shared scene → no DB row written, in-memory offer still fires
# =============================================================================


class SoulTetherStageAdvancePromptNoSharedSceneTests(TestCase):
    """When no shared active scene exists, soul_tether_stage_advance_prompt must not
    write a PendingStageAdvanceOffer row (scene FK is NOT NULL; co-location check
    would be impossible without it).  The in-memory PROMPT_PLAYER offer is still
    recorded so the Sineater can respond via the @reply path if they wish."""

    def setUp(self) -> None:
        from evennia.objects.models import ObjectDB

        wire_soul_tether_content()

        self.room = ObjectDB.objects.create(
            db_key="Room_SAPromptNoScene",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        sinner_tenure = RosterTenureFactory()
        sineater_tenure = RosterTenureFactory()
        self.sinner_sheet = sinner_tenure.roster_entry.character_sheet
        self.sineater_sheet = sineater_tenure.roster_entry.character_sheet

        _set_primary_affinity_abyssal(self.sinner_sheet)
        _set_primary_affinity_primal(self.sineater_sheet)
        _grant_relationship_track_unlock(self.sinner_sheet, self.track)
        CharacterRelationshipFactory(
            source=self.sinner_sheet, target=self.sineater_sheet, is_pending=False
        )
        CharacterRelationshipFactory(
            source=self.sineater_sheet, target=self.sinner_sheet, is_pending=False
        )
        accept_soul_tether(
            initiator_sheet=self.sinner_sheet,
            partner_sheet=self.sineater_sheet,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond for no-scene DB skip test, at least twenty chars.",
            ritual_components=[],
        )
        CharacterResonanceFactory(character_sheet=self.sinner_sheet, resonance=self.resonance)

        # Pre-charge the Sinner's Thread Hollow.
        thread = _get_sinner_tether_thread(self.sinner_sheet, self.resonance)
        thread.hollow_current = 5
        thread.save()

        # Place both in the same room (triggers the subscriber) but do NOT create
        # SceneParticipation rows — _find_shared_active_scene returns None.
        sinner_char = self.sinner_sheet.character
        sineater_char = self.sineater_sheet.character
        sinner_char.location = self.room
        sinner_char.save()
        sineater_char.location = self.room
        sineater_char.save()

        template, _stage2, _check_type = _make_corruption_condition_with_resist(self.resonance)
        from world.conditions.factories import ConditionInstanceFactory

        self.condition_instance = ConditionInstanceFactory(
            condition=template,
            target=self.sinner_sheet.character,
            current_stage=template.stages.get(stage_order=1),
            severity=7,
        )
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    @patch("world.conditions.services.perform_check")
    def test_no_pending_row_when_no_shared_scene(self, mock_check: object) -> None:
        """When no shared SceneParticipation exists, no PendingStageAdvanceOffer is written."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)  # 7+5=12, crosses threshold 10

        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists(),
            "A PendingStageAdvanceOffer row must NOT be written when there is no shared scene.",
        )

    @patch("world.conditions.services.perform_check")
    def test_in_memory_offer_still_recorded_when_no_shared_scene(self, mock_check: object) -> None:
        """Even without a shared scene, the in-memory offer is recorded."""
        from world.conditions.services import advance_condition_severity

        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        self.assertTrue(
            len(_pending_stage_advance_offers) > 0,
            "In-memory offer should still be recorded even when no DB row is written.",
        )


# =============================================================================
# 3. resolve_stage_advance_prompt_from_db happy path
# =============================================================================


class ResolveStageAdvanceFromDbHappyPathTests(TestCase):
    """Happy path: co-located + within TTL (Task 1.7 Step 4)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        # Seed Sineater anima (needed by TetherStrain apply_condition path).
        CharacterAnimaFactory(
            character=cls.sineater_sheet.character,
            current=20,
            maximum=20,
        )

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

        # Pre-charge the Sinner's Thread Hollow.
        cls.thread = _get_sinner_tether_thread(cls.sinner_sheet, cls.resonance)
        cls.thread.hollow_current = 8
        cls.thread.save()

    def test_happy_path_returns_result(self) -> None:
        """resolve_stage_advance_prompt_from_db returns a StageAdvanceBonusResult."""
        _seed_pending_offer(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene=self.scene
        )
        result = resolve_stage_advance_prompt_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_committed=3,
        )
        self.assertEqual(result.units_committed, 3)
        self.assertFalse(result.declined)
        self.assertEqual(result.hollow_drained, 3)

    def test_happy_path_deletes_pending_row(self) -> None:
        """resolve_stage_advance_prompt_from_db deletes the PendingStageAdvanceOffer on success."""
        _seed_pending_offer(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene=self.scene
        )
        resolve_stage_advance_prompt_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_committed=2,
        )
        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

    def test_decline_also_deletes_pending_row(self) -> None:
        """A decline (units_committed=0) also cleans up the pending offer."""
        _seed_pending_offer(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene=self.scene
        )
        result = resolve_stage_advance_prompt_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_committed=0,
        )
        self.assertTrue(result.declined)
        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )


# =============================================================================
# 4. Stale on TTL expiry
# =============================================================================


class ResolveStageAdvanceFromDbTTLStalenessTests(TestCase):
    """resolve_stage_advance_prompt_from_db raises StageAdvanceBonusError when offer expired."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

        cls.thread = _get_sinner_tether_thread(cls.sinner_sheet, cls.resonance)
        cls.thread.hollow_current = 8
        cls.thread.save()

    def _seed_expired_offer(self) -> None:
        """Create a PendingStageAdvanceOffer that is already past its expires_at."""
        rel = CharacterRelationship.objects.get(
            source=self.sinner_sheet, target=self.sineater_sheet
        )
        PendingStageAdvanceOffer.objects.update_or_create(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            defaults={
                "relationship": rel,
                "scene": self.scene,
                "resonance": self.resonance,
                "sinner_corruption_stage": 1,
                "commit_units_max": 5,
                "strain_cost_per_unit": _STRAIN_SEVERITY_PER_UNIT,
                "expires_at": timezone.now() - timedelta(seconds=1),  # Already expired.
            },
        )

    def test_expired_offer_raises_stale_error(self) -> None:
        """Responding to an expired offer raises StageAdvanceBonusError."""
        self._seed_expired_offer()
        with self.assertRaises(StageAdvanceBonusError) as ctx:
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.assertIn("expired", ctx.exception.user_message)
        self.assertIn(ctx.exception.user_message, StageAdvanceBonusError.SAFE_MESSAGES)

    def test_expired_offer_deletes_pending_row(self) -> None:
        """An expired offer is deleted when detected."""
        self._seed_expired_offer()
        with self.assertRaises(StageAdvanceBonusError):
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

    def test_expired_offer_no_hollow_drained(self) -> None:
        """An expired offer does not drain any Hollow (no state change)."""
        self._seed_expired_offer()
        hollow_before = self.thread.hollow_current
        with self.assertRaises(StageAdvanceBonusError):
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, hollow_before)


# =============================================================================
# 5. Stale on sineater departure
# =============================================================================


class ResolveStageAdvanceFromDbSineaterDepartedTests(TestCase):
    """Stale when Sineater left scene: raises StageAdvanceBonusError."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        cls.thread = _get_sinner_tether_thread(cls.sinner_sheet, cls.resonance)
        cls.thread.hollow_current = 8
        cls.thread.save()

    def test_stale_when_sineater_departed(self) -> None:
        """Sineater leaving the scene makes the offer stale: raises StageAdvanceBonusError."""
        scene = SceneFactory()
        # Only Sinner participates; Sineater has left.
        SceneParticipationFactory(scene=scene, account=self.sinner_account)

        _seed_pending_offer(self.sinner_sheet, self.sineater_sheet, self.resonance, scene=scene)

        with self.assertRaises(StageAdvanceBonusError) as ctx:
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.assertIn("scene", ctx.exception.user_message)
        self.assertIn(ctx.exception.user_message, StageAdvanceBonusError.SAFE_MESSAGES)

    def test_stale_sineater_deletes_pending_row(self) -> None:
        """A stale rejection (sineater departed) cleans up the pending row."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.sinner_account)

        _seed_pending_offer(self.sinner_sheet, self.sineater_sheet, self.resonance, scene=scene)

        with self.assertRaises(StageAdvanceBonusError):
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )

        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )


# =============================================================================
# 6. Stale on sinner departure
# =============================================================================


class ResolveStageAdvanceFromDbSinnerDepartedTests(TestCase):
    """resolve_stage_advance_prompt_from_db raises StageAdvanceBonusError when Sinner left scene."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        cls.thread = _get_sinner_tether_thread(cls.sinner_sheet, cls.resonance)
        cls.thread.hollow_current = 8
        cls.thread.save()

    def test_stale_when_sinner_departed(self) -> None:
        """Sinner leaving the scene makes the offer stale."""
        scene = SceneFactory()
        # Only Sineater participates.
        SceneParticipationFactory(scene=scene, account=self.sineater_account)

        _seed_pending_offer(self.sinner_sheet, self.sineater_sheet, self.resonance, scene=scene)

        with self.assertRaises(StageAdvanceBonusError) as ctx:
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.assertIn("scene", ctx.exception.user_message)

    def test_stale_sinner_deletes_pending_row(self) -> None:
        """Stale rejection from Sinner departure also cleans up the pending row."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.sineater_account)

        _seed_pending_offer(self.sinner_sheet, self.sineater_sheet, self.resonance, scene=scene)

        with self.assertRaises(StageAdvanceBonusError):
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )

        self.assertFalse(
            PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )


# =============================================================================
# 7. No pending offer
# =============================================================================


class ResolveStageAdvanceFromDbNoPendingOfferTests(TestCase):
    """resolve_stage_advance_prompt_from_db raises StageAdvanceBonusError when no row found."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet

    def test_no_pending_offer_raises(self) -> None:
        """Without a pending row, raises StageAdvanceBonusError."""
        with self.assertRaises(StageAdvanceBonusError) as ctx:
            resolve_stage_advance_prompt_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_committed=3,
            )
        self.assertIn("No pending", ctx.exception.user_message)
        self.assertIn(ctx.exception.user_message, StageAdvanceBonusError.SAFE_MESSAGES)


# =============================================================================
# 8. Viewset scoping
# =============================================================================


class PendingStageAdvanceOfferViewSetTests(APITestCase):
    """GET /api/magic/soul-tether/stage-advance/pending/ — scoped to caller as Sineater."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Pair A: sinner_a → sineater_a
        sinner_tenure_a, sineater_tenure_a, resonance_a = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_a = sinner_tenure_a.roster_entry.character_sheet
        cls.sineater_sheet_a = sineater_tenure_a.roster_entry.character_sheet
        cls.sineater_account_a = sineater_tenure_a.player_data.account
        cls.resonance_a = resonance_a

        # Pair B: sinner_b → sineater_b
        sinner_tenure_b, sineater_tenure_b, resonance_b = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_b = sinner_tenure_b.roster_entry.character_sheet
        cls.sineater_sheet_b = sineater_tenure_b.roster_entry.character_sheet
        cls.sineater_account_b = sineater_tenure_b.player_data.account
        cls.resonance_b = resonance_b

        # Pre-charge threads so commit_units_max is > 0.
        thread_a = _get_sinner_tether_thread(cls.sinner_sheet_a, cls.resonance_a)
        thread_a.hollow_current = 5
        thread_a.save()
        thread_b = _get_sinner_tether_thread(cls.sinner_sheet_b, cls.resonance_b)
        thread_b.hollow_current = 5
        thread_b.save()

        # Create shared scenes so _seed_pending_offer has a non-null scene.
        cls.scene_a = SceneFactory()
        cls.scene_b = SceneFactory()

    def _seed_offer_a(self) -> None:
        _seed_pending_offer(
            self.sinner_sheet_a, self.sineater_sheet_a, self.resonance_a, self.scene_a
        )

    def _seed_offer_b(self) -> None:
        _seed_pending_offer(
            self.sinner_sheet_b, self.sineater_sheet_b, self.resonance_b, self.scene_b
        )

    def test_sineater_sees_only_their_pending_offers(self) -> None:
        """Authenticated as sineater_a, only offer A appears in the list."""
        self._seed_offer_a()
        self._seed_offer_b()
        self.client.force_authenticate(user=self.sineater_account_a)
        response = self.client.get("/api/magic/soul-tether/stage-advance/pending/")
        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        offer_a = PendingStageAdvanceOffer.objects.get(
            sinner_sheet=self.sinner_sheet_a, sineater_sheet=self.sineater_sheet_a
        )
        offer_b = PendingStageAdvanceOffer.objects.get(
            sinner_sheet=self.sinner_sheet_b, sineater_sheet=self.sineater_sheet_b
        )
        self.assertIn(offer_a.pk, result_ids)
        self.assertNotIn(offer_b.pk, result_ids)

    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get("/api/magic/soul-tether/stage-advance/pending/")
        self.assertIn(response.status_code, (401, 403))

    def test_list_returns_expected_fields(self) -> None:
        """Response includes expected serializer fields."""
        self._seed_offer_a()
        self.client.force_authenticate(user=self.sineater_account_a)
        response = self.client.get("/api/magic/soul-tether/stage-advance/pending/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(len(response.data["results"]), 0)
        row = response.data["results"][0]
        for field in (
            "id",
            "sinner_sheet_id",
            "sinner_persona_name",
            "scene_id",
            "scene_name",
            "resonance_id",
            "sinner_corruption_stage",
            "commit_units_max",
            "strain_cost_per_unit",
            "created_at",
            "expires_at",
        ):
            self.assertIn(field, row, f"Missing field: {field}")
