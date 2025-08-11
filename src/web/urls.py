"""Project URL configuration."""

from django.urls import include, path, re_path

from web.views import FrontendAppView

urlpatterns = [
    path("api/", include("web.api.urls")),
    path("api/roster/", include("world.roster.urls")),
    path("", include("world.scenes.urls")),
    path("webclient/", include("web.webclient.urls")),
    path("admin/", include("web.admin.urls")),
    path("accounts/", include("allauth.urls")),
    # React frontend catch-all - must be last
    re_path(r"^(?:.*)/?$", FrontendAppView.as_view(), name="frontend-home"),
]
