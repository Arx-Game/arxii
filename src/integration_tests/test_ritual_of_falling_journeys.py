"""Journeys through the Ritual of Falling by affinity id (#4681).

A player with a drifting aura types ``ritual Ritual of Falling target_affinity=<id>``.
The command resolves the id to an ``Affinity`` row and the ritual converts her
resonance along the authored pair. An unknown id is refused in plain words.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.magic.constants import GainSource, RitualExecutionKind
from world.magic.factories import (
    CharacterAuraFactory,
    ResonanceFactory,
    RitualFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import (
    CharacterResonance,
    FallRedemptionRecord,
    ResonanceConversion,
    Ritual,
)
from world.magic.services.resonance import grant_resonance

PERFORM_URL = "/api/magic/rituals/perform/"
_FALL_PATH = "world.magic.services.fall_redemption.perform_fall"


class _AFalling(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, _abyssal = ensure_conversion_pairs()
        self.cele_res = ResonanceFactory(name="Bene", affinity=self.celestial)
        self.primal_res = ResonanceFactory(name="Praedari", affinity=self.primal)
        ResonanceConversion.objects.create(
            source_resonance=self.cele_res,
            target_affinity=self.primal,
            target_resonance=self.primal_res,
        )
        RitualFactory(
            name="Ritual of Falling",
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path=_FALL_PATH,
        )
        self.room = self.make_room("The Threshold")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="50", primal="45", abyssal="5")
        grant_resonance(self.sheet, self.cele_res, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(self.sheet, self.primal_res, 100, source=GainSource.STAFF_GRANT)


class FallingByAffinityId(_AFalling):
    def test_she_falls_to_primal_by_its_id(self) -> None:
        told = self.telnet(self.ysmay, f"ritual Ritual of Falling target_affinity={self.primal.pk}")
        self.assertIn("You perform Ritual of Falling.", told)
        record = FallRedemptionRecord.objects.get(character_sheet=self.sheet)
        self.assertEqual(record.from_affinity, self.celestial)
        self.assertEqual(record.to_affinity, self.primal)
        primal_row = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.primal_res
        )
        self.assertEqual(primal_row.balance, 220)

    def test_an_unknown_affinity_id_is_refused_plainly(self) -> None:
        told = self.telnet(self.ysmay, "ritual Ritual of Falling target_affinity=999999")
        self.assertIn("No affinity with id 999999.", told)
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=self.sheet).exists())

    def test_falling_to_the_affinity_she_already_holds_is_refused_plainly(self) -> None:
        told = self.telnet(
            self.ysmay, f"ritual Ritual of Falling target_affinity={self.celestial.pk}"
        )
        self.assertIn("already dominant", told)
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=self.sheet).exists())


class FallingThroughTheWebClient(_AFalling):
    def setUp(self) -> None:
        super().setUp()
        self.ritual = Ritual.objects.get(name="Ritual of Falling")

    def _post(self, affinity_id: int):
        return self.api(self.account_of(self.ysmay)).post(
            PERFORM_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"target_affinity": affinity_id},
            },
            format="json",
        )

    def test_the_web_client_falls_to_primal_by_its_id(self) -> None:
        response = self._post(self.primal.pk)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["result"]["to_affinity"]["id"], self.primal.pk)
        record = FallRedemptionRecord.objects.get(character_sheet=self.sheet)
        self.assertEqual(record.to_affinity, self.primal)

    def test_the_web_client_is_refused_an_unknown_affinity_id(self) -> None:
        response = self._post(999999)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["detail"], "No affinity with id 999999.")
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=self.sheet).exists())
