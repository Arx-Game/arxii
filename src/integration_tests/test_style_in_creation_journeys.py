"""Journeys for choosing a combat style in character creation and asking the Sphinx (#4921).

Slice 5 of #4844. In the Gift stage a player sees the styles her Tradition teaches, each
with how it attacks and defends and nothing about vows, chooses one and trains its skill
from the Tradition's creation pool; a Tradition that teaches no style skips the step.
Finalize writes the style and the trained skill value. After creation the Sphinx of
Black Quartz says whether her style suits a vow, through the REST endpoint and the
``sphinx`` verb.

Driven over the REST seam the browser uses: the combat style list, the draft PATCH and
detail, ``select-tradition``, and staff adding the draft to the roster; the Sphinx
through ``GET /api/covenants/roles/sphinx/`` and the telnet command handler.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    MAGIC_TRAINING_POINTS_TARGET,
    TraditionState,
)
from world.character_creation.factories import BeginningTraditionFactory
from world.character_creation.models import CharacterDraft
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.covenants.constants import DefenseStyle
from world.covenants.factories import (
    CombatStyleFactory,
    CombatStyleGearFactory,
    CovenantRoleFactory,
)
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.items.constants import GearArchetype
from world.magic.factories import TraditionFactory, TraditionGiftGrantFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.roster.factories import RosterTenureFactory
from world.skills.factories import SkillFactory, SkillPointBudgetFactory
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType

#: Tradition Training at rank 1 gives this many Magic training points.
TRAINING_POINTS = 20

DRAFTS = "/api/character-creation/drafts/"


class ChoosingAStyleInCreation(FinalizationTestMixin, JourneyCase):
    """A Tradition that teaches two styles, and one that teaches none."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Style CG", height_min=1600, height_max=1700)
        # ``cls.tradition`` (from the base) teaches two styles; ``cls.plain`` teaches none.
        cls.plain = TraditionFactory()
        TraditionGiftGrantFactory(tradition=cls.plain, gift=cls.gift)
        for tradition in (cls.tradition, cls.plain):
            BeginningTraditionFactory(
                beginning=cls.beginnings, tradition=tradition, state=TraditionState.LIVING_MASTERS
            )

        cls.training = DistinctionFactory(name="Style CG Training", cost_per_rank=1)
        DistinctionEffectFactory(
            distinction=cls.training,
            target=ModifierTargetFactory(
                name=MAGIC_TRAINING_POINTS_TARGET,
                category=ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY),
            ),
            value_per_rank=TRAINING_POINTS,
        )
        SkillPointBudgetFactory(pk=1)

        cls.thaumaturgy = SkillFactory(name="Thaumaturgy", category=TraitCategory.MAGIC)
        dance_skill = SkillFactory(name="The Daring Dance", category=TraitCategory.MAGIC)
        mask_skill = SkillFactory(name="The Iron Mask", category=TraitCategory.MAGIC)
        agility, _ = Trait.objects.get_or_create(
            name="agility", defaults={"trait_type": TraitType.STAT}
        )
        cls.dance = CombatStyleFactory(
            name="The Daring Dance",
            description="Never where the blow lands.",
            defense_style=DefenseStyle.EVASION,
            armor_share_tenths=3,
            skill=dance_skill,
            hit_stat=agility,
        )
        cls.mask = CombatStyleFactory(
            name="The Iron Mask",
            defense_style=DefenseStyle.GEAR_SOAK,
            armor_share_tenths=10,
            skill=mask_skill,
        )
        for style, kinds in (
            (cls.dance, [GearArchetype.MELEE_ONE_HAND, GearArchetype.THROWN]),
            (cls.dance, [GearArchetype.LIGHT_ARMOR]),
            (cls.mask, [GearArchetype.MELEE_TWO_HAND, GearArchetype.HEAVY_ARMOR]),
        ):
            for kind in kinds:
                CombatStyleGearFactory(style=style, gear_archetype=kind)
            style.taught_by.add(cls.tradition)
        # Both styles list a vow; creation never shows it.
        cls.dance.compatible_roles.add(CovenantRoleFactory(name="Quicksilver"))

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory(is_staff=True)
        self.client = self.api(self.account)

    # -- the seams ------------------------------------------------------------

    def _url(self, draft: CharacterDraft) -> str:
        return f"{DRAFTS}{draft.pk}/"

    def _select(self, draft: CharacterDraft, tradition) -> None:
        response = self.client.post(
            f"{self._url(draft)}select-tradition/", {"tradition_id": tradition.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _detail(self, draft: CharacterDraft) -> dict:
        response = self.client.get(self._url(draft))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _gift_errors(self, draft: CharacterDraft) -> list[str]:
        return self._detail(draft)["stage_errors"][str(CharacterDraft.Stage.GIFT)]

    def _styles(self, draft: CharacterDraft) -> list[dict]:
        response = self.client.get(f"/api/character-creation/combat-styles/?draft_id={draft.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _patch(self, draft: CharacterDraft, data: dict):
        return self.client.patch(self._url(draft), data, format="json")

    def _finalize(self, draft: CharacterDraft):
        response = self.client.post(f"{self._url(draft)}add-to-roster/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return ObjectDB.objects.get(pk=response.json()["character_id"]).sheet_data

    def _schooled_draft(self, tradition) -> CharacterDraft:
        """A complete draft in ``tradition`` holding one rank of training (arranged)."""
        draft = self._create_base_draft()
        self._select(draft, tradition)
        draft.refresh_from_db()
        draft.draft_data["distinctions"] = [{"distinction_id": self.training.pk, "rank": 1}]
        draft.save(update_fields=["draft_data"])
        return draft

    def _training_names(self, draft: CharacterDraft) -> list[str]:
        return [skill["name"] for skill in self._detail(draft)["magic_training"]["skills"]]

    # -- the journeys -----------------------------------------------------------

    def test_choose_a_taught_style_train_its_skill_and_finalize(self) -> None:
        draft = self._schooled_draft(self.tradition)

        styles = self._styles(draft)
        self.assertEqual([row["name"] for row in styles], ["The Daring Dance", "The Iron Mask"])
        dance = styles[0]
        self.assertEqual(
            set(dance),
            {
                "id",
                "name",
                "description",
                "defense_style",
                "defense_style_display",
                "armor_share_tenths",
                "hit_stat_name",
                "weapon_kinds",
                "armor_kinds",
            },
        )
        self.assertNotIn("Quicksilver", str(styles))
        self.assertEqual(
            [kind["label"] for kind in dance["weapon_kinds"]], ["One-Handed Melee", "Thrown"]
        )
        self.assertEqual([kind["label"] for kind in dance["armor_kinds"]], ["Light Armor"])
        self.assertEqual(dance["hit_stat_name"], "agility")
        self.assertEqual(dance["defense_style_display"], "Evasion")
        self.assertEqual(dance["armor_share_tenths"], 3)
        self.assertIsNone(styles[1]["hit_stat_name"])

        # Until a style is chosen the stage says so, and no style skill is on the list.
        self.assertIn("Choose a combat style", self._gift_errors(draft))
        self.assertEqual(self._training_names(draft), ["Thaumaturgy"])

        response = self._patch(draft, {"selected_combat_style_id": self.dance.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["selected_combat_style"], self.dance.pk)
        self.assertEqual(self._training_names(draft), ["Thaumaturgy", "The Daring Dance"])

        skill = self.dance.skill
        # Rank 1 training plus the favored Gift's fit bonus; one skill can hold it all.
        total = self._detail(draft)["magic_training"]["total"]
        self.assertGreater(total, TRAINING_POINTS)
        response = self._patch(draft, {"draft_data": {"magic_skills": {str(skill.pk): total}}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._gift_errors(draft), [])

        sheet = self._finalize(draft)

        self.assertEqual(sheet.combat_style, self.dance)
        self.assertEqual(CharacterTraitValue.objects.get(character=sheet, trait=skill).value, total)

    def test_the_owners_sheet_shows_the_style_and_a_strangers_does_not(self) -> None:
        draft = self._schooled_draft(self.tradition)
        self._patch(draft, {"selected_combat_style_id": self.dance.pk})
        skill = self.dance.skill
        total = self._detail(draft)["magic_training"]["total"]
        self._patch(draft, {"draft_data": {"magic_skills": {str(skill.pk): total}}})
        sheet = self._finalize(draft)
        # A player takes up the new character (arranged: the roster's own flow is not
        # what this journey proves).
        owner = AccountFactory()
        RosterTenureFactory(
            roster_entry=sheet.roster_entry, player_data__account=owner, end_date=None
        )
        sheet.roster_entry.invalidate_tenure_cache()
        url = f"/api/character-sheets/{sheet.pk}/"
        # Another Tradition teaches the style too and sorts first; the sheet names hers.
        self.dance.taught_by.add(TraditionFactory(name="A First School", sort_order=0))

        response = self.api(owner).get(url)

        self.assertEqual(response.status_code, 200, response.content)
        style = response.json()["combat_style"]
        self.assertEqual(
            style,
            {
                "id": self.dance.pk,
                "name": "The Daring Dance",
                "description": "Never where the blow lands.",
                "defense_style": DefenseStyle.EVASION,
                "defense_style_display": "Evasion",
                "armor_share_tenths": 3,
                "hit_stat_name": "agility",
                "weapon_kinds": [
                    {"value": GearArchetype.MELEE_ONE_HAND, "label": "One-Handed Melee"},
                    {"value": GearArchetype.THROWN, "label": "Thrown"},
                ],
                "armor_kinds": [{"value": GearArchetype.LIGHT_ARMOR, "label": "Light Armor"}],
                "skill_name": "The Daring Dance",
                "skill_value": total,
                "tradition_name": self.tradition.name,
                # The sheet shows the style's vows; creation never does.
                "vows": ["Quicksilver"],
            },
        )

        stranger = self.api(AccountFactory()).get(url)
        self.assertEqual(stranger.status_code, 200, stranger.content)
        self.assertIsNone(stranger.json()["combat_style"])

    def test_a_tradition_that_teaches_no_style_skips_the_step(self) -> None:
        draft = self._schooled_draft(self.plain)

        self.assertEqual(self._styles(draft), [])
        self.assertEqual(self._training_names(draft), ["Thaumaturgy"])
        total = self._detail(draft)["magic_training"]["total"]
        response = self._patch(
            draft, {"draft_data": {"magic_skills": {str(self.thaumaturgy.pk): total}}}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._gift_errors(draft), [])

        sheet = self._finalize(draft)

        self.assertIsNone(sheet.combat_style)
        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=self.thaumaturgy).value,
            total,
        )

    def test_switching_tradition_clears_a_style_it_does_not_teach(self) -> None:
        draft = self._schooled_draft(self.tradition)
        self._patch(draft, {"selected_combat_style_id": self.dance.pk})
        skill = self.dance.skill
        self._patch(draft, {"draft_data": {"magic_skills": {str(skill.pk): TRAINING_POINTS}}})

        self._select(draft, self.plain)

        detail = self._detail(draft)
        self.assertIsNone(detail["selected_combat_style"])
        self.assertNotIn(str(skill.pk), detail["draft_data"]["magic_skills"])

    def test_switching_style_drops_the_old_styles_points(self) -> None:
        draft = self._schooled_draft(self.tradition)
        self._patch(draft, {"selected_combat_style_id": self.dance.pk})
        old = self.dance.skill
        self._patch(draft, {"draft_data": {"magic_skills": {str(old.pk): TRAINING_POINTS}}})

        self._patch(draft, {"selected_combat_style_id": self.mask.pk})

        detail = self._detail(draft)
        self.assertEqual(detail["selected_combat_style"], self.mask.pk)
        self.assertNotIn(str(old.pk), detail["draft_data"]["magic_skills"])

    def test_another_styles_skill_is_refused_and_an_untaught_style_too(self) -> None:
        draft = self._schooled_draft(self.tradition)
        self._patch(draft, {"selected_combat_style_id": self.dance.pk})

        response = self._patch(
            draft,
            {"draft_data": {"magic_skills": {str(self.mask.skill.pk): TRAINING_POINTS}}},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Magic skills only", self._gift_errors(draft))

        untaught = CombatStyleFactory(name="Veil and Needle")
        refused = self._patch(draft, {"selected_combat_style_id": untaught.pk})
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn("selected_combat_style_id", refused.json())
        self.assertEqual(self._detail(draft)["selected_combat_style"], self.dance.pk)


class AskingTheSphinxAboutAStyle(JourneyCase):
    """Ysmay fights The Daring Dance and asks the Sphinx about two vows; Hobb has no style."""

    def setUp(self) -> None:
        super().setUp()
        hall = self.make_room("The Quartz Hall")
        self.ysmay = self.make_player("Ysmay", room=hall)
        self.hobb = self.make_player("Hobb", room=hall)
        self.quicksilver = CovenantRoleFactory(name="Quicksilver")
        self.bulwark = CovenantRoleFactory(name="Bulwark")
        self.dance = CombatStyleFactory(name="The Daring Dance")
        self.dance.compatible_roles.add(self.quicksilver)
        sheet = self.ysmay.sheet_data
        sheet.combat_style = self.dance
        sheet.save(update_fields=["combat_style"])

    def _verdict(self, character: ObjectDB, role) -> dict:
        client = self.api(self.account_of(character))
        response = client.get(f"/api/covenants/roles/sphinx/?role={role.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_sphinx_says_whether_the_style_suits_each_vow(self) -> None:
        self.assertEqual(
            self._verdict(self.ysmay, self.quicksilver)["style"],
            {"style_name": "The Daring Dance", "suits": True},
        )
        self.assertEqual(
            self._verdict(self.ysmay, self.bulwark)["style"],
            {"style_name": "The Daring Dance", "suits": False},
        )

        self.assertIn("Your style suits it.", self.telnet(self.ysmay, "sphinx Quicksilver"))
        self.assertIn(
            "Your style does not suit it: no style benefits while it is active.",
            self.telnet(self.ysmay, "sphinx Bulwark"),
        )

    def test_a_sub_role_counts_by_its_anchor_vow(self) -> None:
        swift = CovenantRoleFactory(name="Swift Quicksilver", parent_role=self.quicksilver)

        self.assertTrue(self._verdict(self.ysmay, swift)["style"]["suits"])

    def test_no_style_no_line(self) -> None:
        self.assertIsNone(self._verdict(self.hobb, self.bulwark)["style"])

        told = self.telnet(self.hobb, "sphinx Bulwark")
        self.assertIn("The vow will take.", told)
        self.assertNotIn("Your style", told)
