"""Resolution theater: dramatic check outcomes feed the roulette pipeline (#924)."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.checks.models import Consequence
from world.checks.theater import build_roulette_payload, maybe_emit_resolution_theater
from world.traits.factories import CheckOutcomeFactory


class ResolutionTheaterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tier = CheckOutcomeFactory(name="Catastrophe")

    def _consequence(
        self, label: str, *, weight: int = 1, loss: bool = False, theater: bool = False
    ) -> Consequence:
        return Consequence(
            outcome_tier=self.tier,
            label=label,
            weight=weight,
            character_loss=loss,
            theater=theater,
        )

    def test_payload_matches_frontend_contract(self) -> None:
        death = self._consequence("Death", weight=1, loss=True)
        prison = self._consequence("Imprisonment", weight=3)
        payload = build_roulette_payload(
            title="Slum Heist",
            consequences=[death, prison],
            selected=prison,
        )
        assert payload["template_name"] == "Slum Heist"
        rows = payload["consequences"]
        assert [r["label"] for r in rows] == ["Death", "Imprisonment"]
        assert rows[0]["is_selected"] is False
        assert rows[1]["is_selected"] is True
        assert rows[1]["weight"] == 3
        assert rows[0]["tier_name"] == "Catastrophe"

    def test_no_drama_no_emit(self) -> None:
        character = MagicMock()
        plain = self._consequence("Bruised ego")
        emitted = maybe_emit_resolution_theater(
            character=character,
            title="Trivial Check",
            consequences=[plain],
            selected=plain,
        )
        assert emitted is False
        character.msg.assert_not_called()

    def test_character_loss_candidate_triggers_emit(self) -> None:
        character = MagicMock()
        death = self._consequence("Death", loss=True)
        prison = self._consequence("Imprisonment")
        emitted = maybe_emit_resolution_theater(
            character=character,
            title="Slum Heist",
            consequences=[death, prison],
            selected=prison,
        )
        assert emitted is True
        kwargs = character.msg.call_args.kwargs
        assert "roulette_result" in kwargs
        payload = kwargs["roulette_result"][1]
        assert payload["template_name"] == "Slum Heist"
        assert [c["label"] for c in payload["consequences"]] == ["Death", "Imprisonment"]

    def test_authored_theater_flag_triggers_emit(self) -> None:
        character = MagicMock()
        flagged = self._consequence("Dramatic reveal", theater=True)
        emitted = maybe_emit_resolution_theater(
            character=character,
            title="Authored Drama",
            consequences=[flagged],
            selected=flagged,
        )
        assert emitted is True

    def test_empty_candidates_never_emit(self) -> None:
        character = MagicMock()
        emitted = maybe_emit_resolution_theater(
            character=character,
            title="Nothing",
            consequences=[],
            selected=None,
        )
        assert emitted is False

    def test_msg_failure_never_breaks_resolution(self) -> None:
        character = MagicMock()
        character.msg.side_effect = AttributeError("no session")
        death = self._consequence("Death", loss=True)
        emitted = maybe_emit_resolution_theater(
            character=character,
            title="Slum Heist",
            consequences=[death],
            selected=death,
        )
        assert emitted is False
