from django.db import models
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.scenes.models import Persona, Scene, SceneMessage, SceneParticipation


class IsSceneOwnerOrStaff(permissions.BasePermission):
    """
    Permission to check if user is scene owner (via participation) or staff.
    Used for modifying scenes (edit, delete, finish).
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Scene) -> bool:
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

    def has_object_permission(self, request: Request, view: APIView, obj: Scene) -> bool:
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

    def has_object_permission(
        self, request: Request, view: APIView, obj: Scene | SceneMessage
    ) -> bool:
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

    def has_object_permission(self, request: Request, view: APIView, obj: SceneMessage) -> bool:
        # Staff can always modify messages
        if request.user.is_staff:
            return True

        # Check if user owns the persona's character and scene is active
        if not obj.scene.is_active:
            return False
        try:
            roster_entry = obj.persona.character.roster_entry
        except AttributeError:
            roster_entry = None
        if roster_entry is None:
            return False
        from world.roster.models import RosterTenure  # noqa: PLC0415

        return RosterTenure.objects.filter(
            roster_entry=roster_entry,
            player_data__account=request.user,
            end_date__isnull=True,
        ).exists()


class CanCreatePersonaInScene(permissions.BasePermission):
    """
    Permission to check if user can create personas in a scene.
    Users can create personas if they're scene participants or staff.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        # Staff can always create personas
        if request.user.is_staff:
            return True

        # For create operations, check the user owns the character
        if request.method == "POST":
            character_id = request.data.get("character")
            if character_id:
                from world.roster.models import RosterTenure  # noqa: PLC0415

                return RosterTenure.objects.filter(
                    roster_entry__character_id=character_id,
                    player_data__account=request.user,
                    end_date__isnull=True,
                ).exists()

        return True  # For list/other operations

    def has_object_permission(self, request: Request, view: APIView, obj: Persona) -> bool:
        # Staff can always modify personas
        if request.user.is_staff:
            return True

        # Check if user owns the character behind this persona
        from world.roster.models import RosterTenure  # noqa: PLC0415

        return RosterTenure.objects.filter(
            roster_entry__character=obj.character,
            player_data__account=request.user,
            end_date__isnull=True,
        ).exists()


class CanCreateMessageInScene(permissions.BasePermission):
    """
    Permission to check if user can create messages in a scene.
    Users can create messages if they're scene participants or staff.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        # Staff can always create messages
        if request.user.is_staff:
            return True

        # For create operations, check the user owns the persona's character
        if request.method == "POST":
            persona_id = request.data.get("persona_id") or request.data.get("persona")
            if persona_id:
                try:
                    persona = Persona.objects.select_related("character").get(id=persona_id)
                except Persona.DoesNotExist:
                    return False
                from world.roster.models import RosterTenure  # noqa: PLC0415

                return RosterTenure.objects.filter(
                    roster_entry__character=persona.character,
                    player_data__account=request.user,
                    end_date__isnull=True,
                ).exists()

        return True  # For list/other operations


class ReadOnlyOrSceneParticipant(permissions.BasePermission):
    """
    Read-only access for everyone; write access only to scene participants.

    Used for scene viewing: anyone can view public scenes, but only participants
    can modify.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions require authentication
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Scene) -> bool:
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
