"""The Audere reveal and choice (#4098 decisions 1-4, 7, 11, 12, 14, 15)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.constants import RoleArchetype
from world.magic.constants import AudereCeremony, GiftKind, UltimateCardKind, UltimateSource
from world.magic.exceptions import UltimateChoiceUnavailable, UltimateRevealClosed
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterGiftFactory,
    GiftFactory,
    KnownUltimateFactory,
    PathGiftGrantFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.magic.services.ultimates import (
    choose_ultimate,
    clear_readied_ultimate,
    readied_ultimate,
    ultimate_reveal_for,
)
from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import GiftHeldRequirement, TechniqueKnownRequirement
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence


class _RevealFixture(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.audere, cls.majora = wire_audere_power_multipliers()
        cls.threshold = AudereThresholdFactory(
            sword_reveal_label="Edge", shield_reveal_label="Wall", crown_reveal_label="Circlet"
        )
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)
        cls.grant = PathGiftGrantFactory(gift=cls.gift)
        CharacterPathHistoryFactory(character=cls.sheet, path=cls.grant.path)
        cls.strike = UltimateTechniqueFactory(
            gift=cls.gift, name="Strike", level=6, archetype_alignment=RoleArchetype.SWORD
        )
        cls.cleave = UltimateTechniqueFactory(
            gift=cls.gift, name="Cleave", level=7, archetype_alignment=RoleArchetype.SWORD
        )
        cls.ward = UltimateTechniqueFactory(
            gift=cls.gift, name="Ward", level=6, archetype_alignment=RoleArchetype.SHIELD
        )
        cls.grant.ultimate_techniques.add(cls.strike, cls.cleave, cls.ward)
        CharacterEngagementFactory(character=cls.sheet, engagement_type=EngagementType.COMBAT)

    def setUp(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)


class RevealShapeTests(_RevealFixture):
    def test_undiscovered_shown_by_category_only_one_card_per_category(self) -> None:
        reveal = ultimate_reveal_for(self.sheet)
        self.assertIsNotNone(reveal)
        (group,) = reveal.groups
        self.assertEqual(group.source, UltimateSource.OWNED)
        kinds = [(c.kind, c.category, c.label, c.technique) for c in group.cards]
        self.assertEqual(
            kinds,
            [
                (UltimateCardKind.CATEGORY, RoleArchetype.SWORD, "Edge", None),
                (UltimateCardKind.CATEGORY, RoleArchetype.SHIELD, "Wall", None),
            ],
        )
        # No leak (Global Constraints): a CATEGORY choice_key encodes only the
        # source and category, never a technique id — assert the exact key
        # shape rather than a substring check, since a raw pk-substring check
        # coincidentally collides whenever a hidden technique's pk and the
        # owning PathGiftGrant's pk happen to match (both are independent
        # per-table sequences starting at 1 in a fresh test database).
        self.assertEqual(
            [c.choice_key for c in group.cards],
            [
                f"category:owned:{self.grant.pk}:{RoleArchetype.SWORD}",
                f"category:owned:{self.grant.pk}:{RoleArchetype.SHIELD}",
            ],
        )

    def test_known_ultimate_listed_by_name(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.ward)
        (group,) = ultimate_reveal_for(self.sheet).groups
        known = [c for c in group.cards if c.kind == UltimateCardKind.KNOWN]
        self.assertEqual([c.technique for c in known], [self.ward])
        categories = [c.category for c in group.cards if c.kind == UltimateCardKind.CATEGORY]
        self.assertNotIn(RoleArchetype.SHIELD, categories)

    def test_minor_gift_carries_none(self) -> None:
        minor = GiftFactory(kind=GiftKind.MINOR)
        other = CharacterSheetFactory()
        CharacterGiftFactory(character=other, gift=minor)
        grant = PathGiftGrantFactory(gift=minor, path=self.grant.path)
        grant.ultimate_techniques.add(UltimateTechniqueFactory(gift=minor))
        CharacterPathHistoryFactory(character=other, path=self.grant.path)
        CharacterEngagementFactory(character=other, engagement_type=EngagementType.COMBAT)
        ConditionInstanceFactory(target=other.character, condition=self.audere)
        self.assertIsNone(ultimate_reveal_for(other))

    def test_unmet_prerequisite_hides_ultimate(self) -> None:
        GiftHeldRequirement.objects.create(technique=self.ward, gift=GiftFactory())
        (group,) = ultimate_reveal_for(self.sheet).groups
        self.assertNotIn(RoleArchetype.SHIELD, [c.category for c in group.cards])

    def test_upgrade_of_known_ultimate_shown_by_name(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.strike)
        upgrade = UltimateTechniqueFactory(gift=self.gift, name="Collapse", level=11)
        self.grant.ultimate_techniques.add(upgrade)
        TechniqueKnownRequirement.objects.create(technique=upgrade, required_technique=self.strike)
        (group,) = ultimate_reveal_for(self.sheet).groups
        upgrades = [c for c in group.cards if c.kind == UltimateCardKind.UPGRADE]
        self.assertEqual([(c.technique, c.upgrade_of) for c in upgrades], [(upgrade, self.strike)])


class RevealGateTests(_RevealFixture):
    def test_no_reveal_without_active_audere(self) -> None:
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.filter(target=self.character).delete()
        self.assertIsNone(ultimate_reveal_for(self.sheet))

    def test_no_reveal_outside_combat_engagement(self) -> None:
        engagement = self.sheet.engagement  # CharacterEngagement.character related_name
        engagement.engagement_type = EngagementType.CHALLENGE
        engagement.save(update_fields=["engagement_type"])
        self.assertIsNone(ultimate_reveal_for(self.sheet))

    def test_no_reveal_once_readied(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.ward, readied=True)
        self.assertIsNone(ultimate_reveal_for(self.sheet))

    def test_unfinished_path_has_no_reveal(self) -> None:
        self.grant.ultimate_techniques.clear()
        self.assertIsNone(ultimate_reveal_for(self.sheet))


class HasRevealCardsTests(_RevealFixture):
    """`has_reveal_cards` drives the Audere offer's framing line - shown before the
    Audere condition exists, so it must gate on the COMBAT engagement the same way
    the reveal itself does, or a challenge/mission offer shows the framing line with
    no reveal to follow it (#4098 final review item 5)."""

    def test_true_in_combat_with_cards_available(self) -> None:
        from world.magic.services.ultimates import has_reveal_cards

        self.assertTrue(has_reveal_cards(self.sheet))

    def test_false_outside_combat_engagement_even_with_cards_available(self) -> None:
        from world.magic.services.ultimates import has_reveal_cards

        engagement = self.sheet.engagement  # CharacterEngagement.character related_name
        engagement.engagement_type = EngagementType.CHALLENGE
        engagement.save(update_fields=["engagement_type"])
        self.assertFalse(has_reveal_cards(self.sheet))

    def test_false_in_combat_with_no_cards_available(self) -> None:
        from world.magic.services.ultimates import has_reveal_cards

        self.grant.ultimate_techniques.clear()
        self.assertFalse(has_reveal_cards(self.sheet))


class BondSourceTests(_RevealFixture):
    def test_active_patron_adds_patron_group(self) -> None:
        being = WorshippedBeingFactory()
        being.ultimate_techniques.add(
            UltimateTechniqueFactory(archetype_alignment=RoleArchetype.SHIELD)
        )
        DevotionStandingFactory(
            character_sheet=self.sheet, being=being, valence=PatronageValence.DEVOTIONAL
        )
        sources = [g.source for g in ultimate_reveal_for(self.sheet).groups]
        self.assertEqual(sources, [UltimateSource.OWNED, UltimateSource.PATRON])

    def test_ordinary_worship_adds_nothing(self) -> None:
        being = WorshippedBeingFactory()
        being.ultimate_techniques.add(UltimateTechniqueFactory())
        DevotionStandingFactory(character_sheet=self.sheet, being=being, valence=None)
        sources = [g.source for g in ultimate_reveal_for(self.sheet).groups]
        self.assertEqual(sources, [UltimateSource.OWNED])

    def test_bonded_companion_adds_companion_group(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        companion.archetype.ultimate_techniques.add(UltimateTechniqueFactory())
        sources = [g.source for g in ultimate_reveal_for(self.sheet).groups]
        self.assertIn(UltimateSource.COMPANION, sources)

    def test_patron_pools_query_count_does_not_scale_with_patron_count(self) -> None:
        """``active_patronage_for`` must not cost a query per row via ``s.being``."""
        from world.magic.services.ultimates import _patron_pools

        being_a = WorshippedBeingFactory()
        being_b = WorshippedBeingFactory()
        being_a.ultimate_techniques.add(
            UltimateTechniqueFactory(archetype_alignment=RoleArchetype.SHIELD)
        )
        being_b.ultimate_techniques.add(
            UltimateTechniqueFactory(archetype_alignment=RoleArchetype.CROWN)
        )
        DevotionStandingFactory(
            character_sheet=self.sheet, being=being_a, valence=PatronageValence.DEVOTIONAL
        )
        DevotionStandingFactory(
            character_sheet=self.sheet, being=being_b, valence=PatronageValence.DEVOTIONAL
        )

        with self.assertNumQueries(2):
            pools = _patron_pools(self.sheet)
        self.assertEqual(len(pools), 2)


class CrossPathAndBondLifecycleTests(_RevealFixture):
    """#4098 fix round 1, I1: decisions 4/12 — a known ultimate never disappears.

    Owned known ultimates stay listed (and choosable) regardless of the
    character's CURRENT path, as long as the gift that offers them is still
    held as MAJOR. Bond known ultimates (patron, companion) are the opposite:
    they stay listed only while the bond itself is active (decision 5).
    """

    def test_known_ultimate_survives_a_path_crossing(self) -> None:
        from world.classes.factories import PathFactory

        KnownUltimateFactory(character=self.sheet, technique=self.strike)
        path_b = PathFactory()
        CharacterPathHistoryFactory(character=self.sheet, path=path_b)

        reveal = ultimate_reveal_for(self.sheet)
        self.assertIsNotNone(reveal)
        known_cards = [
            c for grp in reveal.groups for c in grp.cards if c.kind == UltimateCardKind.KNOWN
        ]
        self.assertIn(self.strike, [c.technique for c in known_cards])

        key = next(c.choice_key for c in known_cards if c.technique == self.strike)
        known = choose_ultimate(self.sheet, key)
        self.assertEqual(known.technique, self.strike)

    def test_known_ultimate_not_duplicated_when_still_on_its_offering_path(self) -> None:
        """A known ultimate still on its ORIGINAL (current) grant must appear once,
        not once from the current-path pool and again from the known-ultimate pool."""
        KnownUltimateFactory(character=self.sheet, technique=self.strike)
        reveal = ultimate_reveal_for(self.sheet)
        known_cards = [
            c for grp in reveal.groups for c in grp.cards if c.kind == UltimateCardKind.KNOWN
        ]
        self.assertEqual([c.technique for c in known_cards], [self.strike])

    def test_known_patron_ultimate_delisted_once_patronage_is_released(self) -> None:
        from django.utils import timezone

        being = WorshippedBeingFactory()
        patron_tech = UltimateTechniqueFactory(archetype_alignment=RoleArchetype.CROWN)
        being.ultimate_techniques.add(patron_tech)
        standing = DevotionStandingFactory(
            character_sheet=self.sheet, being=being, valence=PatronageValence.DEVOTIONAL
        )
        KnownUltimateFactory(character=self.sheet, technique=patron_tech)

        before = ultimate_reveal_for(self.sheet)
        before_techniques = [
            c.technique for grp in before.groups for c in grp.cards if c.technique is not None
        ]
        self.assertIn(patron_tech, before_techniques)

        standing.released_at = timezone.now()
        standing.save(update_fields=["released_at"])

        after = ultimate_reveal_for(self.sheet)
        after_techniques = (
            [c.technique for grp in after.groups for c in grp.cards if c.technique is not None]
            if after is not None
            else []
        )
        self.assertNotIn(patron_tech, after_techniques)


class UpgradeOfOrderingTests(_RevealFixture):
    def test_upgrade_of_picks_deterministically_by_required_technique_order(self) -> None:
        """Two TechniqueKnownRequirement rows on one upgrade: the winner is driven by
        (required_technique.level, name, pk), not by DB/pk/creation order (#4098 fix
        round 1, M1).

        ``x`` is created FIRST (lower pk) with a HIGH sort key (level 50, "Zulu");
        ``y`` is created SECOND (higher pk) with a LOW sort key (level 1, "Alpha").
        An unordered query (which, empirically, returns these rows sorted by the
        required technique's own pk — x then y) would pick ``y`` as the last
        dict-comprehension write; the (level, name, pk)-ordered fix sorts ``y``
        before ``x`` and picks ``x``. The two disagree, so this proves the fix,
        not an accident of row/pk order.
        """
        x = UltimateTechniqueFactory(gift=self.gift, name="Zulu", level=50)
        y = UltimateTechniqueFactory(gift=self.gift, name="Alpha", level=1)
        self.grant.ultimate_techniques.add(x, y)
        KnownUltimateFactory(character=self.sheet, technique=x)
        KnownUltimateFactory(character=self.sheet, technique=y)
        upgrade = UltimateTechniqueFactory(gift=self.gift, name="Apex", level=99)
        self.grant.ultimate_techniques.add(upgrade)
        TechniqueKnownRequirement.objects.create(technique=upgrade, required_technique=x)
        TechniqueKnownRequirement.objects.create(technique=upgrade, required_technique=y)
        groups = ultimate_reveal_for(self.sheet).groups
        upgrades = [c for grp in groups for c in grp.cards if c.kind == UltimateCardKind.UPGRADE]
        self.assertEqual([(c.technique, c.upgrade_of) for c in upgrades], [(upgrade, x)])


class ChooseTests(_RevealFixture):
    def test_category_choice_reveals_lowest_level_and_readies_it(self) -> None:
        reveal = ultimate_reveal_for(self.sheet)
        sword = next(c for c in reveal.groups[0].cards if c.category == RoleArchetype.SWORD)
        known = choose_ultimate(self.sheet, sword.choice_key)
        self.assertEqual(known.technique, self.strike)
        self.assertTrue(known.readied)
        self.assertIsNone(known.crossing)
        self.assertEqual(readied_ultimate(self.sheet), known)

    def test_known_choice_readies_without_new_row(self) -> None:
        existing = KnownUltimateFactory(character=self.sheet, technique=self.ward)
        card = next(
            c
            for c in ultimate_reveal_for(self.sheet).groups[0].cards
            if c.kind == UltimateCardKind.KNOWN
        )
        chosen = choose_ultimate(self.sheet, card.choice_key)
        self.assertEqual(chosen.pk, existing.pk)
        self.assertEqual(KnownUltimate.objects.filter(character=self.sheet).count(), 1)

    def test_second_choice_in_same_audere_refused(self) -> None:
        key = ultimate_reveal_for(self.sheet).groups[0].cards[0].choice_key
        choose_ultimate(self.sheet, key)
        with self.assertRaises(UltimateRevealClosed):
            choose_ultimate(self.sheet, key)

    def test_forged_key_refused(self) -> None:
        with self.assertRaises(UltimateChoiceUnavailable):
            choose_ultimate(self.sheet, f"known:{self.strike.pk}")

    def test_db_race_past_the_readied_gate_raises_reveal_closed(self) -> None:
        """A race that slips a second readied row past the application-level
        ``_has_readied`` gate hits the ``one_readied_ultimate_per_character``
        constraint; ``choose_ultimate`` must surface it as ``UltimateRevealClosed``,
        not a raw ``IntegrityError`` (#4098 fix round 1, M2)."""
        from unittest.mock import patch

        from world.magic.services import ultimates as ultimates_module

        reveal = ultimate_reveal_for(self.sheet)
        sword = next(c for c in reveal.groups[0].cards if c.category == RoleArchetype.SWORD)
        # Simulate a concurrent request that already readied a different ultimate
        # for this character, racing past the pre-captured `reveal` snapshot above.
        KnownUltimateFactory(character=self.sheet, technique=self.ward, readied=True)
        with patch.object(ultimates_module, "ultimate_reveal_for", return_value=reveal):
            with self.assertRaises(UltimateRevealClosed):
                choose_ultimate(self.sheet, sword.choice_key)

    def test_readied_needs_active_ceremony(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.ward, readied=True)
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.filter(target=self.character).delete()
        self.assertIsNone(readied_ultimate(self.sheet))

    def test_category_choice_skips_a_candidate_with_unmet_prerequisites(self) -> None:
        """Strike (level 6) is the lowest-level SWORD candidate but has an unmet
        GiftHeldRequirement; the category choice must skip it for Cleave (level 7),
        the next-lowest eligible candidate (#4098 fix round 1, M3)."""
        GiftHeldRequirement.objects.create(technique=self.strike, gift=GiftFactory())
        reveal = ultimate_reveal_for(self.sheet)
        sword = next(c for c in reveal.groups[0].cards if c.category == RoleArchetype.SWORD)
        known = choose_ultimate(self.sheet, sword.choice_key)
        self.assertEqual(known.technique, self.cleave)

    def test_fire_first_discoveries_fires_on_first_pick_not_on_reready(self) -> None:
        from unittest.mock import patch

        reveal = ultimate_reveal_for(self.sheet)
        sword = next(c for c in reveal.groups[0].cards if c.category == RoleArchetype.SWORD)
        with patch("world.achievements.discovery.fire_first_discoveries") as mock_fire:
            known = choose_ultimate(self.sheet, sword.choice_key)
        mock_fire.assert_called_once()
        called_sheet, called_gained = mock_fire.call_args.args
        self.assertEqual(called_sheet.pk, self.sheet.pk)
        self.assertEqual(called_gained, [self.strike])

        clear_readied_ultimate(self.sheet)
        reveal2 = ultimate_reveal_for(self.sheet)
        known_card = next(c for c in reveal2.groups[0].cards if c.kind == UltimateCardKind.KNOWN)
        with patch("world.achievements.discovery.fire_first_discoveries") as mock_fire2:
            reready = choose_ultimate(self.sheet, known_card.choice_key)
        mock_fire2.assert_not_called()
        self.assertEqual(reready.pk, known.pk)


class ChooseMajoraTests(_RevealFixture):
    def test_majora_pick_sets_crossing(self) -> None:
        """Choosing during Audere Majora stamps the character's most recent
        AudereMajoraCrossing receipt onto the KnownUltimate row (#4098 fix round 1,
        M3)."""
        from world.classes.factories import PathFactory
        from world.magic.audere_majora import AudereMajoraCrossing
        from world.magic.factories import ensure_audere_majora_threshold

        ConditionInstanceFactory(target=self.character, condition=self.majora)
        threshold = ensure_audere_majora_threshold(boundary_level=97)
        path = PathFactory()
        crossing = AudereMajoraCrossing.objects.create(
            character_sheet=self.sheet,
            threshold=threshold,
            chosen_path=path,
            level_before=4,
            level_after=5,
        )

        reveal = ultimate_reveal_for(self.sheet)
        self.assertEqual(reveal.ceremony, AudereCeremony.AUDERE_MAJORA)
        key = reveal.groups[0].cards[0].choice_key
        known = choose_ultimate(self.sheet, key)
        self.assertEqual(known.crossing, crossing)
