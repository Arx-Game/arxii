"""URL configuration for staff inbox."""

from django.urls import path

from world.staff_inbox.views import AccountHistoryView, StaffInboxView

app_name = "staff_inbox"
urlpatterns = [
    path("", StaffInboxView.as_view(), name="staff-inbox"),
    path(
        "accounts/<int:account_id>/history/",
        AccountHistoryView.as_view(),
        name="account-history",
    ),
]
