"""Tests for the Authoring Workbench dashboard, stats, and queue panels (#3019)."""

from datetime import date
from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import EffectTypeFactory
from world.traits.models import Trait, TraitCategory, TraitType


class AuthoringViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.writer = ContentContributorFactory(name="Writer")
        cls.reviewer = ContentContributorFactory(name="Reviewer")
        # These fragment/dashboard tests exercise the post-setup dashboard, not
        # the setup gate itself (that gate is covered in test_authoring_setup.py)
        # - so cls.super carries a linked contributor from the start.
        PlayerData.objects.create(
            account=cls.super, contributor=ContentContributorFactory(name="Root Admin")
        )

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


class TestAuthoringDashboardView(AuthoringViewsTestCase):
    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_dashboard(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('id="authoring-root"', body)
        self.assertIn('id="panel-authoring-stats"', body)
        self.assertIn('id="panel-authoring-queue"', body)

    def test_dashboard_forwards_its_querystring_to_the_first_queue_load(self) -> None:
        """`/_authoring/?domain=traits` reopens on traits: the URL the fragment kept (#3828)."""
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring"), {"domain": "traits"}).content.decode()
        section = re.search(r'<section[^>]*id="panel-authoring-queue"[^>]*>', body, re.DOTALL)
        self.assertIsNotNone(section)
        queue_url = reverse("admin_authoring_queue")
        self.assertIn(f'hx-get="{queue_url}?domain=traits"', section.group(0))
        # Only the first load comes from the section; the refresh is the form's own.
        self.assertIn('hx-trigger="load"', section.group(0))
        self.assertNotIn("authoring-backlog-changed", section.group(0))


class TestAuthoringStatsFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_stats"))
        self.assertEqual(resp.status_code, 403)

    def test_domain_row_renders_from_factory_data(self) -> None:
        self._trait("Alpha", "One two three four words here.")
        self._trait("Beta", "One two three.", written=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_stats"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("traits", body)
        self.assertIn(">2<", body)


class TestAuthoringQueueFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_queue"))
        self.assertEqual(resp.status_code, 403)

    def test_rows_render_worst_first(self) -> None:
        self._trait("Placeholder Row", "PLACEHOLDER prose here.")
        self._trait("Finished Row", "Ordinary finished prose.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "all"})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertLess(body.index("Placeholder Row"), body.index("Finished Row"))

    def test_domain_filter(self) -> None:
        self._trait("Trait Row", "Ordinary finished prose text.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"domain": "traits"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Trait Row", resp.content.decode())

        resp = self.client.get(reverse("admin_authoring_queue"), {"domain": "tarot"})
        self.assertNotIn("Trait Row", resp.content.decode())

    def test_status_filter_placeholder(self) -> None:
        self._trait("Placeholder Row", "PLACEHOLDER prose here.")
        self._trait("Regular Row", "Ordinary finished prose.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "placeholder"})
        body = resp.content.decode()
        self.assertIn("Placeholder Row", body)
        self.assertNotIn("Regular Row", body)

    def test_status_filter_unwritten(self) -> None:
        self._trait("Unwritten Row", "Ordinary unwritten prose here.")
        self._trait("Written Row", "Ordinary written prose here.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "unwritten"})
        body = resp.content.decode()
        self.assertIn("Unwritten Row", body)
        self.assertNotIn("Written Row", body)

    def test_status_filter_to_review_is_written_and_not_reviewed(self) -> None:
        """`unreviewed` is a review pass: written rows awaiting review, never unwritten ones.

        Before #3828 it meant `not reviewed`, which made it a superset of every
        unwritten row and useless for a review pass.
        """
        self._trait("Unreviewed Row", "Ordinary unreviewed prose.", written=True)
        self._trait("Reviewed Row", "Ordinary reviewed prose.", written=True, reviewed=True)
        self._trait("Unwritten Row", "Ordinary unwritten prose.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "unreviewed"})
        body = resp.content.decode()
        self.assertIn("Unreviewed Row", body)
        self.assertNotIn("Reviewed Row", body)
        self.assertNotIn("Unwritten Row", body)

    def test_default_status_is_to_write(self) -> None:
        """No `?status=` means To write: written rows are hidden until asked for (#3828)."""
        self._trait("Unwritten Row", "Ordinary unwritten prose here.")
        self._trait("Written Row", "Ordinary written prose here.", written=True)

        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring_queue")).content.decode()
        self.assertIn("Unwritten Row", body)
        self.assertNotIn("Written Row", body)
        self.assertIn('<option value="unwritten" selected>', body)

    def test_status_all_shows_every_row(self) -> None:
        self._trait("Unwritten Row", "Ordinary unwritten prose here.")
        self._trait("Written Row", "Ordinary written prose here.", written=True, reviewed=True)

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"status": "all"})
        body = resp.content.decode()
        self.assertIn("Unwritten Row", body)
        self.assertIn("Written Row", body)

    def _headline(self, body: str) -> tuple[str, str]:
        """The queue headline's (count, qualifier) pair, e.g. ("2", "to write · all domains")."""
        match = re.search(r'class="queue-headline">(\d+)<small>(.*?)</small>', body, re.DOTALL)
        self.assertIsNotNone(match, "no queue headline rendered")
        return match.group(1), match.group(2)

    def test_headline_counts_the_filtered_rows_only(self) -> None:
        """The number beside the title is what is left under the filters, never the backlog."""
        self._trait("Alpha", "Ordinary unwritten prose here.")
        self._trait("Beta", "Ordinary unwritten prose here.")
        self._trait("Gamma", "Ordinary written prose here.", written=True, reviewed=True)

        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring_queue")).content.decode()
        count, qualifier = self._headline(body)
        self.assertEqual(count, "2")
        self.assertIn("to write", qualifier)
        self.assertIn("all domains", qualifier)

    def test_headline_names_the_picked_domain_and_status(self) -> None:
        self._trait("Alpha", "Ordinary written prose here.", written=True)

        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_authoring_queue"), {"domain": "traits", "status": "unreviewed"}
        )
        count, qualifier = self._headline(resp.content.decode())
        self.assertEqual(count, "1")
        self.assertIn("to review", qualifier)
        self.assertIn("traits", qualifier)

    def test_q_filter_matches_name_substring(self) -> None:
        self._trait("Sunfire Blessing", "Ordinary finished prose here.")
        self._trait("Moonlit Ward", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"q": "sunfire"})
        body = resp.content.decode()
        self.assertIn("Sunfire Blessing", body)
        self.assertNotIn("Moonlit Ward", body)

    def test_row_carries_editor_link(self) -> None:
        trait = self._trait("Linked Row", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        body = resp.content.decode()
        editor_url = reverse("admin_authoring_editor")
        self.assertIn(editor_url, body)
        self.assertIn("model=traits.Trait", body)
        self.assertIn(f"pk={trait.pk}", body)

    def test_model_filter_excludes_other_models(self) -> None:
        self._trait("Trait Row", "Ordinary finished prose here.")
        EffectTypeFactory(name="Effect Row", description="Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"model": "traits.Trait"})
        body = resp.content.decode()
        self.assertIn("Trait Row", body)
        self.assertNotIn("Effect Row", body)

    def test_model_options_narrow_to_the_selected_domain(self) -> None:
        """Picking a domain must not leave other domains' models offered in the dropdown."""
        self._trait("Trait Row", "Ordinary finished prose here.")
        EffectTypeFactory(name="Effect Row", description="Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"), {"domain": "traits"})
        body = resp.content.decode()
        self.assertIn('value="traits.Trait"', body)
        self.assertNotIn('value="magic.EffectType"', body)

    def test_row_carries_admin_change_link(self) -> None:
        """The workbench editor only exposes prose, so the queue links out to the full row."""
        trait = self._trait("Linked Row", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        self.assertIn(reverse("admin:arxii_trait_change", args=[trait.pk]), resp.content.decode())

    def test_editor_link_anchors_to_the_editor_panel(self) -> None:
        """`href="#"` scrolled nowhere, so the swapped-in editor stayed below the fold."""
        self._trait("Anchored Row", "Ordinary finished prose here.")

        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring_queue")).content.decode()
        self.assertIn('href="#authoring-editor"', body)
        self.assertIn('hx-swap="innerHTML show:top"', body)

    def test_queue_response_replaces_the_browser_url_with_its_filters(self) -> None:
        """A reload comes back to the same filters: the fragment rewrites the page URL (#3828)."""
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_queue"), {"domain": "traits", "status": "unreviewed"}
        )
        self.assertEqual(
            resp["HX-Replace-Url"], f"{reverse('admin_authoring')}?domain=traits&status=unreviewed"
        )

        resp = self.client.get(reverse("admin_authoring_queue"))
        self.assertEqual(resp["HX-Replace-Url"], reverse("admin_authoring"))

    def test_filter_form_refreshes_itself_on_backlog_changed(self) -> None:
        """The credit/review refresh re-submits the live form, so the filters survive it (#3828)."""
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring_queue")).content.decode()
        form = re.search(r"<form[^>]*id=\"queue-filters\"[^>]*>", body, re.DOTALL)
        self.assertIsNotNone(form, "the filter form has no id for the refresh to find")
        self.assertIn("authoring-backlog-changed from:body", form.group(0))

    def test_row_links_carry_the_queue_filters_and_position(self) -> None:
        """Each row hands the editor the list it came from and its index in it (#3828)."""
        self._trait("Alpha Row", "Ordinary unwritten prose here.")
        self._trait("Beta Row", "Ordinary unwritten prose here.")

        self.client.force_login(self.super)
        body = self.client.get(
            reverse("admin_authoring_queue"), {"domain": "traits"}
        ).content.decode()
        links = re.findall(r'hx-get="([^"]*editor/[^"]*)"', body)
        self.assertEqual(len(links), 2)
        self.assertIn("queue=domain%3Dtraits", links[0])
        self.assertIn("pos=0", links[0])
        self.assertIn("pos=1", links[1])

    def test_display_capped_at_100_with_showing_note(self) -> None:
        for i in range(101):
            self._trait(f"Bulk Row {i:03d}", "Ordinary finished prose text goes here now.")

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_authoring_queue"))
        body = resp.content.decode()
        self.assertIn("Showing 100 of 101", body)


class TestAuthoringEditorFragment(AuthoringViewsTestCase):
    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_authoring_editor"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_editor_form_for_a_real_row(self) -> None:
        """A real Trait row renders its prose editor, not just the error shell.

        The original version of this test never created the Trait it
        queried for, so ``pk=1`` almost always resolved to a missing row -
        it was unknowingly asserting against the "does not exist" error
        fragment's own ``<h2>Editing traits.Trait #1</h2>`` heading (which
        renders regardless of whether the row resolved), not a loaded editor
        (#3019 review, Minor).
        """
        trait = self._trait("Editor Shell Trait", "Some prose worth editing.")
        self.client.force_login(self.super)

        resp = self.client.get(
            reverse("admin_authoring_editor"), {"model": "traits.Trait", "pk": str(trait.pk)}
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("does not exist", body)
        self.assertIn('<textarea name="description" id="id_description" autofocus>', body)
        self.assertIn("Some prose worth editing.", body)


class TestAuthoringDashboardLayout(AuthoringViewsTestCase):
    """Page order and the queue/editor hand-off the layout depends on (#3828)."""

    def test_editor_sits_above_the_queue_and_stats_below_it(self) -> None:
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring")).content.decode()

        editor = body.index('id="authoring-editor"')
        queue = body.index('id="panel-authoring-queue"')
        stats = body.index('id="panel-authoring-stats"')
        builders = body.index('id="panel-authoring-builders"')
        reference = body.index('id="panel-authoring-reference"')
        self.assertLess(editor, queue)
        self.assertLess(queue, stats)
        self.assertLess(stats, builders)
        self.assertLess(builders, reference)

    def test_queue_rows_carry_the_row_key_the_shading_script_matches(self) -> None:
        trait = self._trait("Keyed Row", "Ordinary unwritten prose here.")
        self.client.force_login(self.super)

        body = self.client.get(reverse("admin_authoring_queue")).content.decode()
        self.assertIn(f'<tr data-row="traits.Trait:{trait.pk}">', body)

    def test_dashboard_carries_the_shading_script(self) -> None:
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_authoring")).content.decode()
        self.assertIn("queue-row-current", body)
        self.assertIn("data-current", body)
        self.assertIn("htmx:afterSwap", body)


class TestAuthoringStyling(AuthoringViewsTestCase):
    """Every class the queue and editor templates emit must have a rule that REACHES the page.

    The #3667 lesson: a class name in the markup proves nothing, and a rule in a
    stylesheet the page never links proves nothing either. Reachable CSS here is
    the dashboard's own inline styles (which include `_panel_css.html`), each
    fragment's inline `<style>` block, and the stylesheets the dashboard links.
    """

    #: Classes Django admin's own stylesheets define; everything else the two
    #: fragments emit is ours and needs a rule below.
    ADMIN_PROVIDED_CLASSES = frozenset({"errornote", "successnote", "help", "button", "default"})

    #: Applied by the dashboard's script, never emitted in markup - so it is
    #: checked by name rather than collected from a body.
    JS_APPLIED_CLASSES = frozenset({"queue-row-current"})

    def _get(self, name: str, params: dict | None = None) -> str:
        self.client.force_login(self.super)
        resp = self.client.get(reverse(name), params or {})
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _reachable_css(self, dashboard: str, *fragments: str) -> str:
        css = "\n".join(
            block
            for body in (dashboard, *fragments)
            for block in re.findall(r"<style[^>]*>(.*?)</style>", body, re.DOTALL)
        )
        for href in re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', dashboard):
            if not href.startswith(settings.STATIC_URL):
                continue
            found = finders.find(href[len(settings.STATIC_URL) :])
            self.assertIsNotNone(found, f"linked stylesheet does not resolve: {href}")
            css += "\n" + Path(found).read_text()
        return css

    @staticmethod
    def _classes(body: str) -> set[str]:
        return {token for attr in re.findall(r'class="([^"]+)"', body) for token in attr.split()}

    def test_every_queue_and_editor_class_has_a_reachable_rule(self) -> None:
        trait = self._trait("Styled Row", "Ordinary unwritten prose here.")
        self._trait("Styled Successor", "Ordinary unwritten prose here.")
        dashboard = self._get("admin_authoring")
        queue = self._get("admin_authoring_queue")
        editor = self._get(
            "admin_authoring_editor",
            {"model": "traits.Trait", "pk": trait.pk, "queue": "", "pos": 0},
        )
        css = self._reachable_css(dashboard, queue, editor)

        ours = (self._classes(queue) | self._classes(editor) | self.JS_APPLIED_CLASSES) - (
            self.ADMIN_PROVIDED_CLASSES
        )
        unstyled = sorted(name for name in ours if f".{name}" not in css)
        self.assertEqual(unstyled, [], f"classes with no rule reaching the page: {unstyled}")
