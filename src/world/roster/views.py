"""
Views for roster system including gallery management and applications.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from evennia_extensions.models import PlayerData
from world.roster.email_service import RosterEmailService
from world.roster.models import MediaType, RosterEntry, RosterTenure, TenureMedia
from world.roster.serializers import (
    MyRosterEntrySerializer,
    RosterApplicationSerializer,
    RosterEntryListSerializer,
    RosterEntrySerializer,
)
from world.roster.services import CloudinaryGalleryService


@login_required
def gallery_view(request, character_pk):
    """Display gallery for a character."""
    # Find the current tenure for this character
    try:
        tenure = RosterTenure.objects.select_related(
            "roster_entry__character", "player_data__account"
        ).get(roster_entry__character__pk=character_pk, end_date__isnull=True)
    except RosterTenure.DoesNotExist:
        raise Http404("Character not found or not currently active")

    # Get gallery media
    media_items = CloudinaryGalleryService.get_tenure_gallery(tenure)
    primary_image = CloudinaryGalleryService.get_primary_image(tenure)

    # Check if current user owns this character
    try:
        player_data = PlayerData.objects.get(account=request.user)
        is_owner = tenure.player_data == player_data
    except PlayerData.DoesNotExist:
        is_owner = False

    context = {
        "tenure": tenure,
        "character": tenure.character,
        "media_items": media_items,
        "primary_image": primary_image,
        "is_owner": is_owner,
        "media_types": MediaType.choices,
    }

    return render(request, "roster/gallery.html", context)


@login_required
@require_http_methods(["POST"])
def upload_image(request, character_pk):
    """Handle image upload for a character's gallery."""
    # Find the tenure and verify ownership
    try:
        player_data = PlayerData.objects.get(account=request.user)
        tenure = RosterTenure.objects.get(
            roster_entry__character__pk=character_pk,
            player_data=player_data,
            end_date__isnull=True,
        )
    except (PlayerData.DoesNotExist, RosterTenure.DoesNotExist):
        raise PermissionDenied(
            "You don't have permission to upload images for this character"
        )

    if "image" not in request.FILES:
        messages.error(request, "No image file provided")
        return redirect("roster:gallery", character_pk=character_pk)

    image_file = request.FILES["image"]
    media_type = request.POST.get("media_type", MediaType.PHOTO)
    title = request.POST.get("title", "")
    description = request.POST.get("description", "")

    try:
        media = CloudinaryGalleryService.upload_image(
            tenure=tenure,
            image_file=image_file,
            media_type=media_type,
            title=title,
            description=description,
        )

        messages.success(
            request, f"Image '{media.title or 'Untitled'}' uploaded successfully!"
        )

    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Upload failed: {str(e)}")

    return redirect("roster:gallery", character_pk=character_pk)


@login_required
@require_http_methods(["POST"])
def delete_image(request, character_pk, media_id):
    """Delete an image from a character's gallery."""
    try:
        player_data = PlayerData.objects.get(account=request.user)
        media = get_object_or_404(
            TenureMedia,
            id=media_id,
            tenure__character__pk=character_pk,
            tenure__player_data=player_data,
            tenure__end_date__isnull=True,
        )

        success = CloudinaryGalleryService.delete_media(media)

        if success:
            messages.success(request, "Image deleted successfully!")
        else:
            messages.warning(
                request, "Image deleted from gallery, but may still exist on Cloudinary"
            )

    except Exception as e:
        messages.error(request, f"Failed to delete image: {str(e)}")

    return redirect("roster:gallery", character_pk=character_pk)


@login_required
@require_http_methods(["POST"])
def reorder_gallery(request, character_pk):
    """Update the order of images in a gallery."""
    try:
        player_data = PlayerData.objects.get(account=request.user)
        tenure = RosterTenure.objects.get(
            character__pk=character_pk, player_data=player_data, end_date__isnull=True
        )

        data = json.loads(request.body)
        media_ids = data.get("media_ids", [])

        success = CloudinaryGalleryService.update_media_order(tenure, media_ids)

        return JsonResponse({"success": success})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def password_reset_request(request):
    """Handle password reset requests."""
    if request.method == "POST":
        email = request.POST.get("email")
        if email:
            try:
                from django.contrib.auth.models import User

                user = User.objects.get(email=email)
                success = RosterEmailService.send_password_reset_email(user)

                if success:
                    messages.success(
                        request,
                        (
                            "If an account with that email exists, "
                            "a password reset link has been sent."
                        ),
                    )
                else:
                    messages.error(
                        request,
                        "Failed to send password reset email. Please try again.",
                    )

            except User.DoesNotExist:
                # Don't reveal whether the email exists
                messages.success(
                    request,
                    (
                        "If an account with that email exists, "
                        "a password reset link has been sent."
                    ),
                )

        return redirect("roster:password_reset_request")

    return render(request, "roster/password_reset_request.html")


def roster_list(request):
    """Display public roster of characters."""
    from world.roster.models import Roster

    rosters = Roster.objects.filter(is_active=True).prefetch_related(
        "entries__character", "entries__character__tenures"
    )

    context = {
        "rosters": rosters,
    }

    return render(request, "roster/roster_list.html", context)


class RosterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Expose roster entries and related actions."""

    serializer_class = RosterEntrySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        """Return a queryset of roster entries."""

        return RosterEntry.objects.select_related("character").prefetch_related(
            Prefetch(
                "character__tenures",
                queryset=RosterTenure.objects.filter(
                    end_date__isnull=True
                ).prefetch_related(
                    Prefetch(
                        "media",
                        queryset=TenureMedia.objects.all(),
                        to_attr="cached_media",
                    )
                ),
                to_attr="cached_tenures",
            )
        )

    def get_serializer_class(self):
        if self.action == "list":
            return RosterEntryListSerializer
        if self.action == "mine":
            return MyRosterEntrySerializer
        if self.action == "apply":
            return RosterApplicationSerializer
        return super().get_serializer_class()

    @action(
        detail=False,
        permission_classes=[IsAuthenticated],
        serializer_class=MyRosterEntrySerializer,
    )
    def mine(self, request):
        """Return roster entries for characters owned by the current account."""

        entries = RosterEntry.objects.filter(character__in=request.user.characters)
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        serializer_class=RosterApplicationSerializer,
    )
    def apply(self, request, pk=None):
        """Accept a play application for a roster entry's character."""

        self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
