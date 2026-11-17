"""Sineating as a ritual (#5177): the plea, the roll, the corruption and the earnings.

Covers:
    1. SineatingPendingOffer uniqueness
    2. The plea: the tether's resonance, the per-scene cap, one performance per pair per scene
    3. The ritual with the spec's Trace 1 numbers worked out by hand (success and failure)
    4. Every refusal comes before anything is written
    5. Declining a plea
    6. The Sineater's waiting-pleas viewset
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import GainSource, TargetKind
from world.magic.exceptions import SineaterFallenError, SineatingValidationError
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    SineatingOutcomeAwardFactory,
    ThreadWeavingUnlockFactory,
    place_in_active_scene,
    wire_soul_tether_content,
    with_corruption_at_stage,
)
from world.magic.models import MireHolding, SineatingOutcomeAward, Thread
from world.magic.models.aura import CharacterResonance
from world.magic.models.soul_tether import Sineating, SineatingPendingOffer
from world.magic.services.sineating import (
    decline_sineating,
    perform_sineating,
    request_sineating,
    sineating_lines,
)
from world.magic.services.soul_tether import accept_soul_tether, get_soul_tether_config
from world.magic.types.soul_tether import SoulTetherRole as SoulTetherRoleEnum
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTypeFactory,
)
from world.relationships.models import CharacterRelationship
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory
from world.seeds.modifier_values import seed_pool_and_cap_lanes
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

# =============================================================================
# Shared helpers
# =============================================================================


def _set_primary_affinity_abyssal(sheet: object) -> None:
    """Set the character's aura so Abyssal is the dominant affinity."""
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
    """Set the character's aura so Primal is the dominant affinity."""
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
    """Give the character a RELATIONSHIP_TRACK CharacterThreadWeavingUnlock."""
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_type=track,
        unlock_trait=None,
    )
    CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_tethered_pair_with_tenures(track=None):
    """Return (sinner_tenure, sineater_tenure, resonance) with an active Soul Tether.

    Both sides have RosterTenure rows (and thus AccountDB) for scene participation
    and viewset auth tests.
    """
    wire_soul_tether_content()
    if track is None:
        track = RelationshipTypeFactory()
    abyssal_affinity = AffinityFactory(name="Abyssal")
    resonance = ResonanceFactory(affinity=abyssal_affinity)

    sinner_tenure = RosterTenureFactory()
    sineater_tenure = RosterTenureFactory()
    sinner_sheet = sinner_tenure.roster_entry.character_sheet
    sineater_sheet = sineater_tenure.roster_entry.character_sheet

    _set_primary_affinity_abyssal(sinner_sheet)
    _set_primary_affinity_primal(sineater_sheet)
    _grant_relationship_track_unlock(sinner_sheet, track)

    CharacterRelationshipFactory(source=sinner_sheet, target=sineater_sheet)
    CharacterRelationshipFactory(source=sineater_sheet, target=sinner_sheet)

    accept_soul_tether(
        initiator_sheet=sinner_sheet,
        partner_sheet=sineater_sheet,
        sinner_role=SoulTetherRoleEnum.SINNER,
        resonance=resonance,
        ritual_components=[],
    )

    # Seed the Sinner's CharacterResonance so the resonance gate passes.
    CharacterResonanceFactory(character_sheet=sinner_sheet, resonance=resonance)

    return sinner_tenure, sineater_tenure, resonance


def _sinner_thread(sinner_sheet, resonance) -> Thread:
    return Thread.objects.get(
        owner=sinner_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        resonance=resonance,
        retired_at__isnull=True,
    )


class SineatingCase(TestCase):
    """A tethered pair standing in a live scene, Sineating set up the way staff would.

    The Sinner carries 500 corruption in the tether's resonance (stage 3, where the starting
    values are 50, 200, 500). The Sineater has no resistance yet and holds a Primal thread.
    A success earns a full share, a failure a quarter, a critical failure nothing.
    """

    def setUp(self) -> None:
        super().setUp()
        seed_pool_and_cap_lanes()
        sinner_tenure, sineater_tenure, self.resonance = _make_tethered_pair_with_tenures()
        self.sinner = sinner_tenure.roster_entry.character_sheet
        self.sineater = sineater_tenure.roster_entry.character_sheet
        self.primal = ResonanceFactory(affinity=AffinityFactory(name="Primal"))
        CharacterResonanceFactory(character_sheet=self.sineater, resonance=self.primal)
        from world.magic.services.soul_tether import ensure_sineater_thread

        ensure_sineater_thread(self.sineater, self.sinner, resonance=self.primal)
        # Level 30 is rung 3: a Hollow that holds 30 and a scene cap of 11.
        thread = _sinner_thread(self.sinner, self.resonance)
        thread.level = 30
        thread.save(update_fields=["level"])
        with_corruption_at_stage(self.sinner, self.resonance, stage=3)
        self.scene = place_in_active_scene(self.sinner, self.sineater)

        cfg = get_soul_tether_config()
        cfg.sineating_check_type = CheckTypeFactory()
        cfg.save()
        self.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        for name, share in (
            ("Critical Success", "1.50"),
            ("Success", "1.00"),
            ("Partial Success", "0.50"),
            ("Failure", "0.25"),
            ("Critical Failure", "0.00"),
        ):
            SineatingOutcomeAwardFactory(
                outcome_tier=self.outcomes[name], earned_share=Decimal(share)
            )

    def corruption(self, sheet) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=sheet, resonance=self.resonance
        ).first()
        return row.corruption_current if row is not None else 0

    def balance(self, sheet, resonance) -> int:
        row = CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).first()
        return row.balance if row is not None else 0

    def perform(self, units: int, tier: str = "Success"):
        with force_check_outcome(self.outcomes[tier]):
            return perform_sineating(self.sinner, self.sineater, units)


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineatingPleaTests(SineatingCase):
    def test_the_plea_takes_the_tethers_resonance_and_replaces_a_waiting_one(self) -> None:
        offer = request_sineating(self.sinner, self.sineater, 2)
        self.assertEqual((offer.resonance, offer.max_units_offered), (self.resonance, 2))
        # The scene's cap at rung 3 is 11, so a bigger ask is clamped to it.
        offer = request_sineating(self.sinner, self.sineater, 9999)
        self.assertEqual(offer.max_units_offered, 11)
        plea = SineatingPendingOffer.objects.get(sinner_sheet=self.sinner)
        self.assertEqual((plea.units_offered, plea.scene_id), (11, self.scene.pk))

    def test_a_pair_that_already_performed_in_this_scene_cannot_plead_again(self) -> None:
        request_sineating(self.sinner, self.sineater, 2)
        self.perform(2)
        with self.assertRaises(SineatingValidationError) as ctx:
            request_sineating(self.sinner, self.sineater, 2)
        name = self.sineater.primary_persona.name
        self.assertEqual(
            ctx.exception.user_message,
            f"You have already performed Sineating with {name} in this scene.",
        )


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineatingRitualTests(SineatingCase):
    def test_a_success_moves_corruption_refills_the_hollow_and_pays_each_their_own_thread(
        self,
    ) -> None:
        request_sineating(self.sinner, self.sineater, 2)

        result = self.perform(2, "Success")

        # 2 units x 60 corruption: 120 leaves the Sinner, and with no resistance 120 arrive.
        self.assertEqual(self.corruption(self.sinner), 380)
        self.assertEqual(self.corruption(self.sineater), 120)
        self.assertEqual(MireHolding.objects.get(relationship__source=self.sineater).amount, 120)
        self.assertEqual(_sinner_thread(self.sinner, self.resonance).hollow_current, 2)
        # 2 units x 5 resonance x a full share: 10 each, in the resonance of their own thread.
        self.assertEqual(self.balance(self.sinner, self.resonance), 10)
        self.assertEqual(self.balance(self.sineater, self.primal), 10)
        self.assertEqual(self.balance(self.sineater, self.resonance), 0)
        self.assertEqual(
            (result.corruption_left_sinner, result.corruption_taken, result.outcome_name),
            (120, 120, "Success"),
        )
        audit = Sineating.objects.get()
        self.assertEqual(
            (
                audit.units_accepted,
                audit.corruption_moved,
                audit.corruption_taken,
                audit.sinner_resonance_earned,
                audit.sineater_resonance_earned,
            ),
            (2, 120, 120, 10, 10),
        )
        self.assertEqual(audit.outcome, self.outcomes["Success"])
        self.assertFalse(SineatingPendingOffer.objects.exists())
        lines = sineating_lines(result)
        self.assertIn("your corruption in", lines.sinner[0])
        self.assertIn("falls by 120", lines.sinner[0])
        self.assertIn("You take 120", lines.sineater[0])
        self.assertIn(f"Your {self.primal.name} grows by 10", lines.sineater[0])

    def test_a_failure_moves_the_same_corruption_but_earns_a_quarter_share(self) -> None:
        request_sineating(self.sinner, self.sineater, 2)

        self.perform(2, "Failure")

        self.assertEqual(self.corruption(self.sinner), 380)
        self.assertEqual(self.corruption(self.sineater), 120)
        # 2 x 5 x 0.25 = 2.5, which floors to 2 each.
        self.assertEqual(self.balance(self.sinner, self.resonance), 2)
        self.assertEqual(self.balance(self.sineater, self.primal), 2)

    def test_the_sineater_takes_on_fewer_units_than_offered_and_never_more(self) -> None:
        request_sineating(self.sinner, self.sineater, 4)

        result = self.perform(99, "Success")

        self.assertEqual(result.units_accepted, 4)
        self.assertEqual(self.corruption(self.sinner), 500 - 4 * 60)

    def test_the_sinner_never_sheds_more_than_they_carry(self) -> None:
        row = CharacterResonance.objects.get(character_sheet=self.sinner, resonance=self.resonance)
        row.corruption_current = 70
        row.save(update_fields=["corruption_current"])
        request_sineating(self.sinner, self.sineater, 2)

        result = self.perform(2, "Success")

        self.assertEqual((self.corruption(self.sinner), result.corruption_left_sinner), (0, 70))

    def test_every_refusal_comes_before_anything_is_written(self) -> None:
        def assert_untouched(refusal: str) -> None:
            self.assertEqual(self.corruption(self.sinner), 500, refusal)
            self.assertFalse(Sineating.objects.exists(), refusal)
            self.assertEqual(self.balance(self.sinner, self.resonance), 0, refusal)

        # No plea is waiting.
        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)
        self.assertEqual(ctx.exception.user_message, "No pending Sineating offer found.")
        assert_untouched("no plea")

        # Sineating is not set up: no check type.
        request_sineating(self.sinner, self.sineater, 2)
        cfg = get_soul_tether_config()
        cfg.sineating_check_type = None
        cfg.save()
        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)
        self.assertEqual(ctx.exception.user_message, "Sineating has not been set up yet.")
        assert_untouched("no check type")
        cfg.sineating_check_type = CheckTypeFactory()
        cfg.save()

        # Sineating is not set up: an outcome tier has no award.
        SineatingOutcomeAward.objects.filter(outcome_tier=self.outcomes["Failure"]).delete()
        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)
        self.assertEqual(ctx.exception.user_message, "Sineating has not been set up yet.")
        assert_untouched("a tier with no award")
        SineatingOutcomeAwardFactory(
            outcome_tier=self.outcomes["Failure"], earned_share=Decimal("0.25")
        )

        # The Sineater has fallen: an Abyssal aura.
        _set_primary_affinity_abyssal(self.sineater)
        with self.assertRaises(SineaterFallenError):
            self.perform(2)
        assert_untouched("a fallen Sineater")
        _set_primary_affinity_primal(self.sineater)

        # The pair have left the scene the plea was made in: the plea is cleared.
        place_in_active_scene(self.sineater)
        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)
        self.assertIn("no longer in the same scene", ctx.exception.user_message)
        self.assertFalse(SineatingPendingOffer.objects.exists())
        assert_untouched("a stale plea")

    def test_a_second_performance_in_the_same_scene_is_refused(self) -> None:
        request_sineating(self.sinner, self.sineater, 2)
        self.perform(2)
        # A plea written some other way (the Sinner's second ask is refused) cannot be performed.
        SineatingPendingOffer.objects.create(
            sinner_sheet=self.sinner,
            sineater_sheet=self.sineater,
            relationship=CharacterRelationship.objects.get(
                source=self.sinner, target=self.sineater
            ),
            scene=self.scene,
            resonance=self.resonance,
            units_offered=2,
        )
        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)
        self.assertIn("already performed Sineating with", ctx.exception.user_message)
        self.assertEqual(self.corruption(self.sinner), 380)

    def test_declining_removes_the_plea_and_keeps_a_declined_row(self) -> None:
        request_sineating(self.sinner, self.sineater, 3)

        row = decline_sineating(self.sinner, self.sineater)

        self.assertEqual((row.units_accepted, row.units_offered), (0, 3))
        self.assertFalse(SineatingPendingOffer.objects.exists())
        self.assertEqual(self.corruption(self.sinner), 500)
        # A declined plea does not count as a performance: they may plead again.
        request_sineating(self.sinner, self.sineater, 3)

    def test_the_gain_source_is_sineating(self) -> None:
        request_sineating(self.sinner, self.sineater, 2)
        self.perform(2)
        from world.magic.models import ResonanceGrant

        sources = set(ResonanceGrant.objects.values_list("source", flat=True))
        self.assertEqual(sources, {GainSource.SINEATING})


# =============================================================================
# The Sineater's waiting-pleas viewset
# =============================================================================


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineatingPendingOfferViewSetTests(APITestCase):
    """GET /api/magic/soul-tether/sineating/pending/ is scoped to the caller as Sineater."""

    @classmethod
    def setUpTestData(cls) -> None:
        sinner_tenure_a, sineater_tenure_a, cls.resonance_a = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_a = sinner_tenure_a.roster_entry.character_sheet
        cls.sineater_sheet_a = sineater_tenure_a.roster_entry.character_sheet
        cls.sineater_account_a = sineater_tenure_a.player_data.account
        sinner_tenure_b, sineater_tenure_b, cls.resonance_b = _make_tethered_pair_with_tenures()
        cls.sinner_sheet_b = sinner_tenure_b.roster_entry.character_sheet
        cls.sineater_sheet_b = sineater_tenure_b.roster_entry.character_sheet
        cls.scene = SceneFactory()

    def _seed(self, sinner, sineater, resonance) -> SineatingPendingOffer:
        return SineatingPendingOffer.objects.create(
            sinner_sheet=sinner,
            sineater_sheet=sineater,
            relationship=CharacterRelationship.objects.get(source=sinner, target=sineater),
            scene=self.scene,
            resonance=resonance,
            units_offered=4,
        )

    def test_a_sineater_sees_only_their_own_pleas_with_what_the_row_needs(self) -> None:
        offer_a = self._seed(self.sinner_sheet_a, self.sineater_sheet_a, self.resonance_a)
        self._seed(self.sinner_sheet_b, self.sineater_sheet_b, self.resonance_b)
        self.client.force_authenticate(user=self.sineater_account_a)

        response = self.client.get("/api/magic/soul-tether/sineating/pending/")

        self.assertEqual(response.status_code, 200, response.content)
        (row,) = response.data["results"]
        self.assertEqual(row["id"], offer_a.pk)
        self.assertEqual(row["sinner_sheet_id"], self.sinner_sheet_a.pk)
        self.assertEqual(row["units_offered"], 4)
        self.assertEqual(row["resonance_name"], self.resonance_a.name)
        self.assertNotIn("anima_cost_per_unit", row)

    def test_unauthenticated_request_rejected(self) -> None:
        response = self.client.get("/api/magic/soul-tether/sineating/pending/")
        self.assertIn(response.status_code, (401, 403))


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineatingPendingOfferUniquenessTests(TestCase):
    """SineatingPendingOffer.one_pending_sineating_per_pair constraint."""

    def test_duplicate_pair_raises_integrity_error(self) -> None:
        from django.db import IntegrityError

        sinner_tenure, sineater_tenure, resonance = _make_tethered_pair_with_tenures()
        sinner = sinner_tenure.roster_entry.character_sheet
        sineater = sineater_tenure.roster_entry.character_sheet
        rel = CharacterRelationship.objects.get(source=sinner, target=sineater)
        scene = SceneFactory()
        fields = {
            "sinner_sheet": sinner,
            "sineater_sheet": sineater,
            "relationship": rel,
            "scene": scene,
            "resonance": resonance,
        }
        SineatingPendingOffer.objects.create(units_offered=5, **fields)
        with self.assertRaises(IntegrityError):
            SineatingPendingOffer.objects.create(units_offered=3, **fields)
