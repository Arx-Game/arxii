"""Custom django-allauth social account adapters for Arx II."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from evennia_extensions.models import PlayerData


class ArxSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter that creates PlayerData on social signup."""

    def save_user(self, request, sociallogin, form=None):
        """Save user from social login and create associated PlayerData."""
        user = super().save_user(request, sociallogin, form)

        # Create PlayerData for the new user (same as ArxAccountAdapter)
        PlayerData.objects.get_or_create(account=user)

        return user
