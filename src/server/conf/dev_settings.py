"""
Development settings for local testing.

This file imports all settings from settings.py and overrides specific values
for local development, particularly email handling.

To use these settings, set in .env:
    DJANGO_SETTINGS_MODULE=server.conf.dev_settings
"""

from .settings import *  # noqa: F403

# Override email backend to use console for local development
# Emails will be printed to the Evennia server logs instead of being sent
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Can add other dev-specific overrides here as needed
