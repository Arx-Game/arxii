"""The path-starter-pool required-content sentinel (#3712, ruling 1 on #3682).

Ruled on #3682: there will never be a gift a path offers nothing for, so a
`PathGiftGrant` with an empty `starter_techniques` pool for a gift a tradition
makes pickable is missing authored content. The sentinel reports it; the code
does not branch on it.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.classes.factories import PathFactory
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionGiftGrantFactory,
)


def _probe_for(key: str) -> rc.ContentProbe:
    """The shipped declaration's own probe, never a hand-copied duplicate."""
    return next(dep.probe for dep in rc._declarations() if dep.key == key)


class PathGiftStarterPoolProbeTests(TestCase):
    """Break the invariant and watch it fail, rather than only asserting the fix."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.path = PathFactory()
        cls.special = TechniqueFactory(gift=cls.gift)
        cls.starter = TechniqueFactory(gift=cls.gift)

    def _resolve(self) -> rc.ProbeResult:
        return _probe_for("path-gift-starter-pools").resolve(None)

    def test_no_tradition_offering_anything_is_not_a_gap(self) -> None:
        """Nothing pickable means nothing to be missing a pool for."""
        self.assertTrue(self._resolve().present)

    def test_gift_offered_by_tradition_with_no_path_pool_is_reported(self) -> None:
        """The gap: the gift reaches CG on the tradition alone."""
        grant = TraditionGiftGrantFactory(gift=self.gift)
        grant.special_techniques.add(self.special)

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertIn(f"{self.path.name} / {self.gift.name}", result.missing)

    def test_stocked_path_pool_closes_the_gap(self) -> None:
        """The same tradition offer, with the path pool authored, reports nothing."""
        grant = TraditionGiftGrantFactory(gift=self.gift)
        grant.special_techniques.add(self.special)
        path_grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        path_grant.starter_techniques.add(self.starter)

        self.assertTrue(self._resolve().present)

    def test_empty_path_grant_row_is_still_a_gap(self) -> None:
        """The row existing is not the pool being authored.

        The probe counts `starter_techniques`, not the presence of the grant,
        because an empty grant delivers exactly what no grant delivers.
        """
        grant = TraditionGiftGrantFactory(gift=self.gift)
        grant.special_techniques.add(self.special)
        PathGiftGrantFactory(path=self.path, gift=self.gift)

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertIn(f"{self.path.name} / {self.gift.name}", result.missing)

    def test_tradition_grant_with_no_specials_is_never_reported(self) -> None:
        """A tradition that teaches a gift and adds no extras is legitimate.

        39 of 69 authored rows are in this state; folding them in would bury the
        real gaps under false ones. Such a grant adds no availability of its own,
        so it cannot create this gap.
        """
        TraditionGiftGrantFactory(gift=self.gift)

        self.assertTrue(self._resolve().present)

    def test_declaration_is_registered_and_required_tier(self) -> None:
        dep = next(d for d in rc._declarations() if d.key == "path-gift-starter-pools")
        self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
        self.assertIn("get_technique_options", dep.consumer)
