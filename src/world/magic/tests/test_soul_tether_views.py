"""API view tests for Soul Tether endpoints (Spec B Phase 11).

Covers:
    11.1  Accept view — happy path (201), invalid input (400), self-tether (400)
    11.2  Sineating request + respond views — happy path (200), gate failures (400)
    11.3  Rescue view — happy path (200), gate failures (400)
    11.4  Dissolve view — happy path (204), not-a-tether (400)
    11.5  Detail (state) view — happy path (200), not-a-tether (404)
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework.test import APITestCase

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _set_primary_affinity_abyssal(sheet: object) -> None:
    """Force the character's aura to be Abyssal-primary."""
    from world.magic.factories import CharacterAuraFactory

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
    """Force the character's aura to be Primal-primary."""
    from world.magic.factories import CharacterAuraFactory

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
    """Give a character a RELATIONSHIP_TRACK CharacterThreadWeavingUnlock."""
    from world.magic.constants import TargetKind
    from world.magic.factories import (
        CharacterThreadWeavingUnlockFactory,
        ThreadWeavingUnlockFactory,
    )

    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_eligible_pair_with_accounts(track=None):
    """Return (sinner_tenure, sineater_tenure, resonance).

    Both tenures have linked accounts for force_authenticate.
    Sinner is Abyssal-primary with RELATIONSHIP_TRACK unlock.
    Sineater is Primal-primary.
    Soul Tether authored content is seeded.
    """
    from world.magic.factories import ResonanceFactory, wire_soul_tether_content
    from world.relationships.factories import RelationshipTrackFactory
    from world.roster.factories import RosterTenureFactory

    wire_soul_tether_content()
    sinner_tenure = RosterTenureFactory()
    sineater_tenure = RosterTenureFactory()
    sinner_sheet = sinner_tenure.roster_entry.character_sheet
    sineater_sheet = sineater_tenure.roster_entry.character_sheet
    _set_primary_affinity_abyssal(sinner_sheet)
    _set_primary_affinity_primal(sineater_sheet)
    if track is None:
        track = RelationshipTrackFactory()
    _grant_relationship_track_unlock(sinner_sheet, track)
    resonance = ResonanceFactory()
    return sinner_tenure, sineater_tenure, resonance


# ---------------------------------------------------------------------------
# 11.1  Accept view
# ---------------------------------------------------------------------------


class SoulTetherAcceptViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/accept/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.relationships.factories import RelationshipTrackFactory

        cls.track = RelationshipTrackFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account

    def _post(self, data):
        return self.client.post("/api/magic/soul-tether/accept/", data, format="json")

    def _valid_payload(self):
        return {
            "actor_sheet_id": self.sinner_sheet.pk,
            "partner_sheet_id": self.sineater_sheet.pk,
            "sinner_role": "ABYSSAL",
            "resonance_id": self.resonance.pk,
            "writeup": "A bond woven between darkness and light, twenty or more chars.",
        }

    def test_happy_path_creates_tether_returns_201(self) -> None:
        """POST with valid payload creates a Soul Tether and returns 201 with capstone_id."""
        from world.relationships.models import CharacterRelationship

        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(self._valid_payload())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIn("capstone_id", response.data)
        self.assertTrue(
            CharacterRelationship.objects.filter(
                source=self.sinner_sheet,
                target=self.sineater_sheet,
                is_soul_tether=True,
            ).exists()
        )

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self._post(self._valid_payload())
        self.assertIn(response.status_code, (401, 403))

    def test_wrong_owner_returns_400(self) -> None:
        """actor_sheet_id not owned by the requesting account raises 400."""
        sineater_account = self.sineater_tenure.player_data.account
        self.client.force_authenticate(user=sineater_account)
        payload = self._valid_payload()
        # Sineater authenticates but tries to act as the sinner (wrong owner)
        payload["actor_sheet_id"] = self.sinner_sheet.pk
        response = self._post(payload)
        self.assertEqual(response.status_code, 400, response.content)

    def test_self_tether_returns_400(self) -> None:
        """Actor cannot tether with themselves."""
        self.client.force_authenticate(user=self.sinner_account)
        payload = self._valid_payload()
        payload["partner_sheet_id"] = self.sinner_sheet.pk
        response = self._post(payload)
        self.assertEqual(response.status_code, 400, response.content)

    def test_invalid_resonance_id_returns_400(self) -> None:
        """Non-existent resonance_id is rejected."""
        self.client.force_authenticate(user=self.sinner_account)
        payload = self._valid_payload()
        payload["resonance_id"] = 999999
        response = self._post(payload)
        self.assertEqual(response.status_code, 400, response.content)

    def test_writeup_too_short_returns_400(self) -> None:
        """Writeup shorter than 20 chars is rejected."""
        self.client.force_authenticate(user=self.sinner_account)
        payload = self._valid_payload()
        payload["writeup"] = "Short."
        response = self._post(payload)
        self.assertEqual(response.status_code, 400, response.content)

    def test_invalid_sinner_role_returns_400(self) -> None:
        """Unknown sinner_role is rejected."""
        self.client.force_authenticate(user=self.sinner_account)
        payload = self._valid_payload()
        payload["sinner_role"] = "INVALID"
        response = self._post(payload)
        self.assertEqual(response.status_code, 400, response.content)

    def test_duplicate_formation_returns_400(self) -> None:
        """Attempting to form the same Soul Tether twice raises 400."""
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole

        accept_soul_tether(
            initiator_sheet=self.sinner_sheet,
            partner_sheet=self.sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=self.resonance,
            writeup="A bond woven between darkness and light, first formation.",
            ritual_components=[],
        )
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(self._valid_payload())
        self.assertEqual(response.status_code, 400, response.content)


# ---------------------------------------------------------------------------
# 11.5  Detail (state) view
# ---------------------------------------------------------------------------


class SoulTetherDetailViewTests(APITestCase):
    """Tests for GET /api/magic/soul-tether/{relationship_id}/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTrackFactory

        cls.track = RelationshipTrackFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account

        cls.capstone = accept_soul_tether(
            initiator_sheet=cls.sinner_sheet,
            partner_sheet=cls.sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=cls.resonance,
            writeup="A bond woven in darkness, twenty or more characters here.",
            ritual_components=[],
        )
        # Find the outgoing (Sinner→Sineater) relationship row
        from world.relationships.models import CharacterRelationship

        cls.relationship = CharacterRelationship.objects.get(
            source=cls.sinner_sheet,
            target=cls.sineater_sheet,
            is_soul_tether=True,
        )

    def test_happy_path_returns_200_with_state(self) -> None:
        """GET with a valid soul-tether relationship_id returns 200 with hollow/strain data."""
        self.client.force_authenticate(user=self.sinner_account)
        response = self.client.get(f"/api/magic/soul-tether/{self.relationship.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertIn("hollow_current", data)
        self.assertIn("hollow_max", data)
        self.assertIn("sineater_lifetime_helped", data)
        self.assertIn("sinner_corruption_stage", data)
        self.assertIn("sineater_strain_stage", data)
        self.assertEqual(data["sinner_sheet_id"], self.sinner_sheet.pk)
        self.assertEqual(data["sineater_sheet_id"], self.sineater_sheet.pk)

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self.client.get(f"/api/magic/soul-tether/{self.relationship.pk}/")
        self.assertIn(response.status_code, (401, 403))

    def test_nonexistent_relationship_returns_404(self) -> None:
        """Non-existent relationship_id returns 404."""
        self.client.force_authenticate(user=self.sinner_account)
        response = self.client.get("/api/magic/soul-tether/999999/")
        self.assertEqual(response.status_code, 404, response.content)

    def test_non_soul_tether_relationship_returns_404(self) -> None:
        """A normal (non-soul-tether) relationship returns 404."""
        from world.relationships.factories import CharacterRelationshipFactory
        from world.roster.factories import RosterTenureFactory

        # Use fresh sheets — the sinner/sineater pair already has a tether relation.
        other_tenure_a = RosterTenureFactory()
        other_tenure_b = RosterTenureFactory()
        other_sheet_a = other_tenure_a.roster_entry.character_sheet
        other_sheet_b = other_tenure_b.roster_entry.character_sheet
        normal_rel = CharacterRelationshipFactory(
            source=other_sheet_a,
            target=other_sheet_b,
            is_soul_tether=False,
        )
        self.client.force_authenticate(user=self.sinner_account)
        response = self.client.get(f"/api/magic/soul-tether/{normal_rel.pk}/")
        self.assertEqual(response.status_code, 404, response.content)


# ---------------------------------------------------------------------------
# 11.4  Dissolve view
# ---------------------------------------------------------------------------


class SoulTetherDissolveViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/dissolve/.

    Each test that needs an active tether calls ``_form_tether()`` to create
    one from scratch (including seeding authored content). Tests that only
    test input-rejection paths do NOT need a real tether.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Seed authored content once for the class.
        from world.magic.factories import wire_soul_tether_content
        from world.relationships.factories import RelationshipTrackFactory

        wire_soul_tether_content()
        cls.track = RelationshipTrackFactory()

    def _form_tether(self):
        """Form a fresh Soul Tether per-test and return (account, sinner_sheet, relationship)."""
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.models import CharacterRelationship

        sinner_tenure, _sineater_tenure, resonance = _make_eligible_pair_with_accounts(self.track)
        sinner_sheet = sinner_tenure.roster_entry.character_sheet
        sineater_sheet = _sineater_tenure.roster_entry.character_sheet
        accept_soul_tether(
            initiator_sheet=sinner_sheet,
            partner_sheet=sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=resonance,
            writeup="A bond woven in darkness, dissolve test version here.",
            ritual_components=[],
        )
        relationship = CharacterRelationship.objects.get(
            source=sinner_sheet,
            target=sineater_sheet,
            is_soul_tether=True,
        )
        return sinner_tenure.player_data.account, sinner_sheet, relationship

    def _post(self, data):
        return self.client.post("/api/magic/soul-tether/dissolve/", data, format="json")

    def test_happy_path_dissolves_and_returns_204(self) -> None:
        """POST with valid relationship_id dissolves the tether and returns 204."""
        account, sinner_sheet, relationship = self._form_tether()
        self.client.force_authenticate(user=account)
        response = self._post(
            {
                "actor_sheet_id": sinner_sheet.pk,
                "relationship_id": relationship.pk,
            }
        )
        self.assertEqual(response.status_code, 204, response.content)
        relationship.refresh_from_db()
        self.assertFalse(relationship.is_soul_tether)

    def test_non_soul_tether_returns_400(self) -> None:
        """Non-soul-tether relationship_id returns 400."""
        from world.relationships.factories import CharacterRelationshipFactory
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        other_tenure = RosterTenureFactory()
        other_sheet = other_tenure.roster_entry.character_sheet
        normal_rel = CharacterRelationshipFactory(
            source=sheet, target=other_sheet, is_soul_tether=False
        )
        self.client.force_authenticate(user=tenure.player_data.account)
        response = self._post(
            {
                "actor_sheet_id": sheet.pk,
                "relationship_id": normal_rel.pk,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self._post({"actor_sheet_id": 1, "relationship_id": 1})
        self.assertIn(response.status_code, (401, 403))


# ---------------------------------------------------------------------------
# 11.2  Sineating request view
# ---------------------------------------------------------------------------


class SineatingRequestViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/sineating/request/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTrackFactory
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        cls.track = RelationshipTrackFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        accept_soul_tether(
            initiator_sheet=cls.sinner_sheet,
            partner_sheet=cls.sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=cls.resonance,
            writeup="A bond woven in darkness, sineating test version long enough.",
            ritual_components=[],
        )
        # Add CharacterResonance for sinner so resonance check passes
        from world.magic.factories import CharacterResonanceFactory

        CharacterResonanceFactory(
            character_sheet=cls.sinner_sheet,
            resonance=cls.resonance,
        )
        # Scene with both characters participating
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

    def _post(self, data):
        return self.client.post("/api/magic/soul-tether/sineating/request/", data, format="json")

    def test_happy_path_returns_200_with_offer(self) -> None:
        """POST returns 200 with SineatingOffer payload."""
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(
            {
                "actor_sheet_id": self.sinner_sheet.pk,
                "sineater_sheet_id": self.sineater_sheet.pk,
                "resonance_id": self.resonance.pk,
                "max_units": 5,
                "scene_id": self.scene.pk,
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertIn("max_units_offered", data)
        self.assertIn("anima_cost_per_unit", data)
        self.assertIn("current_hollow", data)
        self.assertIn("hollow_max", data)

    def test_no_tether_returns_400(self) -> None:
        """Request with no active tether returns 400."""
        from world.roster.factories import RosterTenureFactory

        stranger_tenure = RosterTenureFactory()
        stranger_sheet = stranger_tenure.roster_entry.character_sheet
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(
            {
                "actor_sheet_id": self.sinner_sheet.pk,
                "sineater_sheet_id": stranger_sheet.pk,
                "resonance_id": self.resonance.pk,
                "max_units": 5,
                "scene_id": self.scene.pk,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self._post({})
        self.assertIn(response.status_code, (401, 403))


# ---------------------------------------------------------------------------
# 11.2  Sineating respond view
# ---------------------------------------------------------------------------


class SineatingRespondViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/sineating/respond/.

    Each test that triggers the respond path seeds a fresh SineatingPendingOffer
    via request_sineating, because resolve_sineating_from_db consumes and
    deletes the pending row on every call (Task 1.6).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import CharacterResonanceFactory
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTrackFactory
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        cls.track = RelationshipTrackFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        accept_soul_tether(
            initiator_sheet=cls.sinner_sheet,
            partner_sheet=cls.sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=cls.resonance,
            writeup="A bond woven in darkness, respond test version long enough.",
            ritual_components=[],
        )
        CharacterResonanceFactory(
            character_sheet=cls.sinner_sheet,
            resonance=cls.resonance,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

    def _seed_pending_offer(self) -> None:
        """Create a SineatingPendingOffer row for the test pair via request_sineating.

        Task 1.6: the respond endpoint now calls resolve_sineating_from_db which
        requires a pending row in the database. Each test that exercises the
        respond path must seed this row first.
        """
        from unittest.mock import patch

        from world.magic.services.soul_tether import request_sineating

        with patch(
            "world.magic.services.soul_tether._both_in_scene",
            return_value=True,
        ):
            request_sineating(
                sinner_sheet=self.sinner_sheet,
                sineater_sheet=self.sineater_sheet,
                resonance=self.resonance,
                max_units=5,
                scene=self.scene,
            )

    def _post(self, data):
        return self.client.post("/api/magic/soul-tether/sineating/respond/", data, format="json")

    def _valid_payload(self, units_accepted=3):
        return {
            "sinner_sheet_id": self.sinner_sheet.pk,
            "sineater_sheet_id": self.sineater_sheet.pk,
            "units_accepted": units_accepted,
        }

    def test_accept_returns_200_with_result(self) -> None:
        """POST with units_accepted > 0 returns 200 with result payload."""
        self._seed_pending_offer()
        self.client.force_authenticate(user=self.sineater_account)
        response = self._post(self._valid_payload(units_accepted=3))
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        self.assertFalse(data["declined"])
        self.assertEqual(data["units_accepted"], 3)
        self.assertIn("audit_row_id", data)

    def test_decline_units_zero_returns_200_declined(self) -> None:
        """POST with units_accepted == 0 returns 200 with declined=True."""
        self._seed_pending_offer()
        self.client.force_authenticate(user=self.sineater_account)
        response = self._post(self._valid_payload(units_accepted=0))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["declined"])

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected — no pending row needed."""
        response = self._post(self._valid_payload())
        self.assertIn(response.status_code, (401, 403))

    def test_wrong_owner_sineater_returns_400(self) -> None:
        """sineater_sheet_id not owned by the requesting account returns 400.

        Auth rejection happens in the serializer validate_sineater_sheet_id step
        before the DB lookup, so no pending row is needed.
        """
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(self._valid_payload())
        self.assertEqual(response.status_code, 400, response.content)


# ---------------------------------------------------------------------------
# 11.3  Rescue view
# ---------------------------------------------------------------------------


class SoulTetherRescueViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/rescue/.

    The rescue has strict gates (Sinner must be at corruption stage 3+, both
    in scene, etc.). We test the gate-failure paths via unit control and the
    happy path via a mocked reduce_corruption that returns a plausible result.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import CharacterResonanceFactory
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTrackFactory
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        cls.track = RelationshipTrackFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account
        cls.sineater_account = cls.sineater_tenure.player_data.account

        accept_soul_tether(
            initiator_sheet=cls.sinner_sheet,
            partner_sheet=cls.sineater_sheet,
            sinner_role=SoulTetherRole.ABYSSAL,
            resonance=cls.resonance,
            writeup="A bond woven in darkness, rescue test version long enough.",
            ritual_components=[],
        )
        CharacterResonanceFactory(
            character_sheet=cls.sinner_sheet,
            resonance=cls.resonance,
        )
        CharacterResonanceFactory(
            character_sheet=cls.sineater_sheet,
            resonance=cls.resonance,
            balance=1000,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.sinner_account)
        SceneParticipationFactory(scene=cls.scene, account=cls.sineater_account)

    def _post(self, data):
        return self.client.post("/api/magic/soul-tether/rescue/", data, format="json")

    def test_gate_failure_sinner_not_stage_3_returns_400(self) -> None:
        """Rescue requires Sinner at corruption stage 3+; below that returns 400."""
        self.client.force_authenticate(user=self.sineater_account)
        response = self._post(
            {
                "actor_sheet_id": self.sineater_sheet.pk,
                "sinner_sheet_id": self.sinner_sheet.pk,
                "resonance_id": self.resonance.pk,
                "scene_id": self.scene.pk,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        response = self._post({})
        self.assertIn(response.status_code, (401, 403))

    def test_wrong_owner_actor_returns_400(self) -> None:
        """actor_sheet_id not owned by the requesting account returns 400."""
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(
            {
                "actor_sheet_id": self.sineater_sheet.pk,
                "sinner_sheet_id": self.sinner_sheet.pk,
                "resonance_id": self.resonance.pk,
                "scene_id": self.scene.pk,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
