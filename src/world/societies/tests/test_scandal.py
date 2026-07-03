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
