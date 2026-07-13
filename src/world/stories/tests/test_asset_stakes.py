"""Tests for stakes-driven asset compromise (#1905).

Verifies that a StakeResolution with transitions_subject_asset fires
transition_asset_status on the stake's subject_asset.
"""

from __future__ import annotations

from django.test import TestCase

from world.assets.constants import AssetStatus
from world.assets.factories import NPCAssetFactory
from world.stories.constants import StakeResolutionColumn, StakeSeverity, StakeSubjectKind
from world.stories.factories import BeatFactory, StakeFactory, StakeResolutionFactory


class AssetStakesTests(TestCase):
    """Tests for ASSET subject-kind stakes + transitions_subject_asset (#1905)."""

    def test_stake_can_reference_asset(self) -> None:
        """A Stake with subject_kind=ASSET and subject_asset is valid."""
        asset = NPCAssetFactory()
        beat = BeatFactory()
        stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.ASSET,
            subject_asset=asset,
            severity=StakeSeverity.GRAVE,
            player_summary="Your informant is in danger.",
        )
        self.assertEqual(stake.subject_asset, asset)
        self.assertEqual(stake.subject_kind, StakeSubjectKind.ASSET)

    def test_resolution_transitions_asset_to_compromised(self) -> None:
        """A LOSS resolution with transitions_subject_asset=COMPROMISED fires."""
        asset = NPCAssetFactory()
        beat = BeatFactory()
        stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.ASSET,
            subject_asset=asset,
            severity=StakeSeverity.GRAVE,
            player_summary="Your informant is in danger.",
        )
        resolution = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            transitions_subject_asset=AssetStatus.COMPROMISED,
        )

        # Simulate the firing of the branch writers.
        from world.stories.services.stake_resolution import _write_asset_transition

        _write_asset_transition(resolution, stake)

        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.COMPROMISED)

    def test_resolution_transitions_asset_to_lost(self) -> None:
        """A LOSS resolution with transitions_subject_asset=LOST fires."""
        asset = NPCAssetFactory()
        beat = BeatFactory()
        stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.ASSET,
            subject_asset=asset,
            severity=StakeSeverity.DIRE,
            player_summary="Your asset's life hangs in the balance.",
        )
        resolution = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            transitions_subject_asset=AssetStatus.LOST,
        )

        from world.stories.services.stake_resolution import _write_asset_transition

        _write_asset_transition(resolution, stake)

        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.LOST)

    def test_resolution_skips_when_subject_asset_is_none(self) -> None:
        """When the stake has no subject_asset, the writer skips gracefully."""
        beat = BeatFactory()
        stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Some custom stake",
            severity=StakeSeverity.SETBACK,
            player_summary="Something is at stake.",
        )
        resolution = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            transitions_subject_asset=AssetStatus.COMPROMISED,
        )

        from world.stories.services.stake_resolution import _write_asset_transition

        # Should not raise — just log a warning and return.
        _write_asset_transition(resolution, stake)
