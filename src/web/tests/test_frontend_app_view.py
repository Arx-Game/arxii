"""The served React page links every file of the build under /static/dist/.

The build is made for the site root, and Django serves it from /static/dist/.
A root path the page still carries is answered by the frontend catch-all with
the page itself, so the browser gets HTML where it asked for a script, a
stylesheet or an icon.
"""

from pathlib import Path
import re
import tempfile
from unittest.mock import patch

from django.test import TestCase

SOURCE_INDEX = Path(__file__).resolve().parents[3] / "frontend" / "index.html"

# The shape `vite build` writes: hashed files under /assets/, public files at
# the root, and full URLs for the font host.
BUILT_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>Arx</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link href="//fonts.example.test/face.css" rel="stylesheet" />
    <script type="module" crossorigin src="/assets/index-abc123.js"></script>
    <link rel="modulepreload" crossorigin href="/assets/vendor-react-def456.js">
    <link rel="stylesheet" crossorigin href="/assets/index-ghi789.css">
  </head>
  <body><div id="root"></div></body>
</html>
"""

LINKED_PATH = re.compile(r'\b(?:href|src)="([^"]+)"')


class FrontendAppViewPathTests(TestCase):
    def serve(self, index_html: str) -> str:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        index = Path(directory.name) / "index.html"
        index.write_text(index_html, encoding="utf-8")
        with patch("web.views.INDEX_PATH", index):
            response = self.client.get("/families/12")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_built_files_are_linked_under_static_dist(self):
        linked = LINKED_PATH.findall(self.serve(BUILT_INDEX))

        self.assertEqual(
            linked,
            [
                "/static/dist/favicon.svg",
                "https://fonts.googleapis.com",
                "//fonts.example.test/face.css",
                "/static/dist/assets/index-abc123.js",
                "/static/dist/assets/vendor-react-def456.js",
                "/static/dist/assets/index-ghi789.css",
            ],
        )

    def test_a_path_already_under_static_dist_is_left_alone(self):
        page = self.serve('<link rel="icon" href="/static/dist/favicon.svg" />')

        self.assertIn('href="/static/dist/favicon.svg"', page)

    def test_every_public_file_the_source_page_links_is_served_from_static_dist(self):
        """Whatever frontend/index.html links from the root today is rewritten.

        The view once named the files it rewrote; the favicon was renamed and
        its link went on pointing at the root.
        """
        source = SOURCE_INDEX.read_text(encoding="utf-8")
        # `/src/main.tsx` is the dev entry; the build replaces it.
        public = [
            path
            for path in LINKED_PATH.findall(source)
            if path.startswith("/") and not path.startswith(("//", "/src/"))
        ]
        self.assertTrue(public, "frontend/index.html links no public file; update this test")

        linked = LINKED_PATH.findall(self.serve(source))

        for path in public:
            self.assertIn(f"/static/dist{path}", linked)
            self.assertNotIn(path, linked)
