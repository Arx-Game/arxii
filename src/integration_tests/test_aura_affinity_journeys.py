"""Journeys for the aura as one share per Affinity row (#4681).

A character starts with the aura her weighted creation picks make (every point on one
resonance is wholly that resonance's affinity). Resonance she then earns moves the shares,
the dominant affinity the aura API names follows, and the Academy's fit line reads that
dominant affinity. Staff renaming an Affinity row loses nothing: recompute keys on the row, never
on its name. Each journey reads what the REST payload and the Academy menu show.

Expected numbers come from the seeded creation lifetime (10 points x 10), and the shares
a grant produces are lifetime earned by affinity as a percentage of the total. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from evennia.objects.models import ObjectDB
from rest_framework import status

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from integration_tests.test_academy_skill_course_journeys import (
    _AcademyCourseCase,
)
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    CharacterGiftFactory,
    GiftFactory,
    ResonanceFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
    ensure_canonical_affinities,
)
from world.magic.models import Affinity, CharacterAura
from world.magic.services.aura import set_aura_shares
from world.magic.services.resonance import grant_resonance
from world.magic.types import AffinityShare


def _shares(payload: dict) -> dict[str, Decimal]:
    """The aura payload's shares as {affinity name: percent}."""
    return {row["affinity_name"]: Decimal(row["percent"]) for row in payload["shares"]}


class StartingAuraAtCharacterCreation(FinalizationTestMixin, JourneyCase):
    """Staff finalize two characters, one picking a Primal resonance and one an Abyssal."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Aura", height_min=700, height_max=800)
        cls.staff = AccountFactory(is_staff=True)
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()

    def _character_made_picking(
        self, first_name: str, affinity: Affinity, *, outward: Affinity | None = None
    ) -> ObjectDB:
        """Finalize a draft whose Gift resonance is of ``affinity``; the character made.

        With ``outward`` the draft also holds one Celestial or Abyssal pick of that affinity,
        the single second pick creation allows (#5231): six points on the first, four on it.
        """
        self.account = self.staff
        self.resonance = ResonanceFactory(affinity=affinity)
        draft = self._create_base_draft(first_name=first_name)
        if outward is not None:
            draft.draft_data["gift_resonance_weights"] = [
                {"resonance_id": self.resonance.pk, "weight": 6},
                {"resonance_id": ResonanceFactory(affinity=outward).pk, "weight": 4},
            ]
            draft.save(update_fields=["draft_data"])
        added = self.api(self.staff).post(
            f"/api/character-creation/drafts/{draft.pk}/add-to-roster/", {}, format="json"
        )
        self.assertEqual(added.status_code, status.HTTP_200_OK, added.content)
        return ObjectDB.objects.get(pk=added.json()["character_id"])

    def _aura_payload(self, character: ObjectDB) -> dict:
        response = self.api(self.staff).get(f"/api/magic/character-auras/?character={character.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        rows = response.json()
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_a_primal_pick_starts_wholly_primal(self) -> None:
        character = self._character_made_picking("Wren", self.primal)
        payload = self._aura_payload(character)
        self.assertEqual(_shares(payload), {"Primal": Decimal(100)})
        self.assertEqual(payload["dominant_affinity"], "Primal")

    def test_an_abyssal_second_pick_starts_the_aura_primal_with_an_abyssal_share(self) -> None:
        # Creation refuses a wholly Abyssal start (a Primal feeling is required, #5231), so the
        # Abyssal pick rides beside one: 6 and 4 of the 10 points give 60 / 40.
        character = self._character_made_picking("Corin", self.primal, outward=self.abyssal)
        payload = self._aura_payload(character)
        self.assertEqual(_shares(payload), {"Primal": Decimal(60), "Abyssal": Decimal(40)})
        self.assertEqual(payload["dominant_affinity"], "Primal")

    def test_granting_resonance_moves_the_dominant_affinity_the_api_shows(self) -> None:
        character = self._character_made_picking("Wren", self.primal)
        self.assertEqual(self._aura_payload(character)["dominant_affinity"], "Primal")

        sheet = character.sheet_data
        grant_resonance(
            sheet,
            ResonanceFactory(affinity=self.abyssal),
            300,
            source=GainSource.STAFF_GRANT,
        )

        # 100 lifetime seeded at creation, 300 earned since: the aura extends, it is not replaced.
        payload = self._aura_payload(character)
        self.assertEqual(payload["dominant_affinity"], "Abyssal")
        self.assertEqual(_shares(payload), {"Abyssal": Decimal(75), "Primal": Decimal(25)})


class AuraAffinityAtTheAcademy(_AcademyCourseCase):
    """Ysmay's Academy fit line follows the affinity her aura is dominant in."""

    def setUp(self) -> None:
        super().setUp()
        _celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.dawn = AffinityFactory(name="Dawn")
        gift = GiftFactory(name="Lantern Gift")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        tradition = TraditionFactory(name="House of Dawn")
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        tradition.favored_affinities.add(self.dawn)
        self.role.teaches_tradition = tradition
        self.role.save()
        # She began mostly Primal, with an Abyssal streak.
        aura = CharacterAura.objects.create(character=self.sheet)
        set_aura_shares(
            aura,
            [
                AffinityShare(affinity=self.primal, percent=Decimal("80.00")),
                AffinityShare(affinity=self.abyssal, percent=Decimal("20.00")),
            ],
        )
        self.dawn_resonance = ResonanceFactory(name="Daybreak Hymn", affinity=self.dawn)

    def fit_line(self) -> str:
        """The fit line the web client is sent for the Occult course when she starts."""
        client = self.api(self.account_of(self.ysmay))
        response = client.post(
            "/api/npc-services/interactions/start/", {"role_id": self.role.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        client.post("/api/npc-services/interactions/end/", {}, format="json")
        offers = {offer["label"]: offer for offer in response.data["available_offers"]}
        return offers["Course: Occult"]["price"]["fit_line"]

    def test_renaming_an_affinity_in_the_admin_keeps_every_share(self) -> None:
        """A two-sided aura: Dawn 100 and Abyssal 50 earned is 66.67 / 33.33. Staff then
        rename Dawn through the admin change page; the next grant recomputes on the row."""
        grant_resonance(self.sheet, self.dawn_resonance, 100, source=GainSource.STAFF_GRANT)
        grant_resonance(
            self.sheet,
            ResonanceFactory(affinity=self.abyssal),
            50,
            source=GainSource.STAFF_GRANT,
        )
        before = self.aura_payload()
        self.assertEqual(_shares(before), {"Dawn": Decimal("66.67"), "Abyssal": Decimal("33.33")})

        staff = AccountFactory(is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        url = reverse("admin:arxii_affinity_change", args=[self.dawn.pk])
        response = self.client.post(
            url,
            {
                "name": "Daybreak",
                "description": self.dawn.description,
                "corruption_coefficient": self.dawn.corruption_coefficient,
                "burn_value": self.dawn.burn_value,
                # The earn and learn rates and the ritual's partner effect (#5181) are
                # required fields a browser posts with their current values.
                "claim_verb": self.dawn.claim_verb,
                "earn_rate_percent": self.dawn.earn_rate_percent,
                # The kindled boost (#5231) is a required percentage like the rates beside it.
                "kindled_boost_percent": self.dawn.kindled_boost_percent,
                "learn_rate_percent": self.dawn.learn_rate_percent,
                "ritual_partner_fatigue": self.dawn.ritual_partner_fatigue,
                # What one gain costs its payer (#5327) is a required number like the rest.
                "gain_fatigue": self.dawn.gain_fatigue,
                # The spend floor (#5308) is a required percentage too; 0 sets no floor.
                "spend_worth_floor_percent": self.dawn.spend_worth_floor_percent,
                # The page carries the affinity's kindling situations inline (#5124); a
                # browser posts the inline's management form with an empty set of rows.
                "kindling_situations-TOTAL_FORMS": "0",
                "kindling_situations-INITIAL_FORMS": "0",
                "kindling_situations-MIN_NUM_FORMS": "0",
                "kindling_situations-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302, response.content[:2000])

        grant_resonance(self.sheet, self.dawn_resonance, 50, source=GainSource.STAFF_GRANT)

        # Dawn row now holds 150 of 200 earned, Abyssal 50: 75 / 25.
        after = self.aura_payload()
        self.assertEqual(_shares(after), {"Daybreak": Decimal(75), "Abyssal": Decimal(25)})
        self.assertEqual(after["dominant_affinity"], "Daybreak")
        self.assertEqual(
            self.fit_line(),
            "Fits your Lantern Gift and its Daybreak affinity. Sessions are easier for you.",
        )

    def aura_payload(self) -> dict:
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/magic/character-auras/?character={self.sheet.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.json()[0]
