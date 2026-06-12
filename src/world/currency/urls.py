"""URLs for the currency player API (#930 prep — org books)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.currency.views import OrgBooksViewSet

app_name = "currency"

router = DefaultRouter()
router.register(r"org-books", OrgBooksViewSet, basename="org-books")

urlpatterns = [
    path("", include(router.urls)),
]
