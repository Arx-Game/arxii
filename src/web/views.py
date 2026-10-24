"""Custom web views for serving the React app."""

from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path

from django.http import HttpResponse, HttpResponseRedirect
from django.views import View

from web.link_previews import apply_preview, preview_for

logger = logging.getLogger(__name__)

# The compiled React entry page; tests point this at a small fixture.
INDEX_PATH = Path(__file__).resolve().parent / "static" / "dist" / "index.html"


class PasswordChangeDiscoveryView(View):
    """Point password managers at the authenticated password-change form."""

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        """Redirect to the existing password-change page."""
        return HttpResponseRedirect("/profile/account")

    head = get


class SecurityTxtView(View):
    """Publish vulnerability-disclosure metadata at the RFC 9116 endpoint."""

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        """Return contact information for reporting security vulnerabilities."""
        expires = (
            (datetime.now(UTC) + timedelta(days=365))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        body = "\n".join(
            (
                "Contact: https://github.com/Arx-Game/arxii/security/advisories/new",
                f"Expires: {expires}",
                "Preferred-Languages: en",
                "",
            )
        )
        return HttpResponse(body, content_type="text/plain")

    head = get


class FrontendAppView(View):
    """Serve the compiled React application."""

    def get(self, request, *args, **kwargs):
        """Serve the React index.html with proper static file URLs."""
        try:
            with INDEX_PATH.open(encoding="utf-8") as f:
                html = f.read()

            # Fix asset paths to include /static/dist/ prefix
            html = html.replace('href="/assets/', 'href="/static/dist/assets/')
            html = html.replace('src="/assets/', 'src="/static/dist/assets/')
            html = html.replace('href="/vite.svg"', 'href="/static/dist/vite.svg"')

            # Strip crossorigin attribute — Vite adds it for CDN deployments but
            # TwistedWeb doesn't send CORS headers on static files, which can cause
            # module evaluation ordering issues with type="module" scripts.
            html = html.replace(" crossorigin", "")

            # Link unfurlers (Discord) never run the React app, so the shared page's
            # title and description are written into the served HTML here.
            # The query string of a page URL, not an API filter.
            query = request.GET.dict()  # noqa: USE_FILTERSET
            html = apply_preview(
                html,
                preview_for(request.path, query),
                request.build_absolute_uri(request.get_full_path()),
            )

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
