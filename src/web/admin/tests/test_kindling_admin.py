"""The kindled resonances admin pages (#5124, Screen 8) render for a staff user."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.magic.factories import (
    AffinityFactory,
    KindledStrengthTierFactory,
    KindlingFactory,
    KindlingSituationFactory,
    ReflectionFactory,
    ResonanceFactory,
    SettlingRiteFactory,
)
from world.missions.factories import MissionTemplateFactory

AUTHORED = (
    "kindledstrengthtier",
    "kindlingconfig",
    "kindleddeedaward",
    "rallykindlingstrength",
    "missiontheme",
)
PLAY_ROWS = ("kindling", "reflection", "settlingrite")


class KindlingAdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "kindling5124", "kindling5124@example.com", "pw-123456"
        )
        cls.resonance = ResonanceFactory()
        cls.affinity = AffinityFactory()
        KindlingSituationFactory(resonance=cls.resonance)
        KindledStrengthTierFactory(rank=1)
        cls.kindling = KindlingFactory()
        cls.reflection = ReflectionFactory()
        cls.rite = SettlingRiteFactory()
        cls.mission = MissionTemplateFactory()

    def test_every_page_renders(self) -> None:
        self.client.force_login(self.staff)
        mission_pk = self.mission.pk
        pages = [
            reverse(f"admin:arxii_{label}_{kind}")
            for label in AUTHORED + PLAY_ROWS
            for kind in ("changelist",)
        ]
        pages += [reverse(f"admin:arxii_{label}_add") for label in AUTHORED]
        pages += [
            reverse("admin:arxii_resonance_change", args=[self.resonance.pk]),
            reverse("admin:arxii_affinity_change", args=[self.affinity.pk]),
            reverse("admin:arxii_driftcorrectionconfig_changelist"),
            reverse("admin:arxii_missiontemplate_change", args=[mission_pk]),
            reverse("admin:arxii_vowsituationalperk_add"),
            reverse("admin:arxii_missionoption_add"),
            reverse("admin:arxii_kindling_change", args=[self.kindling.pk]),
            reverse("admin:arxii_reflection_change", args=[self.reflection.pk]),
            reverse("admin:arxii_settlingrite_change", args=[self.rite.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_play_rows_cannot_be_added_by_hand(self) -> None:
        self.client.force_login(self.staff)
        for label in PLAY_ROWS:
            with self.subTest(label=label):
                response = self.client.get(reverse(f"admin:arxii_{label}_add"))
                self.assertEqual(response.status_code, 403)
