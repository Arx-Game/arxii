"""Tests for the related-entries pane and prose-mentions search (#3019 Task 6)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from actions.factories import ConsequencePoolFactory
from web.admin.authoring.relations import prose_mentions, related_entries
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import GiftFactory, RestrictionFactory, TechniqueFactory
from world.magic.models import Gift, Technique, TechniqueDamageProfile


def _make_account(username: str, *, superuser: bool = True) -> AccountDB:
    if superuser:
        return AccountDB.objects.create_superuser(username, f"{username}@example.com", "pw-123456")
    account = AccountDB.objects.create_user(username, f"{username}@example.com", "pw-123456")
    account.is_staff = True
    account.save()
    return account


class RelatedEntriesTests(TestCase):
    """`related_entries` against a Technique's forward/reverse relation graph."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = ContentContributorFactory(name="Relations Writer")
        cls.gift = GiftFactory(written_by=cls.writer)
        cls.restriction = RestrictionFactory()
        cls.technique = TechniqueFactory(gift=cls.gift)
        cls.technique.restrictions.add(cls.restriction)
        # TechniqueFactory's damage_profile post_generation already seeded one
        # TechniqueDamageProfile row (EffectType.base_power defaults to 10).

    def test_forward_fk_appears_with_credit_from_credited_neighbor(self) -> None:
        entries, _truncated = related_entries(self.technique)
        gift_entries = [e for e in entries if e.model_name == "Gift"]

        self.assertEqual(len(gift_entries), 1)
        entry = gift_entries[0]
        self.assertEqual(entry.pk, self.gift.pk)
        self.assertEqual(entry.relation, "gift")
        self.assertEqual(entry.direction, "forward")
        self.assertEqual(entry.label, str(self.gift))
        self.assertEqual(entry.model_label, f"magic.{Gift.__name__}")
        self.assertTrue(entry.credited)

    def test_forward_m2m_appears_with_credited_false_when_unwritten(self) -> None:
        entries, _truncated = related_entries(self.technique)
        restriction_entries = [e for e in entries if e.model_name == "Restriction"]

        self.assertEqual(len(restriction_entries), 1)
        entry = restriction_entries[0]
        self.assertEqual(entry.pk, self.restriction.pk)
        self.assertEqual(entry.relation, "restrictions")
        self.assertEqual(entry.direction, "forward")
        self.assertIs(entry.credited, False)

    def test_reverse_fk_appears_with_direction_reverse_and_credited_none(self) -> None:
        entries, _truncated = related_entries(self.technique)
        damage_profile_entries = [e for e in entries if e.model_name == "TechniqueDamageProfile"]

        self.assertEqual(len(damage_profile_entries), 1)
        entry = damage_profile_entries[0]
        self.assertEqual(entry.direction, "reverse")
        self.assertEqual(entry.relation, "damage_profiles")
        self.assertIsNone(entry.credited)
        self.assertIsNone(entry.reviewed)

    def test_related_name_plus_relation_is_absent(self) -> None:
        """A `related_name="+"` FK never surfaces on the far side's neighbor list.

        `Technique.clash_resolution_pool` points at `ConsequencePool` with
        `related_name="+"` - so a `ConsequencePool` instance a technique points
        at must never list that technique as a neighbor.
        """
        pool = ConsequencePoolFactory()
        self.technique.clash_resolution_pool = pool
        self.technique.save()

        entries, _truncated = related_entries(pool)

        self.assertFalse(any(e.model_name == "Technique" for e in entries))

    def test_cap_truncates_and_reports_the_remainder(self) -> None:
        full_entries, full_truncated = related_entries(self.technique)
        self.assertEqual(full_truncated, 0)
        total = len(full_entries)
        self.assertGreaterEqual(total, 3)

        capped_entries, capped_truncated = related_entries(self.technique, cap=1)

        self.assertEqual(len(capped_entries), 1)
        self.assertEqual(capped_truncated, total - 1)

    def test_cap_bounds_a_large_relation_and_still_reports_the_exact_remainder(self) -> None:
        # 8 extra restrictions - a relation that alone already exceeds a
        # small cap, standing in for an ever-growing reverse relation (e.g.
        # an audit-ledger FK) that must never be fully materialized before
        # the cap trims it.
        extra_restrictions = [RestrictionFactory() for _ in range(8)]
        self.technique.restrictions.add(*extra_restrictions)

        full_entries, full_truncated = related_entries(self.technique)
        self.assertEqual(full_truncated, 0)
        total = len(full_entries)
        self.assertGreaterEqual(total, 10)

        capped_entries, capped_truncated = related_entries(self.technique, cap=3)

        self.assertEqual(len(capped_entries), 3)
        self.assertEqual(capped_truncated, total - 3)

    def test_forward_m2m_query_is_sliced_at_the_database_not_materialized_in_full(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for _ in range(8):
            self.technique.restrictions.add(RestrictionFactory())

        # cap=3: `gift` and `effect_type` (the only two set forward FKs ahead
        # of `restrictions` in field order) already consume 2 of the 3 slots,
        # leaving exactly 1 slot of room when the 9-row `restrictions` M2M is
        # reached - enough to force the overflow/LIMIT branch in `add_many`
        # rather than the cap<=0 branch, which would only ever run a bare
        # `.count()` with no LIMIT at all.
        with CaptureQueriesContext(connection) as ctx:
            related_entries(self.technique, cap=3)

        restriction_queries = [
            q["sql"] for q in ctx.captured_queries if "restriction" in q["sql"].lower()
        ]
        self.assertTrue(restriction_queries, "expected a query against the restriction table")
        self.assertTrue(
            any("LIMIT" in sql.upper() for sql in restriction_queries),
            "expected the restrictions query to carry a LIMIT clause, not fetch every row",
        )


class ProseMentionsTests(TestCase):
    """`prose_mentions` scanning every credited model's prose for a name."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = ContentContributorFactory(name="Mentions Writer")

    def test_finds_a_row_mentioning_the_name_and_excludes_the_edited_row(self) -> None:
        subject = TechniqueFactory(name="Ember Lance")
        mentioning = TechniqueFactory(
            description="This move echoes Ember Lance's opening flourish."
        )

        mentions = prose_mentions(subject.name, exclude=(Technique, subject.pk))

        mentioned_pks = {e.pk for e in mentions if e.model_name == "Technique"}
        self.assertIn(mentioning.pk, mentioned_pks)
        self.assertNotIn(subject.pk, mentioned_pks)

    def test_mentions_are_capped(self) -> None:
        subject = TechniqueFactory(name="Widowreach")
        for _ in range(3):
            TechniqueFactory(description="Widowreach was taught to me long ago.")

        mentions = prose_mentions(subject.name, exclude=(Technique, subject.pk), cap=2)

        self.assertEqual(len(mentions), 2)

    def test_empty_name_returns_no_mentions(self) -> None:
        self.assertEqual(prose_mentions(""), [])

    def test_scope_callable_narrows_every_model_before_matching(self) -> None:
        """`scope` is the seam a future GM-restricted variant would use (#3019 review, Item 4).

        Mirrors `test_authoring_backlog.TestBuildBacklog
        .test_scope_callable_excludes_a_row_from_every_model` - same idiom,
        applied here to `prose_mentions` instead of `build_backlog`.
        """
        subject = TechniqueFactory(name="Scoped Mentions Subject")
        visible = TechniqueFactory(description="Scoped Mentions Subject appears here too.")
        hidden = TechniqueFactory(description="Scoped Mentions Subject appears here as well.")

        mentions = prose_mentions(
            subject.name,
            exclude=(Technique, subject.pk),
            scope=lambda qs: qs.exclude(pk=hidden.pk),
        )

        mentioned_pks = {e.pk for e in mentions if e.model_name == "Technique"}
        self.assertIn(visible.pk, mentioned_pks)
        self.assertNotIn(hidden.pk, mentioned_pks)


class AuthoringRelatedFragmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = _make_account("relatedsuper")
        cls.staff = _make_account("relatedstaff", superuser=False)
        cls.writer = ContentContributorFactory(name="Related View Writer")
        cls.gift = GiftFactory(written_by=cls.writer)
        cls.technique = TechniqueFactory(gift=cls.gift)

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_related"))
        self.assertEqual(resp.status_code, 403)

    def test_bad_target_shows_error(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_authoring_related"),
            {"model": "bogus.NoSuchModel", "pk": "1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Unknown model.", resp.content.decode())

    def test_workbench_link_shown_for_credited_neighbor_admin_link_for_registered(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_authoring_related"),
            {"model": "magic.Technique", "pk": self.technique.pk},
        )
        body = resp.content.decode()

        self.assertEqual(resp.status_code, 200)
        # Gift is CreditedContent (credited_content_models()) AND has a
        # registered ModelAdmin - both links should render for it. The
        # query string is HTML-escaped by the template ("&" -> "&amp;").
        workbench_url = (
            f"{reverse('admin_authoring_editor')}?model=magic.Gift&amp;pk={self.gift.pk}"
        )
        self.assertIn(workbench_url, body)
        admin_url = reverse("admin:arxii_gift_change", args=[self.gift.pk])
        self.assertIn(admin_url, body)

    def test_admin_link_omitted_for_unregistered_neighbor_model(self) -> None:
        # TechniqueDamageProfile carries no @admin.register at all - an
        # unconditional reverse() there would 500 the first time a technique
        # with an auto-seeded damage profile showed up in this panel.
        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_authoring_related"),
            {"model": "magic.Technique", "pk": self.technique.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(TechniqueDamageProfile.objects.filter(technique=self.technique).exists())
        body = resp.content.decode()
        self.assertIn("TechniqueDamageProfile", body)
        self.assertNotIn("techniquedamageprofile_change", body)


class AuthoringMentionsFragmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = _make_account("mentionssuper")
        cls.staff = _make_account("mentionsstaff", superuser=False)

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_mentions"))
        self.assertEqual(resp.status_code, 403)

    def test_bad_target_shows_error(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_authoring_mentions"),
            {"model": "bogus.NoSuchModel", "pk": "1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Unknown model.", resp.content.decode())

    def test_finds_a_mention_and_excludes_self(self) -> None:
        # Gift, not Technique: the mentions view searches for
        # `str(target.instance)`, and `Gift.__str__` returns the bare
        # `name` field - `Technique.__str__` returns `f"{name} ({gift})"`,
        # which would never appear verbatim in another row's free-text prose.
        subject = GiftFactory(name="Griefsong")
        mentioning = GiftFactory(description="Griefsong echoes in old prayers.")
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_mentions"),
            {"model": "magic.Gift", "pk": subject.pk},
        )
        body = resp.content.decode()

        self.assertEqual(resp.status_code, 200)
        self.assertIn(str(mentioning), body)
