"""Tests for the Great Archive Librarian self-study seed (#2440 ruling 5).

Covers: idempotent role/offer/achievement creation, and the achievement gate
itself (blocked pre-achievement, open post) driven through the real
``NPCServiceOffer.eligibility_rule`` predicate — the same mechanism
``available_offers`` uses to decide what a player sees.
"""

from __future__ import annotations

from django.test import TestCase

from world.achievements.factories import CharacterAchievementFactory
from world.achievements.models import Achievement, CharacterAchievement
from world.npc_services.constants import OfferKind
from world.npc_services.models import NPCRole, NPCServiceOffer, TrainOfferDetails
from world.npc_services.seeds import (
    _SELF_STUDY_TECHNIQUE_NAMES,
    GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME,
    GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG,
    ensure_great_archive_librarian_role,
    ensure_great_archive_self_study_achievement,
)
from world.npc_services.services import available_offers, start_interaction
from world.scenes.factories import PersonaFactory
from world.seeds.game_content.magic import MagicContent


def _build_self_study_catalog():
    """Factory-build a synthetic Path/Gift/Technique catalog for the Great
    Archive self-study tests (#2474) — one (Path, Gift) pair per hardcoded
    technique name ``ensure_great_archive_librarian_role`` looks up, so its
    ORM lookup (``Technique.objects.filter(name__in=...)``) finds real rows
    instead of a catalog seeded by the now-retired ``seed_starter_gift_catalog()``.
    """
    specs = [
        (f"Test Path {i}", f"Test Starter Gift {i}", technique_name)
        for i, technique_name in enumerate(_SELF_STUDY_TECHNIQUE_NAMES, start=1)
    ]
    return MagicContent.create_starter_gift_catalog(specs)


class EnsureGreatArchiveLibrarianRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.catalog = _build_self_study_catalog()

    def test_creates_role_offers_and_achievement(self) -> None:
        role = ensure_great_archive_librarian_role()

        self.assertEqual(role.name, GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME)
        self.assertIsNotNone(role.faction_affiliation)
        self.assertEqual(role.faction_affiliation.name, "Shroudwatch Academy")
        self.assertIsNone(role.teaches_tradition)

        offers = list(NPCServiceOffer.objects.filter(role=role))
        self.assertGreater(len(offers), 0)
        for offer in offers:
            self.assertEqual(offer.kind, OfferKind.TRAIN)
            self.assertEqual(offer.ap_cost, 0)
            self.assertTrue(TrainOfferDetails.objects.filter(offer=offer).exists())
            self.assertEqual(
                offer.eligibility_rule,
                {
                    "leaf": "has_achievement",
                    "params": {"slug": GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG},
                },
            )

        self.assertTrue(
            Achievement.objects.filter(slug=GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG).exists()
        )

    def test_idempotent(self) -> None:
        ensure_great_archive_librarian_role()
        ensure_great_archive_librarian_role()
        ensure_great_archive_librarian_role()

        self.assertEqual(NPCRole.objects.filter(name=GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME).count(), 1)
        self.assertEqual(
            Achievement.objects.filter(slug=GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG).count(), 1
        )
        offers_first_pass = list(
            NPCServiceOffer.objects.filter(role__name=GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        ensure_great_archive_librarian_role()
        offers_second_pass = list(
            NPCServiceOffer.objects.filter(role__name=GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME)
            .order_by("pk")
            .values_list("label", flat=True)
        )
        self.assertEqual(offers_first_pass, offers_second_pass)


class GreatArchiveSelfStudyGateTests(TestCase):
    """Blocked pre-achievement, open post — through the real offer-visibility gate."""

    @classmethod
    def setUpTestData(cls):
        _build_self_study_catalog()
        cls.role = ensure_great_archive_librarian_role()
        cls.achievement = ensure_great_archive_self_study_achievement()

    def setUp(self) -> None:
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

    def _train_offer_labels(self) -> set[str]:
        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        offers = available_offers(session)
        return {offer.label for offer in offers if offer.kind == OfferKind.TRAIN}

    def test_blocked_pre_achievement(self) -> None:
        self.assertEqual(self._train_offer_labels(), set())

    def test_open_post_achievement(self) -> None:
        CharacterAchievementFactory(character_sheet=self.sheet, achievement=self.achievement)

        labels = self._train_offer_labels()

        self.assertGreater(len(labels), 0)
        expected_labels = set(
            NPCServiceOffer.objects.filter(role=self.role, kind=OfferKind.TRAIN).values_list(
                "label", flat=True
            )
        )
        self.assertEqual(labels, expected_labels)

    def test_achievement_row_itself_ungranted_by_seed(self) -> None:
        # The seed only ensures the Achievement definition exists — granting it
        # is the lore-repo quest's job, never this seed's.
        self.assertFalse(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=self.achievement
            ).exists()
        )
