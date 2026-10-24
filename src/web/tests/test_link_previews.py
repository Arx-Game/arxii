from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from web.link_previews import DEFAULT_DESCRIPTION, first_paragraph
from world.character_creation.factories import RealmFactory
from world.codex.factories import CodexEntryFactory
from world.realms.models import RealmTestamentSection


class FirstParagraphTests(SimpleTestCase):
    def test_takes_text_up_to_the_first_blank_line(self):
        self.assertEqual(first_paragraph("One.\n\nTwo."), "One.")

    def test_lore_break_codes_end_the_paragraph_and_flatten_inside_it(self):
        self.assertEqual(first_paragraph("One%rstill one.%r%rTwo."), "One still one.")

    def test_long_paragraph_is_clipped_at_a_word(self):
        clipped = first_paragraph("word " * 100)
        self.assertTrue(clipped.endswith("…"))
        self.assertLessEqual(len(clipped), 200)
        self.assertNotIn("wor…", clipped)


FIXTURE_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <title>Arx</title>
    <meta
      name="description"
      content="Old description."
    />
    <meta property="og:title" content="Arx" />
    <meta
      property="og:description"
      content="Old description."
    />
    <meta property="og:type" content="website" />
  </head>
  <body><div id="root"></div></body>
</html>
"""


class LinkPreviewPageTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        index = Path(directory.name) / "index.html"
        index.write_text(FIXTURE_INDEX, encoding="utf-8")
        patcher = patch("web.views.INDEX_PATH", index)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_page(self, path: str) -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_default_page_carries_the_site_description(self):
        page = self.get_page("/somewhere-else")
        self.assertIn(f'<meta property="og:description" content="{DEFAULT_DESCRIPTION}"', page)
        self.assertEqual(page.count('property="og:description"'), 1)

    def test_realm_page_previews_the_first_testament_paragraph(self):
        realm = RealmFactory(name="Umbros")
        RealmTestamentSection.objects.create(
            realm=realm, sort_order=2, body="Second movement.", motto=""
        )
        RealmTestamentSection.objects.create(
            realm=realm, sort_order=1, body="Dark opens.\n\nSecond paragraph.", motto=""
        )
        page = self.get_page("/realms/umbros")
        self.assertIn('content="Umbros · Arx"', page)
        self.assertIn('property="og:description" content="Dark opens."', page)
        self.assertIn("<title>Umbros · Arx</title>", page)

    def test_unknown_realm_falls_back_to_the_default(self):
        page = self.get_page("/realms/nowhere")
        self.assertIn(DEFAULT_DESCRIPTION, page)

    def test_public_codex_entry_previews_its_first_paragraph(self):
        entry = CodexEntryFactory(
            name="The Shroud", lore_content="It fell.\n\nMore.", is_public=True
        )
        page = self.get_page(f"/codex?entry={entry.pk}")
        self.assertIn('content="The Shroud · Codex · Arx"', page)
        self.assertIn('property="og:description" content="It fell."', page)

    def test_non_public_codex_entry_leaks_nothing(self):
        entry = CodexEntryFactory(name="Hidden", lore_content="Secret lore.", is_public=False)
        page = self.get_page(f"/codex?entry={entry.pk}")
        self.assertNotIn("Secret lore.", page)
        self.assertNotIn("Hidden", page)
        self.assertIn(DEFAULT_DESCRIPTION, page)

    def test_description_text_is_escaped(self):
        entry = CodexEntryFactory(lore_content='A "quoted" <b>line</b>.', is_public=True)
        page = self.get_page(f"/codex?entry={entry.pk}")
        self.assertIn("A &quot;quoted&quot; &lt;b&gt;line&lt;/b&gt;.", page)
