"""Journeys for the aura a character ACTS with while wearing an alternate self (#4731).

A character whose true aura is Celestial 80 / Abyssal 20 wears an alternate self whose
resonance is Abyssal. What she casts and what a place of power or a covenant perk reads
follows the alternate self (100% Abyssal); who she IS (Fall threshold, Soul Tether gate,
the sheet's aura display) keeps reading the true aura. An alternate self with no
resonance changes nothing. Expected numbers come from the ruled split and the
affinity-alignment bonus: bonus x percent / 100. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import status

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatOpponentFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.covenants.perks.constants import Situation
from world.covenants.perks.context import SituationContext, SituationParams
from world.covenants.perks.evaluators import SITUATION_EVALUATORS
from world.forms.factories import AlternateSelfFactory
from world.forms.models import ActiveAlternateSelf
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.exceptions import AffinityGateError, FallEligibilityError
from world.magic.factories import (
    AffinityInteractionFactory,
    AuraPowerConfigFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    ensure_canonical_affinities,
)
from world.magic.models import Affinity
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.services.acting_aura import acting_aura
from world.magic.services.fall_redemption import perform_fall
from world.magic.services.gain import tag_room_resonance
from world.magic.services.soul_tether import accept_soul_tether
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.magic.types.soul_tether import SoulTetherRole
from world.scenes.cast_services import request_technique_cast
from world.scenes.factories import PersonaFactory
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)

ALIGNMENT_BONUS = 100


def _wear(sheet, alt) -> None:
    """The character assumes ``alt`` (None clears it, as a revert does)."""
    ActiveAlternateSelf.objects.update_or_create(character=sheet, defaults={"alternate_self": alt})


def _true_aura(sheet, *, celestial: str = "80.00", abyssal: str = "20.00") -> None:
    """Celestial 80 / Abyssal 20 unless told otherwise."""
    CharacterAuraFactory(
        character=sheet,
        celestial=Decimal(celestial),
        primal=Decimal("0.00"),
        abyssal=Decimal(abyssal),
    )


class AlignmentFollowsTheAlternateSelfOnACast(CastScenarioMixin):
    """She casts an Abyssal technique with and without the Abyssal alternate self."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.sheet = self.caster.character_sheet
        _true_aura(self.sheet)
        AuraPowerConfigFactory(affinity_alignment_bonus=ALIGNMENT_BONUS)
        self.resonance = ResonanceFactory(affinity=self.abyssal)
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        self.technique = make_benign_castable_technique()
        self.technique.gift = gift
        self.technique.save()
        grant_technique(self.caster, self.technique)
        self.alt = AlternateSelfFactory(character=self.sheet, resonance=self.resonance)

    def _alignment_term(self) -> int:
        cast = request_technique_cast(
            scene=self.scene, initiator_persona=self.caster, technique=self.technique
        )
        entries = [e for e in cast.power_ledger.entries if e.source_label == "aura power"]
        self.assertEqual(len(entries), 1, cast.power_ledger.entries)
        return entries[0].amount

    def test_the_alignment_term_is_the_alternate_selfs_while_worn(self) -> None:
        self.assertEqual(self._alignment_term(), 20)  # true aura: 20% Abyssal
        _wear(self.sheet, self.alt)
        self.assertEqual(self._alignment_term(), 100)  # the alternate self: 100% Abyssal
        _wear(self.sheet, None)
        self.assertEqual(self._alignment_term(), 20)  # reverted


class TheTrueAuraStillAnswersWhoSheIs(ResonanceCacheIsolationMixin, JourneyCase):
    """Fall threshold, the sheet's aura display and the Soul Tether gate ignore the mask."""

    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.sheet = CharacterSheetFactory()
        _true_aura(self.sheet)
        self.alt = AlternateSelfFactory(
            character=self.sheet, resonance=ResonanceFactory(affinity=self.abyssal)
        )
        _wear(self.sheet, self.alt)
        self.staff = AccountFactory(is_staff=True)

    def test_the_fall_threshold_reads_the_true_aura(self) -> None:
        with self.assertRaises(FallEligibilityError) as raised:
            perform_fall(self.sheet, target_affinity=self.abyssal)
        self.assertIn("only 20", raised.exception.user_message)

    def test_the_sheet_display_shows_the_true_aura(self) -> None:
        response = self.api(self.staff).get(
            f"/api/magic/character-auras/?character={self.sheet.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        payload = response.json()[0]
        self.assertEqual(payload["dominant_affinity"], "Celestial")
        shares = {row["affinity_name"]: Decimal(row["percent"]) for row in payload["shares"]}
        self.assertEqual(shares, {"Celestial": Decimal(80), "Abyssal": Decimal(20)})

    def test_the_soul_tether_gate_still_sees_a_celestial_sinner(self) -> None:
        sineater = CharacterSheetFactory()
        CharacterAuraFactory(
            character=sineater,
            celestial=Decimal("0.00"),
            primal=Decimal("80.00"),
            abyssal=Decimal("20.00"),
        )
        with self.assertRaises(AffinityGateError):
            accept_soul_tether(
                initiator_sheet=self.sheet,
                partner_sheet=sineater,
                sinner_role=SoulTetherRole.SINNER,
                resonance=ResonanceFactory(),
                ritual_components=[],
            )


class PlacesAndPerksFollowTheAlternateSelf(ResonanceCacheIsolationMixin, JourneyCase):
    """Resonance of place and the covenant affinity situation read the acting aura."""

    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        _true_aura(self.sheet)
        self.alt = AlternateSelfFactory(
            character=self.sheet, resonance=ResonanceFactory(affinity=self.abyssal)
        )

    def test_the_place_of_power_buff_follows_the_alternate_self(self) -> None:
        """Arriving in a Celestial place grants its alignment boon only to the mask."""
        room_profile = RoomProfileFactory()
        mod = tag_room_resonance(room_profile, ResonanceFactory(affinity=self.celestial))
        mod.value = 1
        mod.save(update_fields=["value"])
        interaction = AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )
        boon = ConditionTemplateFactory(name="Celestial Warmth")
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction, min_magnitude=1, condition_template=boon
        )
        # An Abyssal-dominant character has no authored reaction to a Celestial place.
        sheet = CharacterSheetFactory()
        _true_aura(sheet, celestial="20.00", abyssal="80.00")
        mask = AlternateSelfFactory(
            character=sheet, resonance=ResonanceFactory(affinity=self.celestial)
        )
        character = sheet.character
        character.db_location = room_profile.objectdb
        character.save(update_fields=["db_location"])

        def boons() -> int:
            return ConditionInstance.objects.filter(target=character, condition=boon).count()

        character.at_post_move(source_location=None)
        self.assertEqual(boons(), 0)
        _wear(sheet, mask)
        character.at_post_move(source_location=None)
        self.assertEqual(boons(), 1)

    def test_the_covenant_attacker_affinity_follows_the_alternate_self(self) -> None:
        opponent = CombatOpponentFactory(persona=self.persona)
        params = SituationParams(affinity=self.abyssal)
        ctx = SituationContext(
            holder=CharacterSheetFactory(),
            subject=CharacterSheetFactory(),
            target=None,
            resolution=None,
            attacker=opponent,
        )
        self.assertFalse(SITUATION_EVALUATORS[Situation.ATTACKER_AFFINITY](ctx, params))
        _wear(self.sheet, self.alt)
        self.assertTrue(SITUATION_EVALUATORS[Situation.ATTACKER_AFFINITY](ctx, params))


class AnAlternateSelfWithoutAResonance(JourneyCase):
    """Wearing it changes nothing about the aura she acts with."""

    def test_the_acting_aura_is_the_true_aura(self) -> None:
        celestial, _primal, abyssal = ensure_canonical_affinities()
        sheet = CharacterSheetFactory()
        _true_aura(sheet)
        _wear(sheet, AlternateSelfFactory(character=sheet, resonance=None))
        acting = acting_aura(sheet)
        self.assertFalse(acting.is_alternate_self)
        self.assertEqual(acting.percent_for(celestial), Decimal(80))
        self.assertEqual(acting.percent_for(abyssal), Decimal(20))
        self.assertEqual(acting.dominant_affinity, celestial)
