"""URLs for the currency player API (#930 prep — org books; #1446 personal purse)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.currency.views import CharacterPurseView, OrgBooksViewSet

app_name = "currency"

router = DefaultRouter()
router.register(r"org-books", OrgBooksViewSet, basename="org-books")

urlpatterns = [
    path("purse/<int:character_id>/", CharacterPurseView.as_view(), name="character-purse"),
    path("", include(router.urls)),
]
