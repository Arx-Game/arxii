"""Drift holdings and the conversion offer a deed opens (#4733, slice 4 of #4672)."""

from evennia.utils.test_resources import EvenniaTestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    DramaticMomentTagFactory,
    ResonanceFactory,
    SceneEntryEndorsementFactory,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterResonance,
    DriftConversionCap,
    DriftConversionOffer,
    ResonanceGrant,
)
from world.magic.services.drift import (
    convertible_drift,
    drift_holdings,
    lapse_conversion_offers,
    open_or_extend_conversion_offer,
    own_affinity,
)
from world.magic.services.resonance import grant_resonance
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import get_active_scene, invalidate_active_scene_cache


def _hold(sheet, resonance, balance, lifetime=None):
    return CharacterResonance.objects.create(
        character_sheet=sheet,
        resonance=resonance,
        balance=balance,
        lifetime_earned=balance if lifetime is None else lifetime,
    )


def _author_pair(source, target, multiplier, conversion_type):
    pair = AffinityInteraction.objects.get(source_affinity=source, environment_affinity=target)
    pair.conversion_multiplier = multiplier
    pair.conversion_type = conversion_type
    pair.save(update_fields=["conversion_multiplier", "conversion_type"])
    AffinityInteraction.objects.clear_cache()


class DriftOfferTestBase(EvenniaTestCase):
    """A Celestial character holding Abyssal resonance, standing in a live scene."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        self.dawnlight = ResonanceFactory(name="Drift Dawnlight", affinity=self.celestial)
        self.sunrise = ResonanceFactory(name="Drift Sunrise", affinity=self.celestial)
        self.dread = ResonanceFactory(name="Drift Dread", affinity=self.abyssal)
        self.wild = ResonanceFactory(name="Drift Wild", affinity=self.primal)
        self.room = ObjectDBFactory(
            db_key="DriftOfferRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.scene = SceneFactory(room=self.room)
        invalidate_active_scene_cache(self.room)
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="80", primal="10", abyssal="10")
        # grant_resonance recomputes the aura from lifetime earned, so the Celestial
        # history is real: a long Celestial record that the Abyssal holding does not outweigh.
        _hold(self.sheet, self.dawnlight, 0, lifetime=500)
        _hold(self.sheet, self.dread, 30)

    def deed(self, resonance=None, amount=20):
        return grant_resonance(
            self.sheet,
            resonance or self.dawnlight,
            amount,
            source=GainSource.DRAMATIC_MOMENT,
            dramatic_moment=DramaticMomentTagFactory(character_sheet=self.sheet),
        )


class OpenOfferTests(DriftOfferTestBase):
    def test_deed_grant_with_drift_opens_one_offer_with_cap(self) -> None:
        self.deed()
        offer = DriftConversionOffer.objects.get()
        self.assertEqual((offer.character_sheet, offer.scene), (self.sheet, self.scene))
        cap = DriftConversionCap.objects.get()
        self.assertEqual((cap.offer, cap.target_resonance, cap.cap), (offer, self.dawnlight, 10))
        self.assertEqual(
            list(cap.grants.all()), [ResonanceGrant.objects.get(resonance=self.dawnlight)]
        )

    def test_grant_resonance_still_returns_the_character_resonance(self) -> None:
        self.assertIsInstance(self.deed(), CharacterResonance)

    def test_second_deed_in_scene_extends_same_offer(self) -> None:
        self.deed()
        self.deed()
        self.assertEqual(DriftConversionOffer.objects.count(), 1)
        cap = DriftConversionCap.objects.get()
        self.assertEqual(cap.cap, 20)
        self.assertIsInstance(cap.cap, int)
        self.assertEqual(cap.grants.count(), 2)

    def test_other_own_affinity_resonance_adds_a_cap_not_an_offer(self) -> None:
        self.deed()
        self.deed(self.sunrise, amount=10)
        self.assertEqual(DriftConversionOffer.objects.count(), 1)
        caps = {c.target_resonance_id: c.cap for c in DriftConversionCap.objects.all()}
        self.assertEqual(caps, {self.dawnlight.pk: 10, self.sunrise.pk: 5})

    def test_scene_entry_deed_opens_an_offer_too(self) -> None:
        endorsement = SceneEntryEndorsementFactory(
            endorsee_sheet=self.sheet, scene=self.scene, resonance=self.dawnlight
        )
        grant_resonance(
            self.sheet,
            self.dawnlight,
            12,
            source=GainSource.SCENE_ENTRY,
            scene_entry_endorsement=endorsement,
        )
        cap = DriftConversionCap.objects.get()
        self.assertEqual(
            (cap.offer.scene, cap.target_resonance, cap.cap), (self.scene, self.dawnlight, 6)
        )

    def test_finished_scene_still_cached_on_the_room_opens_nothing(self) -> None:
        self.assertEqual(get_active_scene(self.room), self.scene)
        self.scene.finish_scene()
        self.assertEqual(get_active_scene(self.room), self.scene)  # stale cache, not invalidated
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.dawnlight).exists())

    def test_tiny_grant_still_adds_at_least_one(self) -> None:
        self.deed(amount=1)
        self.assertEqual(DriftConversionCap.objects.get().cap, 1)

    def test_non_deed_source_opens_nothing(self) -> None:
        grant_resonance(self.sheet, self.dawnlight, 20, source=GainSource.STAFF_GRANT)
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.dawnlight).exists())

    def test_no_drift_opens_nothing(self) -> None:
        CharacterResonance.objects.filter(resonance=self.dread).delete()
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.dawnlight).exists())

    def test_drift_with_zero_balance_opens_nothing(self) -> None:
        row = CharacterResonance.objects.get(resonance=self.dread)
        row.balance = 0
        row.save(update_fields=["balance"])
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())

    def test_off_affinity_grant_opens_nothing(self) -> None:
        self.deed(self.wild)
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.wild).exists())

    def test_no_active_scene_opens_nothing(self) -> None:
        self.scene.finish_scene()
        invalidate_active_scene_cache(self.room)
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.dawnlight).exists())

    def test_no_location_opens_nothing(self) -> None:
        self.sheet.character.location = None
        self.sheet.character.save()
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())

    def test_no_aura_opens_nothing_and_does_not_raise(self) -> None:
        other = CharacterSheetFactory()
        other.character.location = self.room
        other.character.save()
        _hold(other, self.dread, 30)
        grant_resonance(
            other,
            self.dawnlight,
            20,
            source=GainSource.DRAMATIC_MOMENT,
            dramatic_moment=DramaticMomentTagFactory(character_sheet=other),
        )
        self.assertFalse(DriftConversionOffer.objects.filter(character_sheet=other).exists())

    def test_drift_without_authored_conversion_opens_nothing(self) -> None:
        _author_pair(self.abyssal, self.celestial, None, "")
        self.deed()
        self.assertFalse(DriftConversionOffer.objects.exists())
        self.assertTrue(ResonanceGrant.objects.filter(resonance=self.dawnlight).exists())


class HoldingsTests(DriftOfferTestBase):
    def test_own_affinity_is_none_without_aura(self) -> None:
        self.assertIsNone(own_affinity(CharacterSheetFactory()))

    def test_own_affinity_is_none_for_aura_without_shares(self) -> None:
        bare = CharacterSheetFactory()
        CharacterAuraFactory(character=bare, celestial=0, primal=0, abyssal=0)
        self.assertIsNone(own_affinity(bare))

    def test_own_affinity_is_the_dominant_one(self) -> None:
        self.assertEqual(own_affinity(self.sheet), self.celestial)

    def test_drift_holdings_orders_by_balance_and_skips_own_affinity(self) -> None:
        _hold(self.sheet, self.wild, 50)
        _hold(self.sheet, self.sunrise, 99)
        rows = drift_holdings(self.sheet)
        self.assertEqual([r.resonance for r in rows], [self.wild, self.dread])

    def test_drift_holdings_empty_without_aura(self) -> None:
        sheet = CharacterSheetFactory()
        _hold(sheet, self.dread, 5)
        self.assertEqual(drift_holdings(sheet), [])

    def test_convertible_drift_needs_a_pair_into_the_target_affinity(self) -> None:
        _hold(self.sheet, self.wild, 5)
        _author_pair(self.primal, self.celestial, None, "")
        rows = convertible_drift(self.sheet, self.dawnlight)
        self.assertEqual([r.resonance for r in rows], [self.dread])


class LapseTests(DriftOfferTestBase):
    def test_same_grant_twice_increments_the_cap_once(self) -> None:
        self.deed()
        grant = ResonanceGrant.objects.get(resonance=self.dawnlight)
        offer = open_or_extend_conversion_offer(grant)
        self.assertEqual(offer, DriftConversionOffer.objects.get())
        cap = DriftConversionCap.objects.get()
        self.assertEqual(cap.cap, 10)
        self.assertEqual(cap.grants.count(), 1)
        # The identity-mapped instance holds a plain int, not a pending expression.
        self.assertIsInstance(cap.cap, int)

    def test_lapse_conversion_offers_deletes_scene_offers(self) -> None:
        self.deed()
        other = DriftConversionOffer.objects.create(
            character_sheet=self.sheet, scene=SceneFactory()
        )
        self.assertEqual(lapse_conversion_offers(self.scene), 1)
        self.assertEqual(list(DriftConversionOffer.objects.all()), [other])
        self.assertFalse(DriftConversionCap.objects.exists())

    def test_finish_scene_directly_lapses_only_that_scenes_offers(self) -> None:
        # The event-completion route calls scene.finish_scene() without finish_scene_full.
        self.deed()
        other = DriftConversionOffer.objects.create(
            character_sheet=self.sheet, scene=SceneFactory()
        )
        self.scene.finish_scene()
        self.assertEqual(list(DriftConversionOffer.objects.all()), [other])

    def test_finish_scene_full_lapses_only_that_scenes_offers(self) -> None:
        from world.scenes.scene_admin_services import finish_scene_full

        self.deed()
        other = DriftConversionOffer.objects.create(
            character_sheet=self.sheet, scene=SceneFactory()
        )
        finish_scene_full(self.scene)
        self.assertEqual(list(DriftConversionOffer.objects.all()), [other])
