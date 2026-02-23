from typing import Any, cast

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db.models import Model
from evennia.objects.models import ObjectDB
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.stories.models import Story
from world.stories.types import StoryPrivacy


class IsStoryOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for Story model.
    - Read: Public stories visible to authenticated users, private stories to
      owners/staff only
    - Write: Only owners or staff can modify stories
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if user has permission to access the view"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Authenticated users can read
        if request.method in permissions.SAFE_METHODS:
            return True

        # Only staff or owners can create/modify stories
        return request.user.is_staff

    def has_object_permission(self, request: Request, view: APIView, obj: Story) -> bool:
        """Check if user has permission to access specific story"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Check read permissions
        if request.method in permissions.SAFE_METHODS:
            return self._can_read_story(request.user, obj)

        # Check write permissions
        return self._can_write_story(request.user, obj)

    def _can_read_story(self, user: AbstractBaseUser | AnonymousUser, story: Story) -> bool:
        """Check if user can read this story"""
        # Public stories are readable by all authenticated users
        if story.privacy == StoryPrivacy.PUBLIC:
            return True

        # Private stories only visible to owners, participants, or staff
        if story.privacy == StoryPrivacy.PRIVATE:
            return (
                story.owners.filter(id=user.id).exists()
                or story.participants.filter(
                    character__db_account=user,
                    is_active=True,
                ).exists()
            )

        # Invite-only stories visible to owners, participants with permission
        if story.privacy == StoryPrivacy.INVITE_ONLY:
            return (
                story.owners.filter(id=user.id).exists()
                or story.participants.filter(
                    character__db_account=user,
                    is_active=True,
                    trusted_by_owner=True,
                ).exists()
            )

        return False

    def _can_write_story(self, user: AbstractBaseUser | AnonymousUser, story: Story) -> bool:
        """Check if user can modify this story"""
        return story.owners.filter(id=user.id).exists()


class IsChapterStoryOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for Chapter model.
    Delegates to story ownership permissions.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific chapter"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Delegate to story permissions
        story_permission = IsStoryOwnerOrStaff()
        return story_permission.has_object_permission(request, view, obj.story)


class IsEpisodeStoryOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for Episode model.
    Delegates to story ownership through chapter.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific episode"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Delegate to story permissions
        story_permission = IsStoryOwnerOrStaff()
        return story_permission.has_object_permission(request, view, obj.chapter.story)


class IsParticipationOwnerOrStoryOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for StoryParticipation model.
    - Participants can view their own participation
    - Story owners can manage all participations in their stories
    - Staff can do anything
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific participation"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Character owner can view their own participation
        if request.method in permissions.SAFE_METHODS:
            if obj.character.db_account == request.user:
                return True

        # Story owners can manage participations in their stories
        return obj.story.owners.filter(id=request.user.id).exists()


class IsPlayerTrustOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for PlayerTrust model.
    - Users can view their own trust profile
    - Staff can view and modify all trust profiles
    - Story owners can view trust profiles of their participants
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific trust profile"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Users can view their own trust profile
        if request.method in permissions.SAFE_METHODS and obj.account == request.user:
            return True

        # Story owners can view trust profiles of their participants
        if request.method in permissions.SAFE_METHODS:
            # Check if the requesting user owns any stories
            # where this account participates
            user_owned_stories = cast(Any, Story).objects.filter(owners=request.user)
            participant_stories = cast(Any, Story).objects.filter(
                participants__character__db_account=obj.account,
                participants__is_active=True,
            )
            if user_owned_stories.filter(id__in=participant_stories).exists():
                return True

        # Only staff can modify trust profiles
        return False


class IsReviewerOrStoryOwnerOrStaff(permissions.BasePermission):
    """
    Permission class for StoryFeedback model.
    - Reviewers can view/edit their own feedback
    - Reviewed players can view feedback about them
    - Story owners can view all feedback in their stories
    - Staff can do anything
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific feedback"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Reviewers can manage their own feedback
        if obj.reviewer == request.user:
            return True

        # Read-only permissions
        if request.method in permissions.SAFE_METHODS:
            # Reviewed players can view feedback about them
            if obj.reviewed_player == request.user:
                return True

            # Story owners can view feedback in their stories
            if obj.story.owners.filter(id=request.user.id).exists():
                return True

        return False


class IsGMOrStaff(permissions.BasePermission):
    """
    Permission class for GM-only operations.
    Checks if user has an active GM character.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if user has GM permissions"""
        if not request.user.is_authenticated:
            return False

        # Staff always have GM permissions
        if request.user.is_staff:
            return True

        # Check if user has an active GM character
        return ObjectDB.objects.filter(
            db_account=request.user,
            db_typeclass_path__contains="GMCharacter",
        ).exists()


class CanParticipateInStory(permissions.BasePermission):
    """
    Permission class for checking if a user can participate in a story.
    Checks trust levels and story requirements.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Story) -> bool:
        """Check if user can participate in this story"""
        if not request.user.is_authenticated:
            return False

        # Staff can participate in any story
        if request.user.is_staff:
            return True

        # Check if story allows participation
        if not obj.can_player_apply(request.user):
            return False

        # TODO: Implement trust level checking once PlayerTrust is fully integrated
        # For now, allow participation if basic checks pass
        return True
