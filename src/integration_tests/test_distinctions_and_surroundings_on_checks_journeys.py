"""Journeys for distinctions and scene surroundings on checks (#4638, slice 5 of #4551).

Corvin is a factor who haggles in the river market. Staff gave his distinctions' haggling
effects a size, and the market scene's surroundings a level and a size. He gains each
distinction through ``grant_distinction`` (the one acquisition seam every grant uses);
his next check, through ``perform_check_with_modifiers``, reads each sized distinction
from the modifier value table at HIS level and the effect's size, and the market's
surroundings at their authored level and size. The CHARACTER pile tapers lightly (each
extra at 7/8 of the one before, never below 2/3). The value table and the taper rows are
the example seed, so these journeys also prove the seed is coherent.

- One distinction adds the value table's number for its holder's level and its size; a
  higher-level holder of the same distinction adds more.
- Rank scales the table's number the way it scales the authored value.
- Three distinctions on one check add the tapered total.
- An unsized distinction, and an achievement reward on the same path, keep their flat
  values and still taper with the others.
- A sized penalty stays a penalty, in its own pile.
- Without a level (no class) or a value row, a sized distinction keeps its flat value.
- The market's surroundings add their table value at their own level, whoever rolls;
  unsized surroundings keep their flat value.
- Staff set an effect's size and a scene's level and size on the admin pages; Paramount
  and a half-sized surroundings row are refused.

The player's own ``check <name>`` command rolls through ``perform_check`` without gathering
modifiers, so these journeys read the check through ``perform_check_with_modifiers``, the
seam challenges, social actions and casts roll through.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from evennia.objects.models import ObjectDB

from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.modifier_models import ModifierValue
from world.checks.modifier_values import load_value_table
from world.checks.services import collect_check_modifiers, perform_check_with_modifiers
from world.checks.types import CheckResult, ModifierContribution
from world.classes.factories import CharacterClassLevelFactory
from world.distinctions.admin import DistinctionEffectInline
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.models import Distinction
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import CharacterModifier, ModifierSource
from world.scenes.admin import SceneCheckModifierInline
from world.scenes.factories import SceneFactory
from world.scenes.models import Scene, SceneCheckModifier
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.factories import StatTraitFactory

# The flat per-rank value each effect authors; a sized effect must NOT add it.
FLAT_AUTHORED = 5


class DistinctionsOnChecks(JourneyCase):
    """Corvin's distinctions at the haggling table."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        self.room = self.make_room("The River Market")
        self.haggling = CheckTypeFactory(name="Haggling")
        self.stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.haggling, trait=self.stat, weight=1)
        self.target = ModifierTargetFactory(
            name="haggling_check",
            category=ModifierCategoryFactory(name="check"),
            target_check_type=self.haggling,
        )
        self.corvin = self.factor("Corvin", level=6)
        self.table = load_value_table(ModifierLane.CHECK)

    # -- setup helpers ----------------------------------------------------------

    def factor(self, name: str, *, level: int | None) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        character.traits.set_trait_value(self.stat.name, 20)
        if level is not None:
            CharacterClassLevelFactory(character=character.sheet_data, level=level, is_primary=True)
            character.sheet_data.invalidate_class_level_cache()
        return character

    def distinction(
        self,
        name: str,
        *,
        per_rank: int = FLAT_AUTHORED,
        size: int | None = ModifierSize.LARGE,
        max_rank: int = 1,
    ) -> Distinction:
        """A distinction whose haggling effect staff authored at ``size``."""
        distinction = DistinctionFactory(name=name, slug=name.lower().replace(" ", "-"))
        distinction.max_rank = max_rank
        distinction.save(update_fields=["max_rank"])
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.target,
            value_per_rank=per_rank,
            modifier_size=size,
        )
        return distinction

    def grant(self, character: ObjectDB, distinction: Distinction) -> None:
        grant_distinction(character.sheet_data, distinction, origin=DistinctionOrigin.GM_AWARD)

    def haggle(self, character: ObjectDB) -> CheckResult:
        return perform_check_with_modifiers(character, self.haggling, target_difficulty=50)

    def gain(self, character: ObjectDB, before: CheckResult) -> int:
        return self.haggle(character).total_points - before.total_points

    def contributions(self, character: ObjectDB) -> list[ModifierContribution]:
        return collect_check_modifiers(character.sheet_data, self.haggling).contributions

    # -- journeys -----------------------------------------------------------------

    def test_one_distinction_adds_its_table_number_and_a_higher_holder_adds_more(self) -> None:
        silver_tongue = self.distinction("Silver Tongue")
        before = self.haggle(self.corvin)

        self.grant(self.corvin, silver_tongue)

        # The seed's Large modifier is worth 10 at level 6, not the flat 5.
        self.assertEqual(self.table.value(6, ModifierSize.LARGE), 10)
        self.assertEqual(self.gain(self.corvin, before), 10)
        (row,) = self.contributions(self.corvin)
        self.assertEqual(
            (row.source_kind, row.source_label, row.value, row.level, row.size),
            (ModifierSourceKind.CHARACTER, "Silver Tongue", 10, 6, ModifierSize.LARGE),
        )

        # A level-11 factor with the same distinction: Large is worth 16 there.
        maren = self.factor("Maren", level=11)
        maren_before = self.haggle(maren)
        self.grant(maren, silver_tongue)
        self.assertEqual(self.gain(maren, maren_before), 16)

    def test_rank_scales_the_table_number(self) -> None:
        fluent = self.distinction("Market Fluency", max_rank=3)
        before = self.haggle(self.corvin)

        self.grant(self.corvin, fluent)
        self.assertEqual(self.gain(self.corvin, before), 10)

        # Ranking up: rank 2 of a per-rank effect is twice its rank-1 table number.
        self.grant(self.corvin, fluent)
        self.assertEqual(self.gain(self.corvin, before), 20)

    def test_three_distinctions_taper(self) -> None:
        before = self.haggle(self.corvin)

        for name in ("Silver Tongue", "Ledger Mind", "Patient Eye"):
            self.grant(self.corvin, self.distinction(name))

        # 10 + 10 x 7/8 + 10 x (7/8)^2 = 26.4, rounded once.
        self.assertEqual(self.gain(self.corvin, before), 26)
        self.assertEqual(sorted(c.value for c in self.contributions(self.corvin)), [10, 10, 10])

    def test_unsized_rows_keep_their_flat_values_and_taper(self) -> None:
        before = self.haggle(self.corvin)
        self.grant(self.corvin, self.distinction("Old Habits", size=None))
        self.assertEqual(self.gain(self.corvin, before), FLAT_AUTHORED)

        for name in ("Silver Tongue", "Ledger Mind", "Patient Eye"):
            self.grant(self.corvin, self.distinction(name))
        # The unsized one is fourth in the pile: 26.4 + 5 x (7/8)^3 = 29.8, not 26 + 5.
        self.assertEqual(self.gain(self.corvin, before), 30)
        old_habits = next(
            c for c in self.contributions(self.corvin) if c.source_label == "Old Habits"
        )
        self.assertEqual((old_habits.value, old_habits.level, old_habits.size), (5, None, None))

        # An achievement reward reaches checks on the same CharacterModifier path: flat,
        # and fifth in the same CHARACTER pile, at the 2/3 floor: 29.76 + 3.33 = 33.1.
        CharacterModifier.objects.create(
            character=self.corvin.sheet_data,
            source=ModifierSource.objects.create(achievement_reward=True),
            target=self.target,
            value=FLAT_AUTHORED,
        )
        self.assertEqual(self.gain(self.corvin, before), 33)
        reward = next(
            c for c in self.contributions(self.corvin) if c.source_label == "Achievement reward"
        )
        self.assertEqual(
            (reward.source_kind, reward.value, reward.level),
            (ModifierSourceKind.CHARACTER, 5, None),
        )

    def test_a_sized_penalty_stays_a_penalty_in_its_own_pile(self) -> None:
        before = self.haggle(self.corvin)

        self.grant(self.corvin, self.distinction("Silver Tongue"))
        self.grant(self.corvin, self.distinction("Known Cheat", per_rank=-3))

        # +10 and -10 sit in separate piles, so neither tapers the other.
        self.assertEqual(self.gain(self.corvin, before), 0)
        self.assertEqual(sorted(c.value for c in self.contributions(self.corvin)), [-10, 10])

    def test_without_a_level_or_a_value_row_the_flat_value_stays(self) -> None:
        silver_tongue = self.distinction("Silver Tongue")
        drifter = self.factor("Drifter", level=None)
        drifter_before = self.haggle(drifter)
        self.grant(drifter, silver_tongue)
        # No class level: no level to read the table at.
        self.assertEqual(self.gain(drifter, drifter_before), FLAT_AUTHORED)

        for row in ModifierValue.objects.filter(lane=ModifierLane.CHECK):
            row.delete()
        before = self.haggle(self.corvin)
        self.grant(self.corvin, silver_tongue)
        self.assertEqual(self.gain(self.corvin, before), FLAT_AUTHORED)
        (row,) = self.contributions(self.corvin)
        self.assertEqual((row.value, row.level, row.size), (FLAT_AUTHORED, None, None))

    def test_the_distinction_list_names_the_size_not_the_flat_number(self) -> None:
        for distinction in (
            self.distinction("Silver Tongue"),
            self.distinction("Old Habits", size=None),
        ):
            # No authored description, so the list writes the effect's own line.
            for effect in distinction.effects.all():
                effect.description = ""
                effect.save(update_fields=["description"])

        response = self.api(self.account_of(self.corvin)).get("/api/distinctions/distinctions/")

        self.assertEqual(response.status_code, 200)
        summaries = {row["name"]: row["effects_summary"] for row in response.json()}
        # A sized check effect is worth its holder's level, so the list names its size.
        self.assertEqual(summaries["Silver Tongue"], [{"text": "+Large haggling_check"}])
        self.assertEqual(summaries["Old Habits"], [{"text": "+5 haggling_check"}])


class SurroundingsOnChecks(JourneyCase):
    """The river market's surroundings help whoever haggles there."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        self.room = self.make_room("The River Market")
        self.haggling = CheckTypeFactory(name="Haggling")
        stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.haggling, trait=stat, weight=1)
        self.corvin = self.make_player("Corvin", room=self.room)
        self.corvin.traits.set_trait_value(stat.name, 20)
        CharacterClassLevelFactory(character=self.corvin.sheet_data, level=6, is_primary=True)
        self.corvin.sheet_data.invalidate_class_level_cache()
        self.market = SceneFactory(name="Market Day")

    def haggle(self, scene: Scene | None) -> CheckResult:
        return perform_check_with_modifiers(
            self.corvin, self.haggling, target_difficulty=50, scene=scene
        )

    def test_sized_surroundings_add_their_table_value_at_their_own_level(self) -> None:
        SceneCheckModifier.objects.create(
            scene=self.market,
            check_type=self.haggling,
            modifier_value=FLAT_AUTHORED,
            modifier_level=11,
            modifier_size=ModifierSize.LARGE,
        )

        # Large at level 11 is 16; Corvin's own level (6) is never read.
        self.assertEqual(self.haggle(self.market).total_points - self.haggle(None).total_points, 16)
        (row,) = collect_check_modifiers(
            self.corvin.sheet_data, self.haggling, scene=self.market
        ).contributions
        self.assertEqual(
            (row.source_kind, row.source_label, row.value, row.level, row.size),
            (
                ModifierSourceKind.SCENE,
                "Scene surroundings: Market Day",
                16,
                11,
                ModifierSize.LARGE,
            ),
        )

    def test_unsized_surroundings_keep_their_flat_value(self) -> None:
        SceneCheckModifier.objects.create(
            scene=self.market, check_type=self.haggling, modifier_value=-4
        )

        self.assertEqual(self.haggle(self.market).total_points - self.haggle(None).total_points, -4)


class StaffSizeDistinctionsAndSurroundings(JourneyCase):
    """Staff author an effect's size and a scene's level and size on the admin pages."""

    def setUp(self) -> None:
        super().setUp()
        self.staff = get_user_model().objects.create_superuser("tuner", "t@example.com", "pw-12345")
        self.client.force_login(self.staff)
        self.haggling = CheckTypeFactory(name="Haggling")
        self.target = ModifierTargetFactory(
            name="haggling_check",
            category=ModifierCategoryFactory(name="check"),
            target_check_type=self.haggling,
        )
        self.request = RequestFactory().post("/")
        self.request.user = self.staff

    def test_the_distinction_page_offers_the_size_and_paramount_is_refused(self) -> None:
        distinction = DistinctionFactory(name="Silver Tongue", slug="silver-tongue")
        body = self.client.get(f"/admin/arxii/distinction/{distinction.pk}/change/").content
        self.assertIn(b"effects-0-modifier_size", body)
        self.assertIn(b"Exceptional", body)

        inline = DistinctionEffectInline(Distinction, admin.site)
        formset_class = inline.get_formset(self.request, distinction)
        prefix = formset_class.get_default_prefix()
        posted = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-target": str(self.target.pk),
            f"{prefix}-0-value_per_rank": "5",
            f"{prefix}-0-modifier_size": str(ModifierSize.PARAMOUNT),
            f"{prefix}-0-description": "Talks a price down.",
        }
        refused = formset_class(posted, instance=distinction, prefix=prefix)
        self.assertFalse(refused.is_valid())
        self.assertIn(
            "Paramount is reached only through a vow's size step.",
            refused.forms[0].errors["modifier_size"],
        )
        posted[f"{prefix}-0-modifier_size"] = str(ModifierSize.LARGE)
        accepted = formset_class(posted, instance=distinction, prefix=prefix)
        self.assertTrue(accepted.is_valid(), accepted.errors)

    def test_the_scene_page_offers_level_and_size_and_refuses_half_a_pair(self) -> None:
        scene = SceneFactory(name="Market Day")
        body = self.client.get(f"/admin/arxii/scene/{scene.pk}/change/").content
        self.assertIn(b"check_modifiers-__prefix__-modifier_level", body)
        self.assertIn(b"check_modifiers-__prefix__-modifier_size", body)

        inline = SceneCheckModifierInline(Scene, admin.site)
        formset_class = inline.get_formset(self.request, scene)
        prefix = formset_class.get_default_prefix()
        posted = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-check_type": str(self.haggling.pk),
            f"{prefix}-0-modifier_value": "5",
            f"{prefix}-0-modifier_level": "11",
        }
        half = formset_class(posted, instance=scene, prefix=prefix)
        self.assertFalse(half.is_valid())
        self.assertIn("modifier_size", half.forms[0].errors)

        posted[f"{prefix}-0-modifier_size"] = str(ModifierSize.PARAMOUNT)
        paramount = formset_class(posted, instance=scene, prefix=prefix)
        self.assertFalse(paramount.is_valid())

        posted[f"{prefix}-0-modifier_size"] = str(ModifierSize.LARGE)
        accepted = formset_class(posted, instance=scene, prefix=prefix)
        self.assertTrue(accepted.is_valid(), accepted.errors)
