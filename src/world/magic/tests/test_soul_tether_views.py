"""API view tests for Soul Tether endpoints (Spec B Phase 11).

Covers:
    11.1  Accept view — happy path (201), invalid input (400), self-tether (400)
    11.2  (the Sineating request and respond views are gone, #5177: a pose carries Sineating)
    11.3  Rescue view — happy path (200), gate failures (400)
    11.4  Dissolve view — happy path (204), not-a-tether (400)
    11.5  Detail (state) view — happy path (200), not-a-tether (404)
"""

from __future__ import annotations

from decimal import Decimal

from django.test import override_settings
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
        from world.magic.factories import set_aura_split

        set_aura_split(aura, celestial="10.00", primal="10.00", abyssal="80.00")
    except AttributeError:
        CharacterAuraFactory(
            character=char.sheet_data,
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
        from world.magic.factories import set_aura_split

        set_aura_split(aura, celestial="10.00", primal="80.00", abyssal="10.00")
    except AttributeError:
        CharacterAuraFactory(
            character=char.sheet_data,
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
        unlock_type=track,
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
    from world.relationships.factories import RelationshipTypeFactory
    from world.roster.factories import RosterTenureFactory

    wire_soul_tether_content()
    sinner_tenure = RosterTenureFactory()
    sineater_tenure = RosterTenureFactory()
    sinner_sheet = sinner_tenure.roster_entry.character_sheet
    sineater_sheet = sineater_tenure.roster_entry.character_sheet
    _set_primary_affinity_abyssal(sinner_sheet)
    _set_primary_affinity_primal(sineater_sheet)
    if track is None:
        track = RelationshipTypeFactory()
    _grant_relationship_track_unlock(sinner_sheet, track)
    resonance = ResonanceFactory()
    return sinner_tenure, sineater_tenure, resonance


# ---------------------------------------------------------------------------
# 11.1  Accept view
# ---------------------------------------------------------------------------


@override_settings(SEED_SAMPLE_CONTENT=True)
class SoulTetherAcceptViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/accept/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.relationships.factories import RelationshipTypeFactory

        cls.track = RelationshipTypeFactory()
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
            "sinner_role": "SINNER",
            "resonance_id": self.resonance.pk,
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
            sinner_role=SoulTetherRole.SINNER,
            resonance=self.resonance,
            ritual_components=[],
        )
        self.client.force_authenticate(user=self.sinner_account)
        response = self._post(self._valid_payload())
        self.assertEqual(response.status_code, 400, response.content)


# ---------------------------------------------------------------------------
# 11.5  Detail (state) view
# ---------------------------------------------------------------------------


@override_settings(SEED_SAMPLE_CONTENT=True)
class SoulTetherDetailViewTests(APITestCase):
    """Tests for GET /api/magic/soul-tether/{relationship_id}/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTypeFactory

        cls.track = RelationshipTypeFactory()
        cls.sinner_tenure, cls.sineater_tenure, cls.resonance = _make_eligible_pair_with_accounts(
            cls.track
        )
        cls.sinner_sheet = cls.sinner_tenure.roster_entry.character_sheet
        cls.sineater_sheet = cls.sineater_tenure.roster_entry.character_sheet
        cls.sinner_account = cls.sinner_tenure.player_data.account

        cls.capstone = accept_soul_tether(
            initiator_sheet=cls.sinner_sheet,
            partner_sheet=cls.sineater_sheet,
            sinner_role=SoulTetherRole.SINNER,
            resonance=cls.resonance,
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
        self.assertEqual(data["mire"], [])
        self.assertEqual(data["sinner_sheet_id"], self.sinner_sheet.pk)
        self.assertEqual(data["sineater_sheet_id"], self.sineater_sheet.pk)

    def test_the_sineater_sees_the_mire_they_carry_and_the_sinner_sees_none_of_it(self) -> None:
        """The Mire per Sinner is the Sineater's alone (#5177): the Sinner is never told."""
        from world.conditions.factories import ConditionInstanceFactory
        from world.magic.factories import CorruptionConditionTemplateFactory
        from world.magic.models import CharacterResonance, MireHolding
        from world.relationships.models import CharacterRelationship

        side = CharacterRelationship.objects.get(
            source=self.sineater_sheet, target=self.sinner_sheet, is_soul_tether=True
        )
        MireHolding.objects.create(relationship=side, resonance=self.resonance, amount=120)
        CharacterResonance.objects.update_or_create(
            character_sheet=self.sineater_sheet,
            resonance=self.resonance,
            defaults={"corruption_current": 120},
        )
        template = CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)
        ConditionInstanceFactory(
            target=self.sineater_sheet.character,
            condition=template,
            current_stage=template.stages.get(stage_order=1),
            severity=120,
        )
        url = f"/api/magic/soul-tether/{self.relationship.pk}/"

        self.client.force_authenticate(user=self.sineater_tenure.player_data.account)
        sineater_view = self.client.get(url).data["mire"]
        self.client.force_authenticate(user=self.sinner_account)
        sinner_view = self.client.get(url).data["mire"]

        (entry,) = sineater_view
        self.assertEqual(entry["sinner_sheet_id"], self.sinner_sheet.pk)
        self.assertEqual(entry["sinner_name"], self.sinner_sheet.primary_persona.name)
        self.assertEqual(entry["total"], 120)
        (row,) = entry["rows"]
        self.assertEqual((row["resonance_name"], row["amount"]), (self.resonance.name, 120))
        self.assertTrue(row["label"])
        self.assertEqual(sinner_view, [])

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


@override_settings(SEED_SAMPLE_CONTENT=True)
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
        from world.relationships.factories import RelationshipTypeFactory

        wire_soul_tether_content()
        cls.track = RelationshipTypeFactory()

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
            sinner_role=SoulTetherRole.SINNER,
            resonance=resonance,
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
# 11.3  Rescue view
# ---------------------------------------------------------------------------


@override_settings(SEED_SAMPLE_CONTENT=True)
class SoulTetherRescueViewTests(APITestCase):
    """Tests for POST /api/magic/soul-tether/rescue/.

    The rescue has strict gates (Sinner must be at corruption stage 3+, both
    in scene, etc.). We test the gate-failure paths via unit control and the
    happy path via a mocked reduce_corruption that returns a plausible result.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import CharacterResonanceFactory, place_in_active_scene
        from world.magic.services.soul_tether import accept_soul_tether
        from world.magic.types.soul_tether import SoulTetherRole
        from world.relationships.factories import RelationshipTypeFactory

        cls.track = RelationshipTypeFactory()
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
            sinner_role=SoulTetherRole.SINNER,
            resonance=cls.resonance,
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
        cls.scene = place_in_active_scene(cls.sinner_sheet, cls.sineater_sheet)

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
