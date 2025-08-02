"""Custom web views for serving the React app."""

from pathlib import Path

from django.views.generic import TemplateView


class FrontendAppView(TemplateView):
    """Serve the compiled React application."""

    def get_template_names(self):
        base = Path(__file__).resolve().parent
        return [str(base / "static" / "dist" / "index.html")]
