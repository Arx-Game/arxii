"""
This reroutes from an URL to a python view-function/class.

The main web/urls.py includes these routes for all urls starting with `webclient/`
(the `webclient/` part should not be included again here).

"""

# Uncomment once you need to import it
# from django.urls import path
from evennia.web.webclient.urls import urlpatterns as evennia_urls

# add patterns here
urlpatterns = [
    # path("url-pattern", imported_python_view),
    # path("url-pattern", imported_python_view),
]

# read by Django
urlpatterns = urlpatterns + evennia_urls
