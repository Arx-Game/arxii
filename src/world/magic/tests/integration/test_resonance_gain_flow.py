"""End-to-end integration tests for Spec C resonance gain pipeline.

Each test exercises a slice of the full flow: endorsement creation →
settlement → ledger write → balance update, OR residence trickle, OR
alt-guard rejection, OR API-level DELETE lifecycle.

Pattern matches src/world/magic/tests/integration/test_soulfray_recovery_flow.py.
"""

from __future__ import annotations

import math

from django.test import TestCase
from rest_framework.test import APITestCase

# ---------------------------------------------------------------------------
# Helpers shared across the two test classes
# ---------------------------------------------------------------------------


def _make_tenure_backed_sheet():
    """Return a CharacterSheet anchored to a fresh RosterTenure (has an Account)."""
    from world.roster.factories import RosterTenureFactory

    tenure = RosterTenureFactory()
    return tenure.roster_entry.character_sheet


def _ensure_scene_participation(scene, sheet):
    """Add SceneParticipation for sheet's account, if an account exists."""
    from world.magic.services.gain import account_for_sheet
    from world.scenes.factories import SceneParticipationFactory

    account = account_for_sheet(sheet)
    if account is not None:
        SceneParticipationFactory(scene=scene, account=account)
    return account


# ---------------------------------------------------------------------------
# Service-level end-to-end tests
# ---------------------------------------------------------------------------


class ResonanceGainPipelineTests(TestCase):
    """Service-level end-to-end tests (non-API).

    Each method composes multiple services to exercise a complete slice of
    the Spec C pipeline, rather than testing a single function in isolation.
    """

    def test_full_week_pose_settlement(self) -> None:
        """Five pose endorsements by one endorser → settle_weekly_pot →
        ceil(pot/5) each → five ledger rows + five balance updates.

        Pipeline: create_pose_endorsement × 5 → settle_weekly_pot →
        assert ResonanceGrant count + CharacterResonance.balance.
        """
        from world.magic.constants import GainSource
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.models import CharacterResonance, ResonanceGrant
        from world.magic.services.gain import (
            create_pose_endorsement,
            get_resonance_gain_config,
            settle_weekly_pot,
        )
        from world.scenes.factories import InteractionFactory, SceneFactory

        endorser = _make_tenure_backed_sheet()
        scene = SceneFactory()
        _ensure_scene_participation(scene, endorser)

        endorsees = [_make_tenure_backed_sheet() for _ in range(5)]
        resonances = []
        for endorsee in endorsees:
            resonance = ResonanceFactory()
            CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
            interaction = InteractionFactory(scene=scene, persona=endorsee.primary_persona)
            create_pose_endorsement(endorser, interaction, resonance)
            resonances.append(resonance)

        result = settle_weekly_pot(endorser)
        cfg = get_resonance_gain_config()
        expected_share = math.ceil(cfg.weekly_pot_per_character / 5)

        self.assertEqual(result.endorsements_settled, 5)
        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.POSE_ENDORSEMENT).count(),
            5,
        )
        for endorsee, resonance in zip(endorsees, resonances, strict=True):
            cr = CharacterResonance.objects.get(character_sheet=endorsee, resonance=resonance)
            self.assertEqual(cr.balance, expected_share)

    def test_scene_entry_immediate_grant(self) -> None:
        """Scene entry endorsement fires grant + writes ledger row immediately.

        Pipeline: create_scene_entry_endorsement (with entry pose) →
        assert CharacterResonance.balance == cfg.scene_entry_grant + 1 ledger row.
        """
        from world.magic.constants import GainSource
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.models import CharacterResonance, ResonanceGrant
        from world.magic.services.gain import (
            create_scene_entry_endorsement,
            get_resonance_gain_config,
        )
        from world.scenes.constants import PoseKind
        from world.scenes.factories import InteractionFactory, SceneFactory

        endorser = _make_tenure_backed_sheet()
        endorsee = _make_tenure_backed_sheet()
        scene = SceneFactory()
        _ensure_scene_participation(scene, endorser)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        # Entry pose must exist in this scene for the service to accept the endorsement.
        InteractionFactory(
            scene=scene,
            persona=endorsee.primary_persona,
            pose_kind=PoseKind.ENTRY,
        )

        create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

        cfg = get_resonance_gain_config()
        cr = CharacterResonance.objects.get(character_sheet=endorsee, resonance=resonance)
        self.assertEqual(cr.balance, cfg.scene_entry_grant)
        self.assertEqual(
            ResonanceGrant.objects.filter(
                source=GainSource.SCENE_ENTRY, character_sheet=endorsee
            ).count(),
            1,
        )

    def test_alt_guard_blocks_pose_endorsement(self) -> None:
        """Same account playing both characters → alt guard rejects.

        Pipeline: build same-account alts → create_pose_endorsement →
        assert EndorsementValidationError.
        """
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import create_pose_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import InteractionFactory, SceneFactory

        endorser_tenure = RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet
        # Share the same PlayerData → same Account → alt relationship.
        endorsee_tenure = RosterTenureFactory(player_data=endorser_tenure.player_data)
        endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        scene = SceneFactory()
        _ensure_scene_participation(scene, endorser_sheet)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        interaction = InteractionFactory(scene=scene, persona=endorsee_sheet.primary_persona)

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser_sheet, interaction, resonance)

    def test_masquerade_captures_persona_snapshot(self) -> None:
        """Endorsement captures endorsee's primary persona at endorsement time;
        currency lands on the real CharacterSheet after settlement.

        Pipeline: build endorsement with persona field set to endorsee primary →
        assert endorsement.persona_snapshot == primary → settle → assert balance > 0.
        """
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.models import CharacterResonance
        from world.magic.services.gain import create_pose_endorsement, settle_weekly_pot
        from world.scenes.factories import InteractionFactory, SceneFactory

        endorser = _make_tenure_backed_sheet()
        endorsee = _make_tenure_backed_sheet()
        scene = SceneFactory()
        _ensure_scene_participation(scene, endorser)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        primary = endorsee.primary_persona
        interaction = InteractionFactory(scene=scene, persona=primary)

        endorsement = create_pose_endorsement(endorser, interaction, resonance)
        # Snapshot is captured at endorsement creation time.
        self.assertEqual(endorsement.persona_snapshot, primary)

        # Settlement lands the grant on the real CharacterSheet.
        settle_weekly_pot(endorser)
        cr = CharacterResonance.objects.get(character_sheet=endorsee, resonance=resonance)
        self.assertGreater(cr.balance, 0)

    def test_residence_trickle_end_to_end(self) -> None:
        """Tag room + set residence + run daily tick → balance increments.

        Pipeline: tag_room_resonance (matched + unmatched) → set_residence →
        resonance_daily_tick → assert residence_grants_issued == 1 + balance == cfg.rate.
        """
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.models import CharacterResonance
        from world.magic.services.gain import (
            get_resonance_gain_config,
            resonance_daily_tick,
            set_residence,
            tag_room_resonance,
        )

        sheet = _make_tenure_backed_sheet()
        rp = RoomProfileFactory()
        r_matched = ResonanceFactory()
        r_extra = ResonanceFactory()  # tagged but not claimed — should be ignored

        CharacterResonanceFactory(character_sheet=sheet, resonance=r_matched)
        tag_room_resonance(rp, r_matched)
        tag_room_resonance(rp, r_extra)
        set_residence(sheet, rp)

        cfg = get_resonance_gain_config()
        summary = resonance_daily_tick()
        self.assertGreaterEqual(summary.residence_grants_issued, 1)

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=r_matched)
        self.assertEqual(cr.balance, cfg.residence_daily_trickle_per_resonance)

    def test_outfit_tick_no_items_returns_zero(self) -> None:
        """Daily tick runs without errors; outfit grants is 0 when no items
        equipped.

        Pipeline: resonance_daily_tick → assert outfit_grants_issued == 0.
        The outfit pipeline is live as of Spec D §5.1; this test verifies the
        empty-state baseline.
        """
        from world.magic.services.gain import resonance_daily_tick

        summary = resonance_daily_tick()
        self.assertEqual(summary.outfit_grants_issued, 0)

    def test_tuning_change_affects_next_settlement(self) -> None:
        """Updating config.weekly_pot_per_character affects subsequent settlement.

        Pipeline: create endorsement → bump pot to 100 → settle_weekly_pot →
        assert total_granted == 100 (ceil(100/1) = 100).
        """
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import (
            create_pose_endorsement,
            get_resonance_gain_config,
            settle_weekly_pot,
        )
        from world.scenes.factories import InteractionFactory, SceneFactory

        endorser = _make_tenure_backed_sheet()
        endorsee = _make_tenure_backed_sheet()
        scene = SceneFactory()
        _ensure_scene_participation(scene, endorser)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        interaction = InteractionFactory(scene=scene, persona=endorsee.primary_persona)
        create_pose_endorsement(endorser, interaction, resonance)

        # Bump pot to 100 — settlement should distribute this new value.
        cfg = get_resonance_gain_config()
        cfg.weekly_pot_per_character = 100
        cfg.save(update_fields=["weekly_pot_per_character"])

        result = settle_weekly_pot(endorser)
        # 1 endorsement, pot=100 → ceil(100/1) = 100
        self.assertEqual(result.total_granted, 100)


# ---------------------------------------------------------------------------
# API-level lifecycle tests (DELETE behavior)
# ---------------------------------------------------------------------------


class ResonanceGainAPIPipelineTests(APITestCase):
    """API-level lifecycle tests for the pose-endorsement DELETE surface."""

    def _build_endorsement_for_account(self):
        """Build an unsettled PoseEndorsement via the service layer.

        Returns: (endorsement, endorser_account) so the test can authenticate.
        """
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import account_for_sheet, create_pose_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
            SceneParticipationFactory,
        )

        endorser_tenure = RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet
        endorsee_tenure = RosterTenureFactory()
        endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        scene = SceneFactory()
        endorser_account = account_for_sheet(endorser_sheet)
        if endorser_account is not None:
            SceneParticipationFactory(scene=scene, account=endorser_account)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        interaction = InteractionFactory(scene=scene, persona=endorsee_sheet.primary_persona)

        endorsement = create_pose_endorsement(endorser_sheet, interaction, resonance)
        return endorsement, endorser_account

    def test_delete_unsettled_returns_204(self) -> None:
        """DELETE on an unsettled endorsement → 204 No Content.

        Pipeline: create endorsement via service → authenticate as endorser →
        DELETE /api/magic/pose-endorsements/<pk>/ → assert 204.
        """
        endorsement, account = self._build_endorsement_for_account()
        self.client.force_authenticate(user=account)

        response = self.client.delete(f"/api/magic/pose-endorsements/{endorsement.pk}/")
        self.assertEqual(response.status_code, 204)

    def test_delete_after_settlement_returns_404(self) -> None:
        """DELETE on a settled endorsement → 404 Not Found.

        Pipeline: create endorsement via service → settle_weekly_pot →
        authenticate as endorser → DELETE → assert 404.
        """
        from world.magic.services.gain import settle_weekly_pot

        endorsement, account = self._build_endorsement_for_account()
        endorser_sheet = endorsement.endorser_sheet
        settle_weekly_pot(endorser_sheet)

        self.client.force_authenticate(user=account)
        response = self.client.delete(f"/api/magic/pose-endorsements/{endorsement.pk}/")
        self.assertEqual(response.status_code, 404)
