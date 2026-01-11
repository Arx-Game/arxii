"""
This reroutes from an URL to a python view-function/class.

The main web/urls.py includes these routes for all urls starting with `admin/`
(the `admin/` part should not be included again here).

"""

from django.urls import path

from web.admin import arx_admin_site

# Use our custom admin site instead of the default
urlpatterns = [
    path("", arx_admin_site.urls),
]
