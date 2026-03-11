"""URL configuration for the journal system API."""

from django.urls import path

from world.journals.views import JournalEntryViewSet

app_name = "journals"

entry_list = JournalEntryViewSet.as_view({"get": "list", "post": "create"})
entry_detail = JournalEntryViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
entry_mine = JournalEntryViewSet.as_view({"get": "mine"})
entry_respond = JournalEntryViewSet.as_view({"post": "respond"})

urlpatterns = [
    path("entries/", entry_list, name="entry-list"),
    path("entries/mine/", entry_mine, name="entry-mine"),
    path("entries/<int:pk>/", entry_detail, name="entry-detail"),
    path("entries/<int:pk>/respond/", entry_respond, name="entry-respond"),
]
