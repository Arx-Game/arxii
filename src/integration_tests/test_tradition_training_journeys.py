"""Journeys for Tradition Training teaching the Magic skills at character creation (#4457).

A living Tradition offers three schooling stances, an orphaned one the first two, a
self-taught one none; the stance a player pays for lifts every active Magic skill to its
floor when the character is made, and CG skill points can never buy a Magic skill or one
of its specializations. Driven over the REST seam the browser uses: the Tradition list,
the distinctions sync, the draft PATCH and detail, and staff adding the draft to the roster.
A finalized character's cast then rolls her Path's Magic skill at the stance floor, through
``dispatch_player_action`` on ``cast_technique`` as the web client casts.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    MAGIC_SKILL_POINTS_REFUSAL,
    OfferChapter,
    TraditionState,
)
from world.character_creation.factories import (
    BeginningTraditionFactory,
    DistinctionOfferFactory,
    SchoolingLineFactory,
)
from world.character_creation.models import DistinctionOffer
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterAnima
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import CharacterSkillValue
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    TraitCategory,
    TraitChangeSource,
    TraitType,
)
from world.vitals.models import CharacterVitals

#: Floors staff set per stance: rank 0 trains none, rank 1 a little, rank 2 more.
FLOORS = {0: 0, 1: 20, 2: 30}


class TraditionTrainingCGJourney(FinalizationTestMixin, JourneyCase):
    """A Beginning with a living Tradition, an orphaned one and a self-taught one."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(
            cls, prefix="Tradition Training", height_min=1600, height_max=1700
        )
        cls.living = TraditionFactory()
        cls.orphaned = TraditionFactory()
        cls.self_taught = TraditionFactory()
        for tradition, state in (
            (cls.living, TraditionState.LIVING_MASTERS),
            (cls.orphaned, TraditionState.TEACHERS_GONE),
            (cls.self_taught, TraditionState.SELF_TAUGHT),
        ):
            BeginningTraditionFactory(beginning=cls.beginnings, tradition=tradition, state=state)
            TraditionGiftGrantFactory(tradition=tradition, gift=cls.gift)

        # One Tradition Training distinction; each stance is a line that grants it and an
        # offer that opens it at the Tradition step.
        cls.training = DistinctionFactory(name="Tradition Training", cost_per_rank=1, max_rank=2)
        cls.offers = {}
        for rank, floor in FLOORS.items():
            line = SchoolingLineFactory(
                rank=rank,
                name=f"Stance {rank}",
                player_line="Years of it.",
                grants=cls.training,
                magic_skill_floor=floor,
            )
            cls.offers[rank] = DistinctionOfferFactory(
                distinction=cls.training,
                chapter=OfferChapter.TRADITION_STEP,
                schooling_line=line,
            )

        cls.thaumaturgy = SkillFactory(
            trait__name="Thaumaturgy", trait__category=TraitCategory.MAGIC
        )
        cls.geomancy = SkillFactory(trait__name="Geomancy", trait__category=TraitCategory.MAGIC)
        cls.hermetics = SkillFactory(trait__name="Hermetics", trait__category=TraitCategory.MAGIC)
        cls.lapsed = SkillFactory(
            trait__name="Lapsed Lore", trait__category=TraitCategory.MAGIC, is_active=False
        )
        cls.active_magic = (cls.thaumaturgy, cls.geomancy, cls.hermetics)
        cls.swordplay = SkillFactory(trait__name="Swordplay", trait__category=TraitCategory.COMBAT)
        cls.parrying = SpecializationFactory(name="Parrying", parent_skill=cls.swordplay)
        cls.wards = SpecializationFactory(name="Wards", parent_skill=cls.thaumaturgy)

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        # Staff own the drafts: add-to-roster is staff-only and a draft is owner-scoped.
        self.account = AccountFactory(is_staff=True)
        self.client = self.api(self.account)

    def _draft_url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/"

    def _select(self, draft, tradition) -> None:
        response = self.client.post(
            f"{self._draft_url(draft)}select-tradition/",
            {"tradition_id": tradition.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _sync(self, draft, rank: int):
        return self.client.put(
            f"/api/distinctions/drafts/{draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.training.pk, "rank": rank, "offer_id": self.offers[rank].pk}
                ]
            },
            format="json",
        )

    def _floor(self, draft) -> int:
        response = self.client.get(self._draft_url(draft))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["starting_magic_skill_floor"]

    def _finalize(self, draft):
        """Staff add the draft to the roster; returns the new character's sheet."""
        response = self.client.post(f"{self._draft_url(draft)}add-to-roster/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return ObjectDB.objects.get(pk=response.json()["character_id"]).sheet_data

    def test_stance_rows_show_floor_and_rank_cap(self) -> None:
        response = self.client.get(
            f"/api/character-creation/traditions/?beginning_id={self.beginnings.pk}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in response.json()}
        living = rows[self.living.pk]["schooling"]
        self.assertEqual([s["rank"] for s in living], [0, 1, 2])
        self.assertEqual([s["magic_skill_floor"] for s in living], [0, 20, 30])
        self.assertEqual([s["rank"] for s in rows[self.orphaned.pk]["schooling"]], [0, 1])
        self.assertEqual(rows[self.self_taught.pk]["schooling"], [])

    def test_rank_two_pick_finalizes_floor(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._floor(draft), 30)

        sheet = self._finalize(draft)

        for skill in self.active_magic:
            self.assertEqual(
                CharacterSkillValue.objects.get(character=sheet, skill=skill).value, 30
            )
            self.assertEqual(
                CharacterTraitValue.objects.get(character=sheet, trait=skill.trait).value, 30
            )
            change = CharacterTraitChange.objects.get(character_sheet=sheet, trait=skill.trait)
            self.assertEqual(change.source, TraitChangeSource.CHARACTER_CREATION)
        self.assertFalse(CharacterSkillValue.objects.filter(character=sheet, skill=self.lapsed))
        self.assertFalse(
            CharacterTraitValue.objects.filter(character=sheet, trait=self.lapsed.trait)
        )

    def test_orphaned_rank_one_finalizes_floor_and_rank_two_refused(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.orphaned)

        refused = self._sync(draft, 2)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn("is not offered to you here", refused.json()["detail"])

        self.assertEqual(self._sync(draft, 1).status_code, 200)
        self.assertEqual(self._floor(draft), 20)
        sheet = self._finalize(draft)
        for skill in self.active_magic:
            self.assertEqual(
                CharacterSkillValue.objects.get(character=sheet, skill=skill).value, 20
            )

    def test_switching_tradition_drops_floor(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._floor(draft), 30)

        self._select(draft, self.orphaned)
        draft.refresh_from_db()
        self.assertEqual(self._floor(draft), 0)
        self.assertNotIn(self.offers[2].pk, self._picked_offer_ids(draft))

        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._floor(draft), 30)
        self._select(draft, self.self_taught)
        self.assertEqual(self._floor(draft), 0)

    @staticmethod
    def _picked_offer_ids(draft) -> set[int]:
        draft.refresh_from_db()
        return {
            offer_id
            for entry in draft.draft_data.get("distinctions", [])
            for offer_id in entry.get("offer_ids", [])
            if isinstance(offer_id, int)
        }

    def test_self_taught_writes_no_magic_rows(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.self_taught)
        self.assertEqual(self._floor(draft), 0)

        sheet = self._finalize(draft)

        magic_ids = [skill.pk for skill in (*self.active_magic, self.lapsed)]
        self.assertFalse(
            CharacterSkillValue.objects.filter(character=sheet, skill_id__in=magic_ids)
        )

    def test_magic_points_refused_with_names(self) -> None:
        draft = self._create_base_draft()
        ordinary = {
            "skills": {str(self.swordplay.pk): 30},
            "specializations": {str(self.parrying.pk): 10},
        }
        response = self.client.patch(
            self._draft_url(draft), {"draft_data": ordinary}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        errors = response.json()["stage_errors"][str(draft.Stage.ATTRIBUTES)]
        self.assertFalse([e for e in errors if e.startswith(MAGIC_SKILL_POINTS_REFUSAL)])

        magic = {
            "skills": {str(self.swordplay.pk): 30, str(self.thaumaturgy.pk): 30},
            "specializations": {str(self.parrying.pk): 10, str(self.wards.pk): 10},
        }
        response = self.client.patch(self._draft_url(draft), {"draft_data": magic}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        errors = response.json()["stage_errors"][str(draft.Stage.ATTRIBUTES)]
        self.assertIn(f"{MAGIC_SKILL_POINTS_REFUSAL}Thaumaturgy, Wards.", errors)

    def _cast_and_read_the_roll(
        self, character: ObjectDB, technique
    ) -> tuple[tuple[ExtraTraitTerm, ...], CheckResult]:
        """Cast ``technique`` on the web seam; return the terms its roll carried and the roll."""
        rolled: list[CheckResult] = []

        def spy(*args, **kwargs) -> CheckResult:
            result = perform_check(*args, **kwargs)
            rolled.append(result)
            return result

        success = CheckOutcome.objects.get(name="Success")
        with (
            force_check_outcome(success) as capture,
            patch("actions.services.perform_check", side_effect=spy),
        ):
            outcome = self.web(character, "cast_technique", technique_id=technique.pk)
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertEqual(len(rolled), 1)
        return capture.extra_traits, rolled[0]

    def test_a_schooled_cast_rolls_its_magic_skill_at_the_stance_floor(self) -> None:
        # The CG Path's technique skill is a Magic skill, so a cast on it adds that skill.
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.path.technique_skill = self.thaumaturgy
        self.path.save(update_fields=["technique_skill"])
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        lantern = self.make_room("The Lantern")
        SceneFactory(room=lantern)

        schooled_draft = self._create_base_draft(first_name="Ysmay")
        self._select(schooled_draft, self.living)
        self.assertEqual(self._sync(schooled_draft, 1).status_code, 200)
        self_taught_draft = self._create_base_draft(first_name="Hobb")
        self._select(self_taught_draft, self.self_taught)

        casters = []
        for draft in (schooled_draft, self_taught_draft):
            sheet = self._finalize(draft)
            character = sheet.character
            character.location = lantern
            character.save()
            grant_technique(sheet.primary_persona, technique)
            CharacterAnima.objects.update_or_create(
                character=sheet, defaults={"current": 20, "maximum": 30}
            )
            CharacterVitals.objects.update_or_create(
                character_sheet=sheet,
                defaults={"health": 50, "max_health": 50, "base_max_health": 50},
            )
            casters.append(character)
        schooled, self_taught = casters

        term = ExtraTraitTerm(trait=self.thaumaturgy.trait, weight=Decimal("1.00"))
        terms, schooled_roll = self._cast_and_read_the_roll(schooled, technique)
        self.assertEqual(terms, (term,))
        terms, self_taught_roll = self._cast_and_read_the_roll(self_taught, technique)
        self.assertEqual(terms, (term,))
        self.assertFalse(
            CharacterTraitValue.objects.filter(
                character=self_taught.sheet_data, trait=self.thaumaturgy.trait
            )
        )
        self.assertEqual(schooled_roll.trait_points - self_taught_roll.trait_points, FLOORS[1])

    def test_a_stance_offer_saved_without_its_stance_is_not_offered(self) -> None:
        # Nothing in the database requires a Tradition Step offer to name a stance, so a
        # row saved without full_clean must not break the offers read for every draft.
        stranded = DistinctionOffer.objects.create(
            distinction=DistinctionFactory(name="Stranded Stance", max_rank=1),
            chapter=OfferChapter.TRADITION_STEP,
        )
        draft = self._create_base_draft()
        self._select(draft, self.living)

        response = self.client.get(f"{self._draft_url(draft)}offers/?chapter=tradition_step")

        self.assertEqual(response.status_code, 200, response.content)
        offered = {row["offer_id"] for row in response.json()["offers"]}
        self.assertEqual(offered, {offer.pk for offer in self.offers.values()})
        self.assertNotIn(stranded.pk, offered)
        listing = self.client.get(
            f"/api/character-creation/traditions/?beginning_id={self.beginnings.pk}"
        )
        self.assertEqual(listing.status_code, 200, listing.content)

        # A legacy pick of that offer, written before the offers read refused it, still
        # opens the draft, and lifts no Magic skill.
        draft.refresh_from_db()
        draft.draft_data["distinctions"] = [
            {"distinction_id": stranded.distinction_id, "rank": 1, "offer_ids": [stranded.pk]}
        ]
        draft.save(update_fields=["draft_data"])
        self.assertEqual(self._floor(draft), 0)
