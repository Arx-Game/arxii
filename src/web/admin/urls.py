"""Admin URL configuration."""

from django.urls import path

from web.admin import arx_admin_site
from web.admin.views import is_model_pinned, toggle_pin_model

urlpatterns = [
    path("_pin/", toggle_pin_model, name="admin_toggle_pin"),
    path("_pinned/", is_model_pinned, name="admin_is_pinned"),
    path("", arx_admin_site.urls),
]
