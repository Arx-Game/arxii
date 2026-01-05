"""Custom web views for serving the React app."""

import logging
from pathlib import Path

from django.http import HttpResponse
from django.views import View

logger = logging.getLogger(__name__)


class FrontendAppView(View):
    """Serve the compiled React application."""

    def get(self, request, *args, **kwargs):
        """Serve the React index.html with proper static file URLs."""
        try:
            # Path to the generated index.html - use current directory structure
            current_dir = Path(__file__).resolve().parent.parent
            index_path = current_dir / "web" / "static" / "dist" / "index.html"

            with index_path.open(encoding="utf-8") as f:
                html = f.read()

            # Fix asset paths to include /static/dist/ prefix
            html = html.replace('href="/assets/', 'href="/static/dist/assets/')
            html = html.replace('src="/assets/', 'src="/static/dist/assets/')
            html = html.replace('href="/vite.svg"', 'href="/static/dist/vite.svg"')

            return HttpResponse(html, content_type="text/html")

        except FileNotFoundError as e:
            # Fallback if build hasn't been run
            logger.warning("Frontend build not found: %s", e)
            return HttpResponse(
                "<h1>Frontend not built</h1><p>Run <code>pnpm build</code> "
                "in the frontend directory.</p>",
                content_type="text/html",
                status=500,
            )
        except (OSError, UnicodeError) as e:
            # Other errors - log the full exception with traceback
            logger.exception("Error serving frontend: %s", e)
            return HttpResponse(
                "<h1>Frontend Error</h1><p>Unable to load the frontend.</p>",
                content_type="text/html",
                status=500,
            )
