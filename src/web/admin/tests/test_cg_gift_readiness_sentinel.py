"""The Required content dashboard sees what character creation hides (#4545).

In the 2026-10-21 production dump no technique had a cast template, so character
creation offered no gift under any tradition and path and no new character could
finish the Gift stage, while the dashboard's starter-pool row read complete: it
counted starter techniques without asking whether a player could take them.

These tests put the dashboard and the character creation catalog in the same room.
A staff member loads the dashboard as they would, follows the row's link, wires the
technique the way the Technique admin offers, and the player's gift list changes
with the dashboard.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from web.admin.tuning import required_content as rc
from world.character_creation.factories import CharacterDraftFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import PathGiftGrant, Technique
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.cg_catalog import get_gift_options
from world.progression.factories import TechniqueKnownRequirementFactory
from world.progression.services.spends import concrete_requirement_types

CG_ROW = "Gifts with nothing to take at character creation"
STARTER_ROW = "Path starter technique pools"
EFFECT_ROW = "Techniques with no cast effect"
NO_PATH_ROW = "Tradition techniques on no Path"


def _resolve(key: str) -> rc.ProbeResult:
    """The shipped declaration's own probe, never a hand-copied duplicate."""
    return next(dep.probe for dep in rc._declarations() if dep.key == key).resolve(None)


def _section(html: str, heading: str, next_heading: str) -> str:
    """The panel text between two of its headings."""
    return html.split(heading, 1)[1].split(next_heading, 1)[0]


class GiftReadinessDashboardJourney(TestCase):
    """A catalog where every pooled technique lacks a cast template, as on production."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = get_user_model().objects.create_superuser(
            "warden", "warden@example.com", "pw-123456"
        )
        cls.player = AccountFactory()
        cls.tradition = TraditionFactory(name="Order of the Quiet Lamp")
        cls.path = PathFactory(name="Path of Embers")
        cls.gift = GiftFactory(name="Ashen Voice")
        cls.starter = TechniqueFactory(name="Cinder Word", gift=cls.gift)
        cls.special = TechniqueFactory(name="Lamp Hymn", gift=cls.gift)
        PathGiftGrantFactory(path=cls.path, gift=cls.gift).starter_techniques.add(cls.starter)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift).special_techniques.add(
            cls.special
        )
        cls.draft = CharacterDraftFactory(
            account=cls.player, selected_path=cls.path, selected_tradition=cls.tradition
        )

    def _player_gifts(self) -> list[int]:
        client = APIClient()
        client.force_authenticate(user=self.player)
        response = client.get("/api/character-creation/gifts/", {"draft_id": self.draft.id})
        self.assertEqual(response.status_code, 200)
        return [row["id"] for row in response.data]

    def _missing_required(self) -> str:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(response.status_code, 200)
        return _section(response.content.decode(), "Missing - Required", "Missing - Tuning")

    def test_the_dashboard_reports_the_gift_the_player_cannot_see(self) -> None:
        self.assertEqual(self._player_gifts(), [])

        missing = self._missing_required()

        link = f'href="{reverse("admin:arxii_technique_changelist")}?authoring_gap=not_castable"'
        self.assertIn(f"{link}>{CG_ROW}</a>", missing)
        self.assertIn("blocks every new character at the Gift stage", missing)
        self.assertIn(f"{link}>{STARTER_ROW}</a>", missing)
        self.assertIn("Path of Embers / Ashen Voice", missing)
        self.assertIn("1 of them have starter techniques authored that are not ready", missing)

    def test_a_tradition_technique_on_no_path_is_reported_until_a_path_lists_it(self) -> None:
        """#4555: Lamp Hymn is listed by the tradition and by no Path, so nobody is offered it."""
        missing = self._missing_required()

        link = f'href="{reverse("admin:arxii_pathgiftgrant_changelist")}"'
        self.assertIn(f"{link}>{NO_PATH_ROW}</a>", missing)
        self.assertIn("Ashen Voice / Lamp Hymn (listed by Order of the Quiet Lamp)", missing)
        self.assertIn("so no character is ever offered them", missing)

        PathGiftGrant.objects.get(path=self.path, gift=self.gift).starter_techniques.add(
            self.special
        )

        self.assertNotIn(NO_PATH_ROW, self._missing_required())

    def test_the_row_link_lands_on_the_techniques_to_fix(self) -> None:
        self.client.force_login(self.staff)
        url = f"{reverse('admin:arxii_technique_changelist')}?authoring_gap=not_castable"

        page = self.client.get(url).content.decode()

        self.assertIn("Cinder Word", page)
        self.assertIn("Lamp Hymn", page)

    def test_wiring_the_starter_offers_the_gift_and_clears_both_rows(self) -> None:
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin:arxii_technique_changelist"),
            {"action": "wire_technique_cast_templates", "_selected_action": [self.starter.pk]},
        )
        self.assertIsNotNone(Technique.objects.get(pk=self.starter.pk).action_template_id)

        self.assertEqual(self._player_gifts(), [self.gift.id])
        missing = self._missing_required()
        self.assertNotIn(CG_ROW, missing)
        self.assertNotIn(STARTER_ROW, missing)


class GiftReadinessProbeTests(TestCase):
    """Each way a pooled technique can be untakeable, and the rows agreeing with CG."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = get_standalone_cast_template()
        cls.tradition = TraditionFactory(name="Wardens of the Ford")
        cls.path = PathFactory(name="Path of Reeds")
        cls.gift = GiftFactory(name="River Tongue")
        cls.path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        cls.tradition_grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)

    def _blocked(self) -> tuple[str, ...]:
        return _resolve("cg-gift-pools-takeable").missing

    def test_a_ready_technique_the_tradition_keeps_on_this_path_offers_the_gift(self) -> None:
        kept = TechniqueFactory(gift=self.gift, action_template=self.template)
        self.path_grant.starter_techniques.add(kept)
        self.tradition_grant.special_techniques.add(kept)

        self.assertTrue(_resolve("cg-gift-pools-takeable").present)
        self.assertEqual(get_gift_options(self.tradition, self.path), [self.gift])

    def test_a_tradition_technique_on_no_path_list_offers_nothing(self) -> None:
        """#4555: a tradition's list restricts; only a Path's list offers."""
        self.tradition_grant.special_techniques.add(
            TechniqueFactory(gift=self.gift, action_template=self.template)
        )

        self.assertEqual(self._blocked(), ("Path of Reeds / River Tongue",))
        self.assertEqual(get_gift_options(self.tradition, self.path), [])

    def test_a_pool_of_only_gated_or_ultimate_techniques_is_reported(self) -> None:
        gated = TechniqueFactory(gift=self.gift, action_template=self.template)
        TechniqueKnownRequirementFactory(technique=gated)
        self.path_grant.starter_techniques.add(gated)
        self.tradition_grant.special_techniques.add(
            UltimateTechniqueFactory(gift=self.gift, action_template=self.template)
        )

        # The requirement's own technique brings a second Major Gift with no path list,
        # which is reported too; only River Tongue's row is this test's subject.
        self.assertIn("Path of Reeds / River Tongue", self._blocked())
        self.assertEqual(get_gift_options(self.tradition, self.path), [])

    def test_a_pairing_with_another_gift_offered_is_counted_apart(self) -> None:
        other = GiftFactory(name="Stone Ear")
        PathGiftGrantFactory(path=self.path, gift=other).starter_techniques.add(
            TechniqueFactory(gift=other, action_template=self.template)
        )

        result = _resolve("cg-gift-pools-takeable")

        self.assertEqual(result.missing, ("Path of Reeds / River Tongue",))
        self.assertIn("0 tradition and path pairing(s) offer no gift at all", result.detail)

    def test_a_path_with_no_grant_for_the_gift_is_an_empty_pool(self) -> None:
        """Path of Whispers has no Radiance grant, so Radiance never reaches a Whispers
        character under any tradition, and with no other gift the pairing offers none."""
        whispers = PathFactory(name="Path of Whispers")
        radiance = GiftFactory(name="Radiance")
        PathGiftGrantFactory(path=self.path, gift=radiance).starter_techniques.add(
            TechniqueFactory(gift=radiance, action_template=self.template)
        )

        result = _resolve("cg-gift-pools-takeable")

        self.assertIn("Path of Whispers / Radiance", result.missing)
        self.assertNotIn("Path of Reeds / Radiance", result.missing)
        self.assertEqual(get_gift_options(self.tradition, whispers), [])
        self.assertEqual(get_gift_options(self.tradition, self.path), [radiance])
        self.assertIn("1 tradition and path pairing(s) offer no gift at all", result.detail)

    def test_paths_character_creation_cannot_pick_are_not_combinations(self) -> None:
        later = PathFactory(name="Path of the Delta", stage=PathStage.POTENTIAL)
        PathGiftGrantFactory(path=later, gift=self.gift)

        self.assertNotIn("Path of the Delta", " ".join(self._blocked()))

    def test_the_row_lists_exactly_the_combinations_the_catalog_hides(self) -> None:
        """Parity, with one active tradition: reported iff `get_gift_options` drops the gift."""
        second_path = PathFactory(name="Path of Willows")
        PathGiftGrantFactory(path=second_path, gift=self.gift).starter_techniques.add(
            TechniqueFactory(gift=self.gift, action_template=self.template)
        )
        self.path_grant.starter_techniques.add(TechniqueFactory(gift=self.gift))

        ungranted_path = PathFactory(name="Path of Salt")

        hidden = {
            f"{path.name} / {self.gift.name}"
            for path in (self.path, second_path, ungranted_path)
            if self.gift not in get_gift_options(self.tradition, path)
        }

        self.assertEqual(set(self._blocked()), hidden)
        self.assertEqual(
            hidden,
            {
                "Path of Reeds / River Tongue",
                "Path of Salt / River Tongue",
            },
        )

    def test_a_technique_another_tradition_keeps_does_not_offer_the_gift(self) -> None:
        """#4555: the keeper is offered the gift on this path; nobody else is. A gift a
        tradition keeps to itself is not a gap, but the pairing left with nothing is."""
        kept = TechniqueFactory(gift=self.gift, action_template=self.template)
        self.path_grant.starter_techniques.add(kept)
        keeper = TraditionFactory(name="Lanterns of the Weir")
        TraditionGiftGrantFactory(tradition=keeper, gift=self.gift).special_techniques.add(kept)

        result = _resolve("cg-gift-pools-takeable")

        self.assertEqual(result.missing, ())
        self.assertIn("1 tradition and path pairing(s) offer no gift at all", result.detail)
        self.assertEqual(get_gift_options(self.tradition, self.path), [])
        self.assertEqual(get_gift_options(keeper, self.path), [self.gift])

    def test_declarations_tiers_and_links(self) -> None:
        deps = {dep.key: dep for dep in rc._declarations()}
        self.assertEqual(deps["cg-gift-pools-takeable"].tier, rc.DependencyTier.REQUIRED)
        self.assertEqual(deps["cg-techniques-cast-effect"].tier, rc.DependencyTier.TUNING)
        for key in ("cg-gift-pools-takeable", "path-gift-starter-pools"):
            self.assertTrue(_resolve(key).admin_url.endswith("?authoring_gap=not_castable"))
        self.assertTrue(
            _resolve("cg-techniques-cast-effect").admin_url.endswith(
                "?authoring_gap=underspecified"
            )
        )

    def test_the_probe_query_count_does_not_grow_with_the_catalog(self) -> None:
        for _ in range(4):
            gift = GiftFactory()
            PathGiftGrantFactory(path=PathFactory(), gift=gift).starter_techniques.add(
                TechniqueFactory(gift=gift)
            )
            TraditionGiftGrantFactory(tradition=TraditionFactory(), gift=gift)
        # One query per requirement type for the gated ids, then five for the rest.
        with self.assertNumQueries(len(list(concrete_requirement_types())) + 5):
            _resolve("cg-gift-pools-takeable")


class TechniqueCastEffectProbeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.pooled = TechniqueFactory(name="Hollow Chant", gift=cls.gift, damage_profile=False)
        cls.loose = TechniqueFactory(name="Idle Glyph", gift=cls.gift, damage_profile=False)
        cls.effective = TechniqueFactory(name="Burning Mark", gift=cls.gift, damage_profile=False)
        TechniqueDamageProfileFactory(technique=cls.effective)
        PathGiftGrantFactory(gift=cls.gift).starter_techniques.add(cls.pooled, cls.effective)

    def test_lists_pooled_effectless_techniques_and_counts_all(self) -> None:
        result = _resolve("cg-techniques-cast-effect")

        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Hollow Chant",))
        self.assertIn("2 technique(s) have no cast effect authored", result.detail)
        self.assertIn("1 of them sit in a character creation pool", result.detail)
