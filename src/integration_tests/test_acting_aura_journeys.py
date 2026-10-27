"""Journeys for the aura a character ACTS with while wearing an alternate self (#4731).

Ysmay's true aura is Celestial 80 / Abyssal 20; she can shift into "the Ashen Ysmay",
an alternate self whose resonance is Abyssal. She shifts by typing ``form shift``.
What she casts and what a place of power reads follow the alternate self (100%
Abyssal); who she IS (Fall threshold, Soul Tether gate, the sheet's aura display)
keeps reading the true aura. Her own gift's techniques work in the affinity she acts
with, as her techniques' variants already do, so a Celestial gift cast in the Abyssal
self keeps the full alignment term. An alternate self with no resonance changes
nothing.

Expected numbers come from the ruled split and the affinity-alignment bonus of 100:
bonus x percent / 100. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatOpponentFactory
from world.conditions.capability_content import AT_WILL_SHIFTING
from world.conditions.factories import CapabilityTypeFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.covenants.perks.constants import Situation
from world.covenants.perks.context import SituationContext, SituationParams
from world.covenants.perks.evaluators import SITUATION_EVALUATORS
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, FormType
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
    RitualExecutionKind,
)
from world.magic.factories import (
    AffinityInteractionFactory,
    AuraPowerConfigFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    RitualFactory,
    ensure_canonical_affinities,
    ensure_conversion_pairs,
)
from world.magic.models import Affinity, FallRedemptionRecord
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.services.acting_aura import acting_aura
from world.magic.services.gain import tag_room_resonance
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.mechanics.factories import ModifierCategoryFactory, ModifierSourceFactory
from world.mechanics.models import CharacterModifier, ModifierTarget
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique, make_benign_castable_technique
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

ALIGNMENT_BONUS = 100
ASHEN = "the Ashen Ysmay"
_FALL_PATH = "world.magic.services.fall_redemption.perform_fall"


def _true_aura(
    sheet, *, celestial: str = "80.00", primal: str = "0.00", abyssal: str = "20.00"
) -> None:
    """Celestial 80 / Abyssal 20 unless told otherwise."""
    CharacterAuraFactory(
        character=sheet,
        celestial=Decimal(celestial),
        primal=Decimal(primal),
        abyssal=Decimal(abyssal),
    )


class _AShifter(ResonanceCacheIsolationMixin, JourneyCase):
    """A played character who may shift at will into an alternate self."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.room = self.make_room("The Lantern")

    def make_shifter(self, name: str, *, room, mask_affinity, **aura) -> tuple:
        """A player with the true aura, a true form, the at-will shift capability and
        one alternate self, ``ASHEN``, resonant with ``mask_affinity``."""
        character = self.make_player(name, room=room)
        sheet = character.sheet_data
        _true_aura(sheet, **aura)
        true_form = CharacterFormFactory(character=sheet, name="True", form_type=FormType.TRUE)
        CharacterFormStateFactory(character=sheet, active_form=true_form)
        capability = CapabilityTypeFactory(name=AT_WILL_SHIFTING, innate_baseline=0)
        target = ModifierTarget.objects.get_or_create(
            name=f"capability_{capability.pk}",
            defaults={
                "category": ModifierCategoryFactory(name="capability"),
                "target_capability": capability,
            },
        )[0]
        CharacterModifier.objects.create(
            character=sheet, target=target, source=ModifierSourceFactory(), value=1
        )
        alt = AlternateSelfFactory(
            character=sheet,
            display_name=ASHEN,
            resonance=ResonanceFactory(affinity=mask_affinity),
        )
        return character, sheet, alt

    def shift(self, character) -> None:
        self.assertIn(f"You assume {ASHEN}.", self.telnet(character, f"form shift {ASHEN}"))

    def revert(self, character) -> None:
        self.assertIn("You revert to your true self.", self.telnet(character, "form revert"))


class AlignmentFollowsTheAlternateSelfOnACast(_AShifter):
    """She casts through the web cast endpoint, as herself and as the Ashen Ysmay."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.ysmay, self.sheet, self.alt = self.make_shifter(
            "Ysmay", room=self.room, mask_affinity=self.abyssal
        )
        self.scene = SceneFactory(room=self.room)
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        AuraPowerConfigFactory(affinity_alignment_bonus=ALIGNMENT_BONUS)
        # Kudos accrual reads game-week rows this journey does not build.
        accrue = patch("world.scenes.action_services.accrue")
        accrue.start()
        self.addCleanup(accrue.stop)

    def technique_of(self, affinity):
        """A benign technique of a gift whose one resonance has ``affinity``."""
        gift = GiftFactory()
        gift.resonances.add(ResonanceFactory(affinity=affinity))
        technique = make_benign_castable_technique()
        technique.gift = gift
        technique.save()
        grant_technique(self.sheet.primary_persona, technique)
        return technique

    def alignment_term(self, technique) -> int:
        """The "aura power" line of the power ledger the cast endpoint returns."""
        response = self.api(self.account_of(self.ysmay)).post(
            reverse("sceneactionrequest-cast"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.sheet.primary_persona.pk,
                "technique_id": technique.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        entries = [
            entry
            for entry in response.json()["result"]["power_ledger"]["entries"]
            if entry["source_label"] == "aura power"
        ]
        self.assertEqual(len(entries), 1, response.content)
        return entries[0]["amount"]

    def test_an_abyssal_cast_reads_the_alternate_selfs_aura_while_worn(self) -> None:
        technique = self.technique_of(self.abyssal)
        self.assertEqual(self.alignment_term(technique), 20)  # true aura: 20% Abyssal
        self.shift(self.ysmay)
        self.assertEqual(self.alignment_term(technique), 100)  # the Ashen Ysmay: 100%
        self.revert(self.ysmay)
        self.assertEqual(self.alignment_term(technique), 20)

    def test_her_own_celestial_gift_cast_in_the_abyssal_self_keeps_full_alignment(self) -> None:
        """The worn self's resonance replaces the gift's, as it does for variants."""
        technique = self.technique_of(self.celestial)
        self.assertEqual(self.alignment_term(technique), 80)  # true aura: 80% Celestial
        self.shift(self.ysmay)
        self.assertEqual(self.alignment_term(technique), 100)  # works in Abyssal, 100%


class TheTrueAuraStillAnswersWhoSheIs(_AShifter):
    """Fall threshold, the sheet's aura display and the Soul Tether gate ignore the mask."""

    def setUp(self) -> None:
        super().setUp()
        ensure_conversion_pairs()
        RitualFactory(
            name="Ritual of Falling",
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path=_FALL_PATH,
        )
        self.ysmay, self.sheet, self.alt = self.make_shifter(
            "Ysmay", room=self.room, mask_affinity=self.abyssal
        )
        self.shift(self.ysmay)

    def test_the_fall_threshold_reads_the_true_aura(self) -> None:
        told = self.telnet(
            self.ysmay, f"ritual Ritual of Falling target_affinity={self.abyssal.pk}"
        )
        self.assertIn("only 20", told)
        self.assertFalse(FallRedemptionRecord.objects.filter(character_sheet=self.sheet).exists())

    def test_the_sheet_display_shows_the_true_aura(self) -> None:
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/magic/character-auras/?character={self.sheet.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        payload = response.json()[0]
        self.assertEqual(payload["dominant_affinity"], "Celestial")
        shares = {row["affinity_name"]: Decimal(row["percent"]) for row in payload["shares"]}
        self.assertEqual(shares, {"Celestial": Decimal(80), "Abyssal": Decimal(20)})

    def test_the_soul_tether_gate_still_sees_a_celestial_sinner(self) -> None:
        sineater = CharacterSheetFactory()
        _true_aura(sineater, celestial="0.00", primal="80.00", abyssal="20.00")
        response = self.api(self.account_of(self.ysmay)).post(
            "/api/magic/soul-tether/accept/",
            {
                "actor_sheet_id": self.sheet.pk,
                "partner_sheet_id": sineater.pk,
                "sinner_role": "SINNER",
                "resonance_id": ResonanceFactory().pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("Sinner cannot be Celestial-affinity primary.", response.content.decode())


class APlaceOfPowerFollowsTheAlternateSelf(_AShifter):
    """Walking into a Celestial place grants its alignment boon only to the mask."""

    def setUp(self) -> None:
        super().setUp()
        self.shrine = self.make_room("The Bright Shrine")
        for name, here, there in (("in", self.room, self.shrine), ("out", self.shrine, self.room)):
            exit_obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.exits.Exit")
            exit_obj.location = here
            exit_obj.destination = there
            exit_obj.save()
        mod = tag_room_resonance(
            RoomProfileFactory(objectdb=self.shrine), ResonanceFactory(affinity=self.celestial)
        )
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
        self.boon = ConditionTemplateFactory(name="Celestial Warmth")
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction, min_magnitude=1, condition_template=self.boon
        )
        # Abyssal-dominant: a Celestial place has no authored reaction to her own aura.
        self.hobb, self.sheet, _alt = self.make_shifter(
            "Hobb", room=self.room, mask_affinity=self.celestial, celestial="20.00", abyssal="80.00"
        )

    def warmed(self) -> bool:
        return ConditionInstance.objects.filter(target=self.hobb, condition=self.boon).exists()

    def walk(self, exit_name: str, *, to) -> None:
        self.telnet(self.hobb, exit_name)
        self.assertEqual(self.hobb.location, to)

    def test_only_the_celestial_mask_is_warmed_by_the_shrine(self) -> None:
        """A walk through an exit tells a telnet player no text (the room reaches the
        web client as state) and the boon carries no message of its own, so the
        journey asserts where she stands and what she holds."""
        self.walk("in", to=self.shrine)
        self.assertFalse(self.warmed())

        self.walk("out", to=self.room)
        self.shift(self.hobb)
        self.walk("in", to=self.shrine)
        self.assertTrue(self.warmed())


class TheCovenantAttackerAffinityFollowsTheAlternateSelf(_AShifter):
    """A unit on the registered ATTACKER_AFFINITY evaluator: the only journey to it is a
    full combat round with a covenant perk holder, which buries the one read under test."""

    def test_the_evaluator_reads_the_attackers_acting_aura(self) -> None:
        ysmay, sheet, _alt = self.make_shifter("Ysmay", room=self.room, mask_affinity=self.abyssal)
        opponent = CombatOpponentFactory(persona=sheet.primary_persona)
        params = SituationParams(affinity=self.abyssal)
        ctx = SituationContext(
            holder=CharacterSheetFactory(),
            subject=CharacterSheetFactory(),
            target=None,
            resolution=None,
            attacker=opponent,
        )
        self.assertFalse(SITUATION_EVALUATORS[Situation.ATTACKER_AFFINITY](ctx, params))
        self.shift(ysmay)
        self.assertTrue(SITUATION_EVALUATORS[Situation.ATTACKER_AFFINITY](ctx, params))


class AnAlternateSelfWithoutAResonance(JourneyCase):
    """A unit on ``acting_aura``: every reader of it is covered by a journey above, and a
    resonance-less self only shows there as the absence of a change."""

    def test_the_acting_aura_is_the_true_aura(self) -> None:
        celestial, _primal, abyssal = ensure_canonical_affinities()
        sheet = CharacterSheetFactory()
        _true_aura(sheet)
        ActiveAlternateSelf.objects.create(
            character=sheet, alternate_self=AlternateSelfFactory(character=sheet, resonance=None)
        )
        acting = acting_aura(sheet)
        self.assertFalse(acting.is_alternate_self)
        self.assertEqual(acting.percent_for(celestial), Decimal(80))
        self.assertEqual(acting.percent_for(abyssal), Decimal(20))
        self.assertEqual(acting.dominant_affinity, celestial)
