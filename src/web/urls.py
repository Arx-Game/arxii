"""Project URL configuration."""

from django.urls import include, path, re_path

from web.views import FrontendAppView

urlpatterns = [
    path("api/", include("web.api.urls")),
    path("webclient/", include("web.webclient.urls")),
    path("admin/", include("web.admin.urls")),
    path("roster/", include("world.roster.urls")),
    path("accounts/", include("allauth.urls")),
    re_path(r"^(?!admin/).*", FrontendAppView.as_view(), name="frontend"),
]
