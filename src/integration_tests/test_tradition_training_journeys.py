"""Journeys for Tradition Training teaching the Magic skills at character creation.

A living Tradition offers three schooling stances, an orphaned one the first two, a
self-taught one none (#4457); the stance a player pays for gives Magic training points
(its distinction's ``magic_training_points`` effect at the stance's rank, slice 2 of
#4659) that the player spends on Magic skills, and CG skill points can never buy a Magic
skill or one of its specializations. Driven over the REST seam the browser uses: the
Tradition list, the distinctions sync, the draft PATCH and detail, and staff adding the
draft to the roster. A finalized character's cast then rolls her Path's Magic skill at the
value she allocated, through ``dispatch_player_action`` on ``cast_technique`` as the web
client casts.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    MAGIC_SKILL_POINTS_REFUSAL,
    MAGIC_TRAINING_POINTS_TARGET,
    ApplicationStatus,
    OfferChapter,
    TraditionState,
)
from world.character_creation.factories import (
    BeginningTraditionFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    DraftApplicationFactory,
    SchoolingLineFactory,
)
from world.character_creation.models import CharacterDraft, DistinctionOffer
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.classes.factories import PathFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterAnima, Resonance
from world.magic.seeds_cast import get_standalone_cast_template
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import (
    SkillFactory,
    SkillPointBudgetFactory,
    SpecializationFactory,
)
from world.skills.models import CharacterSkillValue, SkillPointBudget
from world.traits.factories import CheckSystemSetupFactory, SkillTraitFactory, StatTraitFactory
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

#: Magic training points per rank of Tradition Training: rank 1 gives 20, rank 2 gives 40.
POINTS_PER_RANK = 20


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
        # Each rank of Tradition Training also adds Magic training points to spend (#4659).
        pool_target = ModifierTargetFactory(
            name=MAGIC_TRAINING_POINTS_TARGET,
            category=ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY),
        )
        DistinctionEffectFactory(
            distinction=cls.training, target=pool_target, value_per_rank=POINTS_PER_RANK
        )
        SkillPointBudgetFactory(pk=1)
        cls.offers = {}
        for rank in (0, 1, 2):
            line = SchoolingLineFactory(
                rank=rank,
                name=f"Stance {rank}",
                player_line="Years of it.",
                grants=cls.training,
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

    def _training_base(self, draft) -> int:
        """The draft's Magic training points from its distinctions, before fit bonuses."""
        response = self.client.get(self._draft_url(draft))
        self.assertEqual(response.status_code, 200, response.content)
        return sum(source["points"] for source in response.json()["magic_training"]["base_sources"])

    def _finalize(self, draft):
        """Staff add the draft to the roster; returns the new character's sheet."""
        response = self.client.post(f"{self._draft_url(draft)}add-to-roster/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return ObjectDB.objects.get(pk=response.json()["character_id"]).sheet_data

    def test_stance_rows_show_training_points_and_rank_cap(self) -> None:
        response = self.client.get(
            f"/api/character-creation/traditions/?beginning_id={self.beginnings.pk}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in response.json()}
        living = rows[self.living.pk]["schooling"]
        self.assertEqual([s["rank"] for s in living], [0, 1, 2])
        self.assertEqual([s["training_points"] for s in living], [0, 20, 40])
        self.assertNotIn("magic_skill_floor", living[0])
        self.assertEqual([s["rank"] for s in rows[self.orphaned.pk]["schooling"]], [0, 1])
        self.assertEqual(rows[self.self_taught.pk]["schooling"], [])

    def _allocate_pool(self, draft, skill) -> int:
        """Put the draft's whole Magic training pool on ``skill`` (the Gift stage's PATCH)."""
        draft.refresh_from_db()
        total = draft.magic_training_pool.total
        # Past one skill's ceiling the rest goes on a second Magic skill.
        cap = SkillPointBudget.get_active_budget().max_skill_value
        spread = {str(skill.pk): min(total, cap)}
        if total > cap:
            spread[str(self.hermetics.pk)] = total - cap
        response = self.client.patch(
            self._draft_url(draft),
            {"draft_data": {"magic_skills": spread}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return total

    def test_rank_two_pick_finalizes_the_allocation(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._training_base(draft), 40)
        # The breakdown line names the rank held: "Tradition Training, rank 2" (#4659).
        sources = self.client.get(self._draft_url(draft)).json()["magic_training"]["base_sources"]
        self.assertEqual(
            [(s["name"], s["rank"], s["points"], s["show_rank"]) for s in sources],
            [(self.training.name, 2, 40, True)],
        )

        total = self._allocate_pool(draft, self.thaumaturgy)
        self.assertGreater(total, 0)

        sheet = self._finalize(draft)

        held = {
            row.skill_id: row.value for row in CharacterSkillValue.objects.filter(character=sheet)
        }
        self.assertEqual(sum(held.values()), total)
        self.assertIn(held[self.thaumaturgy.pk], range(1, total + 1))
        skill = self.thaumaturgy
        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=skill.trait).value,
            held[skill.pk],
        )
        change = CharacterTraitChange.objects.get(character_sheet=sheet, trait=skill.trait)
        self.assertEqual(change.source, TraitChangeSource.CHARACTER_CREATION)
        # Only allocated Magic skills are written; nothing lifts the rest.
        self.assertFalse(
            CharacterSkillValue.objects.filter(
                character=sheet, skill__in=[self.geomancy, self.lapsed]
            )
        )

    def test_orphaned_rank_one_finalizes_the_allocation_and_rank_two_refused(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.orphaned)

        refused = self._sync(draft, 2)
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn("is not offered to you here", refused.json()["detail"])

        self.assertEqual(self._sync(draft, 1).status_code, 200)
        self.assertEqual(self._training_base(draft), 20)
        total = self._allocate_pool(draft, self.geomancy)
        sheet = self._finalize(draft)
        self.assertEqual(
            CharacterSkillValue.objects.get(character=sheet, skill=self.geomancy).value, total
        )

    def test_switching_tradition_drops_training(self) -> None:
        draft = self._create_base_draft()
        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._training_base(draft), 40)

        self._select(draft, self.orphaned)
        draft.refresh_from_db()
        self.assertEqual(self._training_base(draft), 0)
        self.assertNotIn(self.offers[2].pk, self._picked_offer_ids(draft))

        self._select(draft, self.living)
        self.assertEqual(self._sync(draft, 2).status_code, 200)
        self.assertEqual(self._training_base(draft), 40)
        self._select(draft, self.self_taught)
        self.assertEqual(self._training_base(draft), 0)

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
        self.assertEqual(self._training_base(draft), 0)

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

    def test_a_schooled_cast_rolls_its_magic_skill_at_the_allocated_value(self) -> None:
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

        allocated = self._allocate_pool(schooled_draft, self.thaumaturgy)
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
        self.assertEqual(schooled_roll.trait_points - self_taught_roll.trait_points, allocated)

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
        # opens the draft, and gives no Magic training points.
        draft.refresh_from_db()
        draft.draft_data["distinctions"] = [
            {"distinction_id": stranded.distinction_id, "rank": 1, "offer_ids": [stranded.pk]}
        ]
        draft.save(update_fields=["draft_data"])
        self.assertEqual(self._training_base(draft), 0)


class MagicTrainingAllocationJourney(JourneyCase):
    """A player spends the Magic training pool on the Gift stage over the draft API."""

    @classmethod
    def setUpTestData(cls) -> None:
        category = ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY)
        target = ModifierTargetFactory(name=MAGIC_TRAINING_POINTS_TARGET, category=category)
        SkillPointBudgetFactory(pk=1)
        training = DistinctionFactory(name="Tradition Training")
        DistinctionEffectFactory(distinction=training, target=target, value_per_rank=30)
        path = PathFactory()
        gift = GiftFactory()
        tradition = TraditionFactory()
        PathGiftGrantFactory(path=path, gift=gift).starter_techniques.set(
            [TechniqueFactory(gift=gift, action_template=get_standalone_cast_template())]
        )
        technique = gift.techniques.first()
        cls.skills = [
            SkillFactory(trait=SkillTraitFactory(category=TraitCategory.MAGIC)) for _ in range(3)
        ]
        cls.account = AccountFactory()
        cls.resonance = ResonanceFactory()
        cls.path, cls.tradition = path, tradition
        cls.draft_data = {
            "distinctions": [{"distinction_id": training.pk, "rank": 1}],
            "selected_gift_id": gift.pk,
            "selected_technique_ids": [technique.pk],
            "selected_gift_resonance_id": cls.resonance.pk,
            "anima_check_stat_id": StatTraitFactory(name="strength").pk,
            "anima_check_skill_id": SkillFactory().pk,
        }
        cls.draft = cls._new_draft()

    @classmethod
    def _new_draft(cls, **drop: bool) -> CharacterDraft:
        data = {key: value for key, value in cls.draft_data.items() if key not in drop}
        return CharacterDraftFactory(
            account=cls.account,
            selected_path=cls.path,
            selected_tradition=cls.tradition,
            draft_data=data,
        )

    def _patch(self, magic_skills: dict[str, int]) -> dict:
        client = self.api(self.account)
        url = f"/api/character-creation/drafts/{self.draft.pk}/"
        response = client.patch(url, {"draft_data": {"magic_skills": magic_skills}}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return client.get(url).json()

    def test_allocation_shows_in_payload_and_gates_the_gift_stage(self) -> None:
        first, second, _third = (str(skill.pk) for skill in self.skills)
        stage = str(CharacterDraft.Stage.GIFT)

        body = self._patch({first: 20})
        self.assertEqual(body["magic_training"]["total"], 30)
        # The block steps by the active budget's tier, never a hard-coded 10.
        self.assertEqual(body["magic_training"]["step"], 10)
        # A one-rank distinction is named without its rank ("Tradition Training").
        self.assertEqual([s["show_rank"] for s in body["magic_training"]["base_sources"]], [False])
        self.assertEqual(body["magic_training"]["allocated"], 20)
        self.assertEqual(
            body["stage_errors"][stage], ["Spend all of your magical training: 10 left"]
        )

        body = self._patch({first: 20, second: 10})
        self.assertEqual(body["magic_training"]["allocated"], 30)
        self.assertEqual(body["stage_errors"][stage], [])
        values = {s["id"]: s["value"] for s in body["magic_training"]["skills"]}
        self.assertEqual(values[self.skills[0].pk], 20)
        self.assertEqual(values[self.skills[2].pk], 0)

    def test_resonance_picker_lists_rows_a_player_can_save(self) -> None:
        """The Gift stage's Resonance step: list resonances, save one, the error clears."""
        draft = self._new_draft(selected_gift_resonance_id=True)
        client = self.api(self.account)
        url = f"/api/character-creation/drafts/{draft.pk}/"
        stage = str(CharacterDraft.Stage.GIFT)
        self.assertIn("Select a gift resonance", client.get(url).json()["stage_errors"][stage])

        listed = client.get("/api/magic/resonances/")
        self.assertEqual(listed.status_code, 200, listed.content)
        rows = {row["id"]: row for row in listed.json()}
        self.assertEqual(set(rows), set(Resonance.objects.values_list("pk", flat=True)))
        self.assertEqual(rows[self.resonance.pk]["affinity_name"], self.resonance.affinity.name)

        response = client.patch(
            url, {"draft_data": {"selected_gift_resonance_id": self.resonance.pk}}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        errors = client.get(url).json()["stage_errors"][stage]
        self.assertNotIn("Select a gift resonance", errors)

    def test_resubmit_refuses_a_draft_that_cannot_submit(self) -> None:
        """Revisions that leave the training pool unspent cannot be resubmitted."""
        draft = self._new_draft()
        application = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        client = self.api(self.account)
        url = f"/api/character-creation/drafts/{draft.pk}/"
        stage = str(CharacterDraft.Stage.GIFT)
        self.assertEqual(
            client.get(url).json()["stage_errors"][stage],
            ["Spend all of your magical training: 30 left"],
        )

        response = client.post(f"{url}resubmit/", {}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["detail"], "Draft is not complete enough to submit.")
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.REVISIONS_REQUESTED)
