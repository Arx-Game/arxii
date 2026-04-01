"""Tests for use_technique orchestrator."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.types import TechniqueUseResult
from world.mechanics.factories import CharacterEngagementFactory


class UseTechniqueBasicTests(TestCase):
    """Test the orchestrator with sufficient anima and controlled technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=8,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=10, maximum=10)
        self.character = self.anima.character
        # Engage the character so social safety bonus doesn't apply
        CharacterEngagementFactory(character=self.character)

    def test_sufficient_anima_no_checkpoint(self) -> None:
        """Technique with enough anima resolves without confirmation."""
        mock_resolve = MagicMock(return_value="resolution_result")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
        )

        assert isinstance(result, TechniqueUseResult)
        assert result.confirmed is True
        assert result.resolution_result == "resolution_result"
        assert result.mishap is None
        mock_resolve.assert_called_once()

        # Anima deducted: cost=8, control_delta=5, effective=3
        self.anima.refresh_from_db()
        assert self.anima.current == 7  # 10 - 3

    def test_control_exceeds_intensity_no_mishap(self) -> None:
        """When control > intensity, no mishap rider fires."""
        mock_resolve = MagicMock(return_value="ok")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
        )

        assert result.mishap is None


class UseTechniqueWarpCheckpointTests(TestCase):
    """Test the orchestrator's warp warning checkpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        # High intensity, low control = expensive
        cls.technique = TechniqueFactory(
            intensity=20,
            control=5,
            anima_cost=10,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=5, maximum=10)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    @patch("world.magic.services.get_warp_warning")
    def test_warp_warning_pauses_for_confirmation(
        self,
        mock_warning: MagicMock,
    ) -> None:
        """Warp warning pauses for confirmation with stage info."""
        from world.magic.types import WarpWarning

        mock_warning.return_value = WarpWarning(
            stage_name="Flickering",
            stage_description="Anima flickers.",
            has_death_risk=False,
        )

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(),
            confirm_warp_risk=False,  # Player declines
        )

        assert result.confirmed is False
        assert result.resolution_result is None
        assert result.warp_warning is not None
        assert result.warp_warning.stage_name == "Flickering"

        # Anima NOT deducted when cancelled
        self.anima.refresh_from_db()
        assert self.anima.current == 5

    def test_no_warp_warning_proceeds_normally(self) -> None:
        """Without warp warning, confirm_warp_risk=False has no effect."""
        mock_resolve = MagicMock(return_value="resolved")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
            confirm_warp_risk=False,  # No warning exists, so proceeds
        )

        assert result.confirmed is True
        assert result.resolution_result == "resolved"
        mock_resolve.assert_called_once()

    def test_overburn_confirmed_deducts_and_resolves(self) -> None:
        """Confirmed overburn deducts anima, resolves, applies warp."""
        mock_resolve = MagicMock(return_value="resolved")

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=mock_resolve,
            confirm_warp_risk=True,
        )

        assert result.confirmed is True
        assert result.resolution_result == "resolved"
        assert result.anima_cost.deficit > 0
        mock_resolve.assert_called_once()

        # Anima fully drained
        self.anima.refresh_from_db()
        assert self.anima.current == 0


class UseTechniqueMishapTests(TestCase):
    """Test mishap rider when intensity > control."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Intensity > control but enough anima
        cls.technique = TechniqueFactory(
            intensity=15,
            control=5,
            anima_cost=5,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)

    @patch("world.magic.services.select_mishap_pool")
    def test_mishap_fires_when_intensity_exceeds_control(
        self,
        mock_pool: MagicMock,
    ) -> None:
        """Mishap rider fires after resolution when intensity > control."""
        mock_pool.return_value = None  # No pool configured yet

        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="resolved"),
        )

        # select_mishap_pool called with control_deficit=10
        mock_pool.assert_called_once_with(10)
        assert result.resolution_result == "resolved"
