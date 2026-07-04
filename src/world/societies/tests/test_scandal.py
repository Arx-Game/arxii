"""The #1464 birth fork: scandal judgment, containment, contained Secrets, fame reach.

Threshold/difficulty magnitudes mirror the PLACEHOLDER constants — data, not a
design promise. Containment outcomes are forced via the checks test helper.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.scenes.factories import SceneFactory
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret
from world.societies.constants import FameTier
from world.societies.factories import PhilosophicalArchetypeFactory, SocietyFactory
from world.societies.models import SocietyReputation
from world.societies.scandal import scandalous_societies
from world.societies.services import create_solo_deed
from world.traits.factories import CheckOutcomeFactory


class ScandalForkTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory()
        # mercy=5 × archetype mercy_delta=-2 → dot -10 (== SCANDAL_THRESHOLD).
        cls.prudish = SocietyFactory(realm=cls.realm, mercy=5)
        cls.jaded = SocietyFactory(realm=cls.realm, mercy=0)
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, realm=cls.realm)
        cls.vile = PhilosophicalArchetypeFactory(name="Vile Conduct", mercy_delta=-2)
        cls.noble = PhilosophicalArchetypeFactory(name="Noble Conduct", mercy_delta=2)
        CheckTypeFactory(name="Con")
        CheckTypeFactory(name="Intimidation")

    def _scene(self, *, public: bool):
        profile = RoomProfileFactory(area=self.kingdom, is_public=public)
        return SceneFactory(location=profile.objectdb)

    def _mint(self, scene, archetypes, **kwargs):
        from world.societies.factories import LegendSourceTypeFactory

        return create_solo_deed(
            kwargs.pop("persona", None) or self._persona(),
            "PLACEHOLDER: the deed in question",
            LegendSourceTypeFactory(),
            10,
            scene=scene,
            archetypes=archetypes,
        )

    def _persona(self, fame_tier: str = FameTier.NORMAL):
        from world.character_sheets.factories import CharacterSheetFactory

        persona = CharacterSheetFactory().primary_persona
        if fame_tier != FameTier.NORMAL:
            persona.fame_tier = fame_tier
            persona.save(update_fields=["fame_tier"])
        return persona

    def test_judgment_thresholds(self):
        dots = scandalous_societies([self.vile], [self.prudish, self.jaded])
        self.assertEqual(set(dots), {self.prudish.pk})
        self.assertEqual(scandalous_societies([self.noble], [self.prudish, self.jaded]), {})

    def test_private_scandal_mints_contained_secret(self):
        scene = self._scene(public=False)
        entry = self._mint(scene, [self.vile])
        secret = Secret.objects.get(legend_deed=entry)
        self.assertEqual(secret.provenance, SecretProvenance.ACTION_ANCHORED)
        self.assertEqual(secret.subject_sheet_id, entry.persona.character_sheet_id)
        self.assertEqual(secret.scene_id, scene.pk)
        self.assertEqual({a.pk for a in secret.archetypes.all()}, {self.vile.pk})
        self.assertEqual(entry.societies_aware.count(), 0)
        self.assertEqual(secret.societies_exposed.count(), 0)

    def test_private_unremarkable_mints_nothing(self):
        entry = self._mint(self._scene(public=False), [self.noble])
        self.assertFalse(Secret.objects.filter(legend_deed=entry).exists())
        self.assertEqual(entry.societies_aware.count(), 0)

    def test_public_news_goes_aware_with_reputation(self):
        persona = self._persona()
        entry = self._mint(self._scene(public=True), [self.noble], persona=persona)
        self.assertEqual(set(entry.societies_aware.all()), {self.prudish, self.jaded})
        rep = SocietyReputation.objects.get(persona=persona, society=self.prudish)
        self.assertGreater(rep.value, 0)
        self.assertFalse(Secret.objects.filter(legend_deed=entry).exists())

    def test_public_scandal_contained_on_success(self):
        outcome = CheckOutcomeFactory(name="contain_win", success_level=1)
        with force_check_outcome(outcome):
            entry = self._mint(self._scene(public=True), [self.vile])
        self.assertTrue(Secret.objects.filter(legend_deed=entry).exists())
        self.assertEqual(entry.societies_aware.count(), 0)

    def test_public_scandal_leaks_on_failure(self):
        persona = self._persona()
        outcome = CheckOutcomeFactory(name="contain_lose", success_level=0)
        with force_check_outcome(outcome):
            entry = self._mint(self._scene(public=True), [self.vile], persona=persona)
        self.assertEqual(set(entry.societies_aware.all()), {self.prudish, self.jaded})
        self.assertFalse(Secret.objects.filter(legend_deed=entry).exists())
        rep = SocietyReputation.objects.get(persona=persona, society=self.prudish)
        self.assertLess(rep.value, 0)

    def test_untagged_deed_is_legacy_noop(self):
        entry = self._mint(self._scene(public=True), None)
        self.assertEqual(entry.societies_aware.count(), 0)
        self.assertFalse(Secret.objects.filter(legend_deed=entry).exists())

    def test_fame_scales_spread_multiplier(self):
        famous = self._persona(fame_tier=FameTier.CELEBRITY)
        entry = self._mint(self._scene(public=True), [self.noble], persona=famous)
        entry.refresh_from_db()
        # default multiplier 9 × celebrity factor 3 (PLACEHOLDER map).
        self.assertEqual(entry.spread_multiplier, 27)


class HouseholdContainmentTests(ScandalForkTestCase):
    """Own-household witnesses route containment through Household Command."""

    def test_household_witnesses_use_command_check(self):
        from unittest.mock import patch

        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        CheckTypeFactory(name="Household Command")
        persona = self._persona()
        house = OrganizationFactory(name="House Hushly")
        OrganizationMembershipFactory(persona=persona, organization=house, rank=1)
        witness = self._persona()
        OrganizationMembershipFactory(persona=witness, organization=house, rank=3)

        captured = {}
        from world.checks import services as check_services

        real_perform = check_services.perform_check

        def spy(character, check_type, **kwargs):
            captured["check"] = check_type.name
            return real_perform(character, check_type, **kwargs)

        outcome = CheckOutcomeFactory(name="hh_contain", success_level=1)
        scene = self._scene(public=True)
        # Force the witness list: patch scene_witness_personas to our pair.
        with (
            patch(
                "world.societies.knowledge_services.scene_witness_personas",
                return_value=[witness],
            ),
            patch("world.checks.services.perform_check", side_effect=spy),
            force_check_outcome(outcome),
        ):
            entry = self._mint(scene, [self.vile], persona=persona)
        self.assertEqual(captured.get("check"), "Household Command")
        self.assertTrue(Secret.objects.filter(legend_deed=entry).exists())


class WitnessApproachTests(ScandalForkTestCase):
    """#1824 — the declared capability list replaces the auto-pick."""

    def _mint_with_approach(self, approach_key, *, persona=None, success_level=1):
        from unittest.mock import patch

        from world.societies.factories import LegendSourceTypeFactory

        persona = persona or self._persona()
        captured = {}
        from world.checks import services as check_services

        real_perform = check_services.perform_check

        def spy(character, check_type, **kwargs):
            captured["check"] = check_type.name
            return real_perform(character, check_type, **kwargs)

        outcome = CheckOutcomeFactory(name=f"wa_{approach_key}", success_level=success_level)
        with (
            patch("world.checks.services.perform_check", side_effect=spy),
            force_check_outcome(outcome),
        ):
            entry = create_solo_deed(
                persona,
                "PLACEHOLDER: the deed in question",
                LegendSourceTypeFactory(),
                10,
                scene=self._scene(public=True),
                archetypes=[self.vile],
                containment_approach=approach_key,
            )
        return entry, captured

    def test_declared_intimidation_uses_intimidation(self):
        _, captured = self._mint_with_approach("intimidation")
        self.assertEqual(captured.get("check"), "Intimidation")

    def test_declared_seduction_uses_seduction(self):
        CheckTypeFactory(name="Seduction")
        _, captured = self._mint_with_approach("seduction")
        self.assertEqual(captured.get("check"), "Seduction")

    def test_declared_manipulation_resolves_con_or_deceive(self):
        # charm == presence (equal traits) → the charm branch → Con.
        CheckTypeFactory(name="Deceive")
        _, captured = self._mint_with_approach("manipulation")
        self.assertEqual(captured.get("check"), "Con")

    def test_declared_bribery_tags_the_deed_even_when_contained(self):
        from world.justice.models import CrimeKind, DeedCrimeTag

        CheckTypeFactory(name="Bribery")
        CrimeKind.objects.create(slug="bribery", name="Bribery")
        entry, captured = self._mint_with_approach("bribery", success_level=1)
        self.assertEqual(captured.get("check"), "Bribery")
        self.assertTrue(Secret.objects.filter(legend_deed=entry).exists())
        self.assertTrue(
            DeedCrimeTag.objects.filter(deed=entry, crime_kind__slug="bribery").exists()
        )

    def test_unknown_approach_falls_back_to_auto_pick(self):
        # Equal charm/presence → the legacy Con branch, exactly as undeclared.
        _, captured = self._mint_with_approach("interpretive-dance")
        self.assertEqual(captured.get("check"), "Con")

    def test_capability_list_gates_household_and_unseeded_tools(self):
        from world.societies.scandal import witness_approaches_for

        CheckTypeFactory(name="Seduction")
        CheckTypeFactory(name="Household Command")
        character = self._persona().character_sheet.character
        keys = [a.key for a in witness_approaches_for(character, household=False)]
        # Bribery unseeded here → dropped; household tool needs household=True.
        self.assertIn("intimidation", keys)
        self.assertIn("seduction", keys)
        self.assertIn("manipulation", keys)
        self.assertNotIn("bribery", keys)
        self.assertNotIn("household", keys)
        household_keys = [a.key for a in witness_approaches_for(character, household=True)]
        self.assertIn("household", household_keys)


class ActTimeConcealmentTests(ScandalForkTestCase):
    """#1824 — the declared-sneaky Stealth roll sheds witnesses before minting."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        CheckTypeFactory(name="Stealth")

    def _mint_concealed(self, *, success_level, witnesses, persona):
        from unittest.mock import patch

        from world.societies.factories import LegendSourceTypeFactory

        outcome = CheckOutcomeFactory(name=f"sneak_{success_level}", success_level=success_level)
        with (
            patch(
                "world.societies.knowledge_services.scene_witness_personas",
                return_value=witnesses,
            ),
            force_check_outcome(outcome),
        ):
            return create_solo_deed(
                persona,
                "PLACEHOLDER: the deed in question",
                LegendSourceTypeFactory(),
                10,
                scene=self._scene(public=True),
                archetypes=[self.vile],
                concealed=True,
            )

    def test_full_success_leaves_no_outside_knowledge_and_auto_contains(self):
        from world.societies.models import PersonaDeedKnowledge

        persona = self._persona()
        bystander = self._persona()
        # Forced outcome governs BOTH the stealth roll and any containment roll,
        # so a full success (3) proves auto-containment only via knowledge count.
        entry = self._mint_concealed(
            success_level=3, witnesses=[persona, bystander], persona=persona
        )
        knowers = set(
            PersonaDeedKnowledge.objects.filter(deed=entry).values_list("persona_id", flat=True)
        )
        self.assertNotIn(bystander.pk, knowers)
        self.assertTrue(Secret.objects.filter(legend_deed=entry).exists())
        self.assertEqual(entry.societies_aware.count(), 0)

    def test_failure_changes_nothing(self):
        from world.societies.models import PersonaDeedKnowledge

        persona = self._persona()
        bystander = self._persona()
        # success_level=0 fails the stealth roll AND the containment roll → leak.
        entry = self._mint_concealed(
            success_level=0, witnesses=[persona, bystander], persona=persona
        )
        knowers = set(
            PersonaDeedKnowledge.objects.filter(deed=entry).values_list("persona_id", flat=True)
        )
        self.assertIn(bystander.pk, knowers)
        self.assertFalse(Secret.objects.filter(legend_deed=entry).exists())
        self.assertGreater(entry.societies_aware.count(), 0)

    def test_partial_success_sheds_half_the_outsiders(self):
        from world.societies.scandal import reduce_witnesses_by_stealth

        persona = self._persona()
        outsiders = [self._persona() for _ in range(4)]
        outcome = CheckOutcomeFactory(name="sneak_partial", success_level=1)
        with force_check_outcome(outcome):
            kept, fully = reduce_witnesses_by_stealth(
                [persona.character_sheet.character], [persona], [persona, *outsiders]
            )
        self.assertFalse(fully)
        kept_outsiders = [w for w in kept if w.pk != persona.pk]
        self.assertEqual(len(kept_outsiders), 2)

    def test_group_concealment_is_weakest_link(self):
        from unittest.mock import patch

        from world.societies.scandal import reduce_witnesses_by_stealth

        actor_a = self._persona()
        actor_b = self._persona()
        bystander = self._persona()
        good = CheckOutcomeFactory(name="sneak_good", success_level=3)
        bad = CheckOutcomeFactory(name="sneak_bad", success_level=0)
        from world.checks import services as check_services

        real_perform = check_services.perform_check
        outcomes = iter([good, bad])

        def alternating(character, check_type, **kwargs):
            result = real_perform(character, check_type, **kwargs)
            forced = next(outcomes)
            return type(result)(
                check_type=result.check_type,
                outcome=forced,
                chart=result.chart,
                roller_rank=result.roller_rank,
                target_rank=result.target_rank,
                rank_difference=result.rank_difference,
                trait_points=result.trait_points,
                aspect_bonus=result.aspect_bonus,
                total_points=result.total_points,
            )

        with patch("world.checks.services.perform_check", side_effect=alternating):
            kept, fully = reduce_witnesses_by_stealth(
                [actor_a.character_sheet.character, actor_b.character_sheet.character],
                [actor_a, actor_b],
                [actor_a, actor_b, bystander],
            )
        self.assertFalse(fully)
        self.assertIn(bystander, kept)
