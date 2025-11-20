from django.db import models
from rest_framework import permissions

from world.scenes.models import SceneParticipation


class IsSceneOwnerOrStaff(permissions.BasePermission):
    """
    Permission to check if user is scene owner (via participation) or staff.
    Used for modifying scenes (edit, delete, finish).
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always modify scenes
        if request.user.is_staff:
            return True

        # Check if user is a scene owner
        return SceneParticipation.objects.filter(
            scene=obj,
            account=request.user,
            is_owner=True,
        ).exists()


class IsSceneGMOrOwnerOrStaff(permissions.BasePermission):
    """
    Permission to check if user is scene GM, owner, or staff.
    Used for scene management actions that GMs should also be able to do.
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always do anything
        if request.user.is_staff:
            return True

        # Check if user is a scene GM or owner
        return (
            SceneParticipation.objects.filter(scene=obj, account=request.user)
            .filter(models.Q(is_gm=True) | models.Q(is_owner=True))
            .exists()
        )


class IsSceneParticipantOrStaff(permissions.BasePermission):
    """
    Permission to check if user is a scene participant or staff.
    Used for adding messages to scenes.
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always add messages
        if request.user.is_staff:
            return True

        # For SceneMessage objects, get the scene through the message
        scene = obj if hasattr(obj, "participants") else obj.scene

        # Check if user is a participant
        return SceneParticipation.objects.filter(
            scene=scene,
            account=request.user,
        ).exists()


class IsMessageSenderOrStaff(permissions.BasePermission):
    """
    Permission to check if user is the message sender or staff.
    Used for modifying/deleting messages.
    """

    def has_object_permission(self, request, view, obj):
        # Staff can always modify messages
        if request.user.is_staff:
            return True

        # Check if user sent this message and scene is active
        return obj.persona.participation.account == request.user and obj.scene.is_active


class CanCreatePersonaInScene(permissions.BasePermission):
    """
    Permission to check if user can create personas in a scene.
    Users can create personas if they're scene participants or staff.
    """

    def has_permission(self, request, view):
        # Staff can always create personas
        if request.user.is_staff:
            return True

        # For create operations, check participation in request data
        if request.method == "POST":
            participation_id = request.data.get("participation")
            if participation_id:
                return SceneParticipation.objects.filter(
                    id=participation_id,
                    account=request.user,
                ).exists()

        return True  # For list/other operations

    def has_object_permission(self, request, view, obj):
        # Staff can always modify personas
        if request.user.is_staff:
            return True

        # Check if user is a participant in the persona's scene
        return SceneParticipation.objects.filter(
            scene=obj.participation.scene,
            account=request.user,
        ).exists()


class CanCreateMessageInScene(permissions.BasePermission):
    """
    Permission to check if user can create messages in a scene.
    Users can create messages if they're scene participants or staff.
    """

    def has_permission(self, request, view):
        # Staff can always create messages
        if request.user.is_staff:
            return True

        # For create operations, check persona and verify scene participation
        if request.method == "POST":
            persona_id = request.data.get("persona_id") or request.data.get("persona")
            if persona_id:
                from world.scenes.models import Persona

                try:
                    persona = Persona.objects.select_related(
                        "participation__scene",
                    ).get(id=persona_id)
                    # User can create message if they own the persona and are scene participant
                    return (
                        persona.participation.account == request.user
                        and SceneParticipation.objects.filter(
                            scene=persona.participation.scene,
                            account=request.user,
                        ).exists()
                    )
                except Persona.DoesNotExist:
                    return False

        return True  # For list/other operations


class ReadOnlyOrSceneParticipant(permissions.BasePermission):
    """
    Permission for read-only access to everyone, but write access only to scene participants.
    Used for scene viewing - anyone can view public scenes, but only participants can modify.
    """

    def has_permission(self, request, view):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require authentication
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Read permissions for safe methods
        if request.method in permissions.SAFE_METHODS:
            # For public scenes, anyone can read
            if hasattr(obj, "is_public") and obj.is_public:
                return True
            # For private scenes, only participants and staff can read
            if request.user.is_staff:
                return True
            return SceneParticipation.objects.filter(
                scene=obj,
                account=request.user,
            ).exists()

        # Write permissions require scene participation or staff
        return (
            request.user.is_staff
            or SceneParticipation.objects.filter(
                scene=obj,
                account=request.user,
            ).exists()
        )
