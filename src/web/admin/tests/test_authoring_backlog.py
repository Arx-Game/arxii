"""Tests for the authoring backlog data tier (#3019).

Uses real credited models directly - ``Trait`` (single prose field, mirrors
``test_prose_credits.py``'s pattern), ``ItemTemplate`` (a builder-domain model
outside ``CONTENT_MODELS``, proving the mixin-iteration path pulls it in
anyway), ``TarotCard`` (two prose fields on one row, for the word-count
summation check), ``Beginnings`` (an FK-typed natural-key field,
``starting_area``, for the identity-display fix), and ``ChallengeApproach``
(both of its natural-key fields are FK-typed, for the one-query-per-model
check on a composite key needing two spans). No other credited model gets a
row anywhere in this file, so any domain not named here contributes zero rows
and therefore no ``DomainStats`` entry - that absence is itself an assertion
in ``test_domain_with_zero_rows_has_no_stats_entry``.
"""

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from web.admin.authoring.backlog import _rows_for_model, build_backlog
from world.character_creation.factories import BeginningsFactory, StartingAreaFactory
from world.contributors.factories import ContentContributorFactory
from world.items.factories import ItemTemplateFactory
from world.mechanics.factories import ChallengeApproachFactory
from world.mechanics.models import ChallengeApproach
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import Trait, TraitCategory, TraitType


class BuildBacklogTests(TestCase):
    """One flat worst-first queue across every credited content model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = ContentContributorFactory(name="Writer")
        cls.reviewer = ContentContributorFactory(name="Reviewer")

    def _trait(
        self, name: str, description: str, *, written: bool = False, reviewed: bool = False
    ) -> Trait:
        return Trait.objects.create(
            name=name,
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description=description,
            written_by=self.writer if written else None,
            written_on=date(2026, 8, 4) if written else None,
            reviewed_by=self.reviewer if reviewed else None,
            reviewed_on=date(2026, 8, 5) if reviewed else None,
        )

    def test_full_sort_key_across_every_tier(self):
        # (not has_placeholder, written, reviewed, domain, identity.lower()):
        # placeholder-marked rows first regardless of credit, then unwritten,
        # then unreviewed, then domain, then identity - all six rows below
        # land in a different tier boundary from their neighbor.
        self._trait("Alpha Placeholder", "PLACEHOLDER text here.")
        self._trait("Zeta Placeholder Written", "PLACEHOLDER also here.", written=True)
        ItemTemplateFactory(name="Aardvark Cloak", description="Ordinary described cloak here.")
        self._trait("Beta Regular", "Ordinary finished prose here.")
        self._trait("Charlie Regular Written", "Charlie is finished writing.", written=True)
        self._trait(
            "Delta Regular Written Reviewed",
            "Another finished prose piece done.",
            written=True,
            reviewed=True,
        )

        rows, _ = build_backlog()
        identities = [
            r.identity for r in rows if r.model_label in {"traits.Trait", "items.ItemTemplate"}
        ]
        self.assertEqual(
            identities,
            [
                "Alpha Placeholder",
                "Zeta Placeholder Written",
                "Aardvark Cloak",
                "Beta Regular",
                "Charlie Regular Written",
                "Delta Regular Written Reviewed",
            ],
        )

    def test_placeholder_row_sorts_first_even_when_fully_credited(self):
        self._trait("Finished Row", "Done and reviewed prose here.", written=True, reviewed=True)
        self._trait(
            "Placeholder Row",
            "PLACEHOLDER prose, still credited.",
            written=True,
            reviewed=True,
        )

        rows, _ = build_backlog()
        trait_rows = [r for r in rows if r.model_label == "traits.Trait"]
        self.assertEqual(trait_rows[0].identity, "Placeholder Row")
        self.assertTrue(trait_rows[0].has_placeholder)
        self.assertTrue(trait_rows[0].written)
        self.assertTrue(trait_rows[0].reviewed)

    def test_word_count_sums_across_every_prose_field_on_the_model(self):
        card = TarotCard.objects.create(
            name="The Test Card",
            arcana_type=ArcanaType.MAJOR,
            latin_name="Testus",
            rank=0,
            description="One two three",
            description_reversed="Four five",
        )

        rows, _ = build_backlog()
        row = next(r for r in rows if r.model_label == "tarot.TarotCard" and r.pk == card.pk)
        self.assertEqual(row.words, 5)

    def test_item_template_rows_appear_via_mixin_iteration(self):
        ItemTemplateFactory(name="Mixin Cloak", description="A cloak proving mixin iteration.")

        rows, _ = build_backlog()
        labels = {r.model_label for r in rows}
        self.assertIn("items.ItemTemplate", labels)

    def test_fk_natural_key_field_shows_related_name_not_raw_pk(self):
        area = StartingAreaFactory(name="The Sleeper's Rest")
        BeginningsFactory(
            starting_area=area,
            name="Sleeper",
            description="Ordinary finished worldbuilding text for this path.",
        )

        rows, _ = build_backlog()
        row = next(r for r in rows if r.model_label == "character_creation.Beginnings")
        self.assertEqual(row.identity, "The Sleeper's Rest, Sleeper")

    def test_fk_span_preserves_one_query_per_model(self):
        # ChallengeApproach's natural key is (challenge_template, application) and
        # BOTH fields are FK-typed - challenge_template spans to
        # ChallengeTemplate.name, application spans to Application.name. Calling
        # `_rows_for_model` directly (rather than the full `build_backlog`, which
        # would also fire one query per *other* credited model) isolates exactly
        # the query this one model's scan issues.
        ChallengeApproachFactory(custom_description="Ordinary finished approach description text.")

        with CaptureQueriesContext(connection) as ctx:
            rows = _rows_for_model(ChallengeApproach, None)

        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual(len(rows), 1)
        # The values_list span becomes a SQL join inside that one query rather
        # than a second query per related row - if a future edit regressed to a
        # per-row lookup, this row count check alone wouldn't catch it, but the
        # query count above would.
        self.assertNotRegex(rows[0].identity, r"^\d+, \d+$")

    def test_domain_stats_aggregate_correctly(self):
        self._trait("Stats Alpha", "One two three four.")
        self._trait("Stats Beta", "One two.", written=True)
        self._trait("Stats Gamma", "One two three.", written=True, reviewed=True)

        rows, stats = build_backlog()
        trait_rows = [r for r in rows if r.model_label == "traits.Trait"]
        self.assertEqual(len(trait_rows), 3)

        by_domain = {s.domain: s for s in stats}
        trait_stats = by_domain["traits"]
        self.assertEqual(trait_stats.rows, 3)
        self.assertEqual(trait_stats.unwritten, 1)
        self.assertEqual(trait_stats.unreviewed, 2)
        self.assertEqual(trait_stats.words_total, 9)
        self.assertEqual(trait_stats.words_unwritten, 4)

    def test_scope_callable_excludes_a_row_from_every_model(self):
        self._trait("Scope Included", "Kept row here.")
        excluded = self._trait("Scope Excluded", "Dropped row here.")

        rows, _ = build_backlog(scope=lambda qs: qs.exclude(pk=excluded.pk))
        identities = {r.identity for r in rows if r.model_label == "traits.Trait"}
        self.assertIn("Scope Included", identities)
        self.assertNotIn("Scope Excluded", identities)

    def test_domain_with_zero_rows_has_no_stats_entry(self):
        self._trait("Only Row", "Just one row in this domain.")

        _, stats = build_backlog()
        domains = {s.domain for s in stats}
        self.assertEqual(domains, {"traits"})
