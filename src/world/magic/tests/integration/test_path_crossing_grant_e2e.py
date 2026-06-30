"""E2E: crossing into a path grants that path's gift + curated techniques (#1579).

The north-star journey for the (Gift x Path) grant leg of ADR-0055: the same
authored Gift (Pyromancy) yields a *different* starter technique set per path —
a warrior-line crossing grants attack/defense techniques; a spy-line crossing
would grant confusion/evasion. Drives the real
``resolve_audere_majora_offer -> cross_threshold`` path (no bypass).
"""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.audere_majora import resolve_audere_majora_offer
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    PathGiftGrant,
    Thread,
)
from world.magic.specialization.services import resolve_specialized_variant
from world.magic.tests.majora_fixtures import build_crossing_world


class PathCrossingGrantE2ETests(TestCase):
    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.warrior_path,
            self.offer,
        ) = build_crossing_world(5, "_e2e")

        # A second eligible puissant path off the same prospect = the spy line.
        self.spy_path = PathFactory(
            name="Whispers Adept_e2e", stage=PathStage.PUISSANT, is_active=True
        )
        self.spy_path.parent_paths.add(self.prospect_path)

        # One shared authored Gift; different curated technique sets per path.
        self.gift = GiftFactory(name="Pyromancy_e2e")
        self.gift.resonances.add(ResonanceFactory(name="Ember_e2e"))
        self.warrior_attack = TechniqueFactory(name="Flame Lash_e2e", gift=self.gift)
        self.warrior_defense = TechniqueFactory(name="Cinder Ward_e2e", gift=self.gift)
        self.spy_confuse = TechniqueFactory(name="Heat Mirage_e2e", gift=self.gift)
        self.spy_escape = TechniqueFactory(name="Smoke Veil_e2e", gift=self.gift)

        warrior_grant = PathGiftGrant.objects.create(path=self.warrior_path, gift=self.gift)
        warrior_grant.starter_techniques.add(self.warrior_attack, self.warrior_defense)
        spy_grant = PathGiftGrant.objects.create(path=self.spy_path, gift=self.gift)
        spy_grant.starter_techniques.add(self.spy_confuse, self.spy_escape)

    def _owned_technique_ids(self):
        return set(
            CharacterTechnique.objects.filter(character=self.sheet).values_list(
                "technique_id", flat=True
            )
        )

    def test_crossing_to_warrior_grants_only_the_warrior_set(self) -> None:
        result = resolve_audere_majora_offer(
            self.offer.pk,
            accept=True,
            path_id=self.warrior_path.pk,
            declaration_text="I take up the burning blade.",
        )
        self.assertTrue(result.accepted)

        # Gift granted.
        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())

        # Exactly the warrior set — the spy set is NOT granted (same gift, other path).
        self.assertEqual(
            self._owned_technique_ids(),
            {self.warrior_attack.pk, self.warrior_defense.pk},
        )

        # Latent GIFT thread provisioned at a supported resonance.
        thread = Thread.objects.filter(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        ).first()
        self.assertIsNotNone(thread)
        self.assertIn(
            thread.resonance_id,
            set(self.gift.resonances.values_list("pk", flat=True)),
        )

        # A granted technique flows through the specialization/cast resolution path
        # (base form at thread level 0 — usable, ready to specialize as the thread grows).
        resolved = resolve_specialized_variant(entity=self.warrior_attack, character=self.character)
        self.assertEqual(resolved.name, self.warrior_attack.name)

    def test_grant_is_idempotent_on_recross(self) -> None:
        from world.magic.services.path_magic import grant_path_magic

        resolve_audere_majora_offer(
            self.offer.pk,
            accept=True,
            path_id=self.warrior_path.pk,
            declaration_text="I take up the burning blade.",
        )
        before = self._owned_technique_ids()
        grant_path_magic(self.sheet, self.warrior_path)  # re-grant
        self.assertEqual(self._owned_technique_ids(), before)
        self.assertEqual(
            CharacterGift.objects.filter(character=self.sheet, gift=self.gift).count(), 1
        )

    def test_crossing_keeps_old_gift_and_grants_new_for_it_plus_the_new_gift(self) -> None:
        """An advanced branch keeps the old gift+techniques, deepens the old gift with
        NEW techniques, AND grants the new path's new gift+techniques."""
        # The character already holds a gift (from CG / their prospect path) with one
        # already-known technique — these must survive the crossing untouched.
        old_gift = GiftFactory(name="Geomancy_e2e")
        old_gift.resonances.add(ResonanceFactory(name="Stone_e2e"))
        old_known = TechniqueFactory(name="Stone Skin_e2e", gift=old_gift)
        new_for_old = TechniqueFactory(name="Quake Step_e2e", gift=old_gift)
        CharacterGift.objects.create(character=self.sheet, gift=old_gift)
        CharacterTechnique.objects.create(character=self.sheet, technique=old_known)

        # The warrior path deepens the EXISTING gift (a new technique of it) in addition
        # to introducing the new gift (self.gift, granted via the setUp PathGiftGrant).
        deepen = PathGiftGrant.objects.create(path=self.warrior_path, gift=old_gift)
        deepen.starter_techniques.add(new_for_old)

        resolve_audere_majora_offer(
            self.offer.pk,
            accept=True,
            path_id=self.warrior_path.pk,
            declaration_text="I take up the burning blade.",
        )

        # Old gift retained; new gift acquired.
        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=old_gift).exists())
        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())
        # Techniques: the old one is kept, the existing gift is deepened with a new one,
        # and the new gift's set is added — all at once.
        self.assertEqual(
            self._owned_technique_ids(),
            {
                old_known.pk,  # retained
                new_for_old.pk,  # new technique for the EXISTING gift
                self.warrior_attack.pk,  # new gift's set
                self.warrior_defense.pk,
            },
        )
