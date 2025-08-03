"""Custom web views for serving the React app."""

from django.http import HttpResponse
from django.views import View


class FrontendAppView(View):
    """Serve the compiled React application."""

    def get(self, request, *args, **kwargs):
        """Serve the React index.html with proper static file URLs."""
        html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/static/dist/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Arx II</title>
    <script type="module" crossorigin src="/static/dist/assets/index-CkgXqKYp.js"></script>
    <link rel="stylesheet" crossorigin href="/static/dist/assets/index-C57Hq2bl.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>"""
        return HttpResponse(html, content_type="text/html")
