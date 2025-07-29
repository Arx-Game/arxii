"""
URL patterns for the roster system.
"""

from django.urls import path

from world.roster import views

app_name = "roster"

urlpatterns = [
    # Public roster listing
    path("", views.roster_list, name="roster_list"),
    # Character gallery (using character pk for unique identification)
    path("character/<int:character_pk>/gallery/", views.gallery_view, name="gallery"),
    path(
        "character/<int:character_pk>/gallery/upload/",
        views.upload_image,
        name="upload_image",
    ),
    path(
        "character/<int:character_pk>/gallery/<int:media_id>/delete/",
        views.delete_image,
        name="delete_image",
    ),
    path(
        "character/<int:character_pk>/gallery/reorder/",
        views.reorder_gallery,
        name="reorder_gallery",
    ),
    # Password reset
    path(
        "password-reset/", views.password_reset_request, name="password_reset_request"
    ),
]
