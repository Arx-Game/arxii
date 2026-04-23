from typing import Any, cast

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db.models import Model
from evennia.objects.models import ObjectDB
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.gm.models import GMTable
from world.stories.constants import AssistantClaimStatus, StoryScope
from world.stories.models import AssistantGMClaim, Story
from world.stories.types import AnyStoryProgress, StoryPrivacy


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
        user = cast(AbstractBaseUser, request.user)
        if not obj.can_player_apply(user):
            return False

        # TODO: Implement trust level checking once PlayerTrust is fully integrated
        # For now, allow participation if basic checks pass
        return True


class IsBeatStoryOwnerOrStaff(permissions.BasePermission):
    """Permission class for Beat model.

    Delegates to story ownership through episode -> chapter -> story.
    Mirrors IsEpisodeStoryOwnerOrStaff but walks the Beat -> Episode path.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check basic permission"""
        return request.user.is_authenticated

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user has permission to access specific beat"""
        if not request.user.is_authenticated:
            return False

        # Staff can do anything
        if request.user.is_staff:
            return True

        # Delegate to story permissions via beat -> episode -> chapter -> story
        story_permission = IsStoryOwnerOrStaff()
        return story_permission.has_object_permission(
            request,
            view,
            obj.episode.chapter.story,
        )


class IsGroupProgressMemberOrStaff(permissions.BasePermission):
    """Members of the GMTable with active membership can read; Lead GM of
    the table (GMTable.gm) and staff can write.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Authenticated check at view level; object-level enforces full scope.

        For non-safe (write) methods at the list level (e.g. create), require
        that the user is at least a Lead GM of some GMTable — object-level
        checks then confirm the specific table ownership.
        """
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        # Writes (create/update/delete): must be a Lead GM of at least one table.
        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        if gm_profile is None:
            return False
        return cast(Any, GMTable).objects.filter(gm=gm_profile).exists()

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check read (table member) or write (Lead GM) permissions."""
        if not request.user.is_authenticated:
            return False

        if request.user.is_staff:
            return True

        gm_table = obj.gm_table

        if request.method in permissions.SAFE_METHODS:
            # Any active member of this table (left_at is null = active membership).
            # Persona -> character_sheet -> character (ObjectDB) -> db_account.
            return gm_table.memberships.filter(
                persona__character_sheet__character__db_account=request.user,
                left_at__isnull=True,
            ).exists()

        # Write: Lead GM only (GMTable.gm is the Lead GM's GMProfile)
        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        return gm_profile is not None and gm_table.gm_id == gm_profile.pk


class IsGlobalProgressReadableOrStaff(permissions.BasePermission):
    """GLOBAL progress is readable by any authenticated user; writable only by staff."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Read for any authenticated user; write for staff only."""
        if not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Delegate to view-level permission (same rules apply to objects)."""
        return self.has_permission(request, view)


class IsContributorOrLeadGMOrStaff(permissions.BasePermission):
    """Read access for the contributing character's account, the Lead GM
    of the beat's episode story, and staff. No write access (contributions
    are created via service functions, not direct API writes).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Read only for authenticated users; no write via API."""
        if not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user is the contributor's account, story Lead GM, or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        if request.method not in permissions.SAFE_METHODS:
            return False
        # Character's account owns the contribution
        if obj.character_sheet.character.db_account == request.user:
            return True
        # Lead GM of any story whose episodes contain this beat
        beat = obj.beat
        story = beat.episode.chapter.story
        return story.owners.filter(id=request.user.id).exists()


class IsClaimantOrLeadGMOrStaff(permissions.BasePermission):
    """Read access for the claiming AGM (assistant_gm.account), the Lead GM
    of the story, and staff. No write access — state transitions go through
    action endpoints (Wave 11).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Read only for authenticated users; no write via API."""
        if not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user is the claimant, story owner, or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        if request.method not in permissions.SAFE_METHODS:
            return False
        # The AGM who made the claim
        if obj.assistant_gm.account == request.user:
            return True
        # Lead GM of the story (story owner)
        story = obj.beat.episode.chapter.story
        return story.owners.filter(id=request.user.id).exists()


class IsSessionRequestParticipantOrStaff(permissions.BasePermission):
    """Read access for:
    - Players with StoryParticipation on the episode's story
    - The assigned GM (assigned_gm.account)
    - Story owners (Lead GMs)
    - Staff
    No write access — Wave 11 adds action endpoints for state transitions.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Read only for authenticated users; no write via API."""
        if not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check if user is a participant, assigned GM, story owner, or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        if request.method not in permissions.SAFE_METHODS:
            return False
        story = obj.story
        # Story owners (Lead GMs)
        if story.owners.filter(id=request.user.id).exists():
            return True
        # Assigned GM
        assigned_gm = obj.assigned_gm
        if assigned_gm is not None and assigned_gm.account == request.user:
            return True
        # Players with story participation
        return story.participants.filter(
            character__db_account=request.user,
            is_active=True,
        ).exists()


# ---------------------------------------------------------------------------
# Wave 11: Action endpoint permission classes
# ---------------------------------------------------------------------------


class IsLeadGMOnStoryOrStaff(permissions.BasePermission):
    """Lead GM (primary_table.gm) or staff can perform story-level GM operations.

    Works for Episode objects: walks episode -> chapter -> story to find the story.
    Also works directly for Story objects.
    """

    message = "Only the Lead GM of this story or staff may perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Basic authentication check."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check Lead GM or staff access, routing by object type."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True

        # Find the story from whatever object was passed.
        if isinstance(obj, Story):
            story = obj
        else:
            # Walk episode -> chapter -> story.
            episode = getattr(obj, "chapter", None)  # noqa: GETATTR_LITERAL
            if episode is None:
                # obj is an Episode; it has a chapter attribute.
                episode_obj = obj
                story = episode_obj.chapter.story
            else:
                story = episode.story

        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        if gm_profile is None or not story.primary_table_id:
            return False
        return story.primary_table.gm_id == gm_profile.pk


class CanMarkBeat(permissions.BasePermission):
    """Who can POST /api/beats/{id}/mark/:
    - Lead GM (story's primary_table.gm) — always
    - Staff — always
    - AGM with an APPROVED AssistantGMClaim on *this specific beat*

    Object-level only: the beat PK is in the URL.
    """

    message = "Only the Lead GM, staff, or an AGM with an approved claim may mark this beat."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Basic authentication check."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check Lead GM, staff, or AGM with approved claim."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True

        # Walk beat -> episode -> chapter -> story to find Lead GM.
        story = obj.episode.chapter.story
        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL

        if gm_profile is not None and story.primary_table_id:
            if story.primary_table.gm_id == gm_profile.pk:
                return True

        # AGM with an APPROVED claim on this beat.
        if gm_profile is not None:
            return (
                cast(Any, AssistantGMClaim)
                .objects.filter(
                    beat=obj,
                    assistant_gm=gm_profile,
                    status=AssistantClaimStatus.APPROVED,
                )
                .exists()
            )

        return False


class IsClaimOwnerOrStaff(permissions.BasePermission):
    """The AGM who made the claim (for cancel) or staff."""

    message = "Only the AGM who made this claim or staff may perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Basic authentication check."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check the AGM owner or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        if gm_profile is None:
            return False
        return obj.assistant_gm_id == gm_profile.pk


class IsLeadGMOnClaimStoryOrStaff(permissions.BasePermission):
    """Lead GM of the claim's beat's story — for approve / reject / complete."""

    message = "Only the Lead GM of the story or staff may approve, reject, or complete claims."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Basic authentication check."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check Lead GM or staff via claim -> beat -> episode -> chapter -> story."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        gm_profile = getattr(request.user, "gm_profile", None)  # noqa: GETATTR_LITERAL
        if gm_profile is None:
            return False
        story = obj.beat.episode.chapter.story
        if not story.primary_table_id:
            return False
        return story.primary_table.gm_id == gm_profile.pk


class IsSessionRequestGMOrStaff(permissions.BasePermission):
    """For create-event / cancel / resolve on SessionRequest:
    Lead GM (story owner), or staff.
    """

    message = "Only the Lead GM or staff may manage this session request."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Basic authentication check."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        """Check Lead GM (story owner) or staff."""
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        story = obj.episode.chapter.story
        return story.owners.filter(id=request.user.id).exists()


# ---------------------------------------------------------------------------
# Story log viewer role classifier
# ---------------------------------------------------------------------------

# Viewer role constants for story log visibility filtering.
VIEWER_ROLE_STAFF = "staff"
VIEWER_ROLE_LEAD_GM = "lead_gm"
VIEWER_ROLE_PLAYER = "player"
VIEWER_ROLE_NO_ACCESS = "no_access"


def classify_story_log_viewer_role(
    user: AbstractBaseUser | AnonymousUser,
    story: Story,
    progress: "AnyStoryProgress | None" = None,
) -> str:
    """Return the viewer's role for story log visibility filtering.

    Returns one of: 'staff' | 'lead_gm' | 'player' | 'no_access'.

    Priority order:
    - staff: user.is_staff
    - lead_gm: user has a GMProfile and is the Lead GM of story.primary_table
    - player: user has access to the story (participant, owner, or appropriate scope)
    - no_access: none of the above
    """
    if not getattr(user, "is_authenticated", False):  # noqa: GETATTR_LITERAL
        return VIEWER_ROLE_NO_ACCESS

    if getattr(user, "is_staff", False):  # noqa: GETATTR_LITERAL
        return VIEWER_ROLE_STAFF

    gm_profile = getattr(user, "gm_profile", None)  # noqa: GETATTR_LITERAL
    if (
        gm_profile is not None
        and story.primary_table_id is not None
        and story.primary_table.gm_id == gm_profile.pk
    ):
        return VIEWER_ROLE_LEAD_GM

    if _story_log_user_has_access(user, story, progress):
        return VIEWER_ROLE_PLAYER

    return VIEWER_ROLE_NO_ACCESS


def _story_log_user_has_access(
    user: AbstractBaseUser | AnonymousUser,
    story: Story,
    progress: "AnyStoryProgress | None",
) -> bool:
    """Return True if ``user`` is a player-tier viewer of this story."""
    # CHARACTER scope: the character's ObjectDB account is this user.
    if story.scope == StoryScope.CHARACTER and story.character_sheet_id is not None:
        if story.character_sheet.character.db_account == user:
            return True

    # GROUP scope: user is an active member of the GMTable with progress.
    if story.scope == StoryScope.GROUP and progress is not None:
        gm_table = getattr(progress, "gm_table", None)  # noqa: GETATTR_LITERAL
        if gm_table is not None:
            return (
                cast(Any, gm_table)
                .memberships.filter(
                    persona__character_sheet__character__db_account=user,
                    left_at__isnull=True,
                )
                .exists()
            )

    # GLOBAL scope: any authenticated user has player-tier access.
    if story.scope == StoryScope.GLOBAL:
        return True

    # Fallback: explicit StoryParticipation covers non-owner participants
    # on CHARACTER stories that belong to a different character, and
    # any edge cases not covered by scope rules above.
    return (
        cast(Any, story)
        .participants.filter(
            character__db_account=user,
            is_active=True,
        )
        .exists()
    )
