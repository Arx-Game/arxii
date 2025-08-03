from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from web.api.serializers import AccountPlayerSerializer


class HomePageAPIView(APIView):
    """Return context for the Evennia home page."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Handle GET requests."""
        # Match the data structure expected by the React frontend
        context = {
            "num_accounts_connected": 0,
            "num_accounts_registered": 0,
            "num_accounts_registered_recent": 0,
            "num_accounts_connected_recent": 0,
            "num_characters": 0,
            "num_rooms": 0,
            "num_exits": 0,
            "num_others": 0,
            "page_title": "Arx II",
            "accounts_connected_recent": [],  # Empty array to prevent .map() error
        }
        return Response(context)


class LoginAPIView(APIView):
    """Return account data for the current session and handle authentication."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return the current account.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: Serialized account or ``None``.
        """
        data = None
        if request.user.is_authenticated:
            data = AccountPlayerSerializer(request.user).data
        return Response(data)

    def post(self, request, *args, **kwargs):
        """Authenticate the user and return the account.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: Serialized account on success or form errors.
        """
        form = AuthenticationForm(request=request, data=request.data)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        auth_login(request, form.get_user())
        data = AccountPlayerSerializer(form.get_user()).data
        return Response(data)
