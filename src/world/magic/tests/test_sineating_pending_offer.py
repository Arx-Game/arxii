"""Tests for SineatingPendingOffer model, service integration, and viewset (Task 1.6).

Covers:
    1. Model uniqueness constraint — duplicate (sinner, sineater) pair
    2. request_sineating creates a pending offer row
    3. resolve_sineating_from_db happy path with co-location (offer consumed)
    4. resolve_sineating_from_db stale when sineater departs
    5. resolve_sineating_from_db stale when sinner departs
    6. Viewset scopes to authenticated user as sineater
    7. Viewset rejects unauthenticated requests
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APITestCase

from world.magic.constants import TargetKind
from world.magic.exceptions import SineatingValidationError
from world.magic.factories import (
    AffinityFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models.soul_tether import Sineating, SineatingPendingOffer
from world.magic.services.soul_tether import (
    _ANIMA_COST_PER_UNIT,
    _FATIGUE_COST_PER_UNIT,
    accept_soul_tether,
    request_sineating,
    resolve_sineating_from_db,
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
# Shared helpers
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
        sinner_role=SoulTetherRoleEnum.SINNER,
        resonance=resonance,
        writeup="Bond for pending offer tests, at least twenty chars.",
        ritual_components=[],
    )

    # Seed the Sinner's CharacterResonance so the resonance gate passes.
    CharacterResonanceFactory(character_sheet=sinner_sheet, resonance=resonance)

    return sinner_tenure, sineater_tenure, resonance


def _fire_request_sineating_in_scene(sinner_sheet, sineater_sheet, resonance, scene) -> object:
    """Call request_sineating with co-location patched to True.

    Used by tests that want to seed a SineatingPendingOffer without needing
    actual SceneParticipation rows for the sinner/sineater (avoids roster
    tenure setup complexity in model-only tests).
    """
    with patch(
        "world.magic.services.soul_tether._both_in_scene",
        return_value=True,
    ):
        return request_sineating(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            resonance=resonance,
            max_units=5,
            scene=scene,
        )


# =============================================================================
# 1. Model uniqueness constraint
# =============================================================================


class SineatingPendingOfferUniquenessTests(TestCase):
    """SineatingPendingOffer.one_pending_sineating_per_pair constraint."""

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
            sinner_role=SoulTetherRoleEnum.SINNER,
            resonance=resonance,
            writeup="Bond for uniqueness constraint test, at least twenty chars.",
            ritual_components=[],
        )

        rel = CharacterRelationship.objects.get(source=sinner_sheet, target=sineater_sheet)
        scene = SceneFactory()

        SineatingPendingOffer.objects.create(
            sinner_sheet=sinner_sheet,
            sineater_sheet=sineater_sheet,
            relationship=rel,
            scene=scene,
            resonance=resonance,
            units_offered=5,
            anima_cost_per_unit=_ANIMA_COST_PER_UNIT,
            fatigue_cost_per_unit=_FATIGUE_COST_PER_UNIT,
        )

        with self.assertRaises(IntegrityError):
            SineatingPendingOffer.objects.create(
                sinner_sheet=sinner_sheet,
                sineater_sheet=sineater_sheet,
                relationship=rel,
                scene=scene,
                resonance=resonance,
                units_offered=3,
                anima_cost_per_unit=_ANIMA_COST_PER_UNIT,
                fatigue_cost_per_unit=_FATIGUE_COST_PER_UNIT,
            )


# =============================================================================
# 2. request_sineating creates a pending offer row
# =============================================================================


class RequestSineatingCreatesPendingOfferTests(TestCase):
    """request_sineating writes a SineatingPendingOffer row (Task 1.6 Step 3)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.scene = SceneFactory()

    def test_request_creates_pending_offer_row(self) -> None:
        """Calling request_sineating creates exactly one SineatingPendingOffer row."""
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        self.assertEqual(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).count(),
            1,
        )

    def test_pending_offer_fields_match_request(self) -> None:
        """The pending offer row has correct sinner, sineater, resonance, scene."""
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        row = SineatingPendingOffer.objects.get(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
        )
        self.assertEqual(row.resonance_id, self.resonance.pk)
        self.assertEqual(row.scene_id, self.scene.pk)
        self.assertEqual(row.anima_cost_per_unit, _ANIMA_COST_PER_UNIT)
        self.assertEqual(row.fatigue_cost_per_unit, _FATIGUE_COST_PER_UNIT)

    def test_repeat_request_replaces_row_via_update_or_create(self) -> None:
        """A second request_sineating for the same pair replaces (not duplicates) the row."""
        scene2 = SceneFactory()
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene2
        )
        self.assertEqual(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).count(),
            1,
        )
        row = SineatingPendingOffer.objects.get(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
        )
        # The row should now reflect scene2 (the second request).
        self.assertEqual(row.scene_id, scene2.pk)


# =============================================================================
# 3. resolve_sineating_from_db happy path with co-location
# =============================================================================


class ResolveSineatingFromDbHappyPathTests(TestCase):
    """resolve_sineating_from_db resolves the offer when both are co-located (Task 1.6 Step 4)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        # Seed Sineater anima so the deduction step works.
        CharacterAnimaFactory(
            character=cls.sineater_sheet.character,
            current=20,
            maximum=20,
        )

        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

    def test_happy_path_audit_row_written(self) -> None:
        """resolve_sineating_from_db writes a Sineating audit row and clears the pending row."""
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        result = resolve_sineating_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_accepted=3,
        )
        self.assertEqual(result.units_accepted, 3)
        self.assertFalse(result.declined)
        # Audit row created.
        self.assertTrue(Sineating.objects.filter(sineater_sheet=self.sineater_sheet).exists())

    def test_happy_path_pending_row_deleted(self) -> None:
        """resolve_sineating_from_db deletes the SineatingPendingOffer on success."""
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        resolve_sineating_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_accepted=2,
        )
        self.assertFalse(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

    def test_decline_also_deletes_pending_row(self) -> None:
        """A decline (units_accepted=0) also cleans up the pending offer."""
        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, self.scene
        )
        result = resolve_sineating_from_db(
            sinner_sheet=self.sinner_sheet,
            sineater_sheet=self.sineater_sheet,
            units_accepted=0,
        )
        self.assertTrue(result.declined)
        self.assertFalse(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )


# =============================================================================
# 4. Stale when sineater departs
# =============================================================================


class ResolveSineatingFromDbSineaterDepartedTests(TestCase):
    """resolve_sineating_from_db raises SineatingValidationError when Sineater left scene."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

    def test_stale_when_sineater_departed(self) -> None:
        """Sineater leaving the scene makes the offer stale: raises SineatingValidationError."""
        scene = SceneFactory()
        # Only Sinner participates; Sineater has left (or never joined in time).
        SceneParticipationFactory(scene=scene, account=self.sinner_account)
        # Do NOT add Sineater participation.

        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene
        )

        with self.assertRaises(SineatingValidationError) as ctx:
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )
        self.assertIn("expired", ctx.exception.user_message)
        self.assertIn(ctx.exception.user_message, SineatingValidationError.SAFE_MESSAGES)

    def test_stale_deletes_pending_row(self) -> None:
        """A stale rejection cleans up the pending row so it does not haunt the inbox."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.sinner_account)
        # Sineater absent.

        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene
        )

        with self.assertRaises(SineatingValidationError):
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )

        self.assertFalse(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )

    def test_stale_no_audit_row_created(self) -> None:
        """A stale rejection must not create a Sineating audit row."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.sinner_account)

        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene
        )

        with self.assertRaises(SineatingValidationError):
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )

        self.assertFalse(Sineating.objects.filter(sineater_sheet=self.sineater_sheet).exists())


# =============================================================================
# 5. Stale when sinner departs
# =============================================================================


class ResolveSineatingFromDbSinnerDepartedTests(TestCase):
    """resolve_sineating_from_db raises SineatingValidationError when Sinner left scene."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

    def test_stale_when_sinner_departed(self) -> None:
        """Sinner leaving the scene makes the offer stale."""
        scene = SceneFactory()
        # Only Sineater participates.
        SceneParticipationFactory(scene=scene, account=self.sineater_account)

        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene
        )

        with self.assertRaises(SineatingValidationError) as ctx:
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )
        self.assertIn("expired", ctx.exception.user_message)

    def test_sinner_departed_deletes_pending_row(self) -> None:
        """Stale rejection from Sinner departure also cleans up the pending row."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.sineater_account)

        _fire_request_sineating_in_scene(
            self.sinner_sheet, self.sineater_sheet, self.resonance, scene
        )

        with self.assertRaises(SineatingValidationError):
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )

        self.assertFalse(
            SineatingPendingOffer.objects.filter(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
            ).exists()
        )


# =============================================================================
# 6. resolve_sineating_from_db with no pending offer
# =============================================================================


class ResolveSineatingFromDbNoPendingOfferTests(TestCase):
    """resolve_sineating_from_db raises SineatingValidationError when no row found."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_tethered_pair_with_tenures()
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet

    def test_no_pending_offer_raises(self) -> None:
        """resolve_sineating_from_db without a pending row raises SineatingValidationError."""
        with self.assertRaises(SineatingValidationError) as ctx:
            resolve_sineating_from_db(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                units_accepted=3,
            )
        self.assertIn("No pending", ctx.exception.user_message)
        self.assertIn(ctx.exception.user_message, SineatingValidationError.SAFE_MESSAGES)


# =============================================================================
# 7. Viewset scoping
# =============================================================================


class SineatingPendingOfferViewSetTests(APITestCase):
    """GET /api/magic/soul-tether/sineating/pending/ — scoped to caller as Sineater."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Pair A: sinner_a → sineater_a
        sinner_tenure_a, sineater_tenure_a, resonance_a = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_a = sinner_tenure_a.roster_entry.character_sheet
        cls.sineater_sheet_a = sineater_tenure_a.roster_entry.character_sheet
        cls.sineater_account_a = sineater_tenure_a.player_data.account
        cls.resonance_a = resonance_a

        # Pair B: sinner_b → sineater_b (different accounts)
        sinner_tenure_b, sineater_tenure_b, resonance_b = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_b = sinner_tenure_b.roster_entry.character_sheet
        cls.sineater_sheet_b = sineater_tenure_b.roster_entry.character_sheet
        cls.sineater_account_b = sineater_tenure_b.player_data.account
        cls.resonance_b = resonance_b

        cls.scene = SceneFactory()

    def _seed_offer_a(self) -> None:
        _fire_request_sineating_in_scene(
            self.sinner_sheet_a, self.sineater_sheet_a, self.resonance_a, self.scene
        )

    def _seed_offer_b(self) -> None:
        _fire_request_sineating_in_scene(
            self.sinner_sheet_b, self.sineater_sheet_b, self.resonance_b, self.scene
        )

    def test_sineater_sees_only_their_pending_offers(self) -> None:
        """Authenticated as sineater_a, only offer A appears in the list."""
        self._seed_offer_a()
        self._seed_offer_b()
        self.client.force_authenticate(user=self.sineater_account_a)
        response = self.client.get("/api/magic/soul-tether/sineating/pending/")
        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        offer_a = SineatingPendingOffer.objects.get(
            sinner_sheet=self.sinner_sheet_a,
            sineater_sheet=self.sineater_sheet_a,
        )
        offer_b = SineatingPendingOffer.objects.get(
            sinner_sheet=self.sinner_sheet_b,
            sineater_sheet=self.sineater_sheet_b,
        )
        self.assertIn(offer_a.pk, result_ids)
        self.assertNotIn(offer_b.pk, result_ids)

    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get("/api/magic/soul-tether/sineating/pending/")
        self.assertIn(response.status_code, (401, 403))

    def test_list_returns_expected_fields(self) -> None:
        """Response includes expected serializer fields."""
        self._seed_offer_a()
        self.client.force_authenticate(user=self.sineater_account_a)
        response = self.client.get("/api/magic/soul-tether/sineating/pending/")
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
            "units_offered",
            "anima_cost_per_unit",
            "fatigue_cost_per_unit",
            "created_at",
        ):
            self.assertIn(field, row, f"Missing field: {field}")
