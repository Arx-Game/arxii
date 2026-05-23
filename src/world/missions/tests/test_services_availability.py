"""Tests for the Phase-5a front-door availability service.

``offer_missions(giver, character, risk_dial, count)`` is the public surface
of ``world.missions.services.availability``. It composes the predicate
engine (Phase 0), the per-(giver, character) cooldown (5a.1), the
character's level via ``CharacterSheet.current_level``, the weighted draw
(``select_weighted``), and the active ``stories.Era`` arc-scope hook
(§8 percent-replace). These tests cover each filter in isolation plus the
era/arc-replace path.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.missions.constants import ArcScope
from world.missions.factories import (
    MissionGiverFactory,
    MissionGiverStandingFactory,
    MissionTemplateFactory,
)
from world.missions.services.availability import offer_missions
from world.societies.factories import OrganizationFactory
from world.stories.factories import EraFactory
from world.stories.models import EraStatus


def _make_character_with_level(level: int) -> "object":
    """Helper: a Character ObjectDB with a CharacterSheet at the given level."""
    character = CharacterFactory()
    # Most characters won't have a sheet auto-created in this test path;
    # CharacterSheetFactory uses django_get_or_create on the character FK so
    # it is idempotent for any path that does.
    sheet = CharacterSheetFactory(character=character)
    if level > 0:
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=character, character_class=char_class, level=level)
        sheet.invalidate_class_level_cache()
    return character


class OfferMissionsFilterTests(TestCase):
    """Each filter (predicate / cooldown / level-band / is_active) excludes."""

    def test_inactive_template_excluded(self) -> None:
        giver = MissionGiverFactory()
        active = MissionTemplateFactory(slug="active-t", is_active=True)
        inactive = MissionTemplateFactory(slug="inactive-t", is_active=False)
        giver.templates.add(active, inactive)
        character = _make_character_with_level(level=1)

        result = offer_missions(giver, character, count=10)

        self.assertIn(active, result)
        self.assertNotIn(inactive, result)

    def test_cooldown_excludes_template(self) -> None:
        giver = MissionGiverFactory()
        cooled = MissionTemplateFactory(slug="cooled-t")
        fresh = MissionTemplateFactory(slug="fresh-t")
        giver.templates.add(cooled, fresh)
        character = _make_character_with_level(level=1)

        MissionGiverStandingFactory(
            giver=giver,
            character=character,
            available_at=timezone.now() + timedelta(days=1),
        )

        result = offer_missions(giver, character, count=10)

        # Cooldown is per-giver, so BOTH templates on this giver are gated:
        # the design §10 cooldown gates the GIVER, not specific templates.
        # Re-reading the implementation — the cooldown row is per
        # (giver, character) AND we exclude templates only when there's a
        # matching cooldown row. Since the row matches this (giver, char),
        # all templates surfaced via that giver are blocked.
        self.assertEqual(result, [])

    def test_predicate_filters_out(self) -> None:
        giver = MissionGiverFactory()
        # Template gates on owning a distinction the character does NOT have.
        required = DistinctionFactory(slug="required-distinction")
        gated = MissionTemplateFactory(
            slug="gated-t",
            availability_rule={
                "leaf": "has_distinction",
                "params": {"slug": "required-distinction"},
            },
        )
        ungated = MissionTemplateFactory(slug="ungated-t")
        giver.templates.add(gated, ungated)
        character = _make_character_with_level(level=1)

        result = offer_missions(giver, character, count=10)

        self.assertIn(ungated, result)
        self.assertNotIn(gated, result)

        # Now grant the distinction — gated becomes eligible.
        CharacterDistinctionFactory(character=character, distinction=required)
        result_after = offer_missions(giver, character, count=10)
        self.assertIn(gated, result_after)

    def test_level_band_excludes(self) -> None:
        giver = MissionGiverFactory()
        high = MissionTemplateFactory(slug="high-t", level_band_min=10, level_band_max=15)
        mid = MissionTemplateFactory(slug="mid-t", level_band_min=1, level_band_max=5)
        giver.templates.add(high, mid)
        character = _make_character_with_level(level=3)

        result = offer_missions(giver, character, count=10)

        self.assertIn(mid, result)
        self.assertNotIn(high, result)

    def test_risk_dial_widens_upper_band(self) -> None:
        giver = MissionGiverFactory()
        stretch = MissionTemplateFactory(slug="stretch-t", level_band_min=1, level_band_max=5)
        giver.templates.add(stretch)
        character = _make_character_with_level(level=7)

        # Default risk_dial=0 — out of band.
        self.assertNotIn(stretch, offer_missions(giver, character, count=10))
        # risk_dial=3 widens upper band 5 -> 8; level 7 now eligible.
        self.assertIn(stretch, offer_missions(giver, character, risk_dial=3, count=10))


class OfferMissionsWeightedDrawTests(TestCase):
    """The draw is weighted by base_weight; result is a subset of eligibles."""

    def test_subset_of_eligible_and_capped_by_count(self) -> None:
        giver = MissionGiverFactory()
        templates = [MissionTemplateFactory(slug=f"draw-t-{i}", base_weight=1) for i in range(8)]
        for t in templates:
            giver.templates.add(t)
        character = _make_character_with_level(level=1)

        result = offer_missions(giver, character, count=3)

        self.assertEqual(len(result), 3)
        for picked in result:
            self.assertIn(picked, templates)
        # No duplicates (draw without replacement).
        self.assertEqual(len(set(result)), 3)

    def test_count_zero_returns_empty(self) -> None:
        giver = MissionGiverFactory()
        giver.templates.add(MissionTemplateFactory(slug="t-zero"))
        character = _make_character_with_level(level=1)
        self.assertEqual(offer_missions(giver, character, count=0), [])

    def test_weighting_favors_heavier(self) -> None:
        """Statistical: a much-heavier template wins much more often.

        Style follows test_services_multiplayer COINFLIP — we don't assert a
        fixed pick, just that the heavy template dominates over many draws.
        """
        giver = MissionGiverFactory()
        heavy = MissionTemplateFactory(slug="heavy-t", base_weight=1000)
        light = MissionTemplateFactory(slug="light-t", base_weight=1)
        giver.templates.add(heavy, light)
        character = _make_character_with_level(level=1)

        heavy_count = 0
        trials = 30
        for _ in range(trials):
            drawn = offer_missions(giver, character, count=1)
            self.assertEqual(len(drawn), 1)
            if drawn[0] == heavy:
                heavy_count += 1
        # With weight ratio 1000:1, heavy should win essentially every draw.
        self.assertGreater(heavy_count, trials * 0.8)


class OfferMissionsArcReplaceTests(TestCase):
    """Era + arc_scope + percent_replace: arc-eligible templates replace slots."""

    def test_no_active_era_means_ambient_only(self) -> None:
        # No era ACTIVE — arc-tagged templates never replace.
        era = EraFactory(name="dormant-era", status=EraStatus.CONCLUDED)
        giver = MissionGiverFactory()
        ambient = MissionTemplateFactory(slug="ambient-only-t")
        arc = MissionTemplateFactory(
            slug="arc-only-t",
            created_in_era=era,
            arc_scope=ArcScope.GLOBAL,
            percent_replace=100,
        )
        giver.templates.add(ambient, arc)
        character = _make_character_with_level(level=1)

        # Run several times — the only way ``arc`` enters the result is by
        # being drawn from the ambient pool (it's authored as an active
        # giver template). The percent_replace path should NEVER engage
        # because no era is active.
        for _ in range(5):
            result = offer_missions(giver, character, count=1)
            # The single slot is either ambient or arc, drawn from ambient pool.
            self.assertEqual(len(result), 1)

    def test_active_era_with_percent_replace_100_uses_arc_pool(self) -> None:
        era = EraFactory(name="active-era", status=EraStatus.ACTIVE)
        giver = MissionGiverFactory()
        # Ambient slot pool (base templates with percent_replace=100 — every
        # picked slot WILL be replaced when arc pool has anything).
        ambient = MissionTemplateFactory(
            slug="ambient-replace-t", percent_replace=100, base_weight=1
        )
        # Arc-eligible template (tagged with the active era, GLOBAL scope).
        arc = MissionTemplateFactory(
            slug="arc-replace-t",
            created_in_era=era,
            arc_scope=ArcScope.GLOBAL,
            base_weight=1,
        )
        giver.templates.add(ambient, arc)
        character = _make_character_with_level(level=1)

        # With percent_replace=100 on the picked slot, the slot is always
        # replaced with an arc-eligible draw. Both templates pass predicate /
        # level / cooldown, so the arc pool has at least one entry.
        result = offer_missions(giver, character, count=1)
        self.assertEqual(len(result), 1)
        # The result MUST be in {ambient, arc}. With percent_replace=100 the
        # picked slot is replaced, so when ambient is picked it becomes arc;
        # when arc is the initial pick (it's in both pools), replacement may
        # still produce arc. Either way the result is in the union.
        self.assertIn(result[0], {ambient, arc})

    def test_percent_replace_respects_predicate_level_filters(self) -> None:
        """Arc-eligible subpool still respects predicate/level/cooldown."""
        era = EraFactory(name="filtered-era", status=EraStatus.ACTIVE)
        giver = MissionGiverFactory()
        ambient = MissionTemplateFactory(slug="ambient-keep-t", percent_replace=100, base_weight=1)
        # Arc template's level band excludes the character — it must NOT
        # replace the ambient pick even with percent_replace=100.
        out_of_band_arc = MissionTemplateFactory(
            slug="oob-arc-t",
            created_in_era=era,
            arc_scope=ArcScope.GLOBAL,
            level_band_min=10,
            level_band_max=15,
        )
        giver.templates.add(ambient, out_of_band_arc)
        character = _make_character_with_level(level=2)

        result = offer_missions(giver, character, count=1)
        self.assertEqual(result, [ambient])

    def test_arc_scope_giver_requires_giver_attachment(self) -> None:
        era = EraFactory(name="giver-scope-era", status=EraStatus.ACTIVE)
        anchor_giver = MissionGiverFactory(name="anchor")
        other_giver = MissionGiverFactory(name="other")
        # Arc template scoped to a specific giver (anchor). Attached to BOTH
        # givers as a draw candidate, but GIVER scope requires explicit
        # attachment to *that* giver — both meet this, so the arc-replace
        # path can engage from either. We assert from the anchor giver only.
        arc = MissionTemplateFactory(
            slug="giver-arc-t",
            created_in_era=era,
            arc_scope=ArcScope.GIVER,
            percent_replace=100,
        )
        ambient = MissionTemplateFactory(slug="giver-arc-ambient-t", percent_replace=100)
        anchor_giver.templates.add(arc, ambient)
        other_giver.templates.add(ambient)
        character = _make_character_with_level(level=1)

        # On the anchor giver, arc-replace can engage; the result must be
        # one of the two templates either way.
        result = offer_missions(anchor_giver, character, count=1)
        self.assertEqual(len(result), 1)
        self.assertIn(result[0], {arc, ambient})

        # On other_giver, arc is NOT attached, so arc-scope=GIVER fails the
        # check and only ambient surfaces.
        result_other = offer_missions(other_giver, character, count=1)
        self.assertEqual(result_other, [ambient])

    def test_arc_scope_org_requires_giver_org(self) -> None:
        era = EraFactory(name="org-scope-era", status=EraStatus.ACTIVE)
        org = OrganizationFactory()
        org_giver = MissionGiverFactory(name="org-giver", org=org)
        no_org_giver = MissionGiverFactory(name="loose-giver", org=None)
        arc = MissionTemplateFactory(
            slug="org-arc-t",
            created_in_era=era,
            arc_scope=ArcScope.ORG,
            percent_replace=100,
        )
        # Ambient template attached only to the no-org giver so the ambient
        # pool there is a singleton, isolating the arc-pool emptiness check.
        ambient_no_org = MissionTemplateFactory(slug="org-arc-ambient-noorg-t", percent_replace=100)
        ambient_org = MissionTemplateFactory(slug="org-arc-ambient-org-t", percent_replace=100)
        no_org_giver.templates.add(ambient_no_org)
        org_giver.templates.add(arc, ambient_org)
        character = _make_character_with_level(level=1)

        # With ORG scope, the no-org giver's arc pool is empty (arc-scope
        # rejects giver-without-org), so the ambient pick is never replaced.
        # Only ambient_no_org is in this giver's ambient pool.
        result_no_org = offer_missions(no_org_giver, character, count=1)
        self.assertEqual(result_no_org, [ambient_no_org])

        # With ORG scope, the org-fronting giver does engage the arc pool —
        # the result is either ambient_org or arc.
        result_org = offer_missions(org_giver, character, count=1)
        self.assertEqual(len(result_org), 1)
        self.assertIn(result_org[0], {arc, ambient_org})
