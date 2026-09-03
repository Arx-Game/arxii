"""The admin index leaks no template comment prose onto the rendered page.

Django's ``{# #}`` comment syntax is single-line only: the lexer never joins
lines, so an opening ``{#`` whose ``#}`` sits on a later line is not a comment
and every character of it renders. Three templates shipped that way, and the
admin index put "A real <button> rather than role=..." in front of staff at the
top of the page. ``{% comment %}`` is the multi-line form.

``tools/lint_template_comment.py`` blocks the syntax repo-wide at commit time;
this test covers the user-visible symptom on the page that showed it.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory

# Prose that appears only inside a comment in these templates. Rendered output
# containing any of it means a comment leaked.
COMMENT_PROSE = (
    "A real",
    "rather than role=",
    "keyboard-reachable",
    "come for free",
    "render side by side",
    "mint-vs-sink",
)


class AdminIndexRendersNoCommentProseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = AccountFactory(
            username="template_comment_super", is_staff=True, is_superuser=True
        )

    def test_admin_index_does_not_render_comment_prose(self):
        self.client.force_login(self.superuser)
        content = self.client.get("/admin/").content.decode()
        for prose in COMMENT_PROSE:
            self.assertNotIn(prose, content)

    def test_admin_index_still_renders_the_group_heading_button(self):
        """The comment describes a real <button>; prove the button survived the fix."""
        self.client.force_login(self.superuser)
        content = self.client.get("/admin/").content.decode()
        self.assertIn('class="app-group-header collapsible"', content)
