"""The NPC form's power options, read before the NPC has a sheet (#4418, demo fidelity F1)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from world.classes.factories import PathFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterEntryFactory
from world.skills.factories import SkillFactory
from world.traits.factories import StatTraitFactory

POWER_OPTIONS = "/api/roster/npcs/power-options/"


class NpcPowerOptionsTests(TestCase):
    """A Warden's Way tradition offers the Ember gift on the Path of Steel."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm, level=GMLevel.JUNIOR)
        cls.guide = AccountFactory()
        GuideProfileFactory(account=cls.guide)
        cls.player = AccountFactory()
        cls.path = PathFactory(name="Path of Steel")
        cls.tradition = TraditionFactory(name="Warden's Way")
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory(name="Ember")
        cls.gift.resonances.add(cls.resonance)
        cls.spark = TechniqueFactory(
            gift=cls.gift, name="Spark", action_template=ActionTemplateFactory()
        )
        cls.unready = TechniqueFactory(gift=cls.gift, name="Unready Flame")
        grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        grant.special_techniques.add(cls.spark, cls.unready)
        PathGiftGrantFactory(path=cls.path, gift=cls.gift)

    def _get(self, account, **params):
        client = APIClient()
        client.force_authenticate(user=account)
        return client.get(POWER_OPTIONS, params)

    def test_a_junior_gm_and_a_guide_get_the_options(self) -> None:
        picks = {"path": self.path.pk, "tradition": self.tradition.pk, "gift": self.gift.pk}
        for account in (self.gm, self.guide):
            response = self._get(account, **picks)
            self.assertEqual(response.status_code, 200, response.content[:800])
            data = response.json()
            self.assertIn({"id": self.path.pk, "name": "Path of Steel"}, data["paths"])
            self.assertEqual([row["name"] for row in data["gifts"]], ["Ember"])
            self.assertEqual([row["name"] for row in data["techniques"]], ["Spark"])
            self.assertEqual([row["id"] for row in data["resonances"]], [self.resonance.pk])
            self.assertEqual(data["technique_limit"], 1)

    def test_no_path_picked_offers_no_gifts(self) -> None:
        data = self._get(self.gm, tradition=self.tradition.pk).json()
        self.assertEqual(data["gifts"], [])
        self.assertIn("Warden's Way", [row["name"] for row in data["traditions"]])

    def test_a_plain_player_is_refused(self) -> None:
        self.assertEqual(self._get(self.player).status_code, 403)

    def test_it_matches_staff_magic_options_for_an_empty_sheet_on_that_path(self) -> None:
        sheet = RosterEntryFactory().character_sheet
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        staff = APIClient()
        staff.force_authenticate(user=self.staff)
        for picks in (
            {},
            {"tradition": self.tradition.pk},
            {"tradition": self.tradition.pk, "gift": self.gift.pk},
        ):
            on_sheet = staff.get(f"/api/character-sheets/{sheet.pk}/staff-magic-options/", picks)
            self.assertEqual(on_sheet.status_code, 200, on_sheet.content[:800])
            sheet_free = self._get(self.gm, path=self.path.pk, **picks).json()
            catalogs = {key: sheet_free.pop(key) for key in ("paths", "all_stats", "all_skills")}
            self.assertEqual(sheet_free, on_sheet.json(), picks)

        # The override catalogs are staff-options' Stats and Skills lists and Paths.
        options = staff.get(f"/api/character-sheets/{sheet.pk}/staff-options/").json()
        self.assertEqual(catalogs["all_stats"], options["stats"])
        self.assertEqual(catalogs["all_skills"], options["skills"])
        self.assertEqual(catalogs["paths"], options["paths"])

    def test_the_override_catalogs_include_inactive_skills(self) -> None:
        retired = SkillFactory(is_active=False)
        live = SkillFactory()
        strength = StatTraitFactory(name="power_options_strength")
        data = self._get(self.gm).json()
        self.assertIn({"id": strength.pk, "name": strength.name}, data["all_stats"])
        all_ids = {row["id"] for row in data["all_skills"]}
        self.assertTrue({retired.pk, live.pk} <= all_ids)
        self.assertNotIn(retired.pk, {row["id"] for row in data["skills"]})
