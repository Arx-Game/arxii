"""Sample content may only ever be invented into an empty content universe (#3017).

``assert_sampling_allowed()`` (``world.seeds.sample_content``) is the hard gate:
called by ``seed_dev_database()`` right after the content load and before the
cluster-seeder loop, it refuses to let ``SEED_SAMPLE_CONTENT`` invent rows once
any ``CONTENT_MODELS`` table has ever gained a row - whether that row was
authored (loaded from a real content repo checkout) or came from the SAME call's
own content load (a stub or starter content root). Without this, sample rows can
mix into a real content universe indistinguishably from authored ones, which is
exactly how twelve invented resonances shipped into the lore corpus as if
authored (see ADR-0191).
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from core_management.content_fixtures import ContentError
from world.contributors.models import ContentContributor
from world.projects.models import ContributionMethod
from world.seeds.database import seed_dev_database
from world.seeds.sample_content import assert_sampling_allowed
from world.seeds.tests.content_stub import stub_content_root


class AssertSamplingAllowedTests(TestCase):
    """Unit coverage of the gate function itself, independent of the press."""

    def test_sampling_off_never_raises(self) -> None:
        # SEED_SAMPLE_CONTENT defaults off; content rows present or not, the
        # gate is a no-op when sampling itself is not enabled.
        ContentContributor.objects.create(name="Someone Credited")
        assert_sampling_allowed()  # must not raise

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_sampling_on_empty_universe_passes(self) -> None:
        # No CONTENT_MODELS rows exist anywhere - the universe is empty, so
        # sampling is allowed.
        assert_sampling_allowed()  # must not raise

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_sampling_with_existing_content_rows_raises(self) -> None:
        ContentContributor.objects.create(name="Someone Credited")

        with self.assertRaises(ContentError) as ctx:
            assert_sampling_allowed()

        message = str(ctx.exception)
        self.assertIn("contributors.contentcontributor", message)
        self.assertNotIn("?", message)
        self.assertNotIn("—", message)


class PressWithSamplingAndLoadedContentTests(TestCase):
    """Integration: the full Big Button refuses to mix sampling with a real load."""

    @override_settings(SEED_SAMPLE_CONTENT=True)
    @stub_content_root()
    def test_press_with_sampling_and_loaded_content_raises(self) -> None:
        with self.assertRaises(ContentError):
            seed_dev_database()

        # The gate fires between the content load and the cluster loop, so no
        # cluster seeder ran at all - ContributionMethod (created only by the
        # war-funding cluster seeder, never by the content load) stays empty.
        self.assertFalse(ContributionMethod.objects.exists())
