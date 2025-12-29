"""General API views for the web interface."""

from allauth.account.models import EmailAddress, EmailConfirmation
from django.conf import settings
from django.contrib.auth import logout
from django.utils.decorators import method_decorator
from django.utils.timesince import timesince
from django.views.decorators.csrf import ensure_csrf_cookie
from evennia import SESSION_HANDLER
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils import class_from_module
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.api.serializers import AccountPlayerSerializer
from world.roster.models import RosterEntry


class HomePageAPIView(APIView):
    """Return context for the Evennia home page."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return basic game statistics."""
        recent_accounts = list(AccountDB.objects.get_recently_connected_accounts())
        account_limit = 4
        accounts_data = []
        for account in recent_accounts[:account_limit]:
            last_login = ""
            if account.last_login:
                last_login = timesince(account.last_login)
            accounts_data.append(
                {"username": account.username, "last_login": last_login},
            )

        character_cls = class_from_module(
            settings.BASE_CHARACTER_TYPECLASS,
            fallback=settings.FALLBACK_CHARACTER_TYPECLASS,
        )
        room_cls = class_from_module(
            settings.BASE_ROOM_TYPECLASS,
            fallback=settings.FALLBACK_ROOM_TYPECLASS,
        )
        exit_cls = class_from_module(
            settings.BASE_EXIT_TYPECLASS,
            fallback=settings.FALLBACK_EXIT_TYPECLASS,
        )

        num_characters = character_cls.objects.all_family().count()
        num_rooms = room_cls.objects.all_family().count()
        num_exits = exit_cls.objects.all_family().count()
        num_objects = ObjectDB.objects.count()

        context = {
            "num_accounts_connected": SESSION_HANDLER.account_count(),
            "num_accounts_registered": AccountDB.objects.count(),
            "num_accounts_registered_recent": (
                AccountDB.objects.get_recently_created_accounts().count()
            ),
            "num_accounts_connected_recent": len(recent_accounts),
            "num_characters": num_characters,
            "num_rooms": num_rooms,
            "num_exits": num_exits,
            "num_others": num_objects - num_characters - num_rooms - num_exits,
            "page_title": "Arx II",
            "accounts_connected_recent": accounts_data,
        }
        return Response(context)


class ServerStatusAPIView(APIView):
    """Return overall game status."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return game statistics and recent activity."""
        character_cls = class_from_module(
            settings.BASE_CHARACTER_TYPECLASS,
            fallback=settings.FALLBACK_CHARACTER_TYPECLASS,
        )
        room_cls = class_from_module(
            settings.BASE_ROOM_TYPECLASS,
            fallback=settings.FALLBACK_ROOM_TYPECLASS,
        )

        recent_entries = (
            RosterEntry.objects.filter(
                roster__is_active=True,
                last_puppeted__isnull=False,
            )
            .select_related("character")
            .order_by("-last_puppeted")[:4]
        )
        recent_players = [
            {"id": entry.id, "name": entry.character.key} for entry in recent_entries
        ]

        data = {
            "online": SESSION_HANDLER.account_count(),
            "accounts": AccountDB.objects.count(),
            "characters": character_cls.objects.all_family().count(),
            "rooms": room_cls.objects.all_family().count(),
            "recentPlayers": recent_players,
            "news": [],
        }
        return Response(data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CurrentUserAPIView(APIView):
    """Return the current authenticated user's data."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return the current account."""
        data = None
        if request.user.is_authenticated:
            data = AccountPlayerSerializer(request.user).data
        return Response(data)


class RegisterAvailabilityAPIView(APIView):
    """Check if a username or email is available for registration."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return availability of requested credentials."""
        username = request.query_params.get("username")
        email = request.query_params.get("email")
        if username is None and email is None:
            return Response(
                {"detail": "username or email parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = {}
        if username is not None:
            data["username"] = not AccountDB.objects.filter(
                username__iexact=username,
            ).exists()
        if email is not None:
            data["email"] = not AccountDB.objects.filter(email__iexact=email).exists()
        return Response(data)


class LogoutAPIView(APIView):
    """Simple logout endpoint since allauth headless doesn't provide one."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        """Log out the current user."""
        logout(request)
        return Response({"status": "success"})


class EmailVerificationAPIView(APIView):
    """Custom email verification endpoint to replace broken allauth headless API."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        """Verify email using confirmation key."""
        key = request.data.get("key")
        if not key:
            return Response(
                {"detail": "Email confirmation key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Find the confirmation record
            confirmation = EmailConfirmation.objects.get(key=key.lower())
            email_address = confirmation.email_address

            # Check if already verified
            if email_address.verified:
                return Response(
                    {"detail": "Email address is already verified"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if expired (handle None sent field)
            try:
                if confirmation.key_expired():
                    return Response(
                        {"detail": "Email confirmation key has expired"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except TypeError:
                # Handle case where sent field is None by using created timestamp
                import datetime

                from allauth.account import app_settings
                from django.utils import timezone

                if confirmation.sent is None and confirmation.created:
                    # Use created timestamp if sent is None
                    expiration_date = confirmation.created + datetime.timedelta(
                        days=app_settings.EMAIL_CONFIRMATION_EXPIRE_DAYS
                    )
                    if timezone.now() > expiration_date:
                        return Response(
                            {"detail": "Email confirmation key has expired"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            # Mark email as verified
            email_address.verified = True
            email_address.save()

            # Clean up - remove the confirmation record
            confirmation.delete()

            return Response({"detail": "Email successfully verified"})

        except EmailConfirmation.DoesNotExist:
            return Response(
                {"detail": "Invalid email confirmation key"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendEmailVerificationAPIView(APIView):
    """Resend email verification for logged-in users."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Resend verification email to current user."""
        from allauth.account.utils import send_email_confirmation

        # Check if already verified
        try:
            email_address = EmailAddress.objects.get(user=request.user, primary=True)
            if email_address.verified:
                return Response(
                    {"detail": "Email already verified"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except EmailAddress.DoesNotExist:
            return Response(
                {"detail": "No email address found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_email_confirmation(request, request.user)
        return Response({"detail": "Verification email sent"})
