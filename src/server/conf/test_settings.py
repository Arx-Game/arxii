"""
Test-specific settings for Arx II.

This file contains optimizations specifically for test runs to improve performance
while maintaining test accuracy. These settings should not be used in production.
"""

# Import all base settings
from server.conf.settings import *  # noqa: F403,F401

# Test-specific database optimizations
# Use in-memory SQLite for faster test database creation
DATABASES["default"] = {  # noqa: F405
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
    "OPTIONS": {
        "timeout": 20,
    },
}

# Disable migrations for faster test runs
# This recreates tables from models instead of running migrations
MIGRATION_MODULES = {
    app: None for app in INSTALLED_APPS if not app.startswith("django.")  # noqa: F405
}

# Use fast password hashing for tests (tests don't need secure passwords)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Reduce logging verbosity during tests
LOGGING["loggers"]["django.db.backends"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["evennia"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["django.request"]["level"] = "ERROR"  # noqa: F405
LOGGING["root"]["level"] = "ERROR"  # noqa: F405

# Disable debug mode for tests to avoid debug toolbar overhead
DEBUG = False

# Disable email sending during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable external services during tests
SENDGRID_API_KEY = ""
CLOUDINARY_CLOUD_NAME = ""
CLOUDINARY_API_KEY = ""
CLOUDINARY_API_SECRET = ""
